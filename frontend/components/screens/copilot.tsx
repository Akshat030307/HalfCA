"use client";

import { ArrowRight, Check, Loader2, Send, Sparkles, TriangleAlert } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

import { Card } from "@/components/ui/card";
import {
  askCopilot,
  type ChatTurn,
  type CopilotDone,
  type CopilotInfo,
  type EvidenceChip,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/hooks";

export const SUGGESTIONS = [
  "Why did my liability go up?",
  "Which invoices failed the road check?",
  "Is Kaveri Metals safe to buy from?",
];
export const TOOLS = [
  "reconcile_period",
  "list_discrepancies",
  "trace_goods",
  "supplier_risk",
  "ims_recommendations",
  "estimate_liability",
  "explain",
];
const HISTORY = 6;

type ToolLine = { call: string; done: boolean; ok: boolean; headline: string };
type UserTurn = { id: number; role: "user"; text: string };
type BotTurn = {
  id: number;
  role: "assistant";
  tools: ToolLine[];
  text: string;
  evidence: EvidenceChip[];
  done: CopilotDone | null;
  error: string | null;
};
type Turn = UserTurn | BotTurn;

/** **bold** spans; an unclosed ** (mid-stream) is simply hidden until it closes. */
function Rich({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 ? (
          <b key={i} className="font-semibold">
            {p}
          </b>
        ) : (
          <Fragment key={i}>{p.replaceAll("**", "")}</Fragment>
        ),
      )}
    </>
  );
}

function ToolTrace({ lines }: { lines: ToolLine[] }) {
  return (
    <div className="space-y-1.5 border-l-[3px] border-trace py-0.5 pl-3">
      {lines.map((l, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.25 }}
          className="font-mono text-[12.5px] leading-snug"
        >
          <div className="flex items-start gap-2 text-ink">
            <span className="text-trace">→</span>
            <span className="break-all">{l.call}</span>
            {l.done ? (
              l.ok ? (
                <Check size={14} strokeWidth={3} className="mt-0.5 shrink-0 text-ok" />
              ) : (
                <TriangleAlert size={14} className="mt-0.5 shrink-0 text-warn" />
              )
            ) : (
              <Loader2 size={14} className="mt-0.5 shrink-0 animate-spin text-trace" />
            )}
          </div>
          {l.done && l.headline && (
            <div className="pl-5 text-[11.5px] text-muted">{l.headline}</div>
          )}
        </motion.div>
      ))}
    </div>
  );
}

function Meta({ done }: { done: CopilotDone }) {
  const bits: ReactNode[] = [];
  if (done.mode === "llm") bits.push(<span key="m">✦ {done.model}</span>);
  else if (done.mode === "template") bits.push(<span key="m">Templated answer</span>);
  bits.push(
    <span key="t">
      {done.tool_calls} tool call{done.tool_calls === 1 ? "" : "s"}
    </span>,
  );
  if (done.numbers_checked)
    bits.push(
      <span key="n" className="text-ok">
        ✓ {done.numbers_checked} numbers traced to tool output
      </span>,
    );
  return (
    <div className="space-y-0.5 text-[11.5px] text-muted">
      <div className="flex flex-wrap gap-x-2">
        {bits.map((b, i) => (
          <Fragment key={i}>
            {i > 0 && <span>·</span>}
            {b}
          </Fragment>
        ))}
      </div>
      {done.note && <div className="italic">{done.note}</div>}
    </div>
  );
}

function Answer({ turn, streaming }: { turn: BotTurn; streaming: boolean }) {
  const thinking = streaming && !turn.text && !turn.error;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex max-w-[86%] flex-col gap-3"
    >
      {turn.tools.length > 0 && <ToolTrace lines={turn.tools} />}
      {thinking && turn.tools.every((t) => t.done) && (
        <div className="flex items-center gap-1.5 pl-1 text-[13px] text-muted">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-orange"
              animate={{ opacity: [0.25, 1, 0.25] }}
              transition={{ repeat: Infinity, duration: 1, delay: i * 0.18 }}
            />
          ))}
          <span className="ml-1">{turn.tools.length ? "Writing the answer" : "Thinking"}</span>
        </div>
      )}
      {(turn.text || turn.error) && (
        <div
          className={cn(
            "rounded-2xl rounded-bl-md border-[1.5px] px-4 py-3 text-[14px] leading-relaxed",
            turn.error ? "border-bad/50 bg-bad/10 text-bad" : "border-line bg-peach/60 text-ink",
          )}
        >
          {turn.error ?? <Rich text={turn.text} />}
          {streaming && turn.text && (
            <span className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-orange" />
          )}
        </div>
      )}
      {turn.evidence.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {turn.evidence.map((e, i) => (
            <motion.div
              key={e.label}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.08, type: "spring", stiffness: 380, damping: 18 }}
            >
              <Link
                href={e.href}
                className="inline-flex items-center gap-1 rounded-full border-2 border-orange bg-panel px-3 py-1 text-[12.5px] font-bold text-ink transition-colors hover:bg-orange hover:text-on-orange"
              >
                {e.label} <ArrowRight size={13} strokeWidth={2.5} />
              </Link>
            </motion.div>
          ))}
        </div>
      )}
      {turn.done && <Meta done={turn.done} />}
    </motion.div>
  );
}

