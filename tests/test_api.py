"""End-to-end tests: a real HTTP server, real sockets, real SQLite file.

These tests are the executable version of the assignment checklist:
calculate through the API, read history from the API, delete a record through
the API, and verify that everything was persisted in the database rather than in
server memory.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.config import Settings
from src.server import build_application, create_server


class ApiTestCase(unittest.TestCase):
    """Boots one server for the whole test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.settings = Settings()
        cls.settings.host = "127.0.0.1"
        cls.settings.port = 0  # let the OS choose a free port
        cls.settings.db_path = Path(cls._tmp.name) / "api_test.db"

        cls.application = build_application(cls.settings)
        cls.server = create_server(cls.settings, cls.application)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls._thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls._thread.join(timeout=5)
        cls._tmp.cleanup()

    def setUp(self) -> None:
        # Every test starts from an empty history.
        self.request("DELETE", "/api/history")

    # -- helpers ------------------------------------------------------------
    def request(
        self, method: str, path: str, payload: object | None = None
    ) -> tuple[int, dict, dict]:
        """Perform one request and return ``(status, body, headers)``."""
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body), dict(response.headers)
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8")
            return error.code, (json.loads(raw) if raw else {}), dict(error.headers)

    def post_raw(self, path: str, raw: bytes, content_type: str = "application/json"):
        request = urllib.request.Request(self.base_url + path, data=raw, method="POST")
        request.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raw_body = error.read().decode("utf-8")
            return error.code, (json.loads(raw_body) if raw_body else {})

    # -- meta ---------------------------------------------------------------
    def test_health_endpoint(self) -> None:
        status, body, headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body["database"]["status"], "ok")
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")

    def test_capabilities_endpoint(self) -> None:
        status, body, _ = self.request("GET", "/api/calculator")
        self.assertEqual(status, 200)
        names = {entry["name"] for entry in body["functions"]}
        self.assertIn("sqrt", names)
        self.assertIn("fact", names)

    # -- calculation --------------------------------------------------------
    def test_basic_calculation(self) -> None:
        status, body, _ = self.request("POST", "/api/calculate", {"expression": "12+8"})
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body["result"], 20)
        self.assertEqual(body["result_text"], "20")
        self.assertEqual(body["expression"], "12+8")
        self.assertIsInstance(body["record_id"], int)

    def test_all_four_operations(self) -> None:
        cases = {"12+8": 20, "20-5": 15, "6*7": 42, "84/4": 21}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                _, body, _ = self.request("POST", "/api/calculate", {"expression": expression})
                self.assertEqual(body["result"], expected)

    def test_compound_expression(self) -> None:
        cases = {"1+2*3": 7, "(1+2)*3": 9, "10/2+7": 12, "8-3*2": 2, "-5+8": 3, "3*-2": -6}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                _, body, _ = self.request("POST", "/api/calculate", {"expression": expression})
                self.assertEqual(body["result"], expected)
                self.assertEqual(body["normalized_expression"], expression)

    def test_unicode_symbols_are_normalised(self) -> None:
        _, body, _ = self.request("POST", "/api/calculate", {"expression": "12×8"})
        self.assertEqual(body["result"], 96)
        self.assertEqual(body["normalized_expression"], "12*8")

    def test_invalid_expression_is_rejected(self) -> None:
        status, body, _ = self.request("POST", "/api/calculate", {"expression": "1+*2"})
        self.assertEqual(status, 400)
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], "INVALID_EXPRESSION")
        self.assertIn("message", body)

    def test_division_by_zero_is_reported(self) -> None:
        status, body, _ = self.request("POST", "/api/calculate", {"expression": "5/0"})
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "DIVISION_BY_ZERO")

    def test_missing_and_malformed_payloads(self) -> None:
        status, body, _ = self.request("POST", "/api/calculate")
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "INVALID_REQUEST")

        status, body, _ = self.request("POST", "/api/calculate", {"expression": 42})
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "INVALID_REQUEST")

        status, body, _ = self.request("POST", "/api/calculate", {"expression": "   "})
        self.assertEqual(status, 400)

        status, body = self.post_raw("/api/calculate", b"{not json")
        self.assertEqual(status, 400)
        self.assertIn("valid JSON", body["message"])

    # -- history ------------------------------------------------------------
    def test_history_is_persisted_and_readable(self) -> None:
        for expression in ("1+2", "5*8", "(2+3)*4"):
            self.request("POST", "/api/calculate", {"expression": expression})

        status, body, _ = self.request("GET", "/api/history")
        self.assertEqual(status, 200)
        self.assertEqual(body["total"], 3)
        self.assertEqual([item["expression"] for item in body["items"]], ["(2+3)*4", "5*8", "1+2"])
        self.assertEqual(body["items"][0]["result"], "20")
        self.assertIn("created_at", body["items"][0])

    def test_history_pagination(self) -> None:
        for index in range(5):
            self.request("POST", "/api/calculate", {"expression": f"{index}+1"})

        _, page_one, _ = self.request("GET", "/api/history?page=1&page_size=2")
        _, page_two, _ = self.request("GET", "/api/history?page=2&page_size=2")
        self.assertEqual(page_one["pages"], 3)
        self.assertEqual(len(page_one["items"]), 2)
        self.assertEqual([item["expression"] for item in page_two["items"]], ["2+1", "1+1"])

    def test_history_search_and_favorites(self) -> None:
        self.request("POST", "/api/calculate", {"expression": "1+2"})
        self.request("POST", "/api/calculate", {"expression": "5*8"})

        _, body, _ = self.request("GET", "/api/history?keyword=5")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["expression"], "5*8")

        record_id = body["items"][0]["id"]
        status, favorite, _ = self.request(
            "PUT", f"/api/history/{record_id}/favorite", {"is_favorite": True}
        )
        self.assertEqual(status, 200)
        self.assertTrue(favorite["is_favorite"])

        _, only_favorites, _ = self.request("GET", "/api/history?favorites=1")
        self.assertEqual(only_favorites["total"], 1)

    def test_get_single_record(self) -> None:
        _, created, _ = self.request("POST", "/api/calculate", {"expression": "7*6"})
        status, body, _ = self.request("GET", f"/api/history/{created['record_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["item"]["expression"], "7*6")

        status, body, _ = self.request("GET", "/api/history/999999")
        self.assertEqual(status, 404)
        self.assertEqual(body["code"], "NOT_FOUND")

    def test_delete_single_record(self) -> None:
        _, created, _ = self.request("POST", "/api/calculate", {"expression": "1+1"})
        record_id = created["record_id"]

        status, body, _ = self.request("DELETE", f"/api/history/{record_id}")
        self.assertEqual(status, 200)
        self.assertEqual(body["deleted"], 1)

        _, history, _ = self.request("GET", "/api/history")
        self.assertEqual(history["total"], 0)

        status, body, _ = self.request("DELETE", f"/api/history/{record_id}")
        self.assertEqual(status, 404)

    def test_clear_all_history(self) -> None:
        for index in range(3):
            self.request("POST", "/api/calculate", {"expression": f"{index}+1"})
        status, body, _ = self.request("DELETE", "/api/history")
        self.assertEqual(status, 200)
        self.assertEqual(body["deleted"], 3)
        self.assertEqual(self.request("GET", "/api/history")[1]["total"], 0)

    def test_statistics(self) -> None:
        self.request("POST", "/api/calculate", {"expression": "1+2"})
        self.request("POST", "/api/calculate", {"expression": "5*8"})
        status, body, _ = self.request("GET", "/api/statistics")
        self.assertEqual(status, 200)
        statistics = body["statistics"]
        self.assertEqual(statistics["total"], 2)
        self.assertEqual(statistics["max_result"], 40.0)

    # -- extended features --------------------------------------------------
    def test_base_conversion(self) -> None:
        status, body, _ = self.request(
            "POST", "/api/convert/base", {"value": "255", "from_base": 10, "to_base": 16}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"], "ff")

        status, body, _ = self.request(
            "POST", "/api/convert/base", {"value": "12", "from_base": 2, "to_base": 10}
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "INVALID_EXPRESSION")

    # -- protocol -----------------------------------------------------------
    def test_data_survives_a_server_restart(self) -> None:
        self.request("POST", "/api/calculate", {"expression": "11*11"})
        # A fresh application object on the same database file simulates a restart.
        restarted = build_application(self.settings)
        history = restarted.history_service.list_history()
        self.assertEqual(history["total"], 1)
        self.assertEqual(history["items"][0]["expression"], "11*11")

    def test_unknown_route_returns_404(self) -> None:
        status, body, _ = self.request("GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertEqual(body["code"], "NOT_FOUND")

    def test_wrong_method_returns_405_with_allow_header(self) -> None:
        status, body, headers = self.request("PUT", "/api/calculate")
        self.assertEqual(status, 405)
        self.assertEqual(body["code"], "METHOD_NOT_ALLOWED")
        self.assertIn("POST", headers.get("Allow", ""))

    def test_cors_preflight(self) -> None:
        request = urllib.request.Request(self.base_url + "/api/calculate", method="OPTIONS")
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", response.headers.get("Access-Control-Allow-Methods", ""))

    def test_index_route_is_not_served_by_the_backend(self) -> None:
        # The backend only speaks JSON; the front end lives in its own project.
        status, body, _ = self.request("GET", "/")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
