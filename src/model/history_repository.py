"""Data access for the ``calculation_history`` table.

Only this module contains SQL.  Services call plain Python methods, which keeps
the persistence technology replaceable and makes the queries easy to test.
"""

from __future__ import annotations

from typing import List, Tuple

from ..calculator import describe_operators
from .database import Database
from .entities import CalculationRecord

_OPERATOR_LABELS = {
    "+": "addition",
    "-": "subtraction",
    "*": "multiplication",
    "/": "division",
    "%": "modulo",
    "^": "power",
    "!": "factorial",
}


class HistoryRepository:
    """CRUD operations for calculation history."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # -- writes -------------------------------------------------------------
    def insert(
        self,
        expression: str,
        result: str,
        result_value: float | None,
        created_at: str,
    ) -> CalculationRecord:
        """Store one successful calculation and return the stored row."""
        with self._database.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO calculation_history (expression, result, result_value, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (expression, result, result_value, created_at),
            )
            record_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM calculation_history WHERE id = ?", (record_id,)
            ).fetchone()
        return CalculationRecord.from_row(row)

    def delete(self, record_id: int) -> int:
        """Delete one record; return the number of affected rows."""
        with self._database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM calculation_history WHERE id = ?", (record_id,)
            )
            return int(cursor.rowcount)

    def clear(self) -> int:
        """Delete every record; return how many were removed."""
        with self._database.connection() as connection:
            cursor = connection.execute("DELETE FROM calculation_history")
            return int(cursor.rowcount)

    def set_favorite(self, record_id: int, is_favorite: bool) -> int:
        """Mark or unmark a record as a favourite."""
        with self._database.connection() as connection:
            cursor = connection.execute(
                "UPDATE calculation_history SET is_favorite = ? WHERE id = ?",
                (1 if is_favorite else 0, record_id),
            )
            return int(cursor.rowcount)

    # -- reads --------------------------------------------------------------
    def get(self, record_id: int) -> CalculationRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM calculation_history WHERE id = ?", (record_id,)
            ).fetchone()
        return None if row is None else CalculationRecord.from_row(row)

    def list(
        self,
        keyword: str | None = None,
        favorites_only: bool = False,
        page: int = 1,
        page_size: int = 10,
    ) -> Tuple[List[CalculationRecord], int]:
        """Return one page of history (newest first) and the total match count."""
        clauses: List[str] = []
        parameters: List[object] = []

        if keyword:
            clauses.append("(expression LIKE ? ESCAPE '\\' OR result LIKE ? ESCAPE '\\')")
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend([f"%{escaped}%", f"%{escaped}%"])
        if favorites_only:
            clauses.append("is_favorite = 1")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        offset = (page - 1) * page_size

        with self._database.connection() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS total FROM calculation_history {where}", parameters
                ).fetchone()["total"]
            )
            rows = connection.execute(
                f"""
                SELECT * FROM calculation_history
                {where}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                [*parameters, page_size, offset],
            ).fetchall()

        return [CalculationRecord.from_row(row) for row in rows], total

    # -- statistics ---------------------------------------------------------
    def statistics(self, operator_sample_size: int = 500) -> dict:
        """Aggregate numbers and operator usage for the statistics endpoint."""
        with self._database.connection() as connection:
            summary = connection.execute(
                """
                SELECT COUNT(*)                        AS total,
                       SUM(is_favorite)                AS favorites,
                       AVG(result_value)               AS average_result,
                       MIN(result_value)               AS min_result,
                       MAX(result_value)               AS max_result
                FROM calculation_history
                """
            ).fetchone()
            today = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS total FROM calculation_history
                    WHERE date(created_at) = date('now', 'localtime')
                    """
                ).fetchone()["total"]
            )
            recent = connection.execute(
                """
                SELECT expression FROM calculation_history
                ORDER BY id DESC LIMIT ?
                """,
                (operator_sample_size,),
            ).fetchall()

        counts: dict[str, int] = {}
        for row in recent:
            for operator in describe_operators(row["expression"]):
                counts[operator] = counts.get(operator, 0) + 1

        top_operators = [
            {"operator": operator, "name": _OPERATOR_LABELS[operator], "count": count}
            for operator, count in sorted(counts.items(), key=lambda item: -item[1])
        ]

        average = summary["average_result"]
        return {
            "total": int(summary["total"] or 0),
            "today": today,
            "favorites": int(summary["favorites"] or 0),
            "average_result": None if average is None else round(float(average), 6),
            "min_result": summary["min_result"],
            "max_result": summary["max_result"],
            "top_operators": top_operators,
            "operator_sample_size": len(recent),
        }
