"use client";

import { Download, FolderUp } from "lucide-react";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ButtonLink } from "@/components/ui/button";
import { api } from "@/lib/api";
import { NAV } from "@/lib/nav";
import { useUploaded } from "@/lib/session";

/** Every screen but Upload waits until this tab has uploaded the month's folder. */
export function UploadGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const uploaded = useUploaded();
  if (pathname.startsWith("/upload")) return children;
  if (uploaded === null) return null; // not read from the browser yet
  if (uploaded) return children;

  const item = NAV.find((n) => pathname.startsWith(n.href.replace(/\/$/, "")));
  return (
    <>
      <div className="mb-5 sm:mb-7">
        <h1 className="font-display text-[30px] uppercase leading-none tracking-wide text-ink sm:text-[40px]">
          {item?.label ?? "Half CA"}
        </h1>
        <p className="mt-2 text-[14px] text-muted sm:text-[15px]">
          Waiting for the month&apos;s files.
        </p>
      </div>
      <div className="card halftone flex flex-col items-center gap-4 px-6 py-14 text-center sm:py-20">
        <span className="grid h-14 w-14 place-items-center rounded-2xl border-2 border-ink bg-orange text-on-orange dark:border-orange">
          <FolderUp size={26} />
        </span>
        <div className="font-display text-[30px] uppercase leading-none text-ink sm:text-[38px]">
          Nothing here yet
        </div>
        <p className="max-w-md text-[14px] text-muted">
          This screen fills in from your files. Upload the month&apos;s folder first: the invoice
          register, bank statement, Tally day book, IMS feed and e-way bills (plus any invoice
          PDFs).
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <ButtonLink href="/upload/">Go to Upload →</ButtonLink>
          <ButtonLink href={api.demoPackUrl} variant="ghost" download>
            <Download size={14} /> Download sample folder
          </ButtonLink>
        </div>
      </div>
    </>
  );
}
