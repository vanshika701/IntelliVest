"""Service layer for the mock invest flow.

TODO(mock): nothing here moves money or talks to an AMC/broker. Orders and
SIPs are stored so the UI can show confirmations and a "My investments"
list. When Razorpay is integrated, `record_payment_result` must stop
trusting the client's result and instead verify the Razorpay payment
signature (or receive a webhook) server-side.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.data.investment_repository import (
    get_user_investment,
    insert_investment,
    list_user_investments,
    update_investment_if_status,
)
from app.services.instrument_service import get_instrument

IST = ZoneInfo("Asia/Kolkata")

# TODO(mock): the app has no real brokerage/folio accounts; this demo list
# stands in for them.
DEMO_ACCOUNTS = [
    {"id": "demo-folio-1", "label": "MF folio 1029384756", "kind": "folio", "supports": ["MF"]},
    {"id": "demo-folio-new", "label": "New folio", "kind": "folio", "supports": ["MF"]},
    {"id": "demo-demat-1", "label": "Demat ••••4821", "kind": "demat", "supports": ["STOCK", "ETF"]},
]

_PENDING_STATUS = {"one_time": "pending_payment", "sip": "pending_mandate"}
_SUCCESS_STATUS = {"one_time": "completed", "sip": "active"}


class InvestmentValidationError(Exception):
    pass


class InvestmentNotFound(Exception):
    pass


def list_accounts(instrument_type: str | None = None) -> list[dict]:
    accounts = [{**a, "is_demo": True} for a in DEMO_ACCOUNTS]
    if instrument_type:
        accounts = [a for a in accounts if instrument_type in a["supports"]]
    return accounts


def next_installment_date(day_of_month: int, today: date) -> date:
    """The next date on `day_of_month` strictly after today (day_of_month
    is 1–28, so it exists in every month)."""
    candidate = today.replace(day=day_of_month)
    if candidate > today:
        return candidate
    first_of_next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first_of_next_month.replace(day=day_of_month)


def installment_dates(sip: dict, today: date) -> list[date]:
    """Due dates up to today. The stored date is the first instalment."""
    due, out = date.fromisoformat(sip["next_installment_date"]), []
    while due <= today:
        out.append(due)
        due = next_installment_date(sip["day_of_month"], due)
    return out


async def _create(user_id: str, kind: str, instrument_id: str, amount: float, account_id: str, **extra) -> dict:
    instrument = await get_instrument(instrument_id)
    stats = instrument["stats"]
    minimum = stats["min_sip"] if kind == "sip" else stats["min_investment"]
    if minimum is not None and amount < minimum:
        label = "SIP" if kind == "sip" else "investment"
        raise InvestmentValidationError(f"Minimum {label} for this instrument is ₹{minimum:,.0f}")

    account = next((a for a in DEMO_ACCOUNTS if a["id"] == account_id), None)
    if account is None or instrument["type"] not in account["supports"]:
        raise InvestmentValidationError("This account can't hold this instrument")

    now = datetime.now(UTC)
    price = instrument["price"]
    return await insert_investment(
        {
            "user_id": user_id,
            "kind": kind,
            "status": _PENDING_STATUS[kind],
            "instrument_id": instrument_id,
            "instrument_name": instrument["name"],
            "instrument_type": instrument["type"],
            "amount": round(amount, 2),
            "account_id": account_id,
            "account_label": account["label"],
            "price_at_order": price,
            "estimated_units": round(amount / price, 4) if price else None,
            "is_mock": True,
            "created_at": now,
            "updated_at": now,
            **extra,
        }
    )


async def create_one_time_order(user_id: str, instrument_id: str, amount: float, account_id: str) -> dict:
    return await _create(user_id, "one_time", instrument_id, amount, account_id)


async def create_sip(user_id: str, instrument_id: str, amount: float, account_id: str, day_of_month: int) -> dict:
    return await _create(user_id, "sip", instrument_id, amount, account_id, day_of_month=day_of_month)


async def record_payment_result(
    user_id: str, investment_id: str, status: str, reference: str | None, failure_reason: str | None
) -> dict:
    investment = await get_user_investment(user_id, investment_id)
    if investment is None:
        raise InvestmentNotFound(investment_id)

    kind = investment["kind"]
    changes: dict = {"updated_at": datetime.now(UTC), "payment_reference": reference}
    if status == "success":
        changes["status"] = _SUCCESS_STATUS[kind]
        if kind == "sip":
            changes["next_installment_date"] = next_installment_date(
                investment["day_of_month"], datetime.now(IST).date()
            ).isoformat()
    else:
        changes["status"] = "failed"
        changes["failure_reason"] = failure_reason or "Payment failed"

    updated = await update_investment_if_status(user_id, investment_id, _PENDING_STATUS[kind], changes)
    if updated is None:
        raise InvestmentValidationError(f"This {kind.replace('_', '-')} order is already {investment['status']}")
    return updated


async def list_investments(user_id: str) -> list[dict]:
    today = datetime.now(IST).date()
    items = await list_user_investments(user_id)
    for item in items:
        # Stored once, as the first instalment; show the upcoming one.
        if item["status"] == "active" and item["next_installment_date"] <= today.isoformat():
            item["next_installment_date"] = next_installment_date(item["day_of_month"], today).isoformat()
    return items
