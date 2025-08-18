from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import datetime


def _product_for_repo(full_name: str) -> str:
    # Map repo full names to product buckets / display names
    # Examples: maple-labs/maple-api -> API, maple-labs/hq -> hq, *ya-webapp* or *syrup* -> Syrup
    name = full_name.lower()
    if name.endswith("/ya-webapp") or "syrup" in name:
        return "Syrup"
    if "/hq" in name or name.endswith("/hq"):
        return "hq"
    if "api" in name:
        return "API"
    if name.endswith("/ya-webapp"):
        return "Webapp"
    return full_name


def _emoji_for_category(cat: str) -> str:
    c = cat.lower()
    if c.startswith("feature"):
        return ":sparkles:"
    if c.startswith("fix"):
        return ":bug:"
    if c.startswith("chore"):
        return ":hammer_and_wrench:"
    return ""


def render_md(doc: Dict) -> str:
    # Title
    title = doc.get("title") or "Offchain Release"
    today = datetime.utcnow().strftime("%Y-%m-%d")
    lines: List[str] = []
    lines.append(f"# {title} ({today})")
    lines.append("")

    # Focus areas from TL;DR
    tldr = doc.get("tldr") or []
    if tldr:
        lines.append("Focus areas for the week:")
        for b in tldr[:10]:
            lines.append(f"- {b}")
        lines.append("")

    # Collect bullets per product
    products: Dict[str, List[str]] = {}

    for repo in doc.get("repos", []):
        repo_name = repo.get("name") or "unknown/unknown"
        product = _product_for_repo(repo_name)
        for sec in repo.get("sections", []):
            title = (sec.get("title") or "").strip()
            emoji = _emoji_for_category(title)
            for item in sec.get("items", []):
                text = item.get("text") or ""
                prs = item.get("prs") or []
                pr_links = " ".join([f"[PR #{n}](https://github.com/{repo_name}/pull/{n})" for n in prs])
                bullet = f"- {emoji} {text}".strip()
                if pr_links:
                    bullet += f" {pr_links}"
                products.setdefault(product, []).append(bullet)

    # Render products in preferred order
    for product in products:
        items = products.get(product) or []
        if not items:
            continue
        lines.append(f"**{product}**")
        for b in items:
            lines.append(b)
        lines.append("")

    # Upgrade notes
    upg = doc.get("upgrade_notes") or []
    if upg:
        lines.append("Upgrade notes:")
        for note in upg:
            lines.append(f"- {note}")
        lines.append("")


    return "\n".join(lines)
