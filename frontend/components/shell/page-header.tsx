import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3 sm:mb-7 sm:gap-4">
      <div>
        <h1 className="font-display text-[30px] uppercase leading-none tracking-wide text-ink sm:text-[40px]">
          {title}
        </h1>
        <p className="mt-2 text-[14px] text-muted sm:text-[15px]">{subtitle}</p>
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  );
}