export function CopilotScreen() {
  const { data: info } = useApi<CopilotInfo>("/copilot");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);
  const nextId = useRef(1);

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns]);

  async function ask(q: string) {
    const question = q.trim();
    if (!question || busy !== null) return;
    const history: ChatTurn[] = turns
      .filter((t) => (t.role === "user" ? true : !t.error && t.text))
      .slice(-HISTORY)
      .map((t) => ({ role: t.role, content: t.text }));
    const uid = nextId.current++;
    const bid = nextId.current++;
    setDraft("");
    setBusy(bid);
    setTurns((ts) => [
      ...ts,
      { id: uid, role: "user", text: question },
      { id: bid, role: "assistant", tools: [], text: "", evidence: [], done: null, error: null },
    ]);
    const update = (fn: (t: BotTurn) => BotTurn) =>
      setTurns((ts) => ts.map((t) => (t.id === bid && t.role === "assistant" ? fn(t) : t)));

    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      await askCopilot(
        question,
        history,
        (e) => {
          if (e.type === "tool") {
            const line = { call: e.data.call, done: false, ok: true, headline: "" };
            update((t) => ({ ...t, tools: [...t.tools, line] }));
          } else if (e.type === "tool_done") {
            update((t) => {
              const i = t.tools.findIndex((l) => l.call === e.data.call && !l.done);
              if (i < 0) return t;
              const tools = t.tools.slice();
              tools[i] = { ...tools[i], done: true, ok: e.data.ok, headline: e.data.headline };
              return { ...t, tools };
            });
          } else if (e.type === "token") {
            update((t) => ({ ...t, text: t.text + e.data.text }));
          } else if (e.type === "evidence") {
            update((t) => ({ ...t, evidence: e.data.items }));
          } else if (e.type === "done") {
            update((t) => ({ ...t, done: e.data }));
          }
        },
        ctrl.signal,
      );
    } catch (err) {
      if (!ctrl.signal.aborted)
        update((t) => ({
          ...t,
          error: `I couldn't reach the server (${err instanceof Error ? err.message : "error"}).`,
        }));
    } finally {
      setBusy(null);
    }
  }

  const suggestions = info?.suggestions ?? SUGGESTIONS;
  const tools = info?.tools.map((t) => t.name) ?? TOOLS;

  return (
    <div className="grid items-start gap-5 xl:grid-cols-[260px_1fr]">
      <Card title="Try asking">
        <div className="flex flex-col gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              disabled={busy !== null}
              onClick={() => void ask(s)}
              className="rounded-2xl border-[1.5px] border-line bg-panel px-3 py-2 text-left text-[13px] font-medium text-ink transition-colors hover:border-orange hover:bg-orange-pale/40 disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
        <div className="mt-5 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
          Tools
        </div>
        <ul className="mt-2 space-y-1 font-mono text-[12px] text-ink">
          {tools.map((t) => (
            <li key={t} title={info?.tools.find((x) => x.name === t)?.description}>
              <span className="text-orange">›</span> {t}
            </li>
          ))}
        </ul>
        <p className="mt-4 text-[12px] leading-snug text-muted">
          {info?.llm ? (
            <>
              <b className="text-ink">✦ {info.llm}</b> picks the tools and writes the answer; every
              number in it must come from a tool.
            </>
          ) : (
            <>No AI key here: rules pick the tools and a template writes the answer.</>
          )}{" "}
          The same tools run as an MCP server: <code className="font-mono">make mcp</code>.
        </p>
      </Card>

      <Card
        title="Ask Half CA"
        subtitle="Every answer shows its working"
        bodyClassName="flex flex-col p-0"
      >
        <div
          ref={scroller}
          className="flex h-[calc(100vh-372px)] min-h-[360px] flex-col gap-5 overflow-y-auto p-5"
        >
          {turns.length === 0 && (
            <div className="halftone m-auto flex flex-col items-center gap-3 rounded-3xl px-10 py-12 text-center">
              <Sparkles className="text-orange" />
              <div className="font-display text-[34px] uppercase leading-none text-ink">
                Ask me anything
              </div>
              <div className="max-w-sm text-[13.5px] text-muted">
                About this month&apos;s invoices, suppliers, the road check or what you owe.
                I&apos;ll show every tool I call.
              </div>
            </div>
          )}
          <AnimatePresence initial={false}>
            {turns.map((t) =>
              t.role === "user" ? (
                <motion.div
                  key={t.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="ml-auto max-w-[70%] rounded-2xl rounded-br-md border-2 border-ink bg-orange px-4 py-2.5 text-[14px] font-medium text-on-orange dark:border-orange"
                >
                  {t.text}
                </motion.div>
              ) : (
                <Answer key={t.id} turn={t} streaming={busy === t.id} />
              ),
            )}
          </AnimatePresence>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask(draft);
          }}
          className="flex items-center gap-3 border-t-[1.5px] border-line p-4"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Why did my liability go up?"
            maxLength={2000}
            className="flex-1 rounded-full border-2 border-line bg-panel px-4 py-2.5 text-[14px] text-ink outline-none placeholder:text-muted focus:border-orange"
          />
          <button
            type="submit"
            disabled={busy !== null || !draft.trim()}
            className="btn-press inline-flex items-center gap-2 rounded-full bg-orange px-5 py-2.5 font-heading text-[14px] font-bold text-on-orange disabled:opacity-50"
          >
            {busy !== null ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}{" "}
            Send
          </button>
        </form>
      </Card>
    </div>
  );
}
