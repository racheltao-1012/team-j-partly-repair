from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from pydantic.networks import AnyHttpUrl


class VehicleCapabilities(BaseModel):
    damage_prediction: bool = False
    oem_parts: bool = False
    diagram: bool = False


class VehicleCreate(BaseModel):
    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1886, le=2100)
    trim: str = Field(default="", max_length=100)
    vin: str = Field(default="", max_length=40)


class VehicleResponse(VehicleCreate):
    id: str
    provider_key: str
    display_name: str
    source: Literal["partly", "local_catalogue"]
    capabilities: VehicleCapabilities
    part_count: int = 0
    diagram_count: int = 0
    has_prediction: bool = False


class PartCreate(BaseModel):
    part_name: str = Field(min_length=1, max_length=200)
    oem_number: str = Field(min_length=1, max_length=120)
    category: str = Field(default="", max_length=100)
    diagram_url: AnyHttpUrl | None = None


class CaseItem(BaseModel):
    source: Literal[
        "ai_prediction",
        "visible_damage",
        "impact_path",
        "historical_case",
        "catalogue_candidate",
        "manual",
    ] = "manual"
    raw_part_name: str = ""
    predicted_part_id: str | None = None
    predicted_part_name: str = ""
    oem_number: str | None = None
    diagram_id: str | None = None
    diagram_url: str | None = None
    ai_confidence: float | None = Field(default=None, ge=0, le=1)
    ai_action: str = "Inspect"
    technician_decision: str = "Pending"
    rejection_reason: str = ""
    corrected_part_id: str = ""
    corrected_part_name: str = ""
    technician_note: str = ""
    hotspot: dict[str, Any] | None = None
    damage_type: str = ""
    severity: float | None = Field(default=None, ge=0, le=1)
    evidence_image_id: str | None = None
    evidence_image_url: str | None = None
    evidence_box: dict[str, float] | None = None
    reason: str = ""
    propagation_path: list[str] = Field(default_factory=list)
    probability_band: str = ""
    catalogue_match_score: float | None = Field(default=None, ge=0, le=1)
    historical_support_count: int = Field(default=0, ge=0)
    similar_case_ids: list[str] = Field(default_factory=list)


class ManualRegion(BaseModel):
    diagram_id: str | None = None
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)
    technician_note: str = ""


StockStatus = Literal["unknown", "in_stock", "out_of_stock", "backorder"]


class SupplierQuoteCreate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=200)
    oem_number: str = Field(min_length=1, max_length=120)
    part_name: str = Field(default="", max_length=200)
    supplier: str = Field(default="", max_length=160)
    unit_price: float = Field(gt=0)
    currency: str = Field(default="NZD", pattern=r"^[A-Z]{3}$")
    stock_status: StockStatus = "unknown"
    stock_quantity: int | None = Field(default=None, ge=0)
    estimated_arrival: date | None = None
    notes: str = Field(default="", max_length=1000)
    is_preferred: bool = False

    @model_validator(mode="after")
    def validate_stock(self) -> "SupplierQuoteCreate":
        if self.stock_status == "in_stock":
            if self.stock_quantity is None or self.stock_quantity < 1:
                raise ValueError(
                    "Stock quantity must be at least 1 when availability is in stock"
                )
        elif self.stock_status == "out_of_stock":
            self.stock_quantity = 0
        else:
            # Unknown and backorder are not quantity claims.
            self.stock_quantity = None
        return self


class SupplierQuoteUpdate(BaseModel):
    part_name: str | None = Field(default=None, max_length=200)
    supplier: str | None = Field(default=None, max_length=160)
    unit_price: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    stock_status: StockStatus | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    estimated_arrival: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    is_preferred: bool | None = None


class CaseCreate(BaseModel):
    vehicle_slug: str
    vehicle_make: str = ""
    vehicle_model: str = ""
    vehicle_year: str = ""
    vehicle_trim: str = ""
    vin: str = ""
    status: str = "Reviewed"
    photo_run_id: str | None = None
    items: list[CaseItem]
    manual_regions: list[ManualRegion] = Field(default_factory=list)
    quote_ids: list[str] = Field(default_factory=list)
