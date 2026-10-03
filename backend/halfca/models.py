"""Pydantic API models. Mirrored by hand in frontend/lib/api.ts; keep the two in step."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# ── dataset ──────────────────────────────────────────────────────────────────


class SourceFile(BaseModel):
    kind: str  # invoices | bank | ledger | ims | eway
    filename: str
    records: int


class DatasetInfo(BaseModel):
    dataset_id: str
    scenario: str  # demo | random | upload
    seed: int | None
    period: str
    as_of: str
    user_gstin: str
    user_name: str
    sources: list[SourceFile]
    counts: dict[str, int]
    uploaded_files: list[str] = []


# ── evidence and flags ───────────────────────────────────────────────────────


class EvidenceLink(BaseModel):
    source: str  # invoice | ledger | bank | ims | ewb | toll | graph
    id: str
    label: str
    fields: dict[str, Any]


class Evidence(BaseModel):
    summary: str
    recorded: dict[str, Any]
    expected: dict[str, Any]
    chain: list[EvidenceLink]
    notes: list[str]


class FlagOut(BaseModel):
    flag_id: str
    kind: str
    category: str
    label: str
    invoice_id: str | None
    ref: str
    counterparty: str
    gstin: str | None
    title: str
    recorded: str | None
    expected: str | None
    impact: float
    severity: str
    evidence: Evidence


class TypeCount(BaseModel):
    kind: str
    label: str
    count: int


# ── summary / overview ───────────────────────────────────────────────────────


class Kpis(BaseModel):
    reconciled: int
    matched: int
    discrepancies: int
    duplicates: int
    unmatched: int
    exposure: float
    clean_match_pct: float


class Slice(BaseModel):
    key: str
    label: str
    value: float


class PhysicalCounts(BaseModel):
    checked: int
    verified: int
    failed: int
    failed_inside_matched: int
    by_verdict: dict[str, int]


class ImsCounts(BaseModel):
    records: int
    accept: int
    reject: int
    pending: int
    approved: int = 0


class LiabilitySummary(BaseModel):
    output_tax_filed: float
    output_tax_reconciled: float
    under_reported_output: float
    itc_claimed: float
    itc_rejected: float
    itc_at_risk: float
    itc_eligible: float
    net_payable_filed: float
    net_payable_reconciled: float
    exposure: float


class LlmInfo(BaseModel):
    provider: str | None
    model: str | None
    stage4_skipped: bool


class Summary(BaseModel):
    dataset: DatasetInfo
    kpis: Kpis
    donut: list[Slice]
    discrepancy_types: list[TypeCount]
    tax_errors: dict[str, int]
    physical: PhysicalCounts
    ims: ImsCounts
    liability: LiabilitySummary
    rings: list[list[str]]
    at_risk_suppliers: list[str]
    gaps: dict[str, int]
    anomalies: dict[str, int]
    gstins: dict[str, int]
    llm: LlmInfo
    examples: dict[str, str | None]  # all_clear / road_fail invoice ids for the threads card


# ── matching ─────────────────────────────────────────────────────────────────


class FunnelStage(BaseModel):
    stage: int
    label: str
    method: str
    records_in: int
    paired: int
    left: int
    skipped: bool


class UnmatchedItem(BaseModel):
    invoice_id: str
    invoice_no: str
    invoice_date: str
    direction: str
    counterparty: str
    total: float
    paid: bool


class Funnel(BaseModel):
    stages: list[FunnelStage]
    unmatched: list[UnmatchedItem]
    llm: LlmInfo


class DiscrepancyList(BaseModel):
    counts: list[TypeCount]
    items: list[FlagOut]


# ── invoice detail (all four threads) ────────────────────────────────────────


class InvoiceDetail(BaseModel):
    invoice: dict[str, Any]
    status: str
    stage: int | None
    match_reason: str | None
    voucher: dict[str, Any] | None
    payments: list[dict[str, Any]]
    ims: dict[str, Any] | None
    physical: dict[str, Any] | None
    flags: list[FlagOut]


# ── follow the goods ─────────────────────────────────────────────────────────


class CityOut(BaseModel):
    name: str
    state_code: str
    x: float
    y: float
    hub: bool = False
    minor: bool = False


class RoutePlazaOut(BaseModel):
    id: str
    name: str
    frac: float
    km: float


class RouteOut(BaseModel):
    id: str
    name: str
    highway: str
    origin: str
    destination: str
    distance_km: float
    svg_path: str
    stops: dict[str, float]
    plazas: list[RoutePlazaOut]


class Crossing(BaseModel):
    plaza_id: str
    plaza_name: str
    crossed_at: str
    km: float


class GoodsInvoice(BaseModel):
    invoice_id: str
    invoice_no: str
    invoice_date: str
    supplier: str
    supplier_gstin: str
    total: float
    verdict: str
    ewb_no: str | None
    ewb_doc_no: str | None
    vehicle_no: str | None
    route_id: str | None
    from_city: str | None
    distance_km: float | None
    generated_at: str | None
    window_hours: float | None
    plazas_expected: int | None
    tolls_crossed: int
    speed_kmh: float | None
    trip_minutes: float | None
    crossings: list[Crossing]
    recycled_with: list[str]


class Beat(BaseModel):
    kind: str  # verified | paper_only | impossible_journey | recycled_ewb
    invoice_ids: list[str]


class Goods(BaseModel):
    view_box: list[int]
    cities: list[CityOut]
    routes: list[RouteOut]
    verdicts: dict[str, int]
    invoices: list[GoodsInvoice]
    beats: list[Beat]


class GoodsDetail(BaseModel):
    trip: GoodsInvoice
    flags: list[FlagOut]


# ── follow the credit ────────────────────────────────────────────────────────


class GraphNode(BaseModel):
    gstin: str
    name: str
    city: str | None
    role: str  # you | supplier | upstream
    slot: str  # you | at_risk | supplier | upstream | ring
    risk: float
    own_risk: float
    ring: int | None
    hops_up: int | None
    at_risk: bool
    signals: list[str]
    feeds: str | None = None  # for upstream nodes in the focus view: which supplier they sell to


class GraphEdge(BaseModel):
    seller: str
    buyer: str
    invoices: int
    value: float
    ring_edge: bool


class CreditGraph(BaseModel):
    scope: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    cycles: list[list[str]]
    focus: str | None
    threshold: float


class SupplierInvoice(BaseModel):
    invoice_id: str
    invoice_no: str
    invoice_date: str
    total: float
    itc: float
    ims_decision: str | None


class BenfordOut(BaseModel):
    gstin: str
    name: str
    n: int
    mad: float
    threshold: float
    nonconforming: bool
    observed: list[float]
    expected: list[float]


class SupplierRisk(BaseModel):
    gstin: str
    name: str
    city: str | None
    state: str | None
    risk: float
    own_risk: float
    at_risk: bool
    signals: list[str]
    ring_members: list[str]
    ring_signals: list[str]
    hops_to_you: int | None
    path: list[str]
    invoices: list[SupplierInvoice]
    itc_at_risk: float
    benford: BenfordOut | None
    action: str
    flag: FlagOut | None


# ── IMS ──────────────────────────────────────────────────────────────────────


class ImsRecord(BaseModel):
    ims_id: str
    invoice_id: str | None
    supplier_gstin: str
    supplier_name: str
    invoice_no: str
    invoice_date: str
    taxable_value: float
    itc: float
    decision: str
    rule: str
    reason: str
    taint: float
    approved: bool


class ImsOut(BaseModel):
    records: list[ImsRecord]
    counts: ImsCounts
    gstr2b_date: str
    approved_at: str | None


class ApproveIn(BaseModel):
    ims_ids: list[str] | None = None  # default: every Accept


class ApproveOut(BaseModel):
    approved: int
    rejected: int
    pending: int
    approved_at: str
    message: str


# ── liability ────────────────────────────────────────────────────────────────


class WaterfallStep(BaseModel):
    step: str
    value: float
    kind: str  # total | delta


class HeadRow(BaseModel):
    head: str
    output_filed: float
    output_reconciled: float
    itc_claimed: float
    itc_eligible: float
    net_filed: float
    net_reconciled: float


class LiabilityOut(BaseModel):
    summary: LiabilitySummary
    waterfall: list[WaterfallStep]
    heads: list[HeadRow]
    benford_focus: str | None


# ── jobs (upload / demo / reset / reconcile) ─────────────────────────────────


class JobStep(BaseModel):
    key: str
    label: str
    state: str  # pending | running | done | skipped | error
    detail: str | None


class JobFile(BaseModel):
    name: str
    kind: str | None
    records: int | None
    note: str | None


class JobOut(BaseModel):
    job_id: str
    kind: str  # upload | demo | reset | reconcile
    status: str  # running | done | error
    steps: list[JobStep]
    files: list[JobFile]
    error: str | None
    kpis: Kpis | None
    started_at: str
    finished_at: str | None
