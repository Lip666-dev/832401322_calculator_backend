# Calculator Backend — Front-End/Back-End Separated Calculator System

Backend service of the *First Assignment* calculator project (student ID **832401322**).
It exposes a JSON API over HTTP, parses and evaluates mathematical expressions
safely, and persists every successful calculation in a SQLite database.

* **No third-party runtime dependency** — Python standard library only
  (`http.server`, `sqlite3`, `json`, `math`, `re`).
* **No `eval` / `exec`** — expressions are handled by a hand-written tokenizer
  and recursive-descent parser, so user input is never executed as code.
* **The front end never calculates** — it sends an expression and displays the
  result that this service returns.

| | |
|---|---|
| Front-end repository | `https://github.com/<your-account>/832401322_calculator_frontend` |
| Back-end repository | `https://github.com/<your-account>/832401322_calculator_backend` |
| Code standard | [codestyle.md](codestyle.md) |
| Assignment blog | `https://blog.csdn.net/<your-account>/article/<id>` |

---

## 1. Technology stack

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.10+ | Available everywhere, no build step |
| HTTP | `http.server.ThreadingHTTPServer` | Zero dependencies, fully visible request handling |
| Persistence | SQLite 3 (`sqlite3`) | File based, no server to install, ACID |
| Expression engine | custom tokenizer + recursive-descent parser | Required safety: no `eval`, full control over errors |
| Configuration | dataclass + environment variables + CLI flags | Simple and 12-factor friendly |

## 2. Directory structure

```text
832401322_calculator_backend/
├── src/
│   ├── controller/            # HTTP adapters
│   │   ├── api_controller.py  # one method per endpoint
│   │   ├── request_context.py # transport independent request object
│   │   └── router.py          # method + path -> handler
│   ├── service/               # use cases
│   │   ├── calculator_service.py
│   │   ├── history_service.py
│   │   └── statistics_service.py
│   ├── model/                 # persistence
│   │   ├── database.py        # connections + schema
│   │   ├── entities.py        # CalculationRecord
│   │   └── history_repository.py
│   ├── calculator.py          # tokenizer, parser, evaluator, base conversion
│   ├── validation.py          # request payload validation
│   ├── errors.py              # error types -> HTTP status codes
│   ├── config.py              # settings
│   └── server.py              # entry point: python -m src.server
├── tests/
│   ├── test_calculator.py     # parser, evaluator, error paths, guard rails
│   ├── test_repository.py     # SQLite behaviour
│   └── test_api.py            # end-to-end HTTP tests
├── data/                      # created at runtime, git-ignored
├── init_db.py                 # database initialisation helper
├── run.py                     # convenience launcher
├── requirements.txt           # empty on purpose (standard library only)
├── codestyle.md
└── README.md
```

## 3. Runtime environment

* Python **3.10 or newer** (`python --version`); the code uses `int | float`
  union types.
* Any operating system: Windows, Linux, macOS.
* About 1 MB of disk space plus the database file.

## 4. Installation

```bash
git clone https://github.com/<your-account>/832401322_calculator_backend.git
cd 832401322_calculator_backend

# optional but recommended
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate

pip install -r requirements.txt   # intentionally installs nothing
```

## 5. Database initialisation

The schema is created automatically the first time the service starts, so in the
normal case you can skip this step. To prepare or clean the database explicitly:

```bash
python init_db.py            # create data/calculator.db with its tables and indexes
python init_db.py --reset    # delete every stored calculation first
python init_db.py --db /tmp/other.db
```

Schema:

```sql
CREATE TABLE calculation_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    expression   TEXT    NOT NULL,          -- normalised expression, e.g. "(1+2)*3"
    result       TEXT    NOT NULL,          -- canonical result text, full precision
    result_value REAL,                      -- numeric mirror used for statistics
    is_favorite  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL           -- local time, 'YYYY-MM-DD HH:MM:SS'
);
CREATE INDEX idx_calculation_history_created_at ON calculation_history (created_at DESC, id DESC);
CREATE INDEX idx_calculation_history_expression ON calculation_history (expression);
```

## 6. Starting the service

```bash
python run.py                                   # http://127.0.0.1:8000
python run.py --host 0.0.0.0 --port 8080        # reachable from other machines
python -m src.server --db ./data/dev.db         # equivalent, module form
```

Startup output lists the bound address, the database file and every route.

### Configuration

| CLI flag | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `--host` | `CALC_HOST` | `127.0.0.1` | Interface to bind |
| `--port` | `CALC_PORT` | `8000` | TCP port |
| `--db` | `CALC_DB_PATH` | `data/calculator.db` | SQLite file |
| — | `CALC_CORS_ORIGIN` | `*` | `Access-Control-Allow-Origin` value |

Guard rails (also in `src/config.py`): expression length ≤ 200 characters,
≤ 256 tokens, nesting depth ≤ 64, `fact()` argument ≤ 170, result magnitude
≤ 1e308, request body ≤ 64 KiB.

## 7. API

All responses are JSON. `success` is always present; failures additionally carry
a stable `code` and a user-facing `message`.

