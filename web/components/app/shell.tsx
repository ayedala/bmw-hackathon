"use client";

import { Command } from "cmdk";
import { Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";

import { EvidenceDetail, OpenSourceButton } from "@/components/app/evidence-detail";
import { Button } from "@/components/ui/button";
import { SidePanel } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TooltipProvider } from "@/components/ui/tooltip";
import { decisionStatus, latestRevision, TOPIC_LABEL } from "@/lib/domain/derive";
import { MARKETS, MARKET_LABEL, type MarketCode } from "@/lib/domain/model";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Evidence panel — any screen can open evidence without page hopping  */
/* ------------------------------------------------------------------ */

const EvidencePanelContext = createContext<{ open: (id: string) => void } | null>(null);

export function useEvidencePanel() {
  const ctx = useContext(EvidencePanelContext);
  if (!ctx) throw new Error("useEvidencePanel must be used inside AppShell");
  return ctx;
}

function EvidencePanelHost({ children }: { children: ReactNode }) {
  const { evidenceById } = useStore();
  const [id, setId] = useState<string | null>(null);
  const evidence = id ? evidenceById.get(id) : undefined;
  const value = useMemo(() => ({ open: (next: string) => setId(next) }), []);
  return (
    <EvidencePanelContext.Provider value={value}>
      {children}
      <SidePanel
        open={Boolean(id)}
        onOpenChange={(o) => !o && setId(null)}
        title={evidence ? "Evidence" : "Evidence not found"}
        eyebrow={evidence ? `${evidence.source_name}` : undefined}
        footer={
          evidence ? (
            <>
              <OpenSourceButton evidence={evidence} />
              <Button variant="ghost" onClick={() => setId(null)}>
                Close
              </Button>
            </>
          ) : undefined
        }
      >
        {evidence ? (
          <EvidenceDetail evidence={evidence} />
        ) : (
          <p className="text-xs text-slate-500">
            Record <span className="font-mono">{id}</span> is referenced but its source file is not loaded. Check Settings → Data sources.
          </p>
        )}
      </SidePanel>
    </EvidencePanelContext.Provider>
  );
}

/* ------------------------------------------------------------------ */
/* Sidebar                                                             */
/* ------------------------------------------------------------------ */

interface NavItem {
  href: string;
  label: string;
  count?: number;
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex h-7 items-center justify-between rounded-md px-2 text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
        active
          ? "bg-brand-soft font-medium text-brand shadow-[inset_2px_0_0_0_#0066cc]"
          : "text-zinc-600 hover:bg-slate-100 hover:text-zinc-900",
      )}
    >
      {item.label}
      {item.count !== undefined && <span className={cn("text-2xs tabular-nums", active ? "text-brand" : "text-slate-400")}>{item.count}</span>}
    </Link>
  );
}

