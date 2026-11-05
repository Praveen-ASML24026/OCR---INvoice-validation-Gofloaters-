from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class Invoice(BaseModel):
    number: Optional[str] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    place_of_supply: Optional[str] = None


class Party(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    gstin: Optional[str] = None


class Tax(BaseModel):
    taxable_amount: Optional[float] = None
    cgst: Optional[float] = None
    sgst: Optional[float] = None
    igst: Optional[float] = None
    total: Optional[float] = None


class LineItem(BaseModel):
    description: str
    hsn_sac: Optional[str] = None
    quantity: Optional[float] = None
    rate: Optional[float] = None
    amount: Optional[float] = None


class Issue(BaseModel):
    code: str                                   # REQ1 / REQ2 / REQ4 / EXTRACT
    type: Literal["error", "unverified"]
    message: str                                # plain-English reason
    values: Dict[str, Any] = {}                 # the values that caused it


class Validation(BaseModel):
    valid: bool
    status: Literal["valid", "invalid", "incomplete"]
    summary: str = ""
    errors: List[str] = []
    unverified: List[str] = []
    issues: List[Issue] = []


class InvoiceData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    invoice: Invoice
    operator: Party
    gofloaters: Party
    tax: Tax
    line_items: List[LineItem] = []
    validation: Validation
    confidence: Optional[Dict[str, Any]] = None
    extraction_sources: Dict[str, Any] = {}
    missing_after_extraction: List[str] = []
    warnings: List[str] = []
    evidence: Dict[str, Any] = {}
    step_timings_ms: Optional[Dict[str, float]] = None


class ExtractResponse(BaseModel):
    request_id: str
    filename: str
    status: Literal["ok", "needs_review"]      # needs_review = some key fields not found
    elapsed_ms: int
    data: InvoiceData


class ErrorResponse(BaseModel):
    request_id: str
    error: str
    detail: str
