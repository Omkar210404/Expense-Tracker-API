# PLAN — expense-tracker-api

A FastAPI backend for personal expense tracking with user accounts. SQLite by default.

Status: **approved 2026-10-10**, with the recommended option for each decision in section 13.

## 1. Environment (inspected 2026-10-10)

| Item | Found |
|------|-------|
| OS / shell | Windows 11, PowerShell |
| Python | 3.11.9 (Microsoft Store build, no `py` launcher) |
| SQLite (stdlib `sqlite3`) | 3.45.1 |
| Global packages | old and unsuitable: fastapi 0.95.2, pydantic 1.10.22, starlette 0.27.0. No alembic, passlib, bcrypt, PyJWT or pytest |
| Internet / PyPI | reachable. Latest listed: fastapi 0.143.0, uvicorn 0.54.0, pydantic 2.14.0, pydantic-settings 2.15.0, sqlalchemy 2.1.4, alembic 1.20.0, pyjwt 2.15.1, bcrypt 5.0.0, passlib 1.7.4, python-multipart 0.0.32, email-validator 2.3.0, pytest 9.1.1, httpx 0.28.1 |
| Git | 2.49.0, identity `Omkar210404 <omkarnikamofficial21@gmail.com>`, sibling repos use `main` |
| Docker | **not installed** |
| GitHub CLI (`gh`) | not installed |
| curl | `C:\windows\system32\curl.exe` |
| Browsers | Chrome and Edge installed (headless mode can take the `/docs` screenshots) |

Consequences:

- Everything runs in a project-local `.venv` (git-ignored). `requirements.txt` pins the exact versions that install and pass the tests here.
- The Dockerfile and `docker-compose.yml` cannot be built or run on this machine. See risk 1 and decision 5.
- The GitHub repo has to be created by hand, and the CI badge shows nothing until the first push.

## 2. Scope

In: accounts, per-user expenses, categories, monthly budgets, summaries, CSV export, all over a JSON HTTP API.

Out: no frontend, no shared or household accounts, no multiple currencies, no recurring expenses, no CSV import, no receipt upload, no refresh tokens or logout, no password reset or email verification, no rate limiting, no admin role.

## 3. Endpoints

All paths except `/health`, `/auth/register` and `/auth/login` need `Authorization: Bearer <token>`.

| Method | Path | What it does | Success |
|--------|------|--------------|---------|
| GET | `/health` | Liveness check, used by the Docker health check and CI | 200 |
| POST | `/auth/register` | Create an account (`email`, `password`) and its default categories | 201 |
| POST | `/auth/login` | OAuth2 password form (`username` = email, `password`). Returns `access_token`, `token_type` | 200 |
| GET | `/auth/me` | The logged-in user | 200 |
| GET | `/categories` | The user's categories | 200 |
| POST | `/categories` | Create a category | 201 |
| GET | `/categories/{id}` | One category | 200 |
| PATCH | `/categories/{id}` | Rename | 200 |
| DELETE | `/categories/{id}` | Delete. Refused with 409 while expenses use it; its budgets are deleted with it | 204 |
| POST | `/expenses` | Create an expense | 201 |
| GET | `/expenses` | List with filters, sorting and pagination | 200 |
| GET | `/expenses/export` | CSV download, same filters as the list, no pagination | 200 |
| GET | `/expenses/{id}` | One expense | 200 |
| PATCH | `/expenses/{id}` | Change any field | 200 |
| DELETE | `/expenses/{id}` | Delete | 204 |
| POST | `/budgets` | Set a budget (`category_id`, `month`, `amount`) | 201 |
| GET | `/budgets` | List budgets, optional `month=YYYY-MM` | 200 |
| GET | `/budgets/status` | Spent vs budget for `month=YYYY-MM` | 200 |
| GET | `/budgets/{id}` | One budget | 200 |
| PATCH | `/budgets/{id}` | Change the amount | 200 |
| DELETE | `/budgets/{id}` | Delete | 204 |
| GET | `/summary/monthly` | Total and count per month | 200 |
| GET | `/summary/categories` | Total, count and share per category | 200 |
| GET | `/summary/trends` | Month-over-month change | 200 |

