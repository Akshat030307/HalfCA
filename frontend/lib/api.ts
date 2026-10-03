// Typed client for the Half CA API. Mirrors backend/halfca/models.py; keep the two in step.

// ── dataset ──────────────────────────────────────────────────────────────────
export type SourceFile = { kind: string; filename: string; records: number };

export type DatasetInfo = {
  dataset_id: string;
  scenario: "demo" | "random" | "upload" | string;
  seed: number | null;
  period: string;
  as_of: string;
  user_gstin: string;
  user_name: string;
  sources: SourceFile[];
  counts: Record<string, number>;
  uploaded_files: string[];
};

// ── evidence and flags ───────────────────────────────────────────────────────
export type EvidenceLink = {
  source: "invoice" | "ledger" | "bank" | "ims" | "ewb" | "toll" | "graph" | string;
  id: string;
  label: string;
  fields: Record<string, unknown>;
};

export type Evidence = {
  summary: string;
  recorded: Record<string, unknown>;
  expected: Record<string, unknown>;
  chain: EvidenceLink[];
  notes: string[];
};

export type Flag = {
  flag_id: string;
  kind: string;
  category: string;
  label: string;
  invoice_id: string | null;
  ref: string;
  counterparty: string;
  gstin: string | null;
  title: string;
  recorded: string | null;
  expected: string | null;
  impact: number;
  severity: "low" | "medium" | "high" | string;
  evidence: Evidence;
};

export type TypeCount = { kind: string; label: string; count: number };

// ── summary ──────────────────────────────────────────────────────────────────
export type Kpis = {
  reconciled: number;
  matched: number;
  discrepancies: number;
  duplicates: number;
  unmatched: number;
  exposure: number;
  clean_match_pct: number;
};

export type Slice = { key: string; label: string; value: number };

export type LiabilitySummary = {
  output_tax_filed: number;
  output_tax_reconciled: number;
  under_reported_output: number;
  itc_claimed: number;
  itc_rejected: number;
  itc_at_risk: number;
  itc_eligible: number;
  net_payable_filed: number;
  net_payable_reconciled: number;
  exposure: number;
};

export type LlmInfo = { provider: string | null; model: string | null; stage4_skipped: boolean };

export type ImsCounts = {
  records: number;
  accept: number;
  reject: number;
  pending: number;
  approved: number;
};

export type Summary = {
  dataset: DatasetInfo;
  kpis: Kpis;
  donut: Slice[];
  discrepancy_types: TypeCount[];
  tax_errors: Record<string, number>;
  physical: {
    checked: number;
    verified: number;
    failed: number;
    failed_inside_matched: number;
    by_verdict: Record<string, number>;
  };
  ims: ImsCounts;
  liability: LiabilitySummary;
  rings: string[][];
  at_risk_suppliers: string[];
  gaps: Record<string, number>;
  anomalies: Record<string, number>;
  gstins: Record<string, number>;
  llm: LlmInfo;
};

// ── matching ─────────────────────────────────────────────────────────────────
export type FunnelStage = {
  stage: number;
  label: string;
  method: string;
  records_in: number;
  paired: number;
  left: number;
  skipped: boolean;
};

export type UnmatchedItem = {
  invoice_id: string;
  invoice_no: string;
  invoice_date: string;
  direction: "inward" | "outward";
  counterparty: string;
  total: number;
  paid: boolean;
};

export type Funnel = { stages: FunnelStage[]; unmatched: UnmatchedItem[]; llm: LlmInfo };
export type DiscrepancyList = { counts: TypeCount[]; items: Flag[] };

export type InvoiceDetail = {
  invoice: Record<string, unknown>;
  status: "matched" | "discrepant" | "duplicate" | "unmatched";
  stage: number | null;
  match_reason: string | null;
  voucher: Record<string, unknown> | null;
  payments: Record<string, unknown>[];
  ims: Record<string, unknown> | null;
  physical: Record<string, unknown> | null;
  flags: Flag[];
};

// ── goods ────────────────────────────────────────────────────────────────────
export type City = {
  name: string;
  state_code: string;
  x: number;
  y: number;
  hub: boolean;
  minor: boolean;
};
export type RoutePlaza = { id: string; name: string; frac: number; km: number };
export type Route = {
  id: string;
  name: string;
  highway: string;
  origin: string;
  destination: string;
  distance_km: number;
  svg_path: string;
  stops: Record<string, number>;
  plazas: RoutePlaza[];
};
export type Crossing = { plaza_id: string; plaza_name: string; crossed_at: string; km: number };
export type Verdict =
  | "verified"
  | "paper_only"
  | "impossible_journey"
  | "recycled_ewb"
  | "missing_ewb"
  | "unverifiable";

export type Trip = {
  invoice_id: string;
  invoice_no: string;
  invoice_date: string;
  supplier: string;
  supplier_gstin: string;
  total: number;
  verdict: Verdict;
  ewb_no: string | null;
  ewb_doc_no: string | null;
  vehicle_no: string | null;
  route_id: string | null;
  from_city: string | null;
  distance_km: number | null;
  generated_at: string | null;
  window_hours: number | null;
  plazas_expected: number | null;
  tolls_crossed: number;
  speed_kmh: number | null;
  trip_minutes: number | null;
  crossings: Crossing[];
  recycled_with: string[];
};

export type Beat = { kind: Verdict; invoice_ids: string[] };
export type Goods = {
  view_box: [number, number];
  cities: City[];
  routes: Route[];
  verdicts: Record<string, number>;
  invoices: Trip[];
  beats: Beat[];
};
export type GoodsDetail = { trip: Trip; flags: Flag[] };

