"""Tests for the SQLite persistence layer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.model.database import Database
from src.model.history_repository import HistoryRepository


class HistoryRepositoryTest(unittest.TestCase):
    """Every query the API depends on is exercised against a real SQLite file."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self._tmp.name) / "test_history.db")
        self.database.initialize()
        self.repository = HistoryRepository(self.database)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self, count: int = 3) -> None:
        for index in range(count):
            self.repository.insert(
                expression=f"{index}+1",
                result=str(index + 1),
                result_value=float(index + 1),
                created_at=f"2026-10-0{index + 1} 10:00:0{index}",
            )

    def test_schema_is_created(self) -> None:
        with self.database.connection() as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        self.assertIn("calculation_history", tables)

    def test_insert_returns_the_stored_row(self) -> None:
        record = self.repository.insert("1+2", "3", 3.0, "2026-10-01 10:20:00")
        self.assertEqual(record.id, 1)
        self.assertEqual(record.expression, "1+2")
        self.assertEqual(record.result, "3")
        self.assertFalse(record.is_favorite)
        self.assertEqual(record.created_at, "2026-10-01 10:20:00")

    def test_get_by_id(self) -> None:
        record = self.repository.insert("(2+3)*4", "20", 20.0, "2026-10-01 10:22:00")
        fetched = self.repository.get(record.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.result, "20")
        self.assertIsNone(self.repository.get(9999))

    def test_list_is_newest_first(self) -> None:
        self._seed(3)
        records, total = self.repository.list()
        self.assertEqual(total, 3)
        self.assertEqual([record.id for record in records], [3, 2, 1])

    def test_pagination(self) -> None:
        self._seed(5)
        first_page, total = self.repository.list(page=1, page_size=2)
        second_page, _ = self.repository.list(page=2, page_size=2)
        self.assertEqual(total, 5)
        self.assertEqual([record.id for record in first_page], [5, 4])
        self.assertEqual([record.id for record in second_page], [3, 2])

    def test_keyword_search(self) -> None:
        self._seed(3)
        records, total = self.repository.list(keyword="2+1")
        self.assertEqual(total, 1)
        self.assertEqual(records[0].expression, "2+1")

    def test_like_wildcards_in_keyword_are_escaped(self) -> None:
        self._seed(3)
        records, total = self.repository.list(keyword="%")
        self.assertEqual(total, 0)
        self.assertEqual(records, [])

    def test_favorite_filter_and_toggle(self) -> None:
        self._seed(3)
        self.assertEqual(self.repository.set_favorite(2, True), 1)
        favorites, total = self.repository.list(favorites_only=True)
        self.assertEqual(total, 1)
        self.assertEqual(favorites[0].id, 2)
        self.assertEqual(self.repository.set_favorite(2, False), 1)
        self.assertEqual(self.repository.list(favorites_only=True)[1], 0)

    def test_delete_and_clear(self) -> None:
        self._seed(3)
        self.assertEqual(self.repository.delete(2), 1)
        self.assertEqual(self.repository.delete(2), 0)
        self.assertEqual(self.repository.list()[1], 2)
        self.assertEqual(self.repository.clear(), 2)
        self.assertEqual(self.repository.list()[1], 0)

    def test_statistics(self) -> None:
        self.repository.insert("1+2", "3", 3.0, "2026-10-01 10:20:00")
        self.repository.insert("5*8", "40", 40.0, "2026-10-01 10:21:00")
        self.repository.set_favorite(2, True)

        stats = self.repository.statistics()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["favorites"], 1)
        self.assertEqual(stats["max_result"], 40.0)
        self.assertEqual(stats["min_result"], 3.0)
        self.assertAlmostEqual(stats["average_result"], 21.5)
        operators = {entry["operator"]: entry["count"] for entry in stats["top_operators"]}
        self.assertEqual(operators["+"], 1)
        self.assertEqual(operators["*"], 1)

    def test_data_survives_a_new_connection(self) -> None:
        self._seed(2)
        fresh = HistoryRepository(Database(self.database.path))
        self.assertEqual(fresh.list()[1], 2)


if __name__ == "__main__":
    unittest.main()
