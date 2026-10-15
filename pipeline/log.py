"""Logging helpers that also surface warnings as GitHub Actions annotations."""

from __future__ import annotations

import logging
import os
import sys

LOGGER = logging.getLogger("pipeline")


def configure() -> None:
    if LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


def _escape(message: str) -> str:
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def warn(message: str) -> None:
    LOGGER.warning(message)
    if os.getenv("GITHUB_ACTIONS") == "true":
        sys.stdout.write(f"::warning::{_escape(message)}\n")