// ── credit ───────────────────────────────────────────────────────────────────
export type GraphNode = {
  gstin: string;
  name: string;
  city: string | null;
  role: "you" | "supplier" | "upstream";
  slot: "you" | "at_risk" | "supplier" | "upstream" | "ring";
  risk: number;
  own_risk: number;
  ring: number | null;
  hops_up: number | null;
  at_risk: boolean;
  signals: string[];
  feeds: string | null;
};
export type GraphEdge = {
  seller: string;
  buyer: string;
  invoices: number;
  value: number;
  ring_edge: boolean;
};
export type CreditGraph = {
  scope: "focus" | "full";
  nodes: GraphNode[];
  edges: GraphEdge[];
  cycles: string[][];
  focus: string | null;
  threshold: number;
};

export type Benford = {
  gstin: string;
  name: string;
  n: number;
  mad: number;
  threshold: number;
  nonconforming: boolean;
  observed: number[];
  expected: number[];
};

export type SupplierRisk = {
  gstin: string;
  name: string;
  city: string | null;
  state: string | null;
  risk: number;
  own_risk: number;
  at_risk: boolean;
  signals: string[];
  ring_members: string[];
  ring_signals: string[];
  hops_to_you: number | null;
  path: string[];
  invoices: {
    invoice_id: string;
    invoice_no: string;
    invoice_date: string;
    total: number;
    itc: number;
    ims_decision: string | null;
  }[];
  itc_at_risk: number;
  benford: Benford | null;
  action: string;
  flag: Flag | null;
};

// ── IMS and liability ────────────────────────────────────────────────────────
export type ImsDecision = "Accept" | "Reject" | "Pending";
export type ImsRecord = {
  ims_id: string;
  invoice_id: string | null;
  supplier_gstin: string;
  supplier_name: string;
  invoice_no: string;
  invoice_date: string;
  taxable_value: number;
  itc: number;
  decision: ImsDecision;
  rule: string;
  reason: string;
  taint: number;
  approved: boolean;
};
export type Ims = {
  records: ImsRecord[];
  counts: ImsCounts;
  gstr2b_date: string;
  approved_at: string | null;
};
export type ApproveResult = {
  approved: number;
  rejected: number;
  pending: number;
  approved_at: string;
  message: string;
};

export type WaterfallStep = { step: string; value: number; kind: "total" | "delta" };
export type HeadRow = {
  head: string;
  output_filed: number;
  output_reconciled: number;
  itc_claimed: number;
  itc_eligible: number;
  net_filed: number;
  net_reconciled: number;
};
export type Liability = {
  summary: LiabilitySummary;
  waterfall: WaterfallStep[];
  heads: HeadRow[];
  benford_focus: string | null;
};

// ── jobs ─────────────────────────────────────────────────────────────────────
export type JobStep = {
  key: "extract" | "gstin" | "normalise" | "road" | "match" | string;
  label: string;
  state: "pending" | "running" | "done" | "skipped" | "error";
  detail: string | null;
};
export type JobFile = {
  name: string;
  kind: string | null;
  records: number | null;
  note: string | null;
};
export type Job = {
  job_id: string;
  kind: "upload" | "demo" | "reset" | "reconcile";
  status: "running" | "done" | "error";
  steps: JobStep[];
  files: JobFile[];
  error: string | null;
  kpis: Kpis | null;
  started_at: string;
  finished_at: string | null;
};

// ── fetching ─────────────────────────────────────────────────────────────────
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** SWR fetcher: pass the path after /api, e.g. useSWR("/summary", fetcher). */
export const fetcher = <T>(path: string): Promise<T> => request<T>(path);

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

const enc = (key: string) => key.split("/").map(encodeURIComponent).join("/");

export const api = {
  summary: () => request<Summary>("/summary"),
  dataset: () => request<DatasetInfo>("/dataset"),
  funnel: () => request<Funnel>("/funnel"),
  discrepancies: (q: { type?: string; category?: string } = {}) =>
    request<DiscrepancyList>(`/discrepancies?${new URLSearchParams(q).toString()}`),
  invoice: (key: string) => request<InvoiceDetail>(`/invoices/${enc(key)}`),
  goods: () => request<Goods>("/goods"),
  trip: (key: string) => request<GoodsDetail>(`/goods/${enc(key)}`),
  creditGraph: (scope: "focus" | "full" = "focus") =>
    request<CreditGraph>(`/credit/graph?scope=${scope}`),
  supplier: (gstin: string) => request<SupplierRisk>(`/credit/supplier/${gstin}`),
  benford: (gstin: string) => request<Benford>(`/benford/${gstin}`),
  ims: () => request<Ims>("/ims"),
  approveIms: (imsIds?: string[]) =>
    post<ApproveResult>("/ims/approve", imsIds ? { ims_ids: imsIds } : {}),
  liability: () => request<Liability>("/liability"),

  /** Upload files (a dropped folder or loose files). Returns the job to poll. */
  upload: (files: File[]) => {
    const form = new FormData();
    for (const f of files) {
      const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath;
      form.append("files", f, rel || f.name);
    }
    return request<Job>("/upload", { method: "POST", body: form });
  },
  uploadDemo: () => post<Job>("/upload/demo"),
  reset: () => post<Job>("/reset"),
  reconcile: (period?: string) => post<Job>(`/reconcile${period ? `?period=${period}` : ""}`),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  demoPackUrl: "/api/demo-pack.zip",
};

/** Poll a job until it finishes, reporting every update. */
export async function followJob(
  job: Job,
  onUpdate: (j: Job) => void,
  intervalMs = 250,
): Promise<Job> {
  let current = job;
  onUpdate(current);
  while (current.status === "running") {
    await new Promise((r) => setTimeout(r, intervalMs));
    current = await api.job(current.job_id);
    onUpdate(current);
  }
  return current;
}
