"""A transport independent view of one HTTP request."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RequestContext:
    """Everything a route handler is allowed to look at."""

    method: str
    path: str
    query: Mapping[str, str] = field(default_factory=dict)
    params: Mapping[str, str] = field(default_factory=dict)
    body: Any = None
    headers: Mapping[str, str] = field(default_factory=dict)

    def query_value(self, name: str, default: str | None = None) -> str | None:
        """Return a query string parameter, treating blanks as absent."""
        value = self.query.get(name)
        if value is None or str(value).strip() == "":
            return default
        return str(value).strip()
