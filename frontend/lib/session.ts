"use client";

import { useSyncExternalStore } from "react";

// Each visitor starts empty: the screens unlock once this browser tab has uploaded a folder.
// sessionStorage, so a refresh keeps the results and a new tab starts again from Upload.
const KEY = "halfca.uploaded";
const EVENT = "halfca:uploaded";

let memory = false; // fallback when sessionStorage is unavailable (private modes, blocked storage)

function read(): boolean {
  if (memory) return true;
  try {
    return window.sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** True once this tab has finished an upload; null until the browser has been asked. */
export function useUploaded(): boolean | null {
  return useSyncExternalStore<boolean | null>(subscribe, read, () => null);
}

export function markUploaded(): void {
  try {
    window.sessionStorage.setItem(KEY, "1");
  } catch {
    /* storage blocked: the in-memory flag below still unlocks this page view */
  }
  memory = true;
  window.dispatchEvent(new Event(EVENT));
}
