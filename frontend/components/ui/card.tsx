import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Card({
  title,
  subtitle,
  right,
  className,
  bodyClassName,
  children,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("card flex flex-col", className)}>
      {(title || right) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <div>
            {title && (
              <h2 className="font-heading text-[15px] font-bold leading-tight text-ink">{title}</h2>
            )}
            {subtitle && <p className="mt-0.5 text-[12.5px] text-muted">{subtitle}</p>}
          </div>
          {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
        </header>
      )}
      <div className={cn("flex-1 p-5", title && "pt-3", bodyClassName)}>{children}</div>
    </section>
  );
}
