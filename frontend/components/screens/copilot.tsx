"use client";

import { Send, Sparkles } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

import { Card } from "@/components/ui/card";

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

type Turn = { role: "user" | "assistant"; text: string };

export function CopilotScreen() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");

  function ask(q: string) {
    const question = q.trim();
    if (!question) return;
    setDraft("");
    setTurns((t) => [
      ...t,
      { role: "user", text: question },
      {
        role: "assistant",
        text: "I'm being wired up right now. In the next step I'll answer by calling the same tools the MCP server exposes, show you each call, and link the evidence.",
      },
    ]);
  }

  return (
    <div className="grid items-start gap-5 xl:grid-cols-[260px_1fr]">
      <Card title="Try asking">
        <div className="flex flex-col gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => ask(s)}
              className="rounded-2xl border-[1.5px] border-line bg-panel px-3 py-2 text-left text-[13px] font-medium text-ink transition-colors hover:border-orange hover:bg-orange-pale/40"
            >
              {s}
            </button>
          ))}
        </div>
        <div className="mt-5 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
          Tools
        </div>
        <ul className="mt-2 space-y-1 font-mono text-[12px] text-ink">
          {TOOLS.map((t) => (
            <li key={t}>
              <span className="text-orange">›</span> {t}
            </li>
          ))}
        </ul>
      </Card>

      <Card
        title="Ask Half CA"
        subtitle="Every answer shows its working"
        bodyClassName="flex flex-col p-0"
      >
        <div className="flex min-h-[460px] flex-1 flex-col gap-4 p-5">
          {turns.length === 0 && (
            <div className="halftone m-auto flex flex-col items-center gap-3 rounded-3xl px-10 py-12 text-center">
              <Sparkles className="text-orange" />
              <div className="font-display text-[34px] uppercase leading-none text-ink">
                Ask me anything
              </div>
              <div className="max-w-sm text-[13.5px] text-muted">
                About this month&apos;s invoices, suppliers, the road check or what you owe.
              </div>
            </div>
          )}
          <AnimatePresence initial={false}>
            {turns.map((t, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={
                  t.role === "user"
                    ? "ml-auto max-w-[70%] rounded-2xl rounded-br-md border-2 border-ink bg-orange px-4 py-2.5 text-[14px] font-medium text-on-orange dark:border-orange"
                    : "max-w-[80%] rounded-2xl rounded-bl-md border-[1.5px] border-line bg-peach/60 px-4 py-3 text-[14px] leading-relaxed text-ink"
                }
              >
                {t.text}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(draft);
          }}
          className="flex items-center gap-3 border-t-[1.5px] border-line p-4"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Why did my liability go up?"
            className="flex-1 rounded-full border-2 border-line bg-panel px-4 py-2.5 text-[14px] text-ink outline-none placeholder:text-muted focus:border-orange"
          />
          <button
            type="submit"
            className="btn-press inline-flex items-center gap-2 rounded-full bg-orange px-5 py-2.5 font-heading text-[14px] font-bold text-on-orange"
          >
            <Send size={15} /> Send
          </button>
        </form>
      </Card>
    </div>
  );
}
