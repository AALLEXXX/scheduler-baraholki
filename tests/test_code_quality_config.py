from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mypy_strict_gate_is_configured() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"mypy>=' in pyproject
    assert "[tool.mypy]" in pyproject
    assert "strict = true" in pyproject
