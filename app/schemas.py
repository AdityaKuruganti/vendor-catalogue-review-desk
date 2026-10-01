"""Pydantic models shared by the workflow and the API."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- input ----------
class VendorRow(BaseModel):
    """One row from the vendor CSV."""

    sku: Optional[str] = None
    vendor: Optional[str] = None
    raw_row: str = Field(min_length=3, description="Raw, messy vendor product text")


class SingleListingRequest(BaseModel):
    raw_row: str = Field(
        min_length=3,
        examples=["Gents navy blue formal shirt made of pure linen fabric. Size XL available."],
    )


# ---------- workflow stage outputs ----------
class TitleSize(BaseModel):
    """Output of the demographic router branches (Women / Kids / Men)."""

    title: str = Field(description="Clean product title without size, price or SKU noise")
    size: str = Field(description="Standard size, e.g. S, M, L, XL, 4-5Y, Free Size")


class ListingCopy(BaseModel):
    """Output of Stage 4 (Hinglish description & fit generator)."""

    english_description: str = Field(description="Clear, natural product description in plain English")
    hinglish_description: str = Field(description="Engaging marketing copy in Hinglish")
    fit_guidance: str = Field(description="Specific sizing and fit recommendations for buyers")


# ---------- final object ----------
class ApprovedListingObject(BaseModel):
    title: str = Field(description="Clean standardized product title")
    color: str = Field(description="Normalized standard color name")
    fabric: str = Field(description="Normalized standard fabric/material name")
    demographic: Literal["MEN", "WOMEN", "KIDS"]
    size: str = Field(description="Standard size")
    english_description: str = ""  # default keeps older saved listings loadable
    hinglish_description: str
    fit_guidance: str


# ---------- API responses ----------
class RowResult(BaseModel):
    row_index: int
    sku: Optional[str] = None
    status: Literal["success", "error"]
    listing: Optional[ApprovedListingObject] = None
    error: Optional[str] = None


class BatchResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[RowResult]


class CsvPreviewResponse(BaseModel):
    total_rows: int
    rows: list[VendorRow]


# ---------- review desk ----------
class ListingEdit(BaseModel):
    """Fields a representative may correct before approving."""

    title: Optional[str] = None
    color: Optional[str] = None
    fabric: Optional[str] = None
    demographic: Optional[Literal["MEN", "WOMEN", "KIDS"]] = None
    size: Optional[str] = None
    english_description: Optional[str] = None
    hinglish_description: Optional[str] = None
    fit_guidance: Optional[str] = None


class Decision(BaseModel):
    decision: Literal["approved", "rejected", "pending"]
    note: Optional[str] = None
