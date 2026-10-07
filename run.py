"""Convenience launcher so the project can be started with ``python run.py``."""

from __future__ import annotations

import sys

from src.server import main

if __name__ == "__main__":
    sys.exit(main())
