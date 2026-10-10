"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, FilterBar, PageHeader, type ActiveFilter } from "@/components/app/layout-parts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import type { AuditEvent } from "@/lib/domain/contracts";
import { formatDate, formatTime, humanize } from "@/lib/domain/derive";
import { usePersistentState, useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

interface Filters {
  q: string;
  actor: string;
  action: string;
}
const DEFAULTS: Filters = { q: "", actor: "all", action: "all" };

function verifyChain(events: AuditEvent[]) {
  for (let i = 1; i < events.length; i += 1) {
    const prev = events[i - 1];
    const cur = events[i];
    if (!prev || !cur) continue;
    if (cur.previous_event_hash !== prev.event_hash || cur.monotonic_sequence !== prev.monotonic_sequence + 1) {
      return { ok: false, at: cur.monotonic_sequence };
    }
  }
  return { ok: true, at: null };
}

export function AuditScreen() {
  const { audit, requirementByDisplayId } = useStore();
  const [filters, setFilters] = usePersistentState<Filters>("audit", DEFAULTS);
  const [check, setCheck] = useState<{ ok: boolean; at: number | null } | null>(null);
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }));

  const actions = useMemo(() => [...new Set(audit.map((e) => e.action))].sort(), [audit]);
  const filtered = useMemo(() => {
    const q = filters.q.trim().toLowerCase();
    return audit
      .filter((e) => {
        if (filters.actor !== "all" && e.actor_type !== filters.actor) return false;
        if (filters.action !== "all" && e.action !== filters.action) return false;
        if (q && !`${e.object_id} ${e.reason} ${e.actor_id} ${e.action}`.toLowerCase().includes(q)) return false;
        return true;
      })
      .slice()
      .reverse();
  }, [audit, filters]);

  const active: ActiveFilter[] = [];
  if (filters.q) active.push({ key: "q", label: `“${filters.q}”`, onClear: () => set("q", "") });
  if (filters.actor !== "all") active.push({ key: "actor", label: filters.actor === "human" ? "PM actions" : "Pipeline", onClear: () => set("actor", "all") });
  if (filters.action !== "all") active.push({ key: "action", label: humanize(filters.action), onClear: () => set("action", "all") });

  const columns: Column<AuditEvent>[] = [
    { key: "seq", header: "#", cell: (e) => <span className="font-mono text-2xs text-slate-400">{e.monotonic_sequence}</span>, sortValue: (e) => e.monotonic_sequence, align: "right", className: "w-10" },
    {
      key: "time",
      header: "Time",
      cell: (e) => (
        <span className="whitespace-nowrap tabular-nums">
          <span className="text-xs text-zinc-900">{formatTime(e.recorded_at)}</span>
          <span className="ml-1.5 text-2xs text-slate-400">{formatDate(e.recorded_at)}</span>
        </span>
      ),
      sortValue: (e) => e.recorded_at,
      className: "w-36",
    },
    {
      key: "actor",
      header: "Actor",
      cell: (e) => (
        <span className="text-xs">
          <span className={cn(e.actor_type === "human" ? "font-medium text-zinc-900" : "text-slate-600")}>{e.actor_id}</span>
          <span className="block text-2xs text-slate-400">{e.actor_type}</span>
        </span>
      ),
      sortValue: (e) => e.actor_id,
      className: "w-44",
    },
    { key: "action", header: "Action", cell: (e) => <span className="text-xs font-medium text-zinc-900">{humanize(e.action)}</span>, sortValue: (e) => e.action, className: "w-44" },
    {
      key: "object",
      header: "Object",
      cell: (e) =>
        requirementByDisplayId.has(e.object_id) ? (
          <Link href={`/requirements/${e.object_id}`} className="font-mono text-2xs text-zinc-900 underline decoration-slate-300 underline-offset-2 hover:decoration-zinc-900">
            {e.object_id}
            {e.object_revision !== null && <span className="text-slate-500"> r{e.object_revision}</span>}
          </Link>
        ) : (
          <span className="font-mono text-2xs text-slate-600">
            <span className="block text-slate-400">{e.object_type}</span>
            <span className="break-all">{e.object_id}</span>
          </span>
        ),
      sortValue: (e) => e.object_id,
      className: "w-44",
    },
    { key: "reason", header: "Reason / details", cell: (e) => <span className="text-xs leading-snug text-slate-700">{e.reason}</span>, className: "min-w-[320px]" },
    {
      key: "hash",
      header: "Hash",
      cell: (e) => (
        <Tooltip content={`event ${e.event_hash}\nprevious ${e.previous_event_hash}`}>
          <span tabIndex={0} className="font-mono text-2xs text-slate-400">
            {e.event_hash.slice(0, 8)}
          </span>
        </Tooltip>
      ),
      className: "w-20",
    },
  ];

  return (
    <div>
      <PageHeader
        title="Audit trail"
        question="What happened, who did it, and why?"
        meta={
          <>
            <span>{audit.length} events</span>
            <span>{audit.filter((e) => e.actor_type === "human").length} PM actions</span>
            <span>Append-only, hash-chained (AuditEvent contract)</span>
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            {check && (
              <span className={cn("text-xs", check.ok ? "text-zinc-700" : "text-red-700")} role="status">
                {check.ok ? `Chain intact across ${audit.length} events` : `Chain broken at event ${check.at}`}
              </span>
            )}
            <Button size="sm" onClick={() => setCheck(verifyChain(audit))}>
              Verify chain
            </Button>
          </div>
        }
      />
      <FilterBar active={active} onClearAll={() => setFilters(DEFAULTS)} resultLabel={`${filtered.length} events, newest first`}>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
          <Input value={filters.q} onChange={(e) => set("q", e.target.value)} placeholder="Search object, reason, actor" aria-label="Search audit events" className="h-7 w-60 pl-7 text-xs" />
        </div>
        <Select
          label="Actor"
          value={filters.actor}
          onValueChange={(v) => set("actor", v)}
          options={[
            { value: "all", label: "All" },
            { value: "human", label: "PM actions" },
            { value: "pipeline", label: "Pipeline" },
          ]}
        />
        <Select label="Action" value={filters.action} onValueChange={(v) => set("action", v)} options={[{ value: "all", label: "All" }, ...actions.map((a) => ({ value: a, label: humanize(a) }))]} />
      </FilterBar>
      <DataTable
        caption="Audit events"
        rows={filtered}
        columns={columns}
        getRowId={(e) => e.event_id}
        pageSize={60}
        scrollClassName="max-h-[calc(100vh-230px)]"
        empty={<EmptyState title="No events match these filters." action={<Button size="sm" onClick={() => setFilters(DEFAULTS)}>Clear filters</Button>} />}
      />
    </div>
  );
}