FastAPI also serves `/docs`, `/redoc` and `/openapi.json`.

**Expense list query parameters**

- Filters, combined with AND: `date_from`, `date_to` (both inclusive), `category_id`, `min_amount`, `max_amount`, `payment_method`, `q` (case-insensitive text in the note).
- Pagination: `page` (from 1, default 1), `page_size` (1 to 100, default 20).
- Sorting: `sort` = `date` | `amount` | `created_at` (default `date`), `order` = `asc` | `desc` (default `desc`).
- Response: `{"items": [...], "total": n, "page": n, "page_size": n, "pages": n}`.
- `date_from` after `date_to`, or `min_amount` above `max_amount`, is a 422.

**Summary definitions**

- `/summary/monthly?from=YYYY-MM&to=YYYY-MM`: both optional. Without them, the range runs from the first to the last month that has an expense. Months inside the range with no expenses are returned with zero.
- `/summary/categories?date_from&date_to`: per category, the total, the count, and its share of the overall total as a percentage with one decimal. Share is `null` when the overall total is zero.
- `/summary/trends?months=N` (1 to 36, default 6): the last N calendar months ending with the current one. Per month: total, count, change from the previous month as an amount and as a percentage. The percentage is `null` when the previous month is zero. Also the average monthly total over the window. That is all "trends" means here: no forecasting.
- `/budgets/status?month=YYYY-MM`: per budgeted category: budget, spent, remaining, percent used, `over_budget`. Then totals, and a separate list of spending in categories that have no budget that month.

"Today" comes from a dependency, so tests fix the date instead of depending on the clock.

**Status codes**: 400 is not used. 401 missing, invalid or expired token, or wrong login. 404 unknown id **or an id that belongs to another user**. 409 duplicate email, duplicate category name, duplicate budget, category still in use. 422 validation.

**Error format**, the same for every error including FastAPI's own validation errors and unknown routes:

```json
{"error": {"code": "validation_error", "message": "Request validation failed", "details": [{"field": "body.amount", "message": "Input should be greater than 0"}]}}
```

`details` is present only for validation errors. A 500 returns a generic message and never a stack trace.

## 4. Data model

**users**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `email` | String(254), unique | stored lower-case |
| `hashed_password` | String | bcrypt hash |
| `created_at` | DateTime (UTC) | |

**categories**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | FK → users, ON DELETE CASCADE | |
| `name` | String(50) | unique per user, compared case-insensitively |
| `is_default` | Boolean | true for the ones created at registration |
| `created_at` | DateTime | |

Defaults copied to each new user: Food, Transport, Housing, Utilities, Health, Entertainment, Shopping, Education, Other. They are ordinary rows, so the user can rename or delete them.

**expenses**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | FK → users, ON DELETE CASCADE | |
| `category_id` | FK → categories, ON DELETE RESTRICT | must be the user's own category |
| `amount_minor` | Integer, CHECK > 0 | amount × 100 |
| `date` | Date | |
| `note` | String(500), nullable | |
| `payment_method` | String(20), CHECK | `cash`, `card`, `upi`, `bank_transfer`, `wallet`, `other` |
| `created_at`, `updated_at` | DateTime | |

Indexes on (`user_id`, `date`) and (`user_id`, `category_id`).

**budgets**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | FK → users, ON DELETE CASCADE | |
| `category_id` | FK → categories, ON DELETE CASCADE | |
| `month` | Date | first day of the month; the API reads and writes `YYYY-MM` |
| `amount_minor` | Integer, CHECK > 0 | |

Unique on (`user_id`, `category_id`, `month`).

**Money**: stored as whole minor units in an integer column. SQLite has no decimal type, so a decimal column would be stored as a float and sums would pick up rounding errors. The API takes amounts as numbers or strings with at most two decimal places and returns them as strings (`"249.50"`). One currency, no currency field.

**Validation**

