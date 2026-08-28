"""Static model and feature-flag contracts for Living Loop P0."""

from __future__ import annotations

import importlib
from pathlib import Path

from pydantic import ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_living_loop_feature_flags_are_safe_by_default_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBUG", "true")
    from app.config import Settings

    defaults = Settings(_env_file=None, debug=True)
    assert defaults.living_loop_p0_enabled is False
    assert defaults.living_loop_p0_delay_seconds == 28_800

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            debug=True,
            living_loop_p0_delay_seconds=0,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            debug=True,
            living_loop_p0_delay_seconds=10**9,
        )

    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "LIVING_LOOP_P0_ENABLED=false" in env_example
    assert "LIVING_LOOP_P0_DELAY_SECONDS=28800" in env_example


def test_living_loop_models_are_registered_with_base_metadata() -> None:
    model_init = (ROOT / "app" / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "import app.models.living_loop_day" in model_init
    assert "import app.models.product_event" in model_init

    importlib.import_module("app.models.living_loop_day")
    importlib.import_module("app.models.product_event")

    from app.database import Base

    assert {"living_loop_days", "product_events"} <= set(Base.metadata.tables)
