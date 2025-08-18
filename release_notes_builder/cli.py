from __future__ import annotations
import argparse
from typing import List, Dict, Optional, Set
import sys
import logging
from collections import Counter

from .config import load_config, Config, RepoSpec
from .github_fetcher import GitHubFetcher
from .preclass import classify, summarize_for_llm
from .llm_consolidator import consolidate_openai
from .renderer import render_md


log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("rlsnotes", description="Release Notes Builder")
    p.add_argument("--config", help="Path to YAML config", default=None)
    p.add_argument("--repo", action="append", help="owner/repo (repeatable)")
    p.add_argument("--since-ref", help="since ref (tag or sha) — applied to repos without since_ref")
    p.add_argument("--until-ref", help="until ref (tag or sha) — applied to repos without until_ref")
    p.add_argument("--since-date", help="since date (YYYY-MM-DD) — applied to repos without since_date")
    p.add_argument("--outfile", help="Output markdown file")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    return p.parse_args()


def _apply_overrides_to_repo(r: RepoSpec, since_ref: Optional[str], until_ref: Optional[str], since_date: Optional[str]) -> RepoSpec:
    if since_ref and not r.since_ref:
        r.since_ref = since_ref
    if until_ref and not r.until_ref:
        r.until_ref = until_ref
    if since_date and not r.since_date:
        r.since_date = since_date
    return r


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(name)s: %(message)s")
    log.info("Starting Release Notes Builder")
    cfg = load_config(args.config)
    log.debug("Loaded config from %s", args.config or "(defaults)")

    # Override output path
    if args.outfile:
        cfg.render.outfile = args.outfile

    # Build repo list (prefer config; allow CLI to specify repos)
    repos: List[RepoSpec] = []
    if args.repo:
        for rr in args.repo:
            owner, name = rr.split("/", 1)
            repos.append(RepoSpec(owner=owner, name=name))
    else:
        repos.extend(cfg.repos)

    if not repos:
        log.error("No repositories provided. Use --repo owner/repo or config.yaml")
        print("No repositories provided. Use --repo owner/repo or config.yaml", file=sys.stderr)
        return 2

    # Apply CLI overrides per repo (since_ref/until_ref/since_date)
    repos = [
        _apply_overrides_to_repo(r, args.since_ref, args.until_ref, args.since_date)
        for r in repos
    ]

    # Validate presence of at least one boundary across repos/globals
    missing_any = True
    for r in repos:
        if r.until_ref or r.since_date:
            missing_any = False
            break
    if missing_any and not args.until_ref and not args.since_date:
        log.error("Provide at least one of: per-repo until_ref, global --until-ref, per-repo since_date, or global --since-date")
        print(
            "Provide at least one of: per-repo until_ref, global --until-ref, per-repo since_date, or global --since-date",
            file=sys.stderr,
        )
        return 2

    gh = GitHubFetcher(cfg.github.get_token())

    snapshots: List[Dict] = []
    all_contributors: List[str] = []

    for r in repos:
        log.info("Fetching PRs for %s (since_ref=%s, until_ref=%s, since_date=%s)", r.full_name, r.since_ref, r.until_ref or args.until_ref, r.since_date or args.since_date)
        prs = gh.fetch_prs(
            r.owner,
            r.name,
            r.since_ref,
            r.until_ref or args.until_ref or "HEAD",
            r.since_date or args.since_date,
        )
        log.info("Fetched %d merged PRs for %s", len(prs), r.full_name)
        classified = [classify(p) for p in prs]
        # quick category counts
        counts = Counter([c.category for c in classified])
        log.debug("Category counts for %s: %s", r.full_name, dict(counts))
        snap = {"repo": r.full_name, "prs": summarize_for_llm(classified)}
        snapshots.append(snap)
        all_contributors.extend([f"@{p.author}" for p in prs if p.author])

    # Determine display range for the consolidator header
    def collect_field(field: str) -> Set[str]:
        vals: Set[str] = set()
        for r in repos:
            v = getattr(r, field)
            if v:
                vals.add(v)
        return vals

    since_vals = collect_field("since_ref")
    until_vals = collect_field("until_ref")

    since_display = next(iter(since_vals)) if len(since_vals) == 1 else ("per-repo" if since_vals else "auto")
    until_display = next(iter(until_vals)) if len(until_vals) == 1 else ("per-repo" if until_vals else (args.until_ref or "HEAD"))

    log.info("Consolidating with model=%s; window: %s -> %s", cfg.llm.model, since_display, until_display)
    llm_out = consolidate_openai(snapshots, since_display, until_display, cfg.llm.model)

    # enrich with title
    llm_out_with_title = {**llm_out, "title": cfg.release.title}

    md = render_md(llm_out_with_title)

    outfile = cfg.render.outfile
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(md)

    log.info("Wrote release notes to %s", outfile)
    print(f"Wrote release notes to {outfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
