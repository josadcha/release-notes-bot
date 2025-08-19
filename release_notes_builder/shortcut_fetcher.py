from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict
import logging
import re
import requests


log = logging.getLogger(__name__)


STORY_URL_RE = re.compile(r"https?://app\.shortcut\.com/[^/]+/story/(\d+)")
SC_PREFIX_RE = re.compile(r"\bsc-(\d{3,})\b", re.IGNORECASE)


@dataclass
class ShortcutStory:
    id: int
    name: str
    app_url: str
    description: Optional[str]
    state: Optional[str]
    estimate: Optional[int]


class ShortcutFetcher:
    def __init__(self, token: Optional[str]):
        self.token = token
        self.enabled = bool(token)
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Shortcut-Token": token})

    def extract_story_id(self, title: str, body: str) -> Optional[int]:
        # Prefer explicit URL in body
        m = STORY_URL_RE.search(body or "")
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        # Fallback: sc-<id> in title or body
        for text in (title or "", body or ""):
            m2 = SC_PREFIX_RE.search(text)
            if m2:
                try:
                    return int(m2.group(1))
                except ValueError:
                    continue
        return None

    def get_story(self, story_id: int) -> Optional[ShortcutStory]:
        if not self.enabled:
            return None
        url = f"https://api.app.shortcut.com/api/v3/stories/{story_id}"
        try:
            r = self.session.get(url, timeout=15)
            if r.status_code == 404:
                log.warning("Shortcut story %s not found", story_id)
                return None
            r.raise_for_status()
            data = r.json()
            return ShortcutStory(
                id=data.get("id"),
                name=data.get("name") or "",
                app_url=data.get("app_url") or "",
                description=data.get("description"),
                state=(data.get("workflow_state") or {}).get("name"),
                estimate=data.get("estimate"),
            )
        except requests.RequestException as e:
            log.warning("Shortcut API error for story %s: %s", story_id, e)
            return None
