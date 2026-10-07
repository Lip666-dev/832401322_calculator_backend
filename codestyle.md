# Backend Code Standard

## Source of this standard

This document is derived from the following mainstream, publicly maintained
standards, in this order of precedence:

1. **PEP 8 — Style Guide for Python Code** (https://peps.python.org/pep-0008/)
   — the official Python style guide; governs layout, naming, imports,
   whitespace and comments.
2. **PEP 257 — Docstring Conventions** (https://peps.python.org/pep-0257/)
   — governs module, class and function documentation.
3. **Google Python Style Guide** (https://google.github.io/styleguide/pyguide.html)
   — used where PEP 8 leaves a choice: docstring sections, exception design,
   type-annotation usage and the "one obvious place for SQL" rule.

Where this document and PEP 8 disagree, PEP 8 wins and the deviation is noted
explicitly below.

## 1. Layout

| Rule | Value in this project |
| --- | --- |
| Encoding | UTF-8, no BOM |
| Indentation | 4 spaces, never tabs |
| Line length | 100 characters (PEP 8 allows a team-agreed limit above 79) |
| File ending | exactly one trailing newline |
| Blank lines | 2 between top-level definitions, 1 between methods |
| Trailing whitespace | not allowed |

## 2. Naming

| Element | Convention | Example |
| --- | --- | --- |
| Module / package | `lower_snake_case` | `history_repository.py` |
| Class | `PascalCase` | `CalculatorService`, `CalculationRecord` |
| Function / method | `lower_snake_case`, verb first | `calculate`, `list_history` |
| Constant | `UPPER_SNAKE_CASE` | `MAX_PAGE_SIZE`, `SCHEMA_VERSION` |
| Private member | single leading underscore | `self._repository` |
| Type alias | `PascalCase` | `Node`, `Handler` |

Module level code is limited to constants, imports, class/function definitions
and the `if __name__ == "__main__":` guard.

## 3. Imports

* Absolute imports only (`from src.model.database import Database`), grouped as
  standard library → third party → local, separated by one blank line.
* One import per line; `from x import (a, b, c)` is allowed when the list is long.
* Wildcard imports (`from x import *`) are forbidden.
* Unused imports must not be committed.

## 4. Docstrings and comments

* Every module starts with a docstring that states its responsibility.
* Every public class and function has a docstring. The first line is a single
  imperative sentence ending with a period.
* Docstrings use Google-style sections only when they add information
  (`Raises:` for error behaviour, `Usage::` for entry points).
* Comments explain **why**, not what. Chinese comments are avoided so that the
  repository stays consistent; the assignment blog carries the explanation in
  the language of the course.
* No commented-out code is committed, and no `TODO` without an owner.

## 5. Type annotations

* All public function signatures are annotated, including `-> None`.
* `from __future__ import annotations` is used so newer syntax is available on
  older interpreters.
* `Any` is avoided in favour of precise types or small dataclasses such as
  `RequestContext`.

## 6. Classes, functions and cohesion

* One responsibility per module: `src.calculator` knows nothing about HTTP or
  SQL; `src.model` knows nothing about HTTP; only `src.controller` speaks HTTP.
* Methods are short (target ≤ 40 lines) and at one level of abstraction.
* Mutable default arguments are forbidden (`def f(items: list = [])`).
* Dependency injection through `__init__` (repository, settings, clock) instead
  of module level globals, so every class is testable in isolation.

## 7. Error handling

* Domain failures are raised as `CalculatorError` subclasses defined in
  `src/errors.py`; each one carries `code`, `http_status` and `message`.
* Never raise bare `Exception`; never swallow an exception with a bare
  `except:` — catch the narrowest type, and re-raise with context where useful.
* The HTTP layer is the only place that converts an exception into a status code.
* `eval`, `exec`, `compile` and `pickle` on user input are forbidden by design,
  and a unit test asserts their absence from `src/calculator.py`.

## 8. SQL

* All SQL lives in `src/model/history_repository.py` and `src/model/database.py`.
* Every statement uses parameter binding (`?`), never string formatting.
* `LIKE` patterns escape `%`, `_` and `\` before binding.
* Schema changes are additive and reflected in `SCHEMA_VERSION`.

## 9. Testing

* `unittest` from the standard library, one module per layer:
  `test_calculator.py`, `test_repository.py`, `test_api.py`.
* Test names describe the behaviour (`test_division_by_zero_is_reported`).
* Every error branch and every endpoint has at least one test.
* Tests use temporary databases and an ephemeral port, so they never touch
  developer data and can run in parallel.
* A test suite must pass before a commit is pushed:
  `python -m unittest discover -v`.

## 10. Commits

* Commit messages follow `type(scope): summary`, for example
  `feat(calculator): support unary minus and factorials`,
  `fix(api): return 405 with an Allow header`.
* One logical change per commit; no mixed formatting/feature commits.

## 11. Deviations from PEP 8 in this repository

| Deviation | Reason |
| --- | --- |
| 100 character lines (PEP 8 default 79) | PEP 8 explicitly permits a team-agreed higher limit; 100 keeps f-string SQL and docstring tables readable. |
| `do_GET`-style camelCase method names in `src/server.py` | Required by `http.server.BaseHTTPRequestHandler`; annotated with `# noqa: N802`. |
| Nested `lambda` usage in tests | Avoided in `src/`; tests prefer small named helpers. |
