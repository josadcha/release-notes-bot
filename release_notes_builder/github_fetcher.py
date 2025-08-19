from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
import re
import requests
import logging

from .utils import make_gh_session


log = logging.getLogger(__name__)


@dataclass
class PR:
    number: int
    title: str
    body_excerpt: str
    labels: List[str]
    author: str
    url: str
    merge_sha: Optional[str]
    merged_at: Optional[str]
    changed_files: Optional[int] = None
    # Optional Shortcut enrichment
    shortcut_id: Optional[int] = None
    shortcut_name: Optional[str] = None
    shortcut_url: Optional[str] = None
    shortcut_description: Optional[str] = None


class GitHubFetcher:
    def __init__(self, token: str):
        self.s = make_gh_session(token)

    def _repo(self, owner: str, name: str) -> str:
        return f"/repos/{owner}/{name}"

    def get_default_branch(self, owner: str, name: str) -> str:
        log.debug("Fetching default branch for %s/%s", owner, name)
        r = self.s.get(f"https://api.github.com{self._repo(owner, name)}")
        try:
            r.raise_for_status()
        except requests.HTTPError:
            log.error("Failed to get repo metadata: %s", r.text)
            raise
        return r.json()["default_branch"]

    def list_tags(self, owner: str, name: str, per_page: int = 100) -> List[Dict]:
        log.debug("Listing tags for %s/%s", owner, name)
        r = self.s.get(
            f"https://api.github.com{self._repo(owner, name)}/tags",
            params={"per_page": per_page},
        )
        try:
            r.raise_for_status()
        except requests.HTTPError:
            log.error("Failed to list tags: %s", r.text)
            raise
        return r.json()

    def compare(self, owner: str, name: str, base: str, head: str) -> Dict:
        # base...head supports tags or shas
        url = f"https://api.github.com{self._repo(owner, name)}/compare/{base}...{head}"
        log.debug("Compare range %s..%s via %s", base, head, url)
        r = self.s.get(url)
        try:
            r.raise_for_status()
        except requests.HTTPError:
            log.error("Compare failed (%s..%s): %s", base, head, r.text)
            raise
        return r.json()

    def auto_prev_tag(self, owner: str, name: str, until_ref: str) -> Optional[str]:
        tags = self.list_tags(owner, name)
        tag_names = [t["name"] for t in tags]
        if until_ref in tag_names:
            idx = tag_names.index(until_ref)
            if idx + 1 < len(tag_names):
                prev = tag_names[idx + 1]
                log.info("Auto-detected previous tag for %s/%s: %s (until=%s)", owner, name, prev, until_ref)
                return prev
        if len(tag_names) > 1:
            log.info("Auto-detected previous tag (fallback) for %s/%s: %s", owner, name, tag_names[1])
            return tag_names[1]
        log.warning("No previous tag found for %s/%s", owner, name)
        return None

    def date_range_from_compare(self, cmp: Dict) -> Optional[str]:
        commits = cmp.get("commits") or []
        if not commits:
            return None
        dates = [datetime.fromisoformat(c["commit"]["author"]["date"].replace("Z", "+00:00")) for c in commits]
        since = min(dates).strftime("%Y-%m-%d")
        until = max(dates).strftime("%Y-%m-%d")
        dr = f"{since}..{until}"
        log.debug("Derived date range from compare: %s", dr)
        return dr

    def fetch_prs(self, owner: str, name: str, since_ref: Optional[str], until_ref: str, since_date: Optional[str]) -> List[PR]:
        log.debug("fetch_prs(owner=%s, repo=%s, since_ref=%s, until_ref=%s, since_date=%s)", owner, name, since_ref, until_ref, since_date)
        # If since_ref missing, try auto-detect previous tag on default branch
        if not since_ref:
            prev = self.auto_prev_tag(owner, name, until_ref)
            if prev:
                since_ref = prev
        # Build a date window using compare if refs available
        date_range = None
        if since_ref and until_ref:
            try:
                cmp = self.compare(owner, name, since_ref, until_ref)
                date_range = self.date_range_from_compare(cmp)
            except requests.HTTPError as e:
                log.warning("Compare failed for %s/%s (%s..%s); will try since_date if provided. %s", owner, name, since_ref, until_ref, e)
                date_range = None
        if not date_range and since_date:
            # Use provided since_date up to today
            date_range = f"{since_date}..{datetime.utcnow().strftime('%Y-%m-%d')}"
            log.debug("Using user-provided date range: %s", date_range)

        # Search merged PRs by date range
        prs: List[PR] = []
        page = 1
        while True:
            q = f"repo:{owner}/{name} is:pr is:merged"
            if date_range:
                q += f" merged:{date_range}"
            log.debug("Search issues page %d query: %s", page, q)
            r = self.s.get(
                "https://api.github.com/search/issues",
                params={"q": q, "per_page": 100, "page": page},
            )
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                log.error("Search API error for %s/%s page %d: %s | body=%s", owner, name, page, e, r.text)
                raise
            data = r.json()
            items = data.get("items", [])
            if not items:
                log.debug("No more items on page %d", page)
                break
            for it in items:
                number = it["number"]
                pr = self._hydrate_pr(owner, name, number)
                if pr:
                    prs.append(pr)
            log.debug("Accumulated %d PRs after page %d", len(prs), page)
            if len(items) < 100:
                break
            page += 1
        log.info("Total merged PRs fetched for %s/%s: %d", owner, name, len(prs))
        return prs

    def _hydrate_pr(self, owner: str, name: str, number: int) -> Optional[PR]:
        url = f"https://api.github.com{self._repo(owner, name)}/pulls/{number}"
        log.debug("Hydrating PR #%d via %s", number, url)
        r = self.s.get(url)
        if r.status_code == 404:
            log.warning("PR #%d not found in %s/%s", number, owner, name)
            return None
        try:
            r.raise_for_status()
        except requests.HTTPError:
            log.error("Failed to hydrate PR #%d: %s", number, r.text)
            raise
        p = r.json()
        labels = [l["name"].lower() for l in (p.get("labels") or [])]
        body = p.get("body") or ""
        body_excerpt = "\n".join((body or "").splitlines()[:10])
        author = (p.get("user") or {}).get("login") or ""
        merge_sha = p.get("merge_commit_sha")
        merged_at = p.get("merged_at")
        changed_files = p.get("changed_files")
        return PR(
            number=number,
            title=p.get("title") or "",
            body_excerpt=body_excerpt,
            labels=labels,
            author=author,
            url=p.get("html_url") or "",
            merge_sha=merge_sha,
            merged_at=merged_at,
            changed_files=changed_files,
        )
