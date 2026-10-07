"""Safe mathematical expression parsing and evaluation.

Design notes
------------
``eval``/``exec``/``compile`` are never used: user input is never turned into
program code.  The pipeline is purely data driven:

1. :func:`normalize_expression` maps the symbols a calculator UI shows
   (``×``, ``÷``, ``−``, full width parentheses, ``π`` ...) onto ASCII.
2. :func:`tokenize` scans the text into a flat list of :class:`Token` objects.
3. :class:`Parser` builds an abstract syntax tree with a recursive-descent
   parser, which is what gives operator precedence, parentheses and unary
   signs their mathematical meaning.
4. :func:`evaluate_node` walks the tree and performs the arithmetic, checking
   every single operation against the configured guard rails.

Supported grammar (EBNF)::

    expression := term (('+' | '-') term)*
    term       := unary (('*' | '/' | '%') unary)*
    unary      := ('+' | '-') unary | power
    power      := postfix ('^' unary)?              # right associative
    postfix    := primary ('!')*
    primary    := NUMBER
                | NAME                          # constant, e.g. pi
                | NAME '(' expression (',' expression)* ')'
                | '(' expression ')'

Because only the functions in :data:`FUNCTIONS` and the constants in
:data:`CONSTANTS` are reachable, the worst a malicious expression can do is
raise a validation error.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple

from .config import Settings
from .errors import (
    DivisionByZeroError,
    ExpressionSyntaxError,
    MathDomainError,
    RangeLimitError,
)

# ---------------------------------------------------------------------------
# Token kinds
# ---------------------------------------------------------------------------
NUMBER = "NUMBER"
NAME = "NAME"
OPERATOR = "OPERATOR"
LPAREN = "LPAREN"
RPAREN = "RPAREN"
COMMA = "COMMA"
EOF = "EOF"

# Characters a user may legitimately type, mapped onto the ASCII the parser
# understands.  This is the only place that knows about "pretty" symbols.
_NORMALIZATION: Sequence[Tuple[str, str]] = (
    ("×", "*"),
    ("✕", "*"),
    ("✖", "*"),
    ("∗", "*"),
    ("＊", "*"),
    ("÷", "/"),
    ("／", "/"),
    ("−", "-"),
    ("–", "-"),
    ("—", "-"),
    ("－", "-"),
    ("＋", "+"),
    ("％", "%"),
    ("＾", "^"),
    ("（", "("),
    ("）", ")"),
    ("，", ","),
    ("。", "."),
    ("π", "pi"),
    ("Π", "pi"),
    ("**", "^"),
    ("\u00a0", " "),  # non breaking space: pasted from web pages
)

_NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_OPERATOR_CHARS = set("+-*/%^!")
_SIMPLE_TOKENS = {"(": LPAREN, ")": RPAREN, ",": COMMA}

# ---------------------------------------------------------------------------
# Abstract syntax tree
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    """One lexical unit of an expression."""

    kind: str
    text: str
    position: int
    value: float | int | None = None


@dataclass(frozen=True)
class NumberNode:
    value: float | int
    text: str


@dataclass(frozen=True)
class ConstantNode:
    name: str
    value: float


@dataclass(frozen=True)
class UnaryNode:
    operator: str
    operand: "Node"


@dataclass(frozen=True)
class BinaryNode:
    operator: str
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class CallNode:
    name: str
    arguments: Tuple["Node", ...]
    position: int


Node = NumberNode | ConstantNode | UnaryNode | BinaryNode | CallNode


@dataclass(frozen=True)
class CalculationResult:
    """Outcome of one successful calculation."""

    value: int | float
    expression: str  # normalised expression that was actually evaluated
    result_text: str  # canonical text form, safe for very large integers


# ---------------------------------------------------------------------------
# Normalisation and tokenizing
# ---------------------------------------------------------------------------


def normalize_expression(text: str) -> str:
    """Translate display symbols into parser input and collapse whitespace."""
    normalized = text
    for source, target in _NORMALIZATION:
        normalized = normalized.replace(source, target)
    # Runs of whitespace carry no meaning in this grammar, so collapse them.
    return re.sub(r"\s+", " ", normalized).strip()


def tokenize(text: str, settings: Settings | None = None) -> List[Token]:
    """Split *text* into tokens, raising :class:`ExpressionSyntaxError` on junk."""
    settings = settings or Settings()
    tokens: List[Token] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char.isspace():
            index += 1
            continue

        if char in _SIMPLE_TOKENS:
            tokens.append(Token(_SIMPLE_TOKENS[char], char, index))
            index += 1
        elif char in _OPERATOR_CHARS:
            tokens.append(Token(OPERATOR, char, index))
            index += 1
        else:
            number_match = _NUMBER_RE.match(text, index)
            name_match = _NAME_RE.match(text, index)
            if number_match:
                raw = number_match.group(0)
                tokens.append(Token(NUMBER, raw, index, _parse_number(raw, index)))
                index = number_match.end()
            elif name_match:
                raw = name_match.group(0)
                tokens.append(Token(NAME, raw, index))
                index = name_match.end()
            else:
                raise ExpressionSyntaxError(
                    f"Unexpected character '{char}' at position {index + 1}",
                    position=index + 1,
                    character=char,
                )

        if len(tokens) > settings.max_tokens:
            raise RangeLimitError("The expression is too complex")

    tokens.append(Token(EOF, "", length))
    return tokens


def _parse_number(raw: str, position: int) -> float | int:
    """Convert a numeric literal, preferring exact integers when possible."""
    try:
        if re.fullmatch(r"\d+", raw):
            return int(raw)
        return float(raw)
    except ValueError as exc:  # pragma: no cover - the regex already guarantees this
        raise ExpressionSyntaxError(
            f"Invalid number '{raw}' at position {position + 1}", position=position + 1
        ) from exc


# ---------------------------------------------------------------------------
# Constants and functions reachable from an expression
# ---------------------------------------------------------------------------
CONSTANTS: Dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

Number = float | int
BuiltinFunction = Callable[[Sequence[Number], Settings], Number]


def _require_arity(name: str, arguments: Sequence[Number], minimum: int, maximum: int) -> None:
    """Reject a call whose argument count is outside ``[minimum, maximum]``."""
    if not minimum <= len(arguments) <= maximum:
        expected = str(minimum) if minimum == maximum else f"{minimum} to {maximum}"
        raise ExpressionSyntaxError(
            f"Function '{name}' expects {expected} argument(s) but got {len(arguments)}"
        )


def _fn_sqrt(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("sqrt", args, 1, 1)
    if args[0] < 0:
        raise MathDomainError("sqrt() is only defined for values >= 0")
    return math.sqrt(args[0])


def _fn_abs(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("abs", args, 1, 1)
    return abs(args[0])


def _fn_sin(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("sin", args, 1, 1)
    return math.sin(args[0])


def _fn_cos(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("cos", args, 1, 1)
    return math.cos(args[0])


def _fn_tan(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("tan", args, 1, 1)
    return math.tan(args[0])


def _fn_asin(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("asin", args, 1, 1)
    if not -1 <= args[0] <= 1:
        raise MathDomainError("asin() is only defined for -1 <= x <= 1")
    return math.asin(args[0])


def _fn_acos(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("acos", args, 1, 1)
    if not -1 <= args[0] <= 1:
        raise MathDomainError("acos() is only defined for -1 <= x <= 1")
    return math.acos(args[0])


def _fn_atan(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("atan", args, 1, 1)
    return math.atan(args[0])


def _fn_log(args: Sequence[Number], settings: Settings) -> Number:
    """``log(x)`` is base 10, ``log(x, b)`` uses an explicit base."""
    _require_arity("log", args, 1, 2)
    if args[0] <= 0:
        raise MathDomainError("log() is only defined for values > 0")
    if len(args) == 1:
        return math.log10(args[0])
    if args[1] <= 0 or args[1] == 1:
        raise MathDomainError("log() needs a positive base different from 1")
    return math.log(args[0], args[1])


def _fn_ln(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("ln", args, 1, 1)
    if args[0] <= 0:
        raise MathDomainError("ln() is only defined for values > 0")
    return math.log(args[0])


def _fn_log2(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("log2", args, 1, 1)
    if args[0] <= 0:
        raise MathDomainError("log2() is only defined for values > 0")
    return math.log2(args[0])


def _fn_exp(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("exp", args, 1, 1)
    try:
        return math.exp(args[0])
    except OverflowError as exc:
        raise RangeLimitError("The result is too large to compute") from exc


def _fn_floor(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("floor", args, 1, 1)
    return math.floor(args[0])


def _fn_ceil(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("ceil", args, 1, 1)
    return math.ceil(args[0])


def _fn_round(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("round", args, 1, 2)
    digits = int(args[1]) if len(args) == 2 else 0
    if not -15 <= digits <= 15:
        raise RangeLimitError("round() supports 0 to 15 decimal digits")
    return round(args[0], digits)


def _fn_min(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("min", args, 1, 16)
    return min(args)


def _fn_max(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("max", args, 1, 16)
    return max(args)


def _fn_pow(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("pow", args, 2, 2)
    return _power(args[0], args[1], settings)


def _fn_fact(args: Sequence[Number], settings: Settings) -> Number:
    _require_arity("fact", args, 1, 1)
    value = args[0]
    if float(value) != int(value) or value < 0:
        raise MathDomainError("fact() needs a non-negative integer")
    if value > settings.max_factorial_argument:
        raise RangeLimitError(
            f"fact() supports arguments up to {settings.max_factorial_argument}"
        )
    return math.factorial(int(value))


FUNCTIONS: Dict[str, BuiltinFunction] = {
    "sqrt": _fn_sqrt,
    "abs": _fn_abs,
    "sin": _fn_sin,
    "cos": _fn_cos,
    "tan": _fn_tan,
    "asin": _fn_asin,
    "acos": _fn_acos,
    "atan": _fn_atan,
    "ln": _fn_ln,
    "log": _fn_log,
    "log2": _fn_log2,
    "exp": _fn_exp,
    "floor": _fn_floor,
    "ceil": _fn_ceil,
    "round": _fn_round,
    "min": _fn_min,
    "max": _fn_max,
    "pow": _fn_pow,
    "fact": _fn_fact,
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
class Parser:
    """Recursive-descent parser turning a token list into an AST."""

    def __init__(self, tokens: Sequence[Token], settings: Settings) -> None:
        self._tokens = tokens
        self._index = 0
        self._settings = settings
        self._depth = 0

    # -- helpers ------------------------------------------------------------
    @property
    def _current(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        if token.kind != EOF:
            self._index += 1
        return token

    def _accept(self, kind: str, text: str | None = None) -> Token | None:
        token = self._current
        if token.kind == kind and (text is None or token.text == text):
            return self._advance()
        return None

    def _expect(self, kind: str, text: str | None = None) -> Token:
        token = self._accept(kind, text)
        if token is None:
            raise self._unexpected(f"'{text}'" if text else kind.lower())
        return token

    def _unexpected(self, expected: str) -> ExpressionSyntaxError:
        token = self._current
        if token.kind == EOF:
            found = "the end of the expression"
            position = token.position + 1
        else:
            found = f"'{token.text}'"
            position = token.position + 1
        return ExpressionSyntaxError(
            f"Expected {expected} but found {found} at position {position}",
            position=position,
        )

    def _enter(self) -> None:
        self._depth += 1
        if self._depth > self._settings.max_parse_depth:
            raise RangeLimitError("The expression is nested too deeply")

    def _leave(self) -> None:
        self._depth -= 1

    # -- grammar ------------------------------------------------------------
    def parse(self) -> Node:
        node = self._expression()
        if self._current.kind != EOF:
            raise self._unexpected("the end of the expression")
        return node

    def _expression(self) -> Node:
        self._enter()
        try:
            node = self._term()
            while self._current.kind == OPERATOR and self._current.text in "+-":
                operator = self._advance().text
                node = BinaryNode(operator, node, self._term())
            return node
        finally:
            self._leave()

    def _term(self) -> Node:
        node = self._unary()
        while self._current.kind == OPERATOR and self._current.text in "*/%":
            operator = self._advance().text
            node = BinaryNode(operator, node, self._unary())
        return node

    def _unary(self) -> Node:
        token = self._current
        if token.kind == OPERATOR and token.text in "+-":
            self._advance()
            operand = self._unary()
            return UnaryNode(token.text, operand)
        return self._power()

    def _power(self) -> Node:
        base = self._postfix()
        if self._current.kind == OPERATOR and self._current.text == "^":
            self._advance()
            # Right associative and routed through _unary, so 2^-3 works.
            return BinaryNode("^", base, self._unary())
        return base

    def _postfix(self) -> Node:
        node = self._primary()
        while self._current.kind == OPERATOR and self._current.text == "!":
            position = self._advance().position
            node = CallNode("fact", (node,), position)
        return node

    def _primary(self) -> Node:
        token = self._current

        if token.kind == NUMBER:
            self._advance()
            return NumberNode(token.value, token.text)  # type: ignore[arg-type]

        if token.kind == NAME:
            self._advance()
            name = token.text.lower()
            if self._accept(LPAREN):
                arguments: List[Node] = []
                if not self._accept(RPAREN):
                    arguments.append(self._expression())
                    while self._accept(COMMA):
                        arguments.append(self._expression())
                    self._expect(RPAREN, ")")
                if name not in FUNCTIONS:
                    raise ExpressionSyntaxError(
                        f"Unknown function '{token.text}'", position=token.position + 1
                    )
                _require_arity(name, arguments, *_ARITY.get(name, (1, 1)))
                return CallNode(name, tuple(arguments), token.position)
            if name in CONSTANTS:
                return ConstantNode(name, CONSTANTS[name])
            if name in FUNCTIONS:
                raise ExpressionSyntaxError(
                    f"Function '{token.text}' needs parentheses, e.g. {name}(2)",
                    position=token.position + 1,
                )
            raise ExpressionSyntaxError(
                f"Unknown name '{token.text}'", position=token.position + 1
            )

        if token.kind == LPAREN:
            self._advance()
            node = self._expression()
            self._expect(RPAREN, ")")
            return node

        raise self._unexpected("a number, a function or '('")


_ARITY: Dict[str, Tuple[int, int]] = {
    "sqrt": (1, 1),
    "abs": (1, 1),
    "sin": (1, 1),
    "cos": (1, 1),
    "tan": (1, 1),
    "asin": (1, 1),
    "acos": (1, 1),
    "atan": (1, 1),
    "ln": (1, 1),
    "log": (1, 2),
    "log2": (1, 1),
    "exp": (1, 1),
    "floor": (1, 1),
    "ceil": (1, 1),
    "round": (1, 2),
    "min": (1, 16),
    "max": (1, 16),
    "pow": (2, 2),
    "fact": (1, 1),
}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _guard(value: Number, settings: Settings) -> Number:
    """Reject infinities, NaN and results beyond the supported range."""
    if isinstance(value, complex):
        # Python returns a complex number for e.g. (-8) ** 0.5; a calculator
        # that only speaks real numbers must refuse it instead of leaking it.
        raise MathDomainError("A negative number cannot be raised to a fractional power")
    if isinstance(value, float):
        if math.isnan(value):
            raise MathDomainError("The expression has no real result")
        if math.isinf(value) or abs(value) > settings.max_abs_result:
            raise RangeLimitError("The result is too large to compute")
        return value
    if isinstance(value, int) and value.bit_length() > settings.max_integer_bits:
        raise RangeLimitError("The result is too large to compute")
    return value


def _power(base: Number, exponent: Number, settings: Settings) -> Number:
    """Exponentiation with an exact integer fast path and overflow guards."""
    if isinstance(base, int) and isinstance(exponent, int) and exponent >= 0:
        if exponent > settings.max_integer_exponent:
            raise RangeLimitError("The exponent is too large")
        return _guard(base**exponent, settings)
    try:
        return _guard(float(base) ** float(exponent), settings)
    except OverflowError as exc:
        raise RangeLimitError("The result is too large to compute") from exc
    except ZeroDivisionError as exc:
        raise DivisionByZeroError("Zero cannot be raised to a negative power") from exc
    except ValueError as exc:
        raise MathDomainError(
            "A negative number cannot be raised to a fractional power"
        ) from exc


def _apply_binary(operator: str, left: Number, right: Number, settings: Settings) -> Number:
    if operator == "+":
        return _guard(left + right, settings)
    if operator == "-":
        return _guard(left - right, settings)
    if operator == "*":
        return _guard(left * right, settings)
    if operator == "/":
        if right == 0:
            raise DivisionByZeroError("Cannot divide by zero")
        return _guard(left / right, settings)
    if operator == "%":
        if right == 0:
            raise DivisionByZeroError("Cannot take a remainder modulo zero")
        if isinstance(left, int) and isinstance(right, int):
            return _guard(left % right, settings)
        return _guard(math.fmod(left, right), settings)
    if operator == "^":
        return _power(left, right, settings)
    raise ExpressionSyntaxError(f"Unsupported operator '{operator}'")  # pragma: no cover


def evaluate_node(node: Node, settings: Settings, depth: int = 0) -> Number:
    """Evaluate an AST node, guarding every arithmetic operation."""
    if depth > settings.max_parse_depth:
        raise RangeLimitError("The expression is nested too deeply")

    if isinstance(node, NumberNode):
        return node.value

    if isinstance(node, ConstantNode):
        return node.value

    if isinstance(node, UnaryNode):
        operand = evaluate_node(node.operand, settings, depth + 1)
        return operand if node.operator == "+" else -operand

    if isinstance(node, CallNode):
        arguments = [evaluate_node(argument, settings, depth + 1) for argument in node.arguments]
        function = FUNCTIONS.get(node.name)
        if function is None:  # pragma: no cover - the parser already rejected it
            raise ExpressionSyntaxError(f"Unknown function '{node.name}'")
        return _guard(function(arguments, settings), settings)

    if isinstance(node, BinaryNode):
        left = evaluate_node(node.left, settings, depth + 1)
        right = evaluate_node(node.right, settings, depth + 1)
        return _apply_binary(node.operator, left, right, settings)

    raise RangeLimitError("Unsupported expression node")  # pragma: no cover


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def format_number(value: Number) -> str:
    """Return the canonical text form of a numeric result.

    Floats are rounded to 12 decimals so that ``0.1 + 0.2`` prints as ``0.3``
    instead of ``0.30000000000000004``, while integers keep every digit - which
    matters for values beyond JavaScript's safe integer range.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if value == 0:
        return "0"
    number = float(value)
    if number.is_integer() and abs(number) < 1e16:
        return str(int(number))
    rounded = round(number, 12)
    if rounded == 0:
        return repr(number)
    return f"{rounded:.12f}".rstrip("0").rstrip(".") or "0"


