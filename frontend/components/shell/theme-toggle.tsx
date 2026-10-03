"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // Theme is only known on the client; render a neutral button until then.
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  const dark = mounted && resolvedTheme === "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="btn-press flex w-full items-center justify-between rounded-full bg-panel px-4 py-2 text-sm font-semibold text-ink"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
    >
      <span>{mounted ? (dark ? "Lights off" : "Lights on") : "Theme"}</span>
      <span className="grid h-6 w-6 place-items-center rounded-full bg-orange text-on-orange">
        {dark ? <Moon size={14} /> : <Sun size={14} />}
      </span>
    </button>
  );
}
