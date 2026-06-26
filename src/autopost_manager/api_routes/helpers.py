from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter


def add_dual_route(
    router: APIRouter,
    legacy_path: str,
    current_path: str,
    endpoint: Callable[..., Any],
    **kwargs: Any,
) -> None:
    router.add_api_route(current_path, endpoint, **kwargs)
    router.add_api_route(legacy_path, endpoint, deprecated=True, **kwargs)
