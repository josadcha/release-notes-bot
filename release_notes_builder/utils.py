from datetime import datetime
from typing import Iterable, List
import requests


def iso_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def chunk_lines(text: str, max_lines: int = 12) -> str:
    lines = (text or "").splitlines()
    return "\n".join(lines[:max_lines])


def make_gh_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "release-notes-builder/0.1",
    })
    return s


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out
