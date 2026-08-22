"""Merchant API-key authentication."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from recoverpilot.core import db
from recoverpilot.core.config import DEMO_API_KEY
from recoverpilot.core.db import MerchantRow


def require_merchant(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> MerchantRow:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    merchant = db.get_merchant_by_api_key(x_api_key)
    if merchant is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return merchant


def optional_merchant(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> MerchantRow | None:
    if not x_api_key:
        return None
    return db.get_merchant_by_api_key(x_api_key)


def demo_key_hint() -> str:
    return DEMO_API_KEY
