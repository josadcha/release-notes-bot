from __future__ import annotations
from typing import Any, Dict, List, Tuple
import json
import os
import time
import logging
import re
from urllib.parse import urlparse
from openai import OpenAI

from .schema import is_valid_release, assert_valid_release

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a Release Notes Consolidator. Write concise, user-facing release notes. "
    "Prefer concrete impact and product language over internal implementation. "
    "Group by Features, Fixes, Chore. "
    "Merge duplicate PRs if they describe the same user-visible change. "
    "Flag risky or ambiguous items. Keep bullets short (\u2264 18 words). "
    "Use the provided labels and commit prefixes when helpful, but prioritize clarity for non-engineers. "
    "Respond with strict JSON only, no prose. "
    "Always include all repos present in the input and ensure each repo has sections with non-empty items if relevant PRs exist. "
    "First, produce tldr as 2–4 bullets summarizing the main focus areas of the week based on category frequencies and recurring area/* labels across repos."
)


def build_user_message(snapshots: List[Dict[str, Any]], since_ref: str, until_ref: str) -> str:
    # snapshots: list of { repo: "owner/repo", prs: [ ...compact json... ] }
    parts = [f"Release window: {since_ref} \u2192 {until_ref}"]
    for snap in snapshots:
        parts.append(f"Repo: {snap['repo']}")
        parts.append("PRs snapshot (JSON):")
        parts.append(json.dumps(snap["prs"], ensure_ascii=False))
        parts.append("")
    parts.append(
        "Output schema: { tldr: string[], repos: [{ name: string, sections: [{ title: string, items: [{ text: string, prs: number[] }] }]}], upgrade_notes: string[], contributors: string[] }"
    )
    return "\n".join(parts)


def _extract_owner_repo_and_number(url: str) -> Tuple[str, int]:
    # Expect ... github.com/owner/repo/pull/123
    try:
        path = urlparse(url).path.strip("/")
        parts = path.split("/")
        owner, repo, _, num = parts[0], parts[1], parts[2], parts[3]
        return f"{owner}/{repo}", int(num)
    except Exception:
        return "", -1


def _ensure_required_defaults(doc: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure required top-level keys exist for schema validation
    if not isinstance(doc, dict):
        return doc
    doc.setdefault("tldr", [])
    doc.setdefault("repos", [])
    doc.setdefault("upgrade_notes", [])
    doc.setdefault("contributors", [])
    return doc


def _has_minimal_content(doc: Dict[str, Any]) -> bool:
    try:
        for repo in doc.get("repos", []):
            for sec in repo.get("sections", []):
                if any((sec.get("items") or [])):
                    return True
        return False
    except Exception:
        return False


def _coerce_legacy(doc: Dict[str, Any]) -> Dict[str, Any]:
    # Legacy shape example: { "Features": [ {"title": ..., "url": ...}, ...], "Fixes": [...] }
    CATEGORY_TITLES = [
        "Breaking Changes",
        "Features",
        "Fixes",
        "Performance",
        "Docs",
        "Chore",
    ]
    keys = set(doc.keys()) if isinstance(doc, dict) else set()
    if not keys.intersection({"Features", "Fixes", "Chore"}):
        raise ValueError("not legacy format")

    repos: Dict[str, Dict[str, Any]] = {}

    def ensure_repo(name: str) -> Dict[str, Any]:
        if name not in repos:
            repos[name] = {"name": name, "sections": []}
        return repos[name]

    # Build per-repo sections by parsing URL
    for cat in CATEGORY_TITLES:
        items = (doc.get(cat) if isinstance(doc, dict) else None) or []
        # Group items by repo
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            url = it.get("url") or ""
            repo_name, pr_num = _extract_owner_repo_and_number(url)
            if not repo_name:
                repo_name = "unknown/unknown"
            grouped.setdefault(repo_name, []).append({
                "text": it.get("title") or it.get("description") or "",
                "prs": [pr_num] if pr_num > 0 else [],
            })
        # Append sections into repos
        for repo_name, gitems in grouped.items():
            repo = ensure_repo(repo_name)
            repo["sections"].append({
                "title": cat,
                "items": gitems,
            })

    coerced = {
        "tldr": [],
        "repos": list(repos.values()),
        "upgrade_notes": [],
        "contributors": [],
    }
    return coerced


def consolidate_openai(snapshots: List[Dict[str, Any]], since_ref: str, until_ref: str, model: str, temperature: float) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)

    user_msg = build_user_message(snapshots, since_ref, until_ref)
    log.debug("LLM request prepared: model=%s, user_msg_chars=%d", model, len(user_msg))
    log.debug("LLM System prompt:\n%s", SYSTEM_PROMPT)
    log.debug("LLM User message:\n%s", user_msg)

    for attempt in range(3):
        log.info("LLM consolidate attempt %d (model=%s)", attempt + 1, model)
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        content = resp.choices[0].message.content
        log.debug("LLM raw response chars=%d", len(content or ""))
        try:
            data = json.loads(content)
            data = _ensure_required_defaults(data)
            if is_valid_release(data) and _has_minimal_content(data):
                log.info("LLM output validated successfully on attempt %d", attempt + 1)
                return data
            # Try coercion from legacy/category map format
            try:
                coerced = _coerce_legacy(data)
                coerced = _ensure_required_defaults(coerced)
                if is_valid_release(coerced) and _has_minimal_content(coerced):
                    log.info("LLM output coerced to valid schema on attempt %d", attempt + 1)
                    return coerced
            except Exception:
                pass
            log.warning("LLM output invalid or empty on attempt %d", attempt + 1)
        except Exception as e:
            log.warning("Failed to parse LLM JSON on attempt %d: %s", attempt + 1, e)
        time.sleep(1.2 * (attempt + 1))

    # Final attempt: enforce validation error message and ask model to repair
    repair_prompt = (
        "Your previous JSON did not match the required schema or had no content. "
        "Return a corrected JSON that strictly matches the schema and includes non-empty sections with items for all repos that have PRs."
    )
    log.info("LLM repair attempt (strict JSON)")
    resp = client.chat.completions.create(
        model=model,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            {"role": "user", "content": repair_prompt},
        ],
    )
    content = resp.choices[0].message.content
    data = json.loads(content)
    data = _ensure_required_defaults(data)
    if is_valid_release(data) and _has_minimal_content(data):
        log.info("LLM repair output validated successfully")
        return data
    # Try coercion as last resort
    try:
        coerced = _coerce_legacy(data)
        coerced = _ensure_required_defaults(coerced)
        if is_valid_release(coerced) and _has_minimal_content(coerced):
            log.info("LLM repair output coerced to valid schema")
            return coerced
    except Exception:
        pass
    # If still invalid/empty, raise with validation error
    assert_valid_release(data)
    raise ValueError("LLM produced an empty release document (no items)")
