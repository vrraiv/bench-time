"""Filesystem locations. Everything derives from the repo root unless COURTDELAY_DATA_DIR is set."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    return Path(os.environ.get("COURTDELAY_DATA_DIR", REPO_ROOT / "data"))


def raw_dir(source: str) -> Path:
    p = data_dir() / "raw" / source
    p.mkdir(parents=True, exist_ok=True)
    return p


def processed_dir() -> Path:
    p = data_dir() / "processed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def manifest_path() -> Path:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "manifest.jsonl"


def fixtures_dir(source: str) -> Path:
    return REPO_ROOT / "tests" / "fixtures" / source
