"""Calculation service: the use case behind ``POST /api/calculate``.

Order of operations (this is exactly the pipeline the assignment requires):
validate -> parse -> calculate -> persist -> return to the caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from ..calculator import evaluate
from ..config import Settings
from ..model.history_repository import HistoryRepository


def _default_clock() -> str:
    """Timestamp format used for ``created_at`` (local time, second precision)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class CalculatorService:
    """Evaluate an expression safely and remember the successful result."""

    def __init__(
        self,
        repository: HistoryRepository,
        settings: Settings,
        clock: Callable[[], str] = _default_clock,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._clock = clock

    def calculate(self, expression: str) -> dict:
        """Calculate *expression* and store it in the database.

        Raises a :class:`~src.errors.CalculatorError` subclass when the
        expression is rejected; nothing is stored in that case.
        """
        result = evaluate(expression, self._settings)
        created_at = self._clock()

        record = self._repository.insert(
            expression=result.expression,
            result=result.result_text,
            result_value=_as_float(result.value),
            created_at=created_at,
        )

        return {
            "expression": expression.strip(),
            "normalized_expression": result.expression,
            "result": result.value,
            "result_text": result.result_text,
            "record_id": record.id,
            "created_at": record.created_at,
            "is_favorite": record.is_favorite,
        }


def _as_float(value: int | float) -> float | None:
    """Numeric mirror of the result used for statistics.

    Values that cannot be represented as a float (extremely large integers) are
    stored as NULL so that aggregation never raises.
    """
    try:
        return float(value)
    except (OverflowError, ValueError):  # pragma: no cover - defensive
        return None
