import type { Tone } from "@/components/ui/chip";

/** Status colours from the spec: green ok, amber discrepancy/pending, violet duplicate,
 * slate unmatched, red fraud/reject/ring. */
export const KIND_TONE: Record<string, Tone> = {
  amount: "warn",
  date: "warn",
  invoice_id: "warn",
  tax_rate: "warn",
  tax_head: "warn",
  tax_arith: "warn",
  document: "warn",
  duplicate: "dup",
  near_duplicate: "dup",
  unmatched: "idle",
  unpaid_aged: "idle",
  payment_only: "idle",
  not_in_ims: "idle",
  ims_only: "idle",
  missing_ewb: "bad",
  paper_only: "bad",
  impossible_journey: "bad",
  recycled_ewb: "bad",
  ring_taint: "bad",
  benford: "warn",
  threshold_hugging: "warn",
  outlier: "idle",
  transition_review: "idle",
  invalid_gstin: "warn",
};

export const STATUS_TONE: Record<string, Tone> = {
  matched: "ok",
  discrepant: "warn",
  duplicate: "dup",
  unmatched: "idle",
};

export const DECISION_TONE: Record<string, Tone> = {
  Accept: "ok",
  Reject: "bad",
  Pending: "warn",
};

export const VERDICT_TEXT: Record<string, string> = {
  verified: "✓ Goods verified",
  paper_only: "✕ Paper-only supply",
  impossible_journey: "✕ Impossible journey",
  recycled_ewb: "✕ Recycled e-way bill",
  missing_ewb: "✕ No e-way bill",
  unverifiable: "No tolls on route",
};
