"""Shared utility helpers for configuration, logging, and filesystem setup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file."""
    with Path(path).open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def ensure_directories(config: dict[str, Any]) -> None:
    """Create all configured data and output directories."""
    paths = [
        config["data"]["raw_dir"],
        Path(config["data"]["processed_path"]).parent,
        config["outputs"]["figures_dir"],
        config["outputs"]["tables_dir"],
        config["outputs"]["reports_dir"],
    ]
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)


def setup_logging(log_path: str | Path = "outputs/reports/pipeline.log") -> logging.Logger:
    """Configure console and file logging for the pipeline."""
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("crowding_momentum")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


def normalize_date_string(value: str | None) -> str | None:
    """Normalize YYYY-MM-DD or YYYYMMDD strings to YYYYMMDD."""
    if value is None:
        return None
    return str(value).replace("-", "")
