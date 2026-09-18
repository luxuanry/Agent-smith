"""Minimal .env loader (no external dependency)."""
from __future__ import annotations

import os


def load_env_file(path: str = ".env") -> None:
    """Load KEY=VALUE lines into os.environ. Existing env vars are not overwritten."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
