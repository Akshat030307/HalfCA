"use client";

import { Menu, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/cn";
import { NAV } from "@/lib/nav";

import { Logo, LogoBadge } from "./logo";
import { ThemeToggle } from "./theme-toggle";

/** Logo, the nine screens and the theme toggle: the desktop sidebar and the phone menu. */
function NavContents({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <>
      {/* A full page load: "/" is the landing page, served outside the Next app. */}
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      <a href="/" className="mb-8 block" title="Back to the Half CA home page">
        <Logo />
      </a>

      <div className="mb-3 text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
        Reconcile · Sep 2026
      </div>
      <nav className="flex flex-col gap-1">
        {NAV.map((item) => {
          const active = pathname.startsWith(item.href.replace(/\/$/, ""));
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "group flex items-center gap-3 rounded-full px-2 py-1.5 text-[14px] font-medium transition-colors",
                active ? "bg-peach text-ink" : "text-muted hover:bg-peach/60 hover:text-ink",
              )}
            >
              <span
                className={cn(
                  "grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 font-heading text-[12px] font-bold transition-colors",
                  active
                    ? "border-ink bg-orange text-on-orange"
                    : "border-line bg-panel text-muted group-hover:border-ink/40",
                )}
              >
                {item.letter}
              </span>
              <span className="truncate">{item.label}</span>
              {item.star && <span className="ml-auto pr-1 text-orange">★</span>}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto pt-6">
        <ThemeToggle />
      </div>
    </>
  );
}

export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r-2 border-ink/10 bg-bg px-5 py-6 lg:flex dark:border-line">
      <NavContents />
    </aside>
  );
}

/** Below laptop width: a menu button in the top bar that slides the same nav in. */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const current = NAV.find((n) => pathname.startsWith(n.href.replace(/\/$/, "")));

  return (
    <div className="flex shrink-0 items-center gap-2 lg:hidden">
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open the menu"
        aria-expanded={open}
        className="btn-press grid h-10 w-10 place-items-center rounded-xl bg-panel text-ink"
      >
        <Menu size={18} />
      </button>
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      <a href="/" aria-label="Half CA home" className="shrink-0">
        <LogoBadge size={34} />
      </a>
      {current && (
        <span className="hidden font-heading text-[14px] font-bold text-ink sm:inline">
          {current.label}
        </span>
      )}
      {/* Portalled: the top bar's backdrop blur would otherwise trap a fixed drawer inside it. */}
      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {open && (
              <>
                <motion.div
                  key="scrim"
                  className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[2px]"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  onClick={() => setOpen(false)}
                />
                <motion.aside
                  key="drawer"
                  className="fixed inset-y-0 left-0 z-50 flex w-[272px] max-w-[85vw] flex-col overflow-y-auto border-r-2 border-ink bg-bg px-5 py-6 dark:border-line"
                  initial={{ x: "-100%" }}
                  animate={{ x: 0 }}
                  exit={{ x: "-100%" }}
                  transition={{ type: "spring", stiffness: 380, damping: 36 }}
                >
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    aria-label="Close the menu"
                    className="absolute right-4 top-5 grid h-9 w-9 place-items-center rounded-full text-muted hover:bg-peach hover:text-ink"
                  >
                    <X size={18} />
                  </button>
                  <NavContents onNavigate={() => setOpen(false)} />
                </motion.aside>
              </>
            )}
          </AnimatePresence>,
          document.body,
        )}
    </div>
  );
}
