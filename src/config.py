"""Runtime configuration.

Values come from, in order of precedence: command line flags, environment
variables, built-in defaults.  Nothing here is secret, so a plain dataclass is
enough - the goal is simply to keep every tunable number in one obvious place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# <repo>/src/config.py -> <repo>
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "calculator.db"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None or raw.strip() == "" else raw.strip()


@dataclass
class Settings:
    """All tunable values of the service."""

    host: str = "127.0.0.1"
    port: int = 8000
    db_path: Path = DEFAULT_DB_PATH

    # --- expression guard rails -------------------------------------------------
    max_expression_length: int = 200
    max_tokens: int = 256
    max_parse_depth: int = 64
    max_factorial_argument: int = 170
    max_integer_bits: int = 4096
    max_integer_exponent: int = 4096
    max_abs_result: float = 1e308

    # --- history paging --------------------------------------------------------
    default_page_size: int = 10
    max_page_size: int = 100

    # --- HTTP ------------------------------------------------------------------
    max_body_bytes: int = 64 * 1024
    cors_allow_origin: str = "*"
    request_timeout_seconds: float = 15.0

    # --- misc ------------------------------------------------------------------
    version: str = "1.0.0"
    operator_names: dict = field(
        default_factory=lambda: {
            "+": "addition",
            "-": "subtraction",
            "*": "multiplication",
            "/": "division",
            "%": "modulo",
            "^": "power",
            "!": "factorial",
        }
    )

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls()
        settings.host = _env_str("CALC_HOST", settings.host)
        settings.port = _env_int("CALC_PORT", settings.port)
        raw_db = os.environ.get("CALC_DB_PATH")
        if raw_db and raw_db.strip():
            settings.db_path = Path(raw_db.strip()).expanduser()
        settings.cors_allow_origin = _env_str("CALC_CORS_ORIGIN", settings.cors_allow_origin)
        return settings

    def resolved_db_path(self) -> Path:
        """Absolute path of the SQLite file, with its directory created."""
        path = Path(self.db_path).expanduser()
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
