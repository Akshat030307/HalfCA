"use client";

import { CheckCircle2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

/** A single bottom-right toast; the parent controls the message. */
export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  return (
    <AnimatePresence onExitComplete={() => undefined}>
      {message && (
        <motion.div
          key={message}
          role="status"
          initial={{ opacity: 0, y: 30, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20 }}
          onAnimationComplete={() => window.setTimeout(onDone, 4200)}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-2xl border-2 border-ink bg-ok px-5 py-3 font-heading text-[15px] font-bold text-white shadow-[4px_4px_0_var(--ink)]"
        >
          <CheckCircle2 size={20} />
          {message}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
