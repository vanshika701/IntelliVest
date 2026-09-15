"""Integration tests for expense CRUD, summary, and CSV import — exercises
the full route -> service -> repository -> DB stack.
"""

from fastapi.testclient import TestClient


def test_create_expense_returns_a_valid_response(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Regression test for a real bug found in review: the route used to
    return a dict missing `created_at`, which FastAPI's response_model
    validation rejects — every create silently 500'd."""
    response = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 500, "description": "Groceries", "category": "Food"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == 500
    assert body["category"] == "Food"
    assert body["expense_type"] == "expense"
    assert "id" in body
    assert "created_at" in body
    assert "date" in body


def test_list_expenses_returns_created_expense(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 100, "description": "Coffee", "category": "Food"},
    )

    response = client.get("/api/v1/expenses", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["description"] == "Coffee"


def test_delete_expense_removes_it(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 100, "description": "Coffee", "category": "Food"},
    ).json()

    response = client.delete(f"/api/v1/expenses/{created['id']}", headers=auth_headers)
    assert response.status_code == 204

    listed = client.get("/api/v1/expenses", headers=auth_headers).json()
    assert listed["total"] == 0


def test_summary_aggregates_income_and_expense(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 1000, "description": "Salary", "category": "Salary", "expense_type": "income"},
    )
    client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 200, "description": "Groceries", "category": "Food", "expense_type": "expense"},
    )

    response = client.get("/api/v1/expenses/summary", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_income"] == 1000
    assert body["total_expense"] == 200
    assert body["net"] == 800


def test_sample_csv_download_is_a_valid_csv(client: TestClient) -> None:
    response = client.get("/api/v1/expenses/sample-csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Date,Description,Category,Type,Amount" in response.text


def test_csv_upload_parses_amount_column_and_type_direction(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Regression test: a dedicated Type column with Income/Expense values
    should set expense_type, not get treated as a category label."""
    csv_content = (
        "Date,Description,Category,Type,Amount\n"
        "2026-01-05,Salary,Salary,Income,50000\n"
        "2026-01-07,Groceries,Food,Expense,1500\n"
    )
    response = client.post(
        "/api/v1/expenses/upload-csv",
        headers=auth_headers,
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0

    listed = client.get("/api/v1/expenses", headers=auth_headers).json()
    types_by_desc = {item["description"]: item["expense_type"] for item in listed["items"]}
    assert types_by_desc["Salary"] == "income"
    assert types_by_desc["Groceries"] == "expense"


def test_csv_upload_uses_type_column_as_category_when_not_a_direction_word(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A Type column whose values are category labels (not Income/Expense)
    should fall back to being used as the category, as before."""
    csv_content = "Date,Description,Type,Amount\n2026-01-05,Gym membership,Fitness,1200\n"
    response = client.post(
        "/api/v1/expenses/upload-csv",
        headers=auth_headers,
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1

    listed = client.get("/api/v1/expenses", headers=auth_headers).json()
    assert listed["items"][0]["category"] == "Fitness"
    assert listed["items"][0]["expense_type"] == "expense"


def test_csv_upload_rejects_non_csv_files(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/expenses/upload-csv",
        headers=auth_headers,
        files={"file": ("statement.txt", "not a csv", "text/plain")},
    )

    assert response.status_code == 400
