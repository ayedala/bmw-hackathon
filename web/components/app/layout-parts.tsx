"use client";

import { X } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  question,
  meta,
  actions,
}: {
  title: string;
  /** The decision question this page answers. */
  question?: string;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3 pb-4">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold tracking-tight text-zinc-950">{title}</h1>
        {question && <p className="mt-0.5 text-[13px] text-slate-500">{question}</p>}
        {meta && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">{meta}</div>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Metric({
  label,
  value,
  detail,
  hint,
  href,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  hint?: string;
  href?: string;
}) {
  const body = (
    <div className="flex h-full flex-col justify-between px-3 py-2.5">
      <div className="text-2xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-xl font-semibold tabular-nums tracking-tight text-zinc-950">{value}</span>
        {detail && <span className="truncate text-xs text-slate-500">{detail}</span>}
      </div>
    </div>
  );
  const wrapped = href ? (
    <Link href={href} className="block h-full hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none">
      {body}
    </Link>
  ) : (
    body
  );
  return hint ? (
    <Tooltip content={hint}>
      <div className="h-full">{wrapped}</div>
    </Tooltip>
  ) : (
    wrapped
  );
}

export function MetricStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "grid divide-x divide-slate-200/60 rounded-md border border-slate-200/60 bg-white [&>*]:min-w-0",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("min-w-0", className)} aria-label={title}>
      <div className="mb-2 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[13px] font-semibold tracking-tight text-zinc-900">{title}</h2>
          {description && <p className="text-xs text-slate-500">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

export function EmptyState({
  title,
  detail,
  action,
  className,
}: {
  title: string;
  detail?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-md border border-dashed border-slate-200 bg-white px-4 py-6", className)} role="status">
      <p className="text-[13px] font-medium text-zinc-900">{title}</p>
      {detail && <p className="mt-1 max-w-prose text-xs text-slate-500">{detail}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export interface ActiveFilter {
  key: string;
  label: string;
  onClear: () => void;
}

export function FilterBar({
  children,
  active,
  onClearAll,
  resultLabel,
}: {
  children: ReactNode;
  active: ActiveFilter[];
  onClearAll: () => void;
  resultLabel?: ReactNode;
}) {
  return (
    <div className="mb-3 space-y-2" role="search">
      <div className="flex flex-wrap items-center gap-1.5">{children}</div>
      {(active.length > 0 || resultLabel) && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {resultLabel && <span className="mr-1 text-slate-500">{resultLabel}</span>}
          {active.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={f.onClear}
              className="inline-flex items-center gap-1 rounded-sm bg-slate-100 px-1.5 py-0.5 text-2xs text-zinc-700 hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35"
              aria-label={`Remove filter ${f.label}`}
            >
              {f.label}
              <X className="size-3" />
            </button>
          ))}
          {active.length > 0 && (
            <Button variant="link" size="sm" className="text-xs text-slate-500" onClick={onClearAll}>
              Clear filters
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export function KeyValue({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-2xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-[13px] text-zinc-900">{children}</dd>
    </div>
  );
}

export function SubHeading({ children, count }: { children: ReactNode; count?: number }) {
  return (
    <h3 className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-slate-500">
      {children}
      {count !== undefined && <span className="font-normal tabular-nums text-slate-400">{count}</span>}
    </h3>
  );
}
