"""Application error types.

Every error carries:

* ``code``        - a stable, machine readable identifier the front end can switch on;
* ``http_status`` - the HTTP status code the API layer must answer with;
* ``message``     - a human readable description that is safe to show to the user.

Keeping the three concerns in one place means the HTTP layer never has to guess
how a business failure should be reported, and the front end never has to parse
free text to understand what went wrong.
"""

from __future__ import annotations


class CalculatorError(Exception):
    """Base class for every error the API is allowed to report to a client."""

    code = "INTERNAL_ERROR"
    http_status = 500
    default_message = "Internal server error"

    def __init__(self, message: str | None = None, **details: object) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)

    def to_payload(self) -> dict:
        """Return the JSON body describing this error."""
        payload: dict = {"success": False, "code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class ValidationError(CalculatorError):
    """The request itself is malformed (missing field, wrong type, out of range)."""

    code = "INVALID_REQUEST"
    http_status = 400
    default_message = "Invalid request"


class ExpressionSyntaxError(CalculatorError):
    """The expression cannot be parsed as a mathematical expression."""

    code = "INVALID_EXPRESSION"
    http_status = 400
    default_message = "Invalid expression"


class DivisionByZeroError(CalculatorError):
    """A division (or modulo) by zero was requested."""

    code = "DIVISION_BY_ZERO"
    http_status = 400
    default_message = "Division by zero is not allowed"


class MathDomainError(CalculatorError):
    """The expression is syntactically valid but mathematically undefined."""

    code = "MATH_DOMAIN_ERROR"
    http_status = 400
    default_message = "The expression is mathematically undefined"


class RangeLimitError(CalculatorError):
    """A guard rail was hit: result too large, factorial argument too big, ..."""

    code = "RESULT_OUT_OF_RANGE"
    http_status = 400
    default_message = "The result is out of the supported range"


class NotFoundError(CalculatorError):
    """The addressed resource does not exist."""

    code = "NOT_FOUND"
    http_status = 404
    default_message = "Resource not found"


class MethodNotAllowedError(CalculatorError):
    """The path exists but not for this HTTP method."""

    code = "METHOD_NOT_ALLOWED"
    http_status = 405
    default_message = "Method not allowed"


class PayloadTooLargeError(CalculatorError):
    """The request body exceeds the configured limit."""

    code = "PAYLOAD_TOO_LARGE"
    http_status = 413
    default_message = "Request body is too large"
