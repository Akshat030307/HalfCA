"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import { NAV } from "@/lib/nav";

import { Logo } from "./logo";
import { ThemeToggle } from "./theme-toggle";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 flex h-screen w-[248px] shrink-0 flex-col border-r-2 border-ink/10 bg-bg px-5 py-6 dark:border-line">
      <Link href="/upload/" className="mb-8 block">
        <Logo />
      </Link>

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

      <div className="mt-auto">
        <ThemeToggle />
      </div>
    </aside>
  );
}