- Amount: greater than 0, at most 2 decimal places, at most 9,999,999.99.
- Date: a real calendar date (`2026-02-30` is refused), not before 2000-01-01, not more than one day after today. The one-day margin is for users in time zones ahead of the server's UTC date.
- Month: `YYYY-MM` with a real month.
- Email: valid format. Password: 8 to 72 bytes (72 is bcrypt's limit; longer is refused instead of silently cut).
- Note up to 500 characters, category name 1 to 50 after trimming.

**Schema creation**: Alembic, with one initial migration. `alembic upgrade head` is the only thing that creates tables for a real run; the app does not call `create_all` at startup. Tests use `create_all` on a temporary file for speed, and one test runs the migration on an empty database and compares it with the models so the two cannot drift.

`PRAGMA foreign_keys = ON` is set on every SQLite connection.

## 5. Auth design

- **Passwords**: bcrypt through a maintained library, wrapped in two functions (`hash_password`, `verify_password`). Nothing hand-rolled. Which library is decision 1.
- **Tokens**: JWT signed with HS256 using PyJWT. Claims: `sub` (user id), `iat`, `exp`. The algorithm is fixed in code and passed explicitly when decoding, so a token cannot choose its own.
- **Secret**: `JWT_SECRET` from the environment. There is no default value anywhere in the code. The app refuses to start if it is missing or shorter than 32 characters. Tests generate a random one at run time. `docker-compose.yml` uses `${JWT_SECRET:?...}`, so compose stops with a message if it is not set. `.env.example` holds a placeholder and the command that generates a real one.
- **Lifetime**: `ACCESS_TOKEN_EXPIRE_MINUTES`, default 30. No refresh tokens and no server-side revocation: a token stays valid until it expires.
- **Login**: the OAuth2 password form, so the Authorize button on `/docs` works. Unknown email and wrong password return the same 401 body, and a dummy hash is verified when the email is unknown so the two cases take similar time.
- **Access control**: one `get_current_user` dependency on every protected router. Every repository query takes `user_id` and filters on it; no function looks up a row by id alone. Another user's row returns 404, the same as a row that does not exist, so ids reveal nothing. A category id in an expense or budget body is checked against the caller's own categories.

Environment variables:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `JWT_SECRET` | yes | none | signing key, at least 32 characters |
| `DATABASE_URL` | no | `sqlite:///./expenses.db` | SQLAlchemy URL |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `30` | token lifetime |
| `BCRYPT_ROUNDS` | no | `12` | bcrypt cost factor, 4 to 16; lowered only in tests |
| `CORS_ORIGINS` | no | empty (CORS off) | comma-separated allowed origins |

## 6. File layout

Three layers. Routers know HTTP, services know the rules, repositories know SQL.

```
expense-tracker-api/
├── app/
│   ├── main.py              # create_app(): routers, error handlers, CORS
│   ├── config.py            # Settings read from the environment
│   ├── database.py          # engine, session factory, Base, get_db
│   ├── models.py            # SQLAlchemy models
│   ├── security.py          # password hashing, JWT create / decode
│   ├── deps.py              # get_current_user, get_today
│   ├── errors.py            # AppError classes and the JSON error handlers
│   ├── money.py             # Decimal <-> minor units
│   ├── schemas/             # Pydantic models: auth, category, expense, budget, summary, common
│   ├── routers/             # ROUTES: auth, categories, expenses, budgets, summary, health
│   ├── services/            # SERVICES: auth, categories, expenses, budgets, summaries, export
│   └── repositories/        # DATABASE LAYER: users, categories, expenses, budgets
├── alembic/                 # env.py, versions/0001_initial.py
├── alembic.ini
├── tests/
├── scripts/capture_examples.py   # runs real curl commands against a running instance
├── examples/curl_examples.md     # the captured commands and responses
├── docs/                         # screenshots of /docs
├── Dockerfile  docker-compose.yml  .dockerignore
├── .github/workflows/tests.yml
├── .env.example  .gitignore  .gitattributes  pytest.ini
├── requirements.txt              # runtime, pinned
├── requirements-dev.txt          # adds pytest and httpx
└── README.md  PLAN.md  LICENSE
```

- Routes are plain `def` with synchronous SQLAlchemy sessions. No async database driver.
- `.gitignore`: `.env`, `*.db`, `*.sqlite3`, `*.db-journal`, `.venv/`, `__pycache__/`, `.pytest_cache/`, exported `*.csv`.
- `brain.md` and `prompts/` stay outside this repo. No other project folder is touched.

## 7. Tests (pytest, TestClient, temporary SQLite file per test)

| Module | Covers |
|--------|--------|
| `test_auth.py` | register; duplicate email 409; bad email and short or over-long password 422; login; wrong password and unknown email give the same 401; `/auth/me`; no token, malformed token, expired token, token signed with another secret, token of a deleted user all 401; stored password is a bcrypt hash and not the plain text; email is case-insensitive |
| `test_access_control.py` | user B gets 404 on GET, PATCH and DELETE of user A's expense, category and budget; B's lists, summaries, budget status and CSV export contain none of A's data; B cannot create an expense or budget with A's category id; A's data is unchanged afterwards |
| `test_categories.py` | defaults at registration; create, rename, delete; duplicate name 409 including different case; delete while in use 409 |
| `test_expenses.py` | create, read, update, delete; zero, negative and three-decimal amounts; invalid and far-future dates; unknown payment method; note too long; unknown category |
| `test_expense_filters.py` | each filter alone and combined; inclusive date range; case-insensitive search; total and page count; page past the end; `page_size` limits; sorting; reversed ranges 422 |
| `test_budgets.py` | create, change, delete; duplicate 409; bad month 422; status against hand-worked values: under, exactly at and over budget, no expenses, expenses in other months ignored, unbudgeted spending listed |
| `test_summaries.py` | monthly totals with zero months filled; per category with shares; trends with change and `null` percentage; a user with no expenses gets zeros and no division error. All against hand-worked values |
| `test_export.py` | header and rows; filters apply; notes with commas, quotes and newlines survive; download headers; cells starting with `=`, `+`, `-`, `@` are neutralised |
| `test_errors.py` | the error shape for 401, 404, 405, 409, 422, an unknown route, and a forced 500 with no stack trace |
| `test_config.py` | missing or short `JWT_SECRET` stops startup |
| `test_migrations.py` | `alembic upgrade head` on an empty database produces the same tables and columns as the models |
| `test_money.py` | conversion both ways, rounding refused |

Pass counts in the README and the final report will be copied from the actual pytest run.

## 8. Real examples and screenshots

- `scripts/capture_examples.py` starts the app on a temporary database with a throwaway secret, runs real `curl` commands (register, login, create, filter, budget status, summaries, export, an access-control 404, a validation 422) and writes commands and responses to `examples/curl_examples.md`. The README examples are copied from that file. The account is `demo@example.com` with made-up expenses, labelled as sample data. The JWT is shortened in the README and that is stated.
- Screenshots of `/docs` are taken from the same running instance with headless Chrome. If the page does not render that way (Swagger UI is drawn by JavaScript), I use Playwright as a one-off tool outside `requirements.txt`. If neither gives a real screenshot, the README keeps a labelled placeholder and I say so.

## 9. Docker

- `Dockerfile`: `python:3.11-slim`, runtime requirements only, non-root user, runs `alembic upgrade head` then uvicorn, health check on `/health`.
- `docker-compose.yml`: one service, port 8000, a named volume for the SQLite file, `JWT_SECRET` required from the environment or `.env`.

## 10. CI

`.github/workflows/tests.yml`, on every push and pull request:

1. **pytest**: `ubuntu-latest` and `windows-latest`, Python 3.11 and 3.13.
2. **docker**: build the image, start it with compose and a generated secret, wait for `/health`, register and log in with curl, stop it.

The README badge points at this workflow. I will not describe CI or Docker as passing until a real run has finished on GitHub.

## 11. Commits

Small, one concern each, existing git identity, no `Co-Authored-By` or session lines.

1. Add PLAN.md, LICENSE, .gitignore, .gitattributes, .env.example, requirements
2. Add settings from environment with startup check for the JWT secret
3. Add database setup and SQLAlchemy models
4. Add Alembic with the initial migration and a drift test
5. Add consistent JSON error format
6. Add password hashing and JWT helpers
7. Add registration, login and current user with tests
8. Add categories with defaults
9. Add expense CRUD with validation
10. Add expense filters, sorting and pagination
11. Add access control tests across all resources
12. Add monthly budgets and spent vs budget
13. Add summaries: monthly, per category, trends
14. Add CSV export
15. Add Dockerfile and docker-compose.yml
16. Add GitHub Actions workflow
17. Add example capture script, captured curl examples and screenshots
18. Add README

## 12. Risks and how they are handled

| # | Risk | Handling |
|---|------|----------|
| 1 | Docker is not installed, so the image cannot be built or run here. `brain.md` says every README command must be confirmed | The CI docker job builds and smoke-tests it on GitHub. Until that run exists the README says the Docker steps were not run locally |
| 2 | passlib's last release is 1.7.4 from 2020 and is reported to fail with current bcrypt releases | Decision 1. Whichever is chosen is confirmed in the venv before pinning |
| 3 | A missed `user_id` filter would leak data between users | Every repository function requires `user_id`; a dedicated access-control test module covers every resource and every read path |
| 4 | Float rounding in money sums | Integer minor units, sums done in SQL on integers |
| 5 | SQLite ignores foreign keys by default | Pragma on connect, with tests for restrict and cascade |
| 6 | Month grouping written with SQLite-only functions would break on another database | Use SQLAlchemy `extract`. Only SQLite is tested, and the README says so |
| 7 | fastapi 0.143, pydantic 2.14 and sqlalchemy 2.1 are newer than anything on this machine | Build and test in the venv; pin what passes; step a package back if one is incompatible and record it here |
| 8 | Models and migration drift apart | `test_migrations.py` |
| 9 | Trends and the date check depend on today's date | Date injected through a dependency, fixed in tests |
| 10 | `/expenses/export` could be read as `/expenses/{id}` | Declared before the id route, with a test |
| 11 | Temporary SQLite files stay locked on Windows | Engine disposed in the fixture |
| 12 | Spreadsheet formula injection through an exported note | Cells starting with `=`, `+`, `-`, `@` get a leading apostrophe; documented |
| 13 | Captured responses contain ids, timestamps and a token that differ on each run | Captured once from a real run, dated, token shortened and the throwaway secret discarded |
| 14 | `/docs` loads Swagger UI from a CDN | Needs internet to view; listed as a limitation |
| 15 | CI cannot be checked before the first push | Tests pass locally on Windows first; results reported only from a real run |
| 16 | No rate limiting, so login can be brute-forced | Not built. Stated in the security notes under "not covered" |

## 13. Decisions (approved as recommended)

1. **Password hashing library**. Recommended: the `bcrypt` package used directly (maintained, current release 5.0.0). Alternative: `passlib[bcrypt]` as named in the brief, which means pinning an old bcrypt (4.0.1) to keep it working.
2. **GitHub repo name for the CI badge**: `Omkar210404/Expense-Tracker-API`, following `Job-Tracker-CLI` and `Sap-Data-Cleaner`.
3. **A budget belongs to one category in one month.** It does not repeat by itself; next month needs its own row. Simple to reason about and to test. A repeating default is listed as a future idea.
4. **Amounts are returned as strings** (`"249.50"`), stored as integers. Alternative: JSON numbers.
5. **Docker is verified by CI only**, because it cannot run on this machine.
6. **Paths are flat** (`/expenses`), with no `/api/v1` prefix.

## 14. Deviations from brain.md

- Rule 7 (every README command run and confirmed) cannot be met for the Docker commands on this machine. See risk 1.
- This project is outside the three listed in `brain.md`. `brain.md`, `prompts/` and the other project folders are not touched and stay outside this repo.
- The README gets a Mermaid diagram of the three layers and real `/docs` screenshots.
