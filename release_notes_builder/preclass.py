from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
import re

from .github_fetcher import PR


CATEGORIES = [
    "Features",
    "Fixes",
    "Chore",
]


@dataclass
class ClassifiedPR:
    pr: PR
    category: str
    area: Optional[str]
    is_breaking: bool


def detect_conventional_prefix(title: str) -> Optional[str]:
    m = re.match(r"^(feat|fix|perf|docs|chore|refactor)(!:|:|\(.*\)(!:|:))", title.strip(), re.IGNORECASE)
    if m:
        kind = m.group(1).lower()
        return kind
    return None


def classify(pr: PR) -> ClassifiedPR:
    title = pr.title or ""
    labels = set([l.lower() for l in pr.labels or []])
    body = pr.body_excerpt or ""

    # breaking detector
    breaking = any([
        "breaking" in labels,
        "breaking change" in (body.lower()),
        "breaking-change" in labels,
        "!" in title.split(" ")[0] if title else False,
    ])

    conventional = detect_conventional_prefix(title) or ""

    # area label
    area = next((l for l in labels if l.startswith("area/")), None)

    # Default to Chore
    cat = "Chore"

    # Primary label-based mapping (restricted to 3 classes)
    if breaking:
        cat = "Features"  # treat breaking as feature-level change
    elif any(l in labels for l in ["feature", "enhancement", "type:feat", "feat"]):
        cat = "Features"
    elif any(l in labels for l in ["bug", "fix", "type:bug"]):
        cat = "Fixes"
    elif any(l in labels for l in ["perf", "performance"]):
        cat = "Fixes"  # performance -> fixes bucket
    elif any(l in labels for l in ["docs", "documentation"]):
        cat = "Chore"  # docs -> chore
    elif any(l in labels for l in ["refactor", "chore"]):
        cat = "Chore"

    # Conventional commit overrides (restricted)
    if conventional == "feat":
        cat = "Features"
    elif conventional == "fix":
        cat = "Fixes"
    elif conventional == "perf":
        cat = "Fixes"
    elif conventional == "docs":
        cat = "Chore"
    elif conventional in ("refactor", "chore"):
        cat = "Chore"

    return ClassifiedPR(pr=pr, category=cat, area=area, is_breaking=breaking)


def summarize_for_llm(classified: List[ClassifiedPR]) -> List[Dict]:
    out = []
    for c in classified:
        out.append({
            "number": c.pr.number,
            "title": c.pr.title,
            "labels": list(c.pr.labels or []),
            "author": c.pr.author,
            "url": c.pr.url,
            "body_excerpt": c.pr.body_excerpt,
            "category": c.category,
            "area": c.area,
            "is_breaking": c.is_breaking,
        })
    return out
