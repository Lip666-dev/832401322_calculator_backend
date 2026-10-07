"""HTTP entry point of the calculator backend.

Start it with::

    python -m src.server --host 127.0.0.1 --port 8000

The service speaks JSON over HTTP/1.1 and never renders HTML: the front end is a
separate project that talks to this API.  CORS is enabled so the static front end
can be served from any origin, or even opened straight from disk.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Mapping, Tuple
from urllib.parse import parse_qs, urlparse

from .config import Settings
from .controller.api_controller import ApiController
from .controller.request_context import RequestContext
from .controller.router import Router
from .errors import (
    CalculatorError,
    MethodNotAllowedError,
    PayloadTooLargeError,
    ValidationError,
)
from .model.database import Database
from .model.history_repository import HistoryRepository
from .service.calculator_service import CalculatorService
from .service.history_service import HistoryService
from .service.statistics_service import StatisticsService

CORS_METHODS = "GET, POST, PUT, DELETE, OPTIONS"
CORS_HEADERS = "Content-Type, Accept"


class Application:
    """The assembled object graph of the service."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database = Database(settings.resolved_db_path())
        self.repository = HistoryRepository(self.database)

        self.calculator_service = CalculatorService(self.repository, settings)
        self.history_service = HistoryService(self.repository, settings)
        self.statistics_service = StatisticsService(self.repository)

        self.controller = ApiController(
            calculator_service=self.calculator_service,
            history_service=self.history_service,
            statistics_service=self.statistics_service,
            database=self.database,
            settings=settings,
        )
        self.router = self._build_router()

    def _build_router(self) -> Router:
        router = Router()
        controller = self.controller

        router.add("GET", r"^/api/health$", controller.health)
        router.add("GET", r"^/api/calculator$", controller.describe_calculator)
        router.add("POST", r"^/api/calculate$", controller.calculate)
        router.add("POST", r"^/api/convert/base$", controller.convert_base)
        router.add("GET", r"^/api/statistics$", controller.statistics)
        router.add("GET", r"^/api/history$", controller.list_history)
        router.add("DELETE", r"^/api/history$", controller.clear_history)
        router.add("GET", r"^/api/history/(?P<id>\d+)$", controller.get_history)
        router.add("DELETE", r"^/api/history/(?P<id>\d+)$", controller.delete_history)
        router.add(
            "PUT", r"^/api/history/(?P<id>\d+)/favorite$", controller.set_favorite
        )
        return router

    def initialize(self) -> None:
        """Create the database file and schema when they are missing."""
        self.database.initialize()

    def describe(self) -> list[str]:
        """Human readable route list, printed on startup."""
        return [
            "GET     /api/health",
            "GET     /api/calculator",
            "POST    /api/calculate",
            "POST    /api/convert/base",
            "GET     /api/history?page=&page_size=&keyword=&favorites=",
            "DELETE  /api/history",
            "GET     /api/history/{id}",
            "DELETE  /api/history/{id}",
            "PUT     /api/history/{id}/favorite",
            "GET     /api/statistics",
        ]


class CalculatorRequestHandler(BaseHTTPRequestHandler):
    """Turns an HTTP request into a controller call and back into JSON."""

    server_version = "CalculatorBackend/1.0"
    protocol_version = "HTTP/1.1"

    # Set by :func:`create_server`.
    application: Application

    # -- HTTP verbs ---------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - name fixed by the base class
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    # -- request handling ---------------------------------------------------
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query: Dict[str, str] = {
            key: values[0] for key, values in parse_qs(parsed.query).items() if values
        }
        extra_headers: Dict[str, str] = {}

        try:
            body = self._read_json_body() if method in {"POST", "PUT", "PATCH"} else None
            resolved = self.application.router.resolve(method, path)
            context = RequestContext(
                method=method,
                path=path,
                query=query,
                params=resolved.params,
                body=body,
                headers=dict(self.headers.items()),
            )
            status, payload = resolved.handler(context)
        except MethodNotAllowedError as error:
            status, payload = error.http_status, error.to_payload()
            allowed = list(error.details.get("allowed", []))
            extra_headers["Allow"] = ", ".join([*allowed, "OPTIONS"])
        except CalculatorError as error:
            status, payload = error.http_status, error.to_payload()
        except Exception:  # pragma: no cover - last resort, keep the server alive
            traceback.print_exc()
            status, payload = 500, {
                "success": False,
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
            }

        self._send_json(status, payload, extra_headers)

    def _read_json_body(self):
        """Read and decode the request body, enforcing the size limit."""
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return None
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValidationError("Content-Length must be an integer") from exc
        if length <= 0:
            return None
        if length > self.application.settings.max_body_bytes:
            raise PayloadTooLargeError(
                f"The request body may contain at most "
                f"{self.application.settings.max_body_bytes} bytes",
                limit=self.application.settings.max_body_bytes,
            )

        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError(f"The request body must be valid JSON: {exc}") from exc

    # -- response helpers ---------------------------------------------------
    def _send_cors_headers(self) -> None:
        settings = self.application.settings
        self.send_header("Access-Control-Allow-Origin", settings.cors_allow_origin)
        self.send_header("Access-Control-Allow-Methods", CORS_METHODS)
        self.send_header("Access-Control-Allow-Headers", CORS_HEADERS)

    def _send_json(
        self, status: int, payload: Mapping, extra_headers: Mapping[str, str] | None = None
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_cors_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - base signature
        """Keep the server log on one line per request."""
        sys.stderr.write(
            f"[{self.log_date_time_string()}] {self.address_string()} {format % args}\n"
        )
        sys.stderr.flush()


def build_application(settings: Settings) -> Application:
    application = Application(settings)
    application.initialize()
    return application


def create_server(settings: Settings, application: Application) -> ThreadingHTTPServer:
    handler = type("BoundCalculatorRequestHandler", (CalculatorRequestHandler,), {})
    handler.application = application
    server = ThreadingHTTPServer((settings.host, settings.port), handler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="calculator-backend",
        description="Front-end/back-end separated calculator - JSON API server.",
    )
    parser.add_argument("--host", help="interface to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="TCP port to bind (default 8000)")
    parser.add_argument("--db", dest="db_path", help="path of the SQLite database file")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    if args.db_path:
        settings.db_path = args.db_path

    application = build_application(settings)
    try:
        server = create_server(settings, application)
    except OSError as error:
        print(f"Could not bind {settings.host}:{settings.port} - {error}", file=sys.stderr)
        return 1

    print(f"Calculator backend {settings.version} listening on "
          f"http://{settings.host}:{settings.port}")
    print(f"SQLite database: {application.database.path}")
    print("Routes:")
    for route in application.describe():
        print(f"  {route}")
    print("Press Ctrl+C to stop.")
    sys.stdout.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down ...")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