def evaluate(expression: str, settings: Settings | None = None) -> CalculationResult:
    """Parse and evaluate *expression*.

    Raises a subclass of :class:`~src.errors.CalculatorError` when the input is
    rejected.
    """
    settings = settings or Settings()
    normalized = normalize_expression(expression)
    if normalized == "":
        raise ExpressionSyntaxError("The expression is empty")
    if len(normalized) > settings.max_expression_length:
        raise RangeLimitError(
            f"The expression may contain at most {settings.max_expression_length} characters"
        )

    tokens = tokenize(normalized, settings)
    tree = Parser(tokens, settings).parse()
    value = evaluate_node(tree, settings)
    return CalculationResult(
        value=value, expression=normalized, result_text=format_number(value)
    )


_BASE_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def convert_base(value_text: str, from_base: int, to_base: int) -> str:
    """Convert an integer between bases 2 and 36.

    Digits are validated one by one so the error message can point at the
    offending character instead of failing with a generic parse error.
    """
    text = normalize_expression(value_text).lower().replace(" ", "")
    if not text:
        raise ExpressionSyntaxError("The value to convert is empty")
    if not 2 <= from_base <= 36 or not 2 <= to_base <= 36:
        raise RangeLimitError("Only bases between 2 and 36 are supported")

    negative = text.startswith("-")
    if negative or text.startswith("+"):
        text = text[1:]

    for prefix, base in (("0x", 16), ("0b", 2), ("0o", 8)):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            from_base = base
            break
    if not text:
        raise ExpressionSyntaxError("The value to convert is empty")

    allowed = set(_BASE_DIGITS[:from_base])
    for character in text:
        if character == ".":
            raise ExpressionSyntaxError("Only integers can be converted between bases")
        if character not in allowed:
            raise ExpressionSyntaxError(f"'{character}' is not a valid digit in base {from_base}")

    number = int(text, from_base)
    if number.bit_length() > 512:
        raise RangeLimitError("The value is too large to convert")

    if to_base == 10:
        converted = str(number)
    else:
        digits: List[str] = []
        while number:
            number, remainder = divmod(number, to_base)
            digits.append(_BASE_DIGITS[remainder])
        converted = "".join(reversed(digits)) or "0"
    return f"-{converted}" if negative and converted != "0" else converted


def describe_functions() -> List[dict]:
    """Return metadata about the supported functions (for the front end)."""
    return [
        {"name": name, "min_args": _ARITY[name][0], "max_args": _ARITY[name][1]}
        for name in sorted(FUNCTIONS)
    ]


def describe_constants() -> List[dict]:
    """Return the supported constants and their values."""
    return [
        {"name": name, "value": value, "display": format_number(value)}
        for name, value in sorted(CONSTANTS.items())
    ]


def describe_operators(expression: str) -> List[str]:
    """Return the operators used in *expression* (used by the statistics API)."""
    normalized = normalize_expression(expression)
    return [operator for operator in ("+", "-", "*", "/", "%", "^", "!") if operator in normalized]
