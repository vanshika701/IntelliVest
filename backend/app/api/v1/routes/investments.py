"""Investment routes — mock one-time orders and SIPs (no real payments)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id
from app.schemas.instrument import InstrumentType
from app.schemas.investment import (
    InvestmentAccount,
    InvestmentResponse,
    OneTimeOrderCreate,
    PaymentResultIn,
    Portfolio,
    SipCreate,
)
from app.services.instrument_service import DataProviderError, InstrumentNotFound
from app.services.investment_service import (
    InvestmentNotFound,
    InvestmentValidationError,
    create_one_time_order,
    create_sip,
    list_accounts,
    list_investments,
    record_payment_result,
)
from app.services.portfolio_service import get_portfolio

router = APIRouter(prefix="/investments", tags=["investments"])


async def _guard(call):
    try:
        return await call
    except InvestmentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except (InstrumentNotFound, InvestmentNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    except DataProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None


@router.get("/accounts", response_model=list[InvestmentAccount])
async def get_accounts(
    instrument_type: InstrumentType | None = Query(default=None),
    _user_id: str = Depends(get_current_user_id),
):
    return list_accounts(instrument_type)


@router.get("", response_model=list[InvestmentResponse])
async def get_investments(user_id: str = Depends(get_current_user_id)):
    return await list_investments(user_id)


@router.get("/portfolio", response_model=Portfolio)
async def get_user_portfolio(user_id: str = Depends(get_current_user_id)):
    return await get_portfolio(user_id)


@router.post("/one-time", response_model=InvestmentResponse, status_code=status.HTTP_201_CREATED)
async def post_one_time(body: OneTimeOrderCreate, user_id: str = Depends(get_current_user_id)):
    return await _guard(create_one_time_order(user_id, body.instrument_id, body.amount, body.account_id))


@router.post("/sip", response_model=InvestmentResponse, status_code=status.HTTP_201_CREATED)
async def post_sip(body: SipCreate, user_id: str = Depends(get_current_user_id)):
    return await _guard(create_sip(user_id, body.instrument_id, body.amount, body.account_id, body.day_of_month))


@router.post("/{investment_id}/payment-result", response_model=InvestmentResponse)
async def post_payment_result(
    investment_id: str, body: PaymentResultIn, user_id: str = Depends(get_current_user_id)
):
    # TODO(mock): trusts the client's result; with Razorpay, verify the
    # payment signature server-side instead.
    return await _guard(
        record_payment_result(user_id, investment_id, body.status, body.reference, body.failure_reason)
    )
