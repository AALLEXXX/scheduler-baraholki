from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from fastapi import APIRouter


def add_dual_route(
    router: APIRouter,
    legacy_path: str,
    current_path: str | Sequence[str],
    endpoint: Callable[..., Any],
    **kwargs: Any,
) -> None:
    current_paths = (current_path,) if isinstance(current_path, str) else current_path
    for path in current_paths:
        router.add_api_route(path, endpoint, **kwargs)
    router.add_api_route(legacy_path, endpoint, deprecated=True, **kwargs)
