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
        json={"amount": 500, "description": "Big Basket order", "category": "groceries"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == 500
    assert body["category"] == "groceries"
    assert body["expense_type"] == "expense"
    assert "category_source" not in body
    assert "id" in body
    assert "created_at" in body
    assert "date" in body


def test_create_expense_accepts_category_display_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 250, "description": "Dinner", "category": "Food & Dining Out"},
    )
    assert response.status_code == 201
    assert response.json()["category"] == "food_dining"


def test_create_expense_requires_a_category_from_the_list(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Phase 8: no auto-categorization. A missing or unknown category is a
    validation error, not a guess."""
    missing = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 250, "description": "Starbucks"},
    )
    unknown = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 250, "description": "Starbucks", "category": "Coffee"},
    )
    assert missing.status_code == 422
    assert unknown.status_code == 422


def test_income_always_gets_the_income_category(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 50000, "description": "Salary", "expense_type": "income", "income_source": "salary"},
    )
    assert response.status_code == 201
    assert response.json()["category"] == "income"


def test_categorization_model_endpoint_is_gone(client: TestClient) -> None:
    assert client.get("/api/v1/expenses/categorization-model-info").status_code in (401, 404, 405)


def test_list_expenses_returns_created_expense(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 100, "description": "Coffee", "category": "food_dining"},
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
        json={"amount": 100, "description": "Coffee", "category": "food_dining"},
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
        json={"amount": 1000, "description": "Salary", "expense_type": "income", "income_source": "salary"},
    )
    client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 200, "description": "Groceries", "category": "groceries", "expense_type": "expense"},
    )

    response = client.get("/api/v1/expenses/summary", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_income"] == 1000
    assert body["total_expense"] == 200
    assert body["net"] == 800
    # Income must not show up in the spending-by-category breakdown.
    assert body["by_category"] == {"groceries": 200}


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
    # "Fitness" is mapped onto the fixed list (label mapping, not ML).
    assert listed["items"][0]["category"] == "health_insurance"
    assert listed["items"][0]["expense_type"] == "expense"


def test_csv_upload_maps_labels_and_never_guesses_from_description(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Category labels map onto the fixed list; rows with no label go to
    Other even when the description looks obvious (no auto-categorization)."""
    csv_content = (
        "Date,Description,Category,Amount\n"
        "2026-01-05,Uber ride,,350\n"
        "2026-01-06,Flat rent,Rent,20000\n"
        "2026-01-07,Weird,Something Else,10\n"
    )
    response = client.post(
        "/api/v1/expenses/upload-csv",
        headers=auth_headers,
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 3

    listed = client.get("/api/v1/expenses", headers=auth_headers).json()
    by_desc = {item["description"]: item["category"] for item in listed["items"]}
    assert by_desc == {"Uber ride": "other", "Flat rent": "housing", "Weird": "other"}


def test_csv_upload_rejects_non_csv_files(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/expenses/upload-csv",
        headers=auth_headers,
        files={"file": ("statement.txt", "not a csv", "text/plain")},
    )

    assert response.status_code == 400


def _income(client, headers, **extra):
    return client.post(
        "/api/v1/expenses",
        headers=headers,
        json={"amount": 1000, "description": "x", "expense_type": "income", **extra},
    )


def test_income_needs_a_known_source(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert _income(client, auth_headers).status_code == 422
    assert _income(client, auth_headers, income_source="lottery").status_code == 422
    for source in ("bonus", "dividends", "freelance"):
        assert _income(client, auth_headers, income_source=source).json()["income_source"] == source
    summary = client.get("/api/v1/expenses/summary", headers=auth_headers).json()
    assert summary["by_income_source"] == {"bonus": 1000, "dividends": 1000, "freelance": 1000}


def test_csv_income_source_comes_from_the_label_only(client: TestClient, auth_headers: dict[str, str]) -> None:
    csv_content = (
        "Date,Description,Category,Type,Amount\n"
        "2026-01-05,A,Salary,Income,50000\n"
        "2026-01-06,B,Dividend,Income,500\n"
        "2026-01-07,Salary credit,,Income,10\n"
    )
    client.post(
        "/api/v1/expenses/upload-csv", headers=auth_headers, files={"file": ("s.csv", csv_content, "text/csv")}
    )
    items = client.get("/api/v1/expenses", headers=auth_headers).json()["items"]
    assert {i["description"]: i["income_source"] for i in items} == {
        "A": "salary",
        "B": "dividends",
        "Salary credit": "other_income",
    }


def test_update_expense(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/expenses",
        headers=auth_headers,
        json={"amount": 100, "description": "Coffee", "category": "other"},
    ).json()
    url = f"/api/v1/expenses/{created['id']}"
    body = client.patch(url, headers=auth_headers, json={"category": "food_dining"}).json()
    assert body["category"] == "food_dining" and body["amount"] == 100

    assert client.patch(url, headers=auth_headers, json={"category": "nope"}).status_code == 422
    assert client.patch(url, headers=auth_headers, json={"income_source": "salary"}).status_code == 422
    assert client.patch("/api/v1/expenses/bad-id", headers=auth_headers, json={"amount": 1}).status_code == 404

    creds = {"email": "b@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json={**creds, "full_name": "B", "date_of_birth": "2000-05-17"})
    token = client.post("/api/v1/auth/login", json=creds).json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.patch(url, headers=other, json={"amount": 1}).status_code == 404

    income = _income(client, auth_headers, income_source="salary").json()
    income_url = f"/api/v1/expenses/{income['id']}"
    updated = client.patch(income_url, headers=auth_headers, json={"income_source": "bonus"}).json()
    assert updated["income_source"] == "bonus"
    assert client.patch(income_url, headers=auth_headers, json={"category": "groceries"}).status_code == 422