function AppSidebar() {
  const pathname = usePathname();
  const liveStudio = pathname === "/" || pathname === "/video-memory" || pathname === "/evaluation";
  const { dataset, requirements } = useStore();
  const openDecisions = requirements.filter((r) => {
    const s = decisionStatus(latestRevision(r), r.decisions);
    return s === "under_review" || s === "challenged" || s === "draft";
  }).length;

  const groups: { label?: string; items: NavItem[] }[] = [
    { items: [{ href: "/", label: "Decision Studio" }, { href: "/video-memory", label: "Video memory" }, { href: "/evaluation", label: "Evaluation" }] },
    {label: "Planning workbench", items: [{href: "/overview", label: "Overview"}]},
    {
      label: "Intelligence",
      items: [
        { href: "/findings", label: "Findings", count: dataset.findings.length },
        { href: "/evidence", label: "Evidence", count: dataset.evidence.length },
        { href: "/hypotheses", label: "Hypotheses", count: dataset.hypotheses.length },
      ],
    },
    {
      label: "Requirements",
      items: [
        { href: "/requirements", label: "Requirements", count: requirements.length },
        { href: "/prioritization", label: "Prioritization" },
      ],
    },
    {
      label: "Research",
      items: [
        { href: "/sources", label: "Sources" },
        { href: "/markets", label: "Markets" },
      ],
    },
    {
      label: "Governance",
      items: [
        { href: "/decisions", label: "Decisions", count: openDecisions },
        { href: "/audit", label: "Audit trail" },
      ],
    },
  ];

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`));

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 flex-col border-r border-slate-200 bg-white lg:flex" aria-label="Primary">
      <div className="flex h-14 items-center border-b border-slate-200 px-3">
        <Link href="/" className="flex items-center gap-2.5 focus-visible:outline-none">
          {/* eslint-disable-next-line @next/next/no-img-element -- static local SVG */}
          <img src="/bmw-roundel.svg" alt="BMW" width={30} height={30} className="shrink-0" />
          <span className="leading-tight">
            <span className="block text-[13px] font-semibold tracking-tight text-zinc-950">Product Decision Lab</span>
            <span className="block text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500">Product Mgmt · Internal</span>
          </span>
        </Link>
      </div>
      <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-3">
        {groups.filter((_, index) => !liveStudio || index < 2).map((group, i) => (
          <div key={group.label ?? i}>
            {group.label && <div className="mb-1 px-2 text-2xs font-medium uppercase tracking-wide text-slate-400">{group.label}</div>}
            <div className="space-y-px">
              {group.items.map((item) => (
                <NavLink key={item.href} item={item} active={isActive(item.href)} />
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="border-t border-slate-200 px-2 py-2">
        <NavLink item={{ href: "/settings", label: liveStudio ? "Workbench settings" : "Settings" }} active={isActive("/settings")} />
      </div>
    </aside>
  );
}

/* Compact top navigation shown below lg breakpoint, where the sidebar collapses. */
function CompactNav() {
  const pathname = usePathname();
  const items = [
    ["/", "Decision Studio"],
    ["/video-memory", "Video memory"],
    ["/evaluation", "Evaluation"],
    ["/overview", "Overview"],
    ["/findings", "Findings"],
    ["/evidence", "Evidence"],
    ["/hypotheses", "Hypotheses"],
    ["/requirements", "Requirements"],
    ["/prioritization", "Prioritization"],
    ["/sources", "Sources"],
    ["/markets", "Markets"],
    ["/decisions", "Decisions"],
    ["/audit", "Audit"],
    ["/settings", "Settings"],
  ] as const;
  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-3 py-1.5 lg:hidden" aria-label="Primary">
      {items.filter((_, index) => (pathname !== "/" && pathname !== "/video-memory") || index < 3).map(([href, label]) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn("whitespace-nowrap rounded-md px-2 py-1 text-xs", active ? "bg-brand-soft font-medium text-brand" : "text-zinc-600")}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

/* ------------------------------------------------------------------ */
/* Context bar                                                          */
/* ------------------------------------------------------------------ */

export function MarketSelector({ value, onChange, size = "md" }: { value: MarketCode; onChange: (m: MarketCode) => void; size?: "sm" | "md" }) {
  return (
    <div role="radiogroup" aria-label="Market" className="inline-flex rounded-md border border-slate-200 bg-white p-0.5">
      {MARKETS.map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={value === m}
          title={MARKET_LABEL[m]}
          onClick={() => onChange(m)}
          className={cn(
            "rounded-sm font-mono font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
            size === "sm" ? "px-1.5 py-0.5 text-2xs" : "px-2 py-0.5 text-xs",
            value === m ? "bg-brand text-white" : "text-slate-600 hover:text-zinc-900",
          )}
        >
          {m}
        </button>
      ))}
    </div>
  );
}

function DataStatus() {
  const { dataset, sessionEventCount } = useStore();
  const pipelineCount = dataset.evidence.filter((e) => e.provenance === "pipeline").length;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="hidden items-center gap-1.5 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35 xl:inline-flex"
        >
          <span aria-hidden className={cn("size-1.5 rounded-full", pipelineCount > 0 ? "bg-zinc-900" : "bg-slate-300")} />
          {dataset.requirements.length} proposals · {pipelineCount} pipeline records
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-3">
        <p className="text-xs font-medium text-zinc-900">Data sources</p>
        <ul className="mt-2 space-y-1">
          {dataset.source_files.map((f) => (
            <li key={f.path} className="flex items-center justify-between gap-2 text-2xs">
              <span className="truncate font-mono text-slate-600">{f.path}</span>
              <span className={cn("shrink-0", f.status === "loaded" ? "text-zinc-900" : "text-amber-700")}>
                {f.status === "loaded" ? `${f.records} rec` : f.status}
              </span>
            </li>
          ))}
        </ul>
        <ul className="mt-3 space-y-1 border-t border-slate-100 pt-2 text-2xs text-slate-500">
          {dataset.data_notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
          <li>{sessionEventCount} PM actions recorded in this browser session.</li>
        </ul>
      </PopoverContent>
    </Popover>
  );
}

function ContextBar({ onSearch }: { onSearch: () => void }) {
  const { dataset, market, setMarket } = useStore();
  const pathname = usePathname();
  if (pathname === "/" || pathname === "/video-memory") return (
    <div className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 lg:px-6">
      <span className="text-[13px] font-semibold">BMW Decision Studio</span>
      <span className="text-xs text-slate-500">Customer evidence · Market research · Video memory</span>
    </div>
  );
  return (
    <div className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-slate-200 bg-white px-4 lg:px-6">
      <div className="flex min-w-0 items-center gap-2.5 lg:hidden">
        {/* eslint-disable-next-line @next/next/no-img-element -- static local SVG */}
        <img src="/bmw-roundel.svg" alt="BMW" width={26} height={26} />
      </div>
      <dl className="flex min-w-0 items-center gap-5 text-xs">
        <div className="min-w-0">
          <dt className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500">Vehicle</dt>
          <dd className="truncate font-medium text-zinc-900">
            {dataset.vehicle.family} ({dataset.vehicle.generation})
          </dd>
        </div>
        <div className="hidden sm:block">
          <dt className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500">Planning</dt>
          <dd className="whitespace-nowrap text-zinc-900">Successor {dataset.vehicle.horizon}</dd>
        </div>
        <div className="hidden md:block">
          <dt className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500">Proposal set</dt>
          <dd className="whitespace-nowrap font-mono text-2xs text-zinc-700">{dataset.planning.version}</dd>
        </div>
      </dl>
      <div className="ml-auto flex items-center gap-2">
        <DataStatus />
        <div className="flex items-center gap-1.5">
          <span className="hidden text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500 xl:inline">Market</span>
          <MarketSelector value={market} onChange={setMarket} />
        </div>
        <button
          type="button"
          onClick={onSearch}
          className="inline-flex h-7 items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 text-xs text-slate-500 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35"
          aria-label="Search (Ctrl+K)"
        >
          <Search className="size-3.5" aria-hidden />
          <span className="hidden sm:inline">Search</span>
          <kbd className="hidden rounded-sm border border-slate-200 px-1 font-sans text-2xs text-slate-400 sm:inline">⌘K</kbd>
        </button>
        <span className="hidden rounded-sm border border-slate-300 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-600 md:inline" title="Information classification">
          Internal
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Command menu (Cmd/Ctrl + K)                                         */
/* ------------------------------------------------------------------ */

function CommandMenu({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const { dataset, requirements, setMarket } = useStore();
  const evidencePanel = useEvidencePanel();
  const [query, setQuery] = useState("");

  const run = (fn: () => void) => {
    onOpenChange(false);
    setQuery("");
    fn();
  };

  const item = "flex cursor-default items-start gap-3 rounded-sm px-2 py-1.5 text-[13px] aria-selected:bg-slate-100";
  const heading =
    "[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-2xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-slate-400";

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-zinc-950/20 animate-fade-in" />
        <DialogPrimitive.Content className="fixed left-1/2 top-[12vh] z-50 w-[min(640px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg animate-fade-in">
          <DialogPrimitive.Title className="sr-only">Search</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Search requirements, findings, hypotheses, evidence and markets</DialogPrimitive.Description>
          <Command loop className={heading}>
            <div className="flex items-center gap-2 border-b border-slate-200/70 px-3">
              <Search className="size-4 text-slate-400" aria-hidden />
              <Command.Input
                value={query}
                onValueChange={setQuery}
                placeholder="Search requirements, findings, evidence…"
                className="h-10 flex-1 bg-transparent text-[13px] text-zinc-900 outline-none placeholder:text-slate-400"
              />
            </div>
            <Command.List className="max-h-[60vh] overflow-y-auto p-1.5">
              <Command.Empty className="px-2 py-6 text-center text-xs text-slate-500">No requirement, finding, hypothesis or evidence matches “{query}”.</Command.Empty>
              <Command.Group heading="Requirements">
                {requirements.map((r) => {
                  const rev = latestRevision(r);
                  return (
                    <Command.Item key={r.display_id} value={`${r.display_id} ${rev.title} ${r.topic}`} className={item} onSelect={() => run(() => router.push(`/requirements/${r.display_id}`))}>
                      <span className="w-24 shrink-0 font-mono text-2xs leading-5 text-slate-500">{r.display_id}</span>
                      <span className="min-w-0">
                        <span className="block truncate text-zinc-900">{rev.title}</span>
                        <span className="block text-2xs text-slate-500">
                          Requirement · 5 Series G60 · United States · {TOPIC_LABEL[r.topic] ?? r.topic}
                        </span>
                      </span>
                    </Command.Item>
                  );
                })}
              </Command.Group>
              <Command.Group heading="Findings">
                {dataset.findings.map((f) => (
                  <Command.Item key={f.id} value={`${f.id} ${f.title}`} className={item} onSelect={() => run(() => router.push(`/findings?id=${f.id}`))}>
                    <span className="w-24 shrink-0 font-mono text-2xs leading-5 text-slate-500">{f.id}</span>
                    <span className="min-w-0">
                      <span className="block truncate text-zinc-900">{f.title}</span>
                      <span className="block text-2xs text-slate-500">Finding · {MARKET_LABEL[f.market]} · {TOPIC_LABEL[f.topic]}</span>
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Hypotheses">
                {dataset.hypotheses.map((h) => (
                  <Command.Item key={h.id} value={`${h.id} ${h.statement}`} className={item} onSelect={() => run(() => router.push(`/hypotheses?id=${h.id}`))}>
                    <span className="w-24 shrink-0 font-mono text-2xs leading-5 text-slate-500">{h.id}</span>
                    <span className="min-w-0 truncate text-zinc-900">{h.statement}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              {query.length >= 2 && (
                <Command.Group heading="Evidence">
                  {dataset.evidence.map((e) => (
                    <Command.Item
                      key={e.id}
                      value={`${e.id} ${e.claim} ${e.vehicle} ${e.source_name}`}
                      className={item}
                      onSelect={() => run(() => evidencePanel.open(e.id))}
                    >
                      <span className="w-24 shrink-0 truncate font-mono text-2xs leading-5 text-slate-500">{e.id}</span>
                      <span className="min-w-0">
                        <span className="block truncate text-zinc-900">{e.claim}</span>
                        <span className="block text-2xs text-slate-500">
                          Evidence · {e.vehicle} · {e.market} · {e.source_name}
                        </span>
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              <Command.Group heading="Markets">
                {MARKETS.map((m) => (
                  <Command.Item key={m} value={`market ${m} ${MARKET_LABEL[m]}`} className={item} onSelect={() => run(() => setMarket(m))}>
                    <span className="w-24 shrink-0 font-mono text-2xs leading-5 text-slate-500">{m}</span>
                    <span className="text-zinc-900">Switch market to {MARKET_LABEL[m]}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Vehicles">
                <Command.Item value="vehicle BMW i5 5 Series G60" className={item} onSelect={() => run(() => router.push("/evidence?vehicle=BMW"))}>
                  <span className="w-24 shrink-0 font-mono text-2xs leading-5 text-slate-500">G60</span>
                  <span className="text-zinc-900">BMW 5 Series (G60) — evidence</span>
                </Command.Item>
                {dataset.benchmark
                  .filter((b) => !b.is_reference)
                  .map((b) => (
                    <Command.Item key={b.vehicle} value={`vehicle ${b.vehicle}`} className={item} onSelect={() => run(() => router.push(`/evidence?q=${encodeURIComponent(b.vehicle.split(" ").slice(-2).join(" "))}`))}>
                      <span className="w-24 shrink-0 font-mono text-2xs leading-5 text-slate-500">Cohort</span>
                      <span className="text-zinc-900">{b.vehicle} — evidence</span>
                    </Command.Item>
                  ))}
              </Command.Group>
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/* ------------------------------------------------------------------ */
/* Shell                                                                */
/* ------------------------------------------------------------------ */

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [searchOpen, setSearchOpen] = useState(false);
  const toggle = useCallback(() => setSearchOpen((o) => !o), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  return (
    <TooltipProvider delayDuration={250}>
      <EvidencePanelHost>
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-white focus:px-2 focus:py-1 focus:text-xs">
          Skip to content
        </a>
        <AppSidebar />
        <div className="lg:pl-56">
          <ContextBar onSearch={() => setSearchOpen(true)} />
          <CompactNav />
          <main id="main" className="mx-auto max-w-[1680px] px-4 py-5 lg:px-6">
            {pathname !== "/" && pathname !== "/video-memory" && pathname !== "/evaluation" && <div className="mb-4 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">Planning workbench includes labelled synthetic examples and browser-local review actions. <Link href="/" className="font-medium text-brand">Open Decision Studio</Link> for live research using the evidence database.</div>}
            {children}
          </main>
        </div>
        <CommandMenu open={searchOpen} onOpenChange={setSearchOpen} />
      </EvidencePanelHost>
    </TooltipProvider>
  );
}
