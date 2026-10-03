"use client";

import {
  BookOpen,
  Check,
  Download,
  FileText,
  FolderOpen,
  Inbox,
  Landmark,
  Loader2,
  Sparkles,
  Truck,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type DragEvent } from "react";

import { Button, ButtonLink } from "@/components/ui/button";
import { Chip, type Tone } from "@/components/ui/chip";
import { api, followJob, type DatasetInfo, type Job, type JobFile, type JobStep } from "@/lib/api";
import { cn } from "@/lib/cn";
import { filesFromDrop } from "@/lib/drop";
import { count } from "@/lib/format";
import { useApi, useRefreshAll } from "@/lib/hooks";
import { markUploaded, useUploaded } from "@/lib/session";

const KIND: Record<string, { icon: typeof FileText; chip: string; tone: Tone; unit: string }> = {
  invoices: { icon: FileText, chip: "Invoices", tone: "neutral", unit: "invoices" },
  bank: { icon: Landmark, chip: "Payments", tone: "neutral", unit: "bank transactions" },
  ledger: { icon: BookOpen, chip: "Ledger", tone: "neutral", unit: "ledger vouchers" },
  ims: { icon: Inbox, chip: "IMS", tone: "neutral", unit: "supplier records" },
  eway: { icon: Truck, chip: "Road", tone: "orange", unit: "e-way bills + toll crossings" },
};
const ORDER = ["invoices", "bank", "ledger", "ims", "eway"];
const DEFAULT_STEPS: JobStep[] = [
  { key: "extract", label: "Reading the month's invoices", state: "pending", detail: null },
  {
    key: "gstin",
    label: "Validating GSTINs (state · PAN · check digit)",
    state: "pending",
    detail: null,
  },
  { key: "normalise", label: "Normalising invoice numbers", state: "pending", detail: null },
  { key: "road", label: "Linking e-way bills to toll crossings", state: "pending", detail: null },
  { key: "match", label: "Matching across four threads", state: "pending", detail: null },
];
const STEP_MS = 650;

type Row = { kind: string; name: string; detail: string; note: string | null };

function rowsFrom(job: Job | null, ds: DatasetInfo | undefined): Row[] {
  if (job && job.files.some((f) => f.kind && KIND[f.kind])) {
    const docs = job.files.filter((f) => f.kind === "document").length;
    return ORDER.flatMap((kind) => {
      const f = job.files.find((x: JobFile) => x.kind === kind);
      if (!f) return [];
      const n = f.records ?? 0;
      const extra = kind === "invoices" && docs ? ` · CSV + ${docs} PDFs` : "";
      return [
        { kind, name: f.name, detail: `${count(n)} ${KIND[kind].unit}${extra}`, note: f.note },
      ];
    });
  }
  if (!ds) return [];
  return ORDER.map((kind) => {
    const s = ds.sources.find((x) => x.kind === kind);
    return {
      kind,
      name: s?.filename ?? kind,
      detail: `${count(s?.records ?? 0)} ${KIND[kind].unit}`,
      note: null,
    };
  });
}

function docTone(note: string | null): Tone {
  if (!note) return "idle";
  if (note.includes("agrees") || note.includes("added")) return "ok";
  if (note.startsWith("Not read")) return "idle";
  return "warn";
}

/** 'Rohilkhand-Alloys_MB-0877.pdf' → 'MB-0877' */
function docLabel(name: string): string {
  const base = name.replace(/\.pdf$/i, "");
  return base.includes("_") ? base.slice(base.lastIndexOf("_") + 1) : base;
}

function docSummary(c: Record<string, number>): string | null {
  if (!c.documents) return null;
  if (!c.read) return `${c.documents} invoice PDFs on file · not read (no AI model)`;
  const bits = [`${c.read} of ${c.documents} PDFs read by AI`];
  if (c.agree) bits.push(`${c.agree} agree with the register`);
  if (c.differ) bits.push(`${c.differ} differ`);
  if (c.added) bits.push(`${c.added} added as new invoices`);
  if (c.needs_review) bits.push(`${c.needs_review} need review`);
  return bits.join(" · ");
}

