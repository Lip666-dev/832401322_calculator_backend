"""A very small regex based router.

Chosen over a web framework because the whole point of the assignment is to
show the front-end/back-end separation, and this keeps the request path fully
visible: method + path pattern -> one controller method.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Tuple

from ..errors import MethodNotAllowedError, NotFoundError

Handler = Callable[[object], Tuple[int, dict]]


@dataclass(frozen=True)
class Route:
    method: str
    pattern: re.Pattern
    handler: Handler


@dataclass(frozen=True)
class ResolvedRoute:
    handler: Handler
    method: str
    params: Mapping[str, str]


class Router:
    """Match ``METHOD /path`` onto a handler."""

    def __init__(self) -> None:
        self._routes: List[Route] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        self._routes.append(Route(method.upper(), re.compile(pattern), handler))

    def resolve(self, method: str, path: str) -> ResolvedRoute:
        """Return the handler for *method* + *path*.

        Raises :class:`NotFoundError` when the path is unknown and
        :class:`MethodNotAllowedError` when the path exists for other methods.
        """
        method = method.upper()
        allowed: Dict[str, bool] = {}

        for route in self._routes:
            match = route.pattern.match(path)
            if match is None:
                continue
            allowed[route.method] = True
            if route.method == method:
                return ResolvedRoute(
                    handler=route.handler,
                    method=route.method,
                    params={key: value for key, value in match.groupdict().items()},
                )

        if allowed:
            raise MethodNotAllowedError(
                f"Method {method} is not supported for {path}",
                allowed=sorted(allowed),
            )
        raise NotFoundError(f"No route matches {method} {path}", path=path)
