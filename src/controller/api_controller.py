"""API controller: validates the request, calls a service, builds the response.

Controllers are HTTP agnostic on purpose - they receive a
:class:`~src.controller.request_context.RequestContext` and return a
``(status_code, payload)`` tuple.  The HTTP server in :mod:`src.server` is then
a thin adapter, which makes every endpoint testable without a socket.
"""

from __future__ import annotations

from datetime import datetime
from typing import Tuple

from ..calculator import convert_base, describe_constants, describe_functions
from ..config import Settings
from ..errors import NotFoundError
from ..model.database import Database
from ..service.calculator_service import CalculatorService
from ..service.history_service import HistoryService
from ..service.statistics_service import StatisticsService
from ..validation import (
    require_bool,
    require_expression,
    require_int,
    require_json_object,
    require_value_text,
    parse_record_id,
)
from .request_context import RequestContext

Response = Tuple[int, dict]


class ApiController:
    """One method per endpoint."""

    def __init__(
        self,
        calculator_service: CalculatorService,
        history_service: HistoryService,
        statistics_service: StatisticsService,
        database: Database,
        settings: Settings,
    ) -> None:
        self._calculator_service = calculator_service
        self._history_service = history_service
        self._statistics_service = statistics_service
        self._database = database
        self._settings = settings

    # -- meta ---------------------------------------------------------------
    def health(self, context: RequestContext) -> Response:
        return 200, {
            "success": True,
            "service": "calculator-backend",
            "version": self._settings.version,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "database": self._database.health(),
        }

    def describe_calculator(self, context: RequestContext) -> Response:
        """Advertise the supported functions, constants and limits."""
        return 200, {
            "success": True,
            "functions": describe_functions(),
            "constants": describe_constants(),
            "operators": list(self._settings.operator_names.keys()),
            "limits": {
                "max_expression_length": self._settings.max_expression_length,
                "max_page_size": self._settings.max_page_size,
                "default_page_size": self._settings.default_page_size,
            },
        }

    # -- calculation --------------------------------------------------------
    def calculate(self, context: RequestContext) -> Response:
        payload = require_json_object(context.body)
        expression = require_expression(payload, self._settings)
        outcome = self._calculator_service.calculate(expression)
        return 200, {"success": True, **outcome}

    def convert_base(self, context: RequestContext) -> Response:
        payload = require_json_object(context.body)
        value = require_value_text(payload)
        from_base = require_int(payload, "from_base", 2, 36, default=10)
        to_base = require_int(payload, "to_base", 2, 36, default=2)
        converted = convert_base(value, from_base, to_base)
        return 200, {
            "success": True,
            "value": value,
            "from_base": from_base,
            "to_base": to_base,
            "result": converted,
        }

    # -- history ------------------------------------------------------------
    def list_history(self, context: RequestContext) -> Response:
        page = require_int(
            {"page": context.query_value("page")}, "page", 1, 1_000_000, default=1
        )
        page_size = require_int(
            {"page_size": context.query_value("page_size")},
            "page_size",
            1,
            self._settings.max_page_size,
            default=self._settings.default_page_size,
        )
        favorites_only = require_bool(
            {"favorites": context.query_value("favorites")}, "favorites", default=False
        )
        result = self._history_service.list_history(
            keyword=context.query_value("keyword"),
            favorites_only=favorites_only,
            page=page,
            page_size=page_size,
        )
        return 200, {"success": True, **result}

    def get_history(self, context: RequestContext) -> Response:
        record_id = parse_record_id(context.params["id"])
        return 200, {"success": True, "item": self._history_service.get_record(record_id)}

    def delete_history(self, context: RequestContext) -> Response:
        record_id = parse_record_id(context.params["id"])
        outcome = self._history_service.delete_record(record_id)
        return 200, {"success": True, **outcome}

    def clear_history(self, context: RequestContext) -> Response:
        outcome = self._history_service.clear_history()
        return 200, {"success": True, **outcome}

    def set_favorite(self, context: RequestContext) -> Response:
        record_id = parse_record_id(context.params["id"])
        payload = require_json_object(context.body)
        is_favorite = require_bool(payload, "is_favorite", default=True)
        outcome = self._history_service.set_favorite(record_id, is_favorite)
        return 200, {"success": True, **outcome}

    # -- statistics ---------------------------------------------------------
    def statistics(self, context: RequestContext) -> Response:
        return 200, {"success": True, "statistics": self._statistics_service.summarize()}