/** The invoice PDFs: one chip per document, coloured by what reading it found. */
function Documents({ job, ds }: { job: Job | null; ds: DatasetInfo | undefined }) {
  const docs = job?.files.filter((f) => f.kind === "document") ?? [];
  const summary = job ? null : docSummary(ds?.documents ?? {});
  if (!docs.length && !summary) return null;
  return (
    <div className="mt-3 rounded-2xl border-[1.5px] border-dashed border-line bg-panel/70 p-3">
      <div className="mb-2 flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.12em] text-muted">
        <Sparkles size={13} className="text-orange" /> Invoice PDFs · read by AI
      </div>
      {summary && <div className="text-[12.5px] text-muted">{summary}</div>}
      <div className="flex flex-wrap gap-1.5">
        {docs.map((d, i) => (
          <motion.span
            key={d.name}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.6 + i * 0.05 }}
            title={`${d.name}: ${d.note ?? ""}`}
          >
            <Chip tone={docTone(d.note)} className="font-mono">
              {docTone(d.note) === "ok" ? <Check size={11} strokeWidth={3} /> : null}
              {docLabel(d.name)}
            </Chip>
          </motion.span>
        ))}
      </div>
      {docs.some((d) => docTone(d.note) === "warn") && (
        <ul className="mt-2 space-y-0.5 text-[12px] text-warn">
          {docs
            .filter((d) => docTone(d.note) === "warn")
            .slice(0, 4)
            .map((d) => (
              <li key={d.name}>
                <span className="font-mono">{docLabel(d.name)}</span>: {d.note}
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}

/** Show the job's real progress, but let each step breathe on screen. */
function usePacedSteps(job: Job | null): { steps: JobStep[]; finished: boolean } {
  // Pacing is keyed by job id, so a new job starts from step one without a reset effect.
  const [pace, setPace] = useState<{ id: string | null; n: number }>({ id: null, n: 0 });
  const shown = job && pace.id === job.job_id ? pace.n : 0;
  const realDone = job
    ? job.steps.filter((s) => s.state === "done" || s.state === "skipped").length
    : 0;
  const errored = job?.status === "error";

  useEffect(() => {
    if (!job || errored || shown >= realDone) return;
    const t = window.setTimeout(() => setPace({ id: job.job_id, n: shown + 1 }), STEP_MS);
    return () => window.clearTimeout(t);
  }, [job, errored, shown, realDone]);

  if (!job) return { steps: DEFAULT_STEPS, finished: false };
  const steps = job.steps.map((s, i): JobStep => {
    if (errored) return s;
    if (i < shown) return { ...s, state: s.state === "skipped" ? "skipped" : "done" };
    if (i === shown && (job.status === "running" || shown < realDone))
      return { ...s, state: "running", detail: null };
    return { ...s, state: "pending", detail: null };
  });
  return { steps, finished: job.status === "done" && shown >= job.steps.length };
}

function StepIcon({ state }: { state: JobStep["state"] }) {
  if (state === "running") return <Loader2 size={16} className="animate-spin text-orange" />;
  if (state === "done") return <Check size={14} strokeWidth={3} className="text-white" />;
  if (state === "error") return <X size={14} strokeWidth={3} className="text-white" />;
  return null;
}

export function UploadScreen() {
  const { data: ds } = useApi<DatasetInfo>("/dataset");
  const refreshAll = useRefreshAll();
  const [job, setJob] = useState<Job | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const { steps, finished } = usePacedSteps(job);
  const busy = job?.status === "running" || (job !== null && job.status === "done" && !finished);
  const uploaded = useUploaded();
  const rows = rowsFrom(job, uploaded ? ds : undefined);
  const ignored = job?.files.filter((f) => !f.kind) ?? [];

  useEffect(() => {
    folderInput.current?.setAttribute("webkitdirectory", "");
  }, []);

  useEffect(() => {
    if (finished) void refreshAll();
    // refreshAll is stable enough; only react to finishing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished]);

  async function run(start: () => Promise<Job>) {
    setError(null);
    try {
      const final = await followJob(await start(), setJob);
      if (final.status === "error") setError(final.error ?? "Something went wrong");
      else if (final.status === "done") markUploaded();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function send(files: File[]) {
    if (files.length === 0 || busy) return;
    void run(() => api.upload(files));
  }

  async function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    send(await filesFromDrop(e.dataTransfer));
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
      className={cn(
        "relative rounded-[24px] border-[2.5px] border-dashed p-3 transition-colors sm:p-6",
        dragging ? "border-orange bg-orange-pale/40" : "border-ink/30 bg-panel/40 dark:border-line",
      )}
    >
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
        {/* Left: the files */}
        <section className="card halftone min-w-0 p-4 sm:p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-heading text-[15px] font-bold text-ink">The month&apos;s files</h2>
            <span className="text-[12px] text-muted">
              {job
                ? "This upload"
                : uploaded && ds
                  ? `Loaded now · ${ds.scenario}`
                  : "Waiting for your files"}
            </span>
          </div>
          {rows.length === 0 && (
            <div className="flex flex-col items-center gap-2 rounded-2xl border-[1.5px] border-dashed border-line bg-panel/70 px-4 py-12 text-center">
              {busy ? (
                <Loader2 size={26} className="animate-spin text-orange" />
              ) : (
                <FolderOpen size={26} className="text-orange" />
              )}
              <div className="font-heading text-[15px] font-bold text-ink">
                {busy ? "Reading your files…" : "Drop the month's folder here"}
              </div>
              <p className="max-w-xs text-[12.5px] text-muted">
                Invoice register, bank statement, Tally day book, IMS feed and e-way bills. Invoice
                PDFs in the folder are read by AI.
              </p>
            </div>
          )}
          <ul className="space-y-3">
            <AnimatePresence initial>
              {rows.map((r, i) => {
                const k = KIND[r.kind];
                const Icon = k.icon;
                return (
                  <motion.li
                    key={`${job?.job_id ?? "ds"}-${r.kind}`}
                    initial={{ opacity: 0, x: -24 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.12, type: "spring", stiffness: 260, damping: 24 }}
                    className="flex items-center gap-3 rounded-2xl border-[1.5px] border-line bg-panel p-3"
                  >
                    <span
                      className={cn(
                        "grid h-11 w-11 shrink-0 place-items-center rounded-xl border-2",
                        r.kind === "eway"
                          ? "border-ink bg-orange text-on-orange dark:border-orange"
                          : "border-line bg-peach text-ink",
                      )}
                    >
                      <Icon size={20} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-mono text-[13.5px] font-semibold text-ink">
                        {r.name}
                      </div>
                      <div className="truncate text-[12.5px] text-muted">
                        {r.detail}
                        {r.note && <span className="italic"> · {r.note}</span>}
                      </div>
                    </div>
                    <Chip tone={k.tone}>{k.chip}</Chip>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ul>
          <Documents job={job} ds={uploaded ? ds : undefined} />
          {ignored.length > 0 && (
            <p className="mt-3 text-[12px] text-muted">
              Ignored: {ignored.map((f) => f.name).join(", ")}
            </p>
          )}
        </section>

        {/* Right: what happens */}
        <section className="card flex min-w-0 flex-col p-4 sm:p-5">
          <h2 className="mb-4 font-heading text-[15px] font-bold text-ink">What Half CA does</h2>
          <ol className="space-y-2.5">
            {steps.map((s, i) => (
              <li
                key={s.key}
                className={cn(
                  "flex items-start gap-3 rounded-2xl border-[1.5px] p-3 transition-colors",
                  s.state === "running"
                    ? "border-orange bg-orange-pale/30"
                    : "border-line bg-panel",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border-2",
                    s.state === "done" && "border-ok bg-ok",
                    s.state === "error" && "border-bad bg-bad",
                    s.state === "running" && "border-orange",
                    (s.state === "pending" || s.state === "skipped") && "border-line",
                  )}
                >
                  <StepIcon state={s.state} />
                </span>
                <div className="min-w-0">
                  <div
                    className={cn(
                      "text-[14px] font-semibold",
                      s.state === "pending" ? "text-muted" : "text-ink",
                    )}
                  >
                    <span className="mr-1.5 font-mono text-[12px] text-muted">{i + 1}.</span>
                    {s.label}
                  </div>
                  <AnimatePresence>
                    {s.detail && s.state === "done" && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="text-[12.5px] text-muted"
                      >
                        {s.detail}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-auto pt-5">
            {error && (
              <div className="mb-3 rounded-xl border-[1.5px] border-bad/40 bg-bad/10 px-3 py-2 text-[13px] text-bad">
                {error}
              </div>
            )}
            {finished && job?.kpis ? (
              <motion.div
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-wrap items-center justify-between gap-3"
              >
                <div className="text-[13px] text-muted">
                  <b className="text-ok">{count(job.kpis.matched)}</b> matched ·{" "}
                  <b className="text-warn">{job.kpis.discrepancies}</b> discrepancies ·{" "}
                  <b className="text-dup">{job.kpis.duplicates}</b> duplicates ·{" "}
                  <b className="text-idle">{job.kpis.unmatched}</b> unmatched
                </div>
                <ButtonLink href="/overview/">View results →</ButtonLink>
              </motion.div>
            ) : (
              <div className="text-[12.5px] text-muted">
                {busy ? "Working through the month…" : "Nothing runs until you start it."}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Actions */}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button disabled={busy} onClick={() => folderInput.current?.click()}>
          <FolderOpen size={16} /> Choose a folder
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => filesInput.current?.click()}>
          <FileText size={16} /> Choose files
        </Button>
        <span className="text-[13px] text-muted">
          …or drop the month&apos;s folder anywhere here.
        </span>
        <div className="ml-auto">
          <ButtonLink href={api.demoPackUrl} variant="ghost" download>
            <Download size={14} /> Download sample folder
          </ButtonLink>
        </div>
        <input
          ref={folderInput}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            send(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
        <input
          ref={filesInput}
          type="file"
          multiple
          hidden
          accept=".csv,.xml,.json,.zip,.pdf"
          onChange={(e) => {
            send(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
      </div>

      <AnimatePresence>
        {dragging && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="pointer-events-none absolute inset-0 grid place-items-center rounded-[22px] bg-bg/80 backdrop-blur-sm"
          >
            <div className="text-center">
              <div className="font-display text-6xl uppercase text-orange">Drop it.</div>
              <div className="mt-2 text-muted">A folder, a zip or loose files</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
