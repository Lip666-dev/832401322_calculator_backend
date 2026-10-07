"""Unit tests for the expression parser and evaluator.

Run from the repository root::

    python -m unittest discover -v
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from src import calculator
from src.calculator import (
    CalculationResult,
    convert_base,
    evaluate,
    format_number,
    normalize_expression,
    tokenize,
)
from src.errors import (
    DivisionByZeroError,
    ExpressionSyntaxError,
    MathDomainError,
    RangeLimitError,
)


def value_of(expression: str):
    """Evaluate *expression* and return its numeric value."""
    return evaluate(expression).value


def text_of(expression: str) -> str:
    """Evaluate *expression* and return its canonical text form."""
    return evaluate(expression).result_text


class BasicCalculationTest(unittest.TestCase):
    """Function 1 of the assignment: the four basic operations."""

    def test_addition(self) -> None:
        self.assertEqual(value_of("12+8"), 20)

    def test_subtraction(self) -> None:
        self.assertEqual(value_of("9-21"), -12)

    def test_multiplication(self) -> None:
        self.assertEqual(value_of("6*7"), 42)

    def test_division(self) -> None:
        self.assertEqual(text_of("84/4"), "21")

    def test_division_keeps_decimals(self) -> None:
        self.assertEqual(text_of("7/2"), "3.5")

    def test_integer_result_of_division_is_not_a_float_string(self) -> None:
        self.assertEqual(text_of("10/2"), "5")


class CompoundExpressionTest(unittest.TestCase):
    """Function 2 of the assignment: compound expressions."""

    def test_operator_precedence(self) -> None:
        self.assertEqual(value_of("1+2*3"), 7)
        self.assertEqual(value_of("8-3*2"), 2)
        self.assertEqual(value_of("10/2+7"), 12)
        self.assertEqual(value_of("2+3*4-6/3"), 12)

    def test_parentheses(self) -> None:
        self.assertEqual(value_of("(1+2)*3"), 9)
        self.assertEqual(value_of("((2+3)*(4-1))"), 15)

    def test_unary_plus_and_minus(self) -> None:
        self.assertEqual(value_of("-5+8"), 3)
        self.assertEqual(value_of("3*-2"), -6)
        self.assertEqual(value_of("--5"), 5)
        self.assertEqual(value_of("-+5"), -5)
        self.assertEqual(value_of("2^-3"), 0.125)

    def test_decimals(self) -> None:
        self.assertEqual(text_of("1.5*4"), "6")
        self.assertEqual(text_of("0.1+0.2"), "0.3")
        self.assertEqual(text_of(".5+.5"), "1")
        self.assertEqual(text_of("1e3+1"), "1001")

    def test_power_is_right_associative(self) -> None:
        self.assertEqual(value_of("2^3^2"), 512)

    def test_modulo(self) -> None:
        self.assertEqual(value_of("7%3"), 1)
        self.assertEqual(text_of("5.5%2"), "1.5")

    def test_factorial(self) -> None:
        self.assertEqual(value_of("5!"), 120)
        self.assertEqual(value_of("0!"), 1)
        self.assertEqual(value_of("fact(6)"), 720)

    def test_scientific_functions(self) -> None:
        self.assertEqual(text_of("sqrt(16)"), "4")
        self.assertEqual(text_of("abs(-3.5)"), "3.5")
        self.assertEqual(text_of("log(1000)"), "3")
        self.assertEqual(text_of("log(8,2)"), "3")
        self.assertEqual(text_of("ln(e)"), "1")
        self.assertEqual(text_of("floor(2.9)"), "2")
        self.assertEqual(text_of("ceil(2.1)"), "3")
        self.assertEqual(text_of("round(3.14159,2)"), "3.14")
        self.assertEqual(text_of("min(3,1,2)"), "1")
        self.assertEqual(text_of("max(3,1,2)"), "3")
        self.assertEqual(text_of("pow(2,10)"), "1024")
        self.assertAlmostEqual(value_of("sin(0)"), 0.0)

    def test_constants(self) -> None:
        self.assertEqual(text_of("pi"), "3.14159265359")
        self.assertEqual(text_of("e"), "2.718281828459")

    def test_large_integers_keep_full_precision(self) -> None:
        self.assertEqual(text_of("2^100"), "1267650600228229401496703205376")


class PrettySymbolTest(unittest.TestCase):
    """The UI shows ×, ÷ and full width symbols; the API accepts them too."""

    def test_multiplication_and_division_symbols(self) -> None:
        self.assertEqual(value_of("12×8"), 96)
        self.assertEqual(value_of("9÷3"), 3)

    def test_unicode_minus_and_parentheses(self) -> None:
        self.assertEqual(value_of("−5+8"), 3)
        self.assertEqual(value_of("（1+2）*3"), 9)

    def test_pi_symbol(self) -> None:
        self.assertEqual(value_of("π"), calculator.CONSTANTS["pi"])

    def test_power_alias(self) -> None:
        self.assertEqual(value_of("2**10"), 1024)

    def test_normalisation_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_expression("  1  +   2 × 3 "), "1 + 2 * 3")

    def test_tokenizer_returns_positions(self) -> None:
        tokens = tokenize("12+8")
        self.assertEqual([token.kind for token in tokens], ["NUMBER", "OPERATOR", "NUMBER", "EOF"])
        self.assertEqual([token.position for token in tokens], [0, 2, 3, 4])


class ErrorHandlingTest(unittest.TestCase):
    """Invalid input, division by zero and every other rejection path."""

    def assert_error(self, expression: str, error_type: type) -> None:
        with self.assertRaises(error_type):
            evaluate(expression)

    def test_division_by_zero(self) -> None:
        self.assert_error("5/0", DivisionByZeroError)
        self.assert_error("5/(3-3)", DivisionByZeroError)
        self.assert_error("5%0", DivisionByZeroError)
        self.assert_error("0^-1", DivisionByZeroError)

    def test_incomplete_expression(self) -> None:
        self.assert_error("1+", ExpressionSyntaxError)
        self.assert_error("*2", ExpressionSyntaxError)
        self.assert_error("(1+2", ExpressionSyntaxError)
        self.assert_error("1+2)", ExpressionSyntaxError)
        self.assert_error("()", ExpressionSyntaxError)

    def test_missing_operator_between_numbers(self) -> None:
        self.assert_error("1 2", ExpressionSyntaxError)

    def test_unknown_name_and_function(self) -> None:
        self.assert_error("foo", ExpressionSyntaxError)
        self.assert_error("foo(1)", ExpressionSyntaxError)
        self.assert_error("sqrt", ExpressionSyntaxError)

    def test_wrong_argument_count(self) -> None:
        self.assert_error("sqrt()", ExpressionSyntaxError)
        self.assert_error("sqrt(1,2)", ExpressionSyntaxError)
        self.assert_error("pow(2)", ExpressionSyntaxError)

    def test_unexpected_character(self) -> None:
        self.assert_error("1+@", ExpressionSyntaxError)
        self.assert_error("1 $ 2", ExpressionSyntaxError)

    def test_mathematically_undefined_input(self) -> None:
        self.assert_error("sqrt(-1)", MathDomainError)
        self.assert_error("ln(0)", MathDomainError)
        self.assert_error("log(-5)", MathDomainError)
        self.assert_error("asin(2)", MathDomainError)
        self.assert_error("(-8)^(1/3)", MathDomainError)
        self.assert_error("fact(2.5)", MathDomainError)
        self.assert_error("fact(-1)", MathDomainError)

    def test_guard_rails(self) -> None:
        self.assert_error("2^5000", RangeLimitError)
        self.assert_error("2^3000*2^3000", RangeLimitError)
        self.assert_error("fact(500)", RangeLimitError)
        # 601 characters, over the 200 character limit
        self.assert_error("1+" * 200 + "1", RangeLimitError)
        # 70 nested parentheses, deeper than the parser allows
        self.assert_error("(" * 70 + "1" + ")" * 70, RangeLimitError)

    def test_empty_expression(self) -> None:
        self.assert_error("", ExpressionSyntaxError)
        self.assert_error("   ", ExpressionSyntaxError)

    def test_error_messages_are_descriptive(self) -> None:
        with self.assertRaises(ExpressionSyntaxError) as context:
            evaluate("1+@")
        self.assertIn("position 3", str(context.exception))

        with self.assertRaises(DivisionByZeroError) as context:
            evaluate("1/0")
        self.assertEqual(context.exception.code, "DIVISION_BY_ZERO")


class NoArbitraryCodeExecutionTest(unittest.TestCase):
    """The assignment forbids eval/exec; this test proves the code base obeys.

    The check works on the abstract syntax tree instead of the raw text, so a
    legitimate ``re.compile(...)`` call is not mistaken for the builtin
    ``compile()``.
    """

    FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "system", "popen", "check_output"}

    def test_no_module_calls_an_arbitrary_code_execution_builtin(self) -> None:
        src_root = Path(calculator.__file__).resolve().parent
        modules = sorted(src_root.rglob("*.py"))
        self.assertGreaterEqual(len(modules), 10, "expected to scan the whole src package")

        offenders = []
        for module_path in modules:
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in self.FORBIDDEN_CALLS:
                        offenders.append(f"{module_path.name}:{node.lineno} {node.func.id}()")
                if isinstance(node, ast.Name) and node.id in {"eval", "exec", "__import__"}:
                    offenders.append(f"{module_path.name}:{node.lineno} references {node.id}")

        self.assertEqual(offenders, [], f"forbidden constructs found: {offenders}")

    def test_user_input_is_never_compiled_as_source(self) -> None:
        source = Path(calculator.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from builtins", source)
        self.assertNotIn("import builtins", source)


class FormatNumberTest(unittest.TestCase):
    """Canonical text output of numeric results."""

    def test_integers(self) -> None:
        self.assertEqual(format_number(20), "20")
        self.assertEqual(format_number(-7), "-7")

    def test_floats_that_are_integers(self) -> None:
        self.assertEqual(format_number(21.0), "21")

    def test_floating_point_noise_is_rounded(self) -> None:
        self.assertEqual(format_number(0.30000000000000004), "0.3")
        self.assertEqual(format_number(1 / 3), "0.333333333333")

    def test_zero_and_negative_zero(self) -> None:
        self.assertEqual(format_number(0), "0")
        self.assertEqual(format_number(-0.0), "0")


class ConvertBaseTest(unittest.TestCase):
    """Extended feature: number base conversion."""

    def test_decimal_to_binary_and_hex(self) -> None:
        self.assertEqual(convert_base("255", 10, 2), "11111111")
        self.assertEqual(convert_base("255", 10, 16), "ff")

    def test_binary_hex_octal_to_decimal(self) -> None:
        self.assertEqual(convert_base("1010", 2, 10), "10")
        self.assertEqual(convert_base("0xff", 16, 10), "255")
        self.assertEqual(convert_base("0o17", 8, 10), "15")

    def test_negative_values(self) -> None:
        self.assertEqual(convert_base("-10", 10, 2), "-1010")

    def test_base_36(self) -> None:
        self.assertEqual(convert_base("z", 36, 10), "35")
        self.assertEqual(convert_base("35", 10, 36), "z")

    def test_invalid_digit_and_base(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            convert_base("2", 2, 10)
        with self.assertRaises(ExpressionSyntaxError):
            convert_base("1.5", 10, 2)
        with self.assertRaises(RangeLimitError):
            convert_base("10", 10, 40)


class CalculationResultTest(unittest.TestCase):
    """The result object carries both the numeric and the textual form."""

    def test_result_exposes_both_forms(self) -> None:
        result = evaluate("12+8")
        self.assertIsInstance(result, CalculationResult)
        self.assertEqual(result.value, 20)
        self.assertEqual(result.result_text, "20")
        self.assertEqual(result.expression, "12+8")

    def test_normalised_expression_is_reported(self) -> None:
        self.assertEqual(evaluate("12×8").expression, "12*8")


if __name__ == "__main__":
    unittest.main()
