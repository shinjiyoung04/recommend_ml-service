"""Atomic model activation with validation and rollback."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import joblib


def activate_model(bundle, model_dir: Path):
    """Validate a candidate, atomically activate it, and return the loaded object.

    The previous model remains available as ``previous.joblib``. Any failure
    restores it before the exception is propagated.
    """
    model_dir.mkdir(parents=True, exist_ok=True)
    current = model_dir / "current.joblib"
    previous = model_dir / "previous.joblib"
    candidate = model_dir / "candidate.joblib"
    bundle.save(candidate)
    loaded = joblib.load(candidate)
    if getattr(loaded, "matrix", None) is None:
        candidate.unlink(missing_ok=True)
        raise ValueError("candidate model has no fitted feature matrix")

    had_current = current.exists()
    try:
        if had_current:
            shutil.copy2(current, previous)
        os.replace(candidate, current)
        activated = joblib.load(current)
        if getattr(activated, "matrix", None) is None:
            raise ValueError("activated model failed validation")
        return activated
    except Exception:
        candidate.unlink(missing_ok=True)
        if had_current and previous.exists():
            shutil.copy2(previous, current)
        elif not had_current:
            current.unlink(missing_ok=True)
        raise
