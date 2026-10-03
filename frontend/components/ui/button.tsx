import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "btn-press bg-orange text-on-orange",
  secondary: "btn-press bg-panel text-ink",
  ghost: "text-muted hover:text-ink hover:bg-peach/70",
};

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-[14px] font-bold " +
  "font-heading transition-colors disabled:pointer-events-none disabled:opacity-50 select-none";

export function Button({
  variant = "primary",
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode }) {
  return (
    <button type="button" className={cn(BASE, VARIANTS[variant], className)} {...rest}>
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "primary",
  className,
  children,
  download,
}: {
  href: string;
  variant?: Variant;
  className?: string;
  children: ReactNode;
  download?: boolean;
}) {
  const cls = cn(BASE, VARIANTS[variant], className);
  if (download || href.startsWith("/api/")) {
    return (
      <a href={href} className={cls} download={download}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}
