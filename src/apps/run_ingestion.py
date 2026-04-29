"""
Entry point for Phase 2 ingestion: Polygon WebSocket -> decode -> Redpanda.

Loads `.env` from the repository root (if present) without requiring python-dotenv.
Run from repo root: `PYTHONPATH=. python -m src.apps.run_ingestion`
or: `make run-ingestion`
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_repo_on_path() -> Path:
    root = _project_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def _load_dotenv_file(path: Path) -> None:
    """Parse KEY=VALUE lines from `.env`; does not override existing os.environ."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def main() -> None:
    root = _ensure_repo_on_path()
    _load_dotenv_file(root / ".env")

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    from src.ingestion.listener import main as ingestion_main

    asyncio.run(ingestion_main())


if __name__ == "__main__":
    main()
