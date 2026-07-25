from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.dependencies import database
from app.schemas import SupplierQuoteCreate, SupplierQuoteUpdate


router = APIRouter(prefix="/api/v1/supplier-quotes", tags=["supplier quotes"])


@router.get("")
async def list_supplier_quotes(
    vehicle_id: str = Query(min_length=1),
    oem_number: str = Query(min_length=1),
) -> list[dict[str, Any]]:
    return database.list_supplier_quotes(vehicle_id, oem_number)


@router.post("", status_code=201)
async def create_supplier_quote(
    payload: SupplierQuoteCreate,
) -> dict[str, Any]:
    try:
        return database.create_supplier_quote(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{quote_id}")
async def update_supplier_quote(
    quote_id: str,
    payload: SupplierQuoteUpdate,
) -> dict[str, Any]:
    try:
        quote = database.update_supplier_quote(
            quote_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if quote is None:
        raise HTTPException(status_code=404, detail="Supplier quote not found")
    return quote


@router.delete("/{quote_id}", status_code=204)
async def delete_supplier_quote(quote_id: str) -> Response:
    if not database.delete_supplier_quote(quote_id):
        raise HTTPException(status_code=404, detail="Supplier quote not found")
    return Response(status_code=204)
