from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from recoverpilot.core.config import PLAYBOOKS_DIR


@lru_cache(maxsize=1)
def load_playbooks() -> list[dict[str, Any]]:
    path = PLAYBOOKS_DIR / "decline_playbooks.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)["playbooks"]


def playbook_for_decline(decline_code: str) -> dict[str, Any]:
    books = load_playbooks()
    for pb in books:
        if decline_code in pb.get("decline_codes", []):
            return pb
    # default soft
    for pb in books:
        if pb["id"] == "PB_DEFAULT_SOFT":
            return pb
    return books[0]


def all_playbook_documents() -> list[dict[str, str]]:
    docs = []
    for pb in load_playbooks():
        text = (
            f"Playbook {pb['id']}: {pb['title']}. "
            f"Decline codes: {', '.join(pb['decline_codes'])}. "
            f"Preferred action: {pb['preferred_action']}. "
            f"Channel: {pb.get('channel')}. "
            f"Retry after hours: {pb.get('retry_after_hours')}. "
            f"Guidance: {pb['guidance']}"
        )
        docs.append({"id": pb["id"], "text": text, "title": pb["title"]})
    return docs