| Method | Path | Purpose | Success |
| --- | --- | --- | --- |
| `GET` | `/api/health` | Liveness + database status | `200` |
| `GET` | `/api/calculator` | Supported functions, constants, limits | `200` |
| `POST` | `/api/calculate` | Calculate an expression and store it | `200` |
| `POST` | `/api/convert/base` | Number base conversion (extended) | `200` |
| `GET` | `/api/history` | Paged history (`page`, `page_size`, `keyword`, `favorites`) | `200` |
| `GET` | `/api/history/{id}` | One history record | `200` |
| `DELETE` | `/api/history/{id}` | Delete one history record | `200` |
| `DELETE` | `/api/history` | Clear the whole history (extended) | `200` |
| `PUT` | `/api/history/{id}/favorite` | Mark/unmark a favourite (extended) | `200` |
| `GET` | `/api/statistics` | Aggregate statistics (extended) | `200` |

Status codes: `200` success, `204` CORS preflight, `400` invalid request /
invalid expression / division by zero, `404` unknown id or route, `405` wrong
method (with `Allow`), `413` body too large, `500` unexpected server error.

### Examples

```bash
# Basic calculation
curl -X POST http://127.0.0.1:8000/api/calculate \
     -H "Content-Type: application/json" \
     -d '{"expression":"12+8"}'
```

```json
{"success": true, "expression": "12+8", "normalized_expression": "12+8",
 "result": 20, "result_text": "20", "record_id": 1,
 "created_at": "2026-10-01 10:20:00", "is_favorite": false}
```

```bash
# Compound expression, unary minus, decimals
curl -X POST http://127.0.0.1:8000/api/calculate -H "Content-Type: application/json" \
     -d '{"expression":"3 * -2 + (1+2)*3 / 1.5"}'

# Invalid expression
curl -X POST http://127.0.0.1:8000/api/calculate -H "Content-Type: application/json" \
     -d '{"expression":"1+*2"}'
# {"success": false, "code": "INVALID_EXPRESSION", "message": "Expected a number, a function or '(' but found '*' at position 3"}

# Division by zero
curl -X POST http://127.0.0.1:8000/api/calculate -H "Content-Type: application/json" \
     -d '{"expression":"5/0"}'
# {"success": false, "code": "DIVISION_BY_ZERO", "message": "Cannot divide by zero"}

# History, search, pagination
curl "http://127.0.0.1:8000/api/history?page=1&page_size=10&keyword=12"

# Delete one record
curl -X DELETE http://127.0.0.1:8000/api/history/1

# Extended: scientific functions, power, factorial, base conversion
curl -X POST http://127.0.0.1:8000/api/calculate -H "Content-Type: application/json" \
     -d '{"expression":"sqrt(16) + 2^10 + 5!"}'
curl -X POST http://127.0.0.1:8000/api/convert/base -H "Content-Type: application/json" \
     -d '{"value":"255","from_base":10,"to_base":16}'
```

### Supported expression syntax

| Feature | Examples |
| --- | --- |
| Arithmetic | `+` `-` `*` `/` `%` (also accepts `×` `÷` `−`) |
| Precedence & parentheses | `1+2*3` → 7, `(1+2)*3` → 9 |
| Unary signs | `-5+8`, `3*-2`, `2^-3`, `--5` |
| Decimals & exponents | `1.5*4`, `.5+.5`, `1e3+1` |
| Power / factorial | `2^10`, `2**10`, `5!`, `fact(6)`, `pow(2,10)` |
| Functions | `sqrt` `abs` `sin` `cos` `tan` `asin` `acos` `atan` `ln` `log` `log2` `exp` `floor` `ceil` `round` `min` `max` `pow` `fact` |
| Constants | `pi`, `e`, `tau` (also `π`) |

`log(x)` is base 10; `log(x, b)` uses an explicit base. Trigonometric functions
work in radians. `%` follows Python semantics for negative operands.

## 8. Connecting the front end

The front end is a separate project and talks to this service over HTTP; it is
not served by this service. Two supported setups:

1. **Recommended** — serve the front-end folder with any static server and set
   its API base URL to this backend:

   ```bash
   # front end (port 5500)
   cd ../832401322_calculator_frontend && python -m http.server 5500
   # back end (port 8000)
   cd ../832401322_calculator_backend  && python run.py
   ```

   In the front end, `src/js/config.js` → `API_BASE_URL` must be
   `http://127.0.0.1:8000`.

2. **Opened from disk** (`file://`) — also works, because the API sends
   `Access-Control-Allow-Origin: *` and answers `OPTIONS` preflight requests.

When the backend is stopped, the front end still renders and accepts button
presses but every calculation request fails with a connection error, which
demonstrates that all calculation logic lives on the server.

## 9. Testing

```bash
python -m unittest discover -v          # from the repository root
python -m unittest tests.test_calculator -v
python -m unittest tests.test_api -v
```

The suite covers the four assignment features (basic calculation, compound
expressions, history storage, history deletion) plus error handling, protocol
behaviour and a check that `eval`/`exec` never appear in the calculation module.

## 10. Deployment notes

* Bind to `0.0.0.0` (`python run.py --host 0.0.0.0 --port 8080`) behind a reverse
  proxy, or run it as a systemd service / Windows scheduled task.
* Point `CALC_DB_PATH` at a persistent volume so history survives restarts.
* For a public demo, the repository can be deployed as-is on any host that runs
  Python 3.10+ (Render, Railway, PythonAnywhere, a VPS, …).
