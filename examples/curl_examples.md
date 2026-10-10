# curl examples

Captured on 2026-10-10 from a real running instance by `scripts/capture_examples.py`
(Python 3.11.9, FastAPI 0.143.0, SQLAlchemy 2.1.4, curl 8.21.0, win32).

- Every command below was run with `curl` and every response is what the server returned.
- The data is **synthetic**: the accounts are `demo@example.com` and `other@example.com`, and the expenses are made up.
- The database was a temporary SQLite file and the JWT secret was random. Both were discarded after the run.
- Two things are edited for reading: the server ran on a random free port and is shown as `http://localhost:8000`,
  and the access token is shown as `$TOKEN` in commands and shortened in the login response.
- JSON is re-indented. Nothing else is changed.
- The commands are written for a POSIX shell (Linux, macOS, Git Bash, WSL). In PowerShell use `curl.exe` and
  adjust the quoting.

To capture them again: `python scripts/capture_examples.py --write`. Ids, timestamps and dates will differ.

### Health check

```bash
curl -s http://localhost:8000/health
```

Response (HTTP 200):

```json
{
  "status": "ok"
}
```

### Register

```bash
curl -s http://localhost:8000/auth/register \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"email": "demo@example.com", "password": "demo-passphrase-123"}'
```

Response (HTTP 201):

```json
{
  "id": 1,
  "email": "demo@example.com",
  "created_at": "2026-10-10T14:12:51.924749Z"
}
```

### Log in

The login is an OAuth2 password form. The email goes in the `username` field. The token in the response is shortened here.

```bash
curl -s http://localhost:8000/auth/login \
  -X POST \
  --data-urlencode username=demo@example.com \
  --data-urlencode password=demo-passphrase-123
```

Response (HTTP 200):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...(shortened, 141 characters)",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### Wrong password

An unknown email gets exactly the same answer.

```bash
curl -s http://localhost:8000/auth/login \
  -X POST \
  --data-urlencode username=demo@example.com \
  --data-urlencode password=not-the-password
```

Response (HTTP 401):

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Incorrect email or password"
  }
}
```

### No token

```bash
curl -s http://localhost:8000/expenses
```

Response (HTTP 401):

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Not authenticated"
  }
}
```

### List categories

Set `TOKEN` to the `access_token` from the login. A new account starts with these defaults.

```bash
curl -s http://localhost:8000/categories \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```json
[
  {"id": 8, "name": "Education", "is_default": true, "created_at": "2026-10-10T14:12:51.968227Z"},
  {"id": 6, "name": "Entertainment", "is_default": true, "created_at": "2026-10-10T14:12:51.967230Z"},
  {"id": 1, "name": "Food", "is_default": true, "created_at": "2026-10-10T14:12:51.960935Z"},
  {"id": 5, "name": "Health", "is_default": true, "created_at": "2026-10-10T14:12:51.965738Z"},
  {"id": 3, "name": "Housing", "is_default": true, "created_at": "2026-10-10T14:12:51.963717Z"},
  {"id": 9, "name": "Other", "is_default": true, "created_at": "2026-10-10T14:12:51.968227Z"},
  {"id": 7, "name": "Shopping", "is_default": true, "created_at": "2026-10-10T14:12:51.967230Z"},
  {"id": 2, "name": "Transport", "is_default": true, "created_at": "2026-10-10T14:12:51.963717Z"},
  {"id": 4, "name": "Utilities", "is_default": true, "created_at": "2026-10-10T14:12:51.964717Z"}
]
```

### Create an expense

```bash
curl -s http://localhost:8000/expenses \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"amount": "620.00", "category_id": 2, "date": "2026-10-06", "note": "Cab to the airport", "payment_method": "upi"}'
```

Response (HTTP 201):

```json
{
  "id": 1,
  "amount": "620.00",
  "category_id": 2,
  "category_name": "Transport",
  "date": "2026-10-06",
  "note": "Cab to the airport",
  "payment_method": "upi",
  "created_at": "2026-10-10T14:12:53.982530Z",
  "updated_at": "2026-10-10T14:12:53.982530Z"
}
```

### Validation error

A negative amount, a date that does not exist and an unknown payment method, all reported at once.

```bash
curl -s http://localhost:8000/expenses \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"amount": -50, "category_id": 1, "date": "2026-02-30", "payment_method": "cheque"}'
```

Response (HTTP 422):

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      {"field": "body.amount", "message": "Input should be greater than 0"},
      {"field": "body.date", "message": "Input should be a valid date or datetime, day value is outside expected range"},
      {"field": "body.payment_method", "message": "Input should be 'cash', 'card', 'upi', 'bank_transfer', 'wallet' or 'other'"}
    ]
  }
}
```

