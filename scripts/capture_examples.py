"""Run real curl commands against a real running instance and record what comes back.

    python scripts/capture_examples.py            # print the transcript
    python scripts/capture_examples.py --write    # also save it to examples/curl_examples.md
    python scripts/capture_examples.py --serve    # then keep the server up (for /docs screenshots)

What it does:

1. Creates a SQLite database in a temporary folder and a random JWT secret.
   Neither is kept. Your own database and .env are not touched.
2. Runs `alembic upgrade head` and starts uvicorn on a free local port.
3. Runs each example with the system `curl` and records the status and body.

All data is SYNTHETIC: the account is demo@example.com and the expenses are
made up. Dates are placed in the current month and the two before it, so the
output depends on the day the script is run.
"""

import argparse
import json
import os
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "curl_examples.md"

# What the commands show. The real port is picked at run time.
SHOWN_BASE = "http://localhost:8000"

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-passphrase-123"
OTHER_EMAIL = "other@example.com"
OTHER_PASSWORD = "another-passphrase-456"


# --- dates relative to the day of the run -----------------------------------


def month_offset(today: date, offset: int, day: int) -> str:
    """ISO date for `day` of the month `offset` months from today's month, never after today."""
    index = today.year * 12 + (today.month - 1) + offset
    result = date(index // 12, index % 12 + 1, day)
    return min(result, today).isoformat()


def sample_expenses(today: date) -> list[dict]:
    """(synthetic) Three months of made-up spending."""
    rows = [
        # two months ago
        (-2, 1, "12000.00", "Housing", "bank_transfer", "Rent"),
        (-2, 4, "2350.75", "Food", "upi", "Monthly groceries"),
        (-2, 9, "480.00", "Transport", "upi", "Metro card recharge"),
        # last month
        (-1, 1, "12000.00", "Housing", "bank_transfer", "Rent"),
        (-1, 3, "2610.40", "Food", "card", "Monthly groceries"),
        (-1, 12, "1450.00", "Utilities", "upi", "Electricity bill"),
        (-1, 20, "899.00", "Entertainment", "card", "Concert ticket"),
        # this month
        (0, 1, "12000.00", "Housing", "bank_transfer", "Rent"),
        (0, 3, "1890.25", "Food", "upi", "Monthly groceries"),
        (0, 5, "349.50", "Food", "cash", "Lunch with friends"),
        (0, 6, "620.00", "Transport", "upi", "Cab to the airport"),
        (0, 8, "1499.00", "Shopping", "card", "Running shoes"),
    ]
    return [
        {
            "amount": amount,
            "date": month_offset(today, offset, day),
            "category": category,
            "payment_method": method,
            "note": note,
        }
        for offset, day, amount, category, method, note in rows
    ]


# --- running curl ------------------------------------------------------------


class Api:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.curl = shutil.which("curl")
        if self.curl is None:
            raise SystemExit("curl was not found on PATH")
        self.sections: list[str] = []

    def call(self, method: str, path: str, *, token: str | None = None, json_body=None, form=None):
        """Run one curl command. Returns (status code, body text, shell command as shown)."""
        options: list[list[str]] = []
        if method != "GET":
            options.append(["-X", method])
        if token:
            options.append(["-H", f"Authorization: Bearer {token}"])
        if json_body is not None:
            options.append(["-H", "Content-Type: application/json"])
            options.append(["-d", json.dumps(json_body)])
        for key, value in (form or {}).items():
            options.append(["--data-urlencode", f"{key}={value}"])

        args = [self.curl, "-s", "-w", "\n%{http_code}"]
        for option in options:
            args.extend(option)
        args.append(self.base_url + path)
        completed = subprocess.run(args, capture_output=True, check=True)
        body, _, status = completed.stdout.decode("utf-8").rpartition("\n")

        shown = ["curl -s " + shlex.quote(SHOWN_BASE + path)]
        for flag, value in options:
            if token and value == f"Authorization: Bearer {token}":
                shown.append(f'{flag} "Authorization: Bearer $TOKEN"')
            else:
                shown.append(f"{flag} {shlex.quote(value)}")
        return int(status), body, " \\\n  ".join(shown)

    def quiet(self, method: str, path: str, **kwargs) -> dict:
        """Run a command that is part of the setup and is not shown."""
        status, body, _ = self.call(method, path, **kwargs)
        if status >= 400:
            raise SystemExit(f"setup call {method} {path} failed with HTTP {status}: {body}")
        return json.loads(body) if body else {}

    def show(self, title: str, method: str, path: str, *, note: str = "", edit=None, **kwargs):
        """Run a command and add it, with its real response, to the transcript."""
        status, body, command = self.call(method, path, **kwargs)
        is_json = body.startswith(("{", "["))
        parsed = json.loads(body) if is_json else None
        if edit and parsed is not None:
            parsed = edit(parsed)
        text = pretty(parsed) if is_json else body.replace("\r\n", "\n").rstrip("\n")

        lines = [f"### {title}", ""]
        if note:
            lines += [note, ""]
        lines += ["```bash", command, "```", "", f"Response (HTTP {status}):", ""]
        if text:
            lines += ["```json" if is_json else "```text", text, "```", ""]
        else:
            lines += ["(empty body)", ""]
        self.sections.append("\n".join(lines))
        return parsed if is_json else body


def pretty(value, indent: int = 0) -> str:
    """JSON with one line per object in a list, so long lists stay readable."""
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = [f'{pad}  {json.dumps(key)}: {pretty(item, indent + 1)}' for key, item in value.items()]
        return "{\n" + ",\n".join(inner) + f"\n{pad}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(not isinstance(item, (dict, list)) for item in value):
            return json.dumps(value, ensure_ascii=False)
        inner = []
        for item in value:
            one_line = json.dumps(item, ensure_ascii=False)
            inner.append(f"{pad}  {one_line if len(one_line) <= 150 else pretty(item, indent + 1)}")
        return "[\n" + ",\n".join(inner) + f"\n{pad}]"
    return json.dumps(value, ensure_ascii=False)


def shorten_token(body: dict) -> dict:
    token = body["access_token"]
    return {**body, "access_token": f"{token[:20]}...(shortened, {len(token)} characters)"}


# --- the server --------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(workdir: Path, port: int) -> subprocess.Popen:
    env = {
        **os.environ,
        "JWT_SECRET": secrets.token_urlsafe(48),
        "DATABASE_URL": f"sqlite:///{(workdir / 'demo.db').as_posix()}",
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT, env=env, check=True, capture_output=True,
    )
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise SystemExit("the server stopped while starting")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return server
        except OSError:
            time.sleep(0.2)
    server.terminate()
    raise SystemExit("the server did not start within 30 seconds")


# --- the examples ------------------------------------------------------------


def run_examples(api: Api, today: date) -> None:
    this_month = today.strftime("%Y-%m")
    month_start = today.replace(day=1).isoformat()

    api.show("Health check", "GET", "/health")

    api.show(
        "Register",
        "POST", "/auth/register",
        json_body={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )

    token = api.show(
        "Log in",
        "POST", "/auth/login",
        note="The login is an OAuth2 password form. The email goes in the `username` field. "
        "The token in the response is shortened here.",
        form={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
        edit=shorten_token,
    )
    # The shown body is shortened; log in again for the real token.
    token = api.quiet("POST", "/auth/login", form={"username": DEMO_EMAIL, "password": DEMO_PASSWORD})["access_token"]

    api.show(
        "Wrong password",
        "POST", "/auth/login",
        note="An unknown email gets exactly the same answer.",
        form={"username": DEMO_EMAIL, "password": "not-the-password"},
    )

    api.show("No token", "GET", "/expenses")

    categories = api.show(
        "List categories",
        "GET", "/categories",
        note="Set `TOKEN` to the `access_token` from the login. A new account starts with these defaults.",
        token=token,
    )
    category_ids = {category["name"]: category["id"] for category in categories}

    samples = sample_expenses(today)
    first, rest = samples[-2], samples[:-2] + samples[-1:]
    created = api.show(
        "Create an expense",
        "POST", "/expenses",
        token=token,
        json_body={
            "amount": first["amount"],
            "category_id": category_ids[first["category"]],
            "date": first["date"],
            "note": first["note"],
            "payment_method": first["payment_method"],
        },
    )
    for sample in rest:
        api.quiet(
            "POST", "/expenses",
            token=token,
            json_body={
                "amount": sample["amount"],
                "category_id": category_ids[sample["category"]],
                "date": sample["date"],
                "note": sample["note"],
                "payment_method": sample["payment_method"],
            },
        )

    api.show(
        "Validation error",
        "POST", "/expenses",
        note="A negative amount, a date that does not exist and an unknown payment method, all reported at once.",
        token=token,
        json_body={
            "amount": -50,
            "category_id": category_ids["Food"],
            "date": "2026-02-30",
            "payment_method": "cheque",
        },
    )

    api.show(
        "List expenses: filters and pagination",
        "GET",
        f"/expenses?date_from={month_start}&category_id={category_ids['Food']}&min_amount=100&page_size=2",
        note=f"{len(samples)} sample expenses exist at this point. This asks for Food expenses of 100 or more "
        "from the start of the month, two per page.",
        token=token,
    )

    api.show(
        "List expenses: text search and sorting",
        "GET", "/expenses?q=groceries&sort=amount&order=desc",
        token=token,
    )

    api.show(
        "Change an expense",
        "PATCH", f"/expenses/{created['id']}",
        note="Only the fields that are sent change.",
        token=token,
        json_body={"amount": "650.00", "note": "Cab to the airport (with toll)"},
    )

    for category, amount in (("Food", "4000"), ("Housing", "12000")):
        api.quiet(
            "POST", "/budgets",
            token=token,
            json_body={"category_id": category_ids[category], "month": this_month, "amount": amount},
        )
    api.show(
        "Set a budget",
        "POST", "/budgets",
        token=token,
        json_body={"category_id": category_ids["Transport"], "month": this_month, "amount": "500"},
    )

    api.show(
        "Spent vs budget",
        "GET", f"/budgets/status?month={this_month}",
        note="Budgets exist for Food (4000), Housing (12000) and Transport (500). "
        "Shopping has no budget, so it is listed under `unbudgeted`.",
        token=token,
    )

    api.show("Summary: total per month", "GET", "/summary/monthly", token=token)

    api.show(
        "Summary: total per category",
        "GET", f"/summary/categories?date_from={month_start}",
        token=token,
    )

    api.show(
        "Summary: trends",
        "GET", "/summary/trends?months=3",
        note="`change_percent` is null for the first month because the month before it has no spending.",
        token=token,
    )

    api.show(
        "CSV export",
        "GET", f"/expenses/export?date_from={month_start}",
        note="Takes the same filters as the list. Add `-o expenses.csv` to save it to a file.",
        token=token,
    )

    api.quiet("POST", "/auth/register", json_body={"email": OTHER_EMAIL, "password": OTHER_PASSWORD})
    other_token = api.quiet("POST", "/auth/login", form={"username": OTHER_EMAIL, "password": OTHER_PASSWORD})["access_token"]
    api.show(
        "Access control: another user's expense",
        "GET", f"/expenses/{created['id']}",
        note=f"A second account, `{OTHER_EMAIL}`, asks for the first account's expense with its own valid token "
        "(`TOKEN` here is the second account's). The answer is the same as for an id that does not exist.",
        token=other_token,
    )
    api.show(
        "Access control: another user's list",
        "GET", "/expenses",
        note="The second account's own list is empty.",
        token=other_token,
    )

    api.show("Delete an expense", "DELETE", f"/expenses/{created['id']}", token=token)


def transcript(api: Api, today: date) -> str:
    versions = subprocess.run(
        [sys.executable, "-c", "import fastapi, sqlalchemy, sys; print(sys.version.split()[0], fastapi.__version__, sqlalchemy.__version__)"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    curl_version = subprocess.run([api.curl, "--version"], capture_output=True, text=True).stdout.split()[1]
    header = f"""# curl examples

Captured on {today.isoformat()} from a real running instance by `scripts/capture_examples.py`
(Python {versions[0]}, FastAPI {versions[1]}, SQLAlchemy {versions[2]}, curl {curl_version}, {sys.platform}).

- Every command below was run with `curl` and every response is what the server returned.
- The data is **synthetic**: the accounts are `{DEMO_EMAIL}` and `{OTHER_EMAIL}`, and the expenses are made up.
- The database was a temporary SQLite file and the JWT secret was random. Both were discarded after the run.
- Two things are edited for reading: the server ran on a random free port and is shown as `{SHOWN_BASE}`,
  and the access token is shown as `$TOKEN` in commands and shortened in the login response.
- JSON is re-indented. Nothing else is changed.
- The commands are written for a POSIX shell (Linux, macOS, Git Bash, WSL). In PowerShell use `curl.exe` and
  adjust the quoting.

To capture them again: `python scripts/capture_examples.py --write`. Ids, timestamps and dates will differ.

"""
    return header + "\n".join(api.sections)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help=f"save the transcript to {OUTPUT.relative_to(ROOT)}")
    parser.add_argument("--serve", action="store_true", help="keep the server running afterwards, until Ctrl+C")
    arguments = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    port = free_port()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as workdir:
        server = start_server(Path(workdir), port)
        try:
            api = Api(f"http://127.0.0.1:{port}")
            run_examples(api, today)
            text = transcript(api, today)
            if arguments.write:
                OUTPUT.parent.mkdir(exist_ok=True)
                OUTPUT.write_text(text, encoding="utf-8", newline="\n")
                print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(api.sections)} examples)")
            else:
                sys.stdout.reconfigure(encoding="utf-8")
                print(text)
            if arguments.serve:
                print(f"serving the demo data on http://127.0.0.1:{port} (docs: /docs). Ctrl+C to stop.", flush=True)
                try:
                    server.wait()
                except KeyboardInterrupt:
                    pass
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
