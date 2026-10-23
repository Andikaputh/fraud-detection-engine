"""Shared API dependencies."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from backend.api.runtime import runtime
from backend.config import settings
from backend.stream.pipeline import TransactionPipeline


def get_pipeline() -> TransactionPipeline:
    return runtime.require_pipeline()


def require_write_access(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Optional key-based protection for mutating endpoints.

    With `SENTINEL_API_KEY` unset the demo accepts writes from same-origin clients.
    Any public deployment should set the key; the console then stores it locally.
    """
    if not settings.api_key:
        return
    supplied = x_api_key
    if not supplied and authorization and authorization.lower().startswith("bearer "):
        supplied = authorization.split(" ", 1)[1]
    if supplied != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def operator_identity(request: Request) -> str:
    return request.headers.get("x-operator", "operator")
