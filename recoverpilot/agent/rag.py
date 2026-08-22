"""Playbook retrieval.

Prefers Chroma + sentence-transformers when installed; otherwise uses
deterministic keyword / decline-code matching (still grounded).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from recoverpilot.data.playbooks_loader import all_playbook_documents, playbook_for_decline


class PlaybookRAG:
    def __init__(self) -> None:
        self.mode = "keyword"
        self._index = None
        self._docs = all_playbook_documents()
        self._try_init_chroma()

    def _try_init_chroma(self) -> None:
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            client = chromadb.Client()
            ef = embedding_functions.DefaultEmbeddingFunction()
            coll = client.get_or_create_collection("decline_playbooks", embedding_function=ef)
            if coll.count() == 0:
                coll.add(
                    ids=[d["id"] for d in self._docs],
                    documents=[d["text"] for d in self._docs],
                    metadatas=[{"title": d["title"]} for d in self._docs],
                )
            self._index = coll
            self.mode = "chroma"
        except Exception:
            self.mode = "keyword"
            self._index = None

    def retrieve(self, decline_code: str, query_extra: str = "") -> dict[str, Any]:
        # Always prefer exact decline-code playbook for grounding.
        exact = playbook_for_decline(decline_code)
        excerpt = exact["guidance"]
        if self._index is not None:
            try:
                q = f"{decline_code} {query_extra} recovery playbook"
                res = self._index.query(query_texts=[q], n_results=1)
                if res and res.get("documents") and res["documents"][0]:
                    excerpt = res["documents"][0][0][:500]
            except Exception:
                pass
        return {
            "playbook_id": exact["id"],
            "playbook": exact,
            "excerpt": excerpt,
            "retrieval_mode": self.mode,
        }


@lru_cache(maxsize=1)
def get_rag() -> PlaybookRAG:
    return PlaybookRAG()