### List expenses: filters and pagination

12 sample expenses exist at this point. This asks for Food expenses of 100 or more from the start of the month, two per page.

```bash
curl -s 'http://localhost:8000/expenses?date_from=2026-10-01&category_id=1&min_amount=100&page_size=2' \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```json
{
  "items": [
    {
      "id": 11,
      "amount": "349.50",
      "category_id": 1,
      "category_name": "Food",
      "date": "2026-10-05",
      "note": "Lunch with friends",
      "payment_method": "cash",
      "created_at": "2026-10-10T14:12:54.920439Z",
      "updated_at": "2026-10-10T14:12:54.920439Z"
    },
    {
      "id": 10,
      "amount": "1890.25",
      "category_id": 1,
      "category_name": "Food",
      "date": "2026-10-03",
      "note": "Monthly groceries",
      "payment_method": "upi",
      "created_at": "2026-10-10T14:12:54.830505Z",
      "updated_at": "2026-10-10T14:12:54.830505Z"
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 2,
  "pages": 1
}
```

### List expenses: text search and sorting

```bash
curl -s 'http://localhost:8000/expenses?q=groceries&sort=amount&order=desc' \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```json
{
  "items": [
    {
      "id": 6,
      "amount": "2610.40",
      "category_id": 1,
      "category_name": "Food",
      "date": "2026-09-03",
      "note": "Monthly groceries",
      "payment_method": "card",
      "created_at": "2026-10-10T14:12:54.464993Z",
      "updated_at": "2026-10-10T14:12:54.464993Z"
    },
    {
      "id": 3,
      "amount": "2350.75",
      "category_id": 1,
      "category_name": "Food",
      "date": "2026-08-04",
      "note": "Monthly groceries",
      "payment_method": "upi",
      "created_at": "2026-10-10T14:12:54.183721Z",
      "updated_at": "2026-10-10T14:12:54.183721Z"
    },
    {
      "id": 10,
      "amount": "1890.25",
      "category_id": 1,
      "category_name": "Food",
      "date": "2026-10-03",
      "note": "Monthly groceries",
      "payment_method": "upi",
      "created_at": "2026-10-10T14:12:54.830505Z",
      "updated_at": "2026-10-10T14:12:54.830505Z"
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

### Change an expense

Only the fields that are sent change.

```bash
curl -s http://localhost:8000/expenses/1 \
  -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"amount": "650.00", "note": "Cab to the airport (with toll)"}'
```

Response (HTTP 200):

```json
{
  "id": 1,
  "amount": "650.00",
  "category_id": 2,
  "category_name": "Transport",
  "date": "2026-10-06",
  "note": "Cab to the airport (with toll)",
  "payment_method": "upi",
  "created_at": "2026-10-10T14:12:53.982530Z",
  "updated_at": "2026-10-10T14:12:55.396918Z"
}
```

### Set a budget

```bash
curl -s http://localhost:8000/budgets \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"category_id": 2, "month": "2026-10", "amount": "500"}'
```

Response (HTTP 201):

```json
{
  "id": 3,
  "category_id": 2,
  "category_name": "Transport",
  "month": "2026-10",
  "amount": "500.00"
}
```

### Spent vs budget

Budgets exist for Food (4000), Housing (12000) and Transport (500). Shopping has no budget, so it is listed under `unbudgeted`.

```bash
curl -s 'http://localhost:8000/budgets/status?month=2026-10' \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```json
{
  "month": "2026-10",
  "items": [
    {
      "budget_id": 1,
      "category_id": 1,
      "category_name": "Food",
      "budget": "4000.00",
      "spent": "2239.75",
      "remaining": "1760.25",
      "percent_used": 56.0,
      "over_budget": false
    },
    {
      "budget_id": 2,
      "category_id": 3,
      "category_name": "Housing",
      "budget": "12000.00",
      "spent": "12000.00",
      "remaining": "0.00",
      "percent_used": 100.0,
      "over_budget": false
    },
    {
      "budget_id": 3,
      "category_id": 2,
      "category_name": "Transport",
      "budget": "500.00",
      "spent": "650.00",
      "remaining": "-150.00",
      "percent_used": 130.0,
      "over_budget": true
    }
  ],
  "totals": {
    "budget": "16500.00",
    "spent": "14889.75",
    "remaining": "1610.25",
    "percent_used": 90.2
  },
  "unbudgeted": [
    {"category_id": 7, "category_name": "Shopping", "spent": "1499.00"}
  ],
  "unbudgeted_spent": "1499.00",
  "total_spent": "16388.75"
}
```

### Summary: total per month

```bash
curl -s http://localhost:8000/summary/monthly \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```json
{
  "months": [
    {"month": "2026-08", "total": "14830.75", "count": 3},
    {"month": "2026-09", "total": "16959.40", "count": 4},
    {"month": "2026-10", "total": "16388.75", "count": 5}
  ],
  "total": "48178.90",
  "count": 12
}
```

### Summary: total per category

```bash
curl -s 'http://localhost:8000/summary/categories?date_from=2026-10-01' \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```json
{
  "date_from": "2026-10-01",
  "date_to": null,
  "categories": [
    {"category_id": 3, "category_name": "Housing", "total": "12000.00", "count": 1, "share": 73.2},
    {"category_id": 1, "category_name": "Food", "total": "2239.75", "count": 2, "share": 13.7},
    {"category_id": 7, "category_name": "Shopping", "total": "1499.00", "count": 1, "share": 9.1},
    {"category_id": 2, "category_name": "Transport", "total": "650.00", "count": 1, "share": 4.0}
  ],
  "total": "16388.75",
  "count": 5
}
```

### Summary: trends

`change_percent` is null for the first month because the month before it has no spending.

```bash
curl -s 'http://localhost:8000/summary/trends?months=3' \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```json
{
  "months": [
    {"month": "2026-08", "total": "14830.75", "count": 3, "change": "14830.75", "change_percent": null},
    {"month": "2026-09", "total": "16959.40", "count": 4, "change": "2128.65", "change_percent": 14.4},
    {"month": "2026-10", "total": "16388.75", "count": 5, "change": "-570.65", "change_percent": -3.4}
  ],
  "total": "48178.90",
  "average_monthly_total": "16059.63"
}
```

### CSV export

Takes the same filters as the list. Add `-o expenses.csv` to save it to a file.

```bash
curl -s 'http://localhost:8000/expenses/export?date_from=2026-10-01' \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```text
id,date,amount,category,payment_method,note
9,2026-10-01,12000.00,Housing,bank_transfer,Rent
10,2026-10-03,1890.25,Food,upi,Monthly groceries
11,2026-10-05,349.50,Food,cash,Lunch with friends
1,2026-10-06,650.00,Transport,upi,Cab to the airport (with toll)
12,2026-10-08,1499.00,Shopping,card,Running shoes
```

### Access control: another user's expense

A second account, `other@example.com`, asks for the first account's expense with its own valid token (`TOKEN` here is the second account's). The answer is the same as for an id that does not exist.

```bash
curl -s http://localhost:8000/expenses/1 \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 404):

```json
{
  "error": {
    "code": "not_found",
    "message": "Expense not found"
  }
}
```

### Access control: another user's list

The second account's own list is empty.

```bash
curl -s http://localhost:8000/expenses \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 200):

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 0
}
```

### Delete an expense

```bash
curl -s http://localhost:8000/expenses/1 \
  -X DELETE \
  -H "Authorization: Bearer $TOKEN"
```

Response (HTTP 204):

(empty body)
