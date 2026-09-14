"""Expense routes — CRUD + CSV upload + spending summary."""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.api.deps import get_current_user_id
from app.schemas.expense import CsvUploadResult, ExpenseCreate, ExpenseResponse, ExpenseSummary
from app.services.expense_service import add_expense, import_csv, list_expenses, remove_expense, summarize_expenses

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=dict)
async def get_expenses(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
):
    return await list_expenses(user_id, skip=skip, limit=limit)


@router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(body: ExpenseCreate, user_id: str = Depends(get_current_user_id)):
    expense_id = await add_expense(user_id, body.model_dump())
    return {
        "id": expense_id,
        "user_id": user_id,
        **body.model_dump(),
    }


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(expense_id: str, user_id: str = Depends(get_current_user_id)):
    deleted = await remove_expense(user_id, expense_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")


@router.post("/upload-csv", response_model=CsvUploadResult)
async def upload_csv(file: UploadFile, user_id: str = Depends(get_current_user_id)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV files are accepted")
    contents = await file.read()
    return await import_csv(user_id, contents)


@router.get("/summary", response_model=ExpenseSummary)
async def get_summary(user_id: str = Depends(get_current_user_id)):
    return await summarize_expenses(user_id)
