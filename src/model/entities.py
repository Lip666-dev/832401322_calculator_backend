"""Database entity definitions.

The entities are plain frozen dataclasses: they carry data between the
repository, the services and the API layer without any framework magic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CalculationRecord:
    """One row of the ``calculation_history`` table."""

    id: int
    expression: str
    result: str
    result_value: float | None
    is_favorite: bool
    created_at: str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CalculationRecord":
        stored_result = row["result_value"]
        return cls(
            id=int(row["id"]),
            expression=str(row["expression"]),
            result=str(row["result"]),
            result_value=None if stored_result is None else float(stored_result),
            is_favorite=bool(row["is_favorite"]),
            created_at=str(row["created_at"]),
        )

    def result_number(self) -> int | float | None:
        """Return the result as a JSON number.

        Very long integers are returned verbatim as text by
        :meth:`to_dict` instead, because JavaScript numbers would lose
        precision on them.
        """
        text = self.result
        try:
            if text.lstrip("-").isdigit():
                return int(text)
            return float(text)
        except ValueError:  # pragma: no cover - stored values are always numeric
            return None

    def to_dict(self) -> dict:
        number = self.result_number()
        return {
            "id": self.id,
            "expression": self.expression,
            "result": self.result,
            "result_number": number,
            "result_value": self.result_value,
            "is_favorite": self.is_favorite,
            "created_at": self.created_at,
        }
