"use client";

import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number;
  className?: string;
  headerClassName?: string;
  align?: "left" | "right";
  /** Accessible header label when `header` is not plain text. */
  label?: string;
}

export interface SortState {
  key: string;
  direction: "asc" | "desc";
}

export function DataTable<T>({
  rows,
  columns,
  getRowId,
  onRowClick,
  selectedId,
  defaultSort,
  pageSize = 50,
  empty,
  caption,
  scrollClassName,
  rowClassName,
}: {
  rows: T[];
  columns: Column<T>[];
  getRowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedId?: string | null;
  defaultSort?: SortState;
  pageSize?: number;
  empty?: ReactNode;
  caption: string;
  scrollClassName?: string;
  rowClassName?: (row: T) => string | undefined;
}) {
  const [sort, setSort] = useState<SortState | undefined>(defaultSort);
  const [page, setPage] = useState(0);
  const [activeIndex, setActiveIndex] = useState(-1);
  const bodyRef = useRef<HTMLTableSectionElement>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return rows;
    const factor = sort.direction === "asc" ? 1 : -1;
    const getter = column.sortValue;
    return [...rows].sort((a, b) => {
      const va = getter(a);
      const vb = getter(b);
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * factor;
      return String(va).localeCompare(String(vb)) * factor;
    });
  }, [rows, columns, sort]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visible = sorted.slice(safePage * pageSize, safePage * pageSize + pageSize);

  const toggleSort = (key: string) => {
    setSort((prev) => {
      if (prev?.key !== key) return { key, direction: "desc" };
      return { key, direction: prev.direction === "desc" ? "asc" : "desc" };
    });
    setPage(0);
  };

  const focusRow = (index: number) => {
    const row = bodyRef.current?.querySelectorAll<HTMLTableRowElement>("tr[data-row]")[index];
    row?.focus();
    setActiveIndex(index);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, index: number, row: T) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusRow(Math.min(index + 1, visible.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusRow(Math.max(index - 1, 0));
    } else if ((event.key === "Enter" || event.key === " ") && onRowClick) {
      event.preventDefault();
      onRowClick(row);
    }
  };

  if (rows.length === 0 && empty) return <>{empty}</>;

  return (
    <div className="rounded-md border border-slate-200/60 bg-white">
      <div className={cn("overflow-auto", scrollClassName)}>
        <table className="w-full border-collapse text-[13px]">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 z-10 bg-white">
            <tr className="border-b border-slate-200/70">
              {columns.map((column) => {
                const sortable = Boolean(column.sortValue);
                const isSorted = sort?.key === column.key;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={isSorted ? (sort?.direction === "asc" ? "ascending" : "descending") : undefined}
                    className={cn(
                      "h-8 whitespace-nowrap px-3 text-left text-2xs font-medium uppercase tracking-wide text-slate-500",
                      column.align === "right" && "text-right",
                      column.headerClassName,
                    )}
                  >
                    {sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.key)}
                        className={cn(
                          "inline-flex items-center gap-1 uppercase hover:text-zinc-900 focus-visible:outline-none focus-visible:text-zinc-900",
                          isSorted && "text-zinc-900",
                        )}
                      >
                        {column.header}
                        {isSorted ? (
                          sort?.direction === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />
                        ) : (
                          <ChevronsUpDown className="size-3 opacity-40" />
                        )}
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody ref={bodyRef}>
            {visible.map((row, index) => {
              const id = getRowId(row);
              const selected = selectedId === id;
              return (
                <tr
                  key={id}
                  data-row
                  tabIndex={onRowClick ? 0 : -1}
                  aria-selected={selected || undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={(e) => onKeyDown(e, index, row)}
                  onFocus={() => setActiveIndex(index)}
                  className={cn(
                    "border-b border-slate-100 last:border-0 focus-visible:outline-none",
                    onRowClick && "cursor-pointer hover:bg-slate-50 focus-visible:bg-slate-50",
                    selected && "bg-slate-100/70 hover:bg-slate-100/70",
                    activeIndex === index && "focus-visible:shadow-[inset_2px_0_0_0_#18181b]",
                    rowClassName?.(row),
                  )}
                >
                  {columns.map((column) => (
                    <td key={column.key} className={cn("px-3 py-1.5 align-middle", column.align === "right" && "text-right", column.className)}>
                      {column.cell(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pageCount > 1 && (
        <div className="flex items-center justify-between border-t border-slate-200/60 px-3 py-1.5 text-xs text-slate-500">
          <span className="tabular-nums">
            {safePage * pageSize + 1}–{Math.min((safePage + 1) * pageSize, sorted.length)} of {sorted.length}
          </span>
          <div className="flex gap-1">
            <Button size="sm" variant="ghost" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
              Previous
            </Button>
            <Button size="sm" variant="ghost" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function TableSkeleton({ rows = 8, columns = 6 }: { rows?: number; columns?: number }) {
  return (
    <div className="rounded-md border border-slate-200/60 bg-white" aria-busy="true" aria-label="Loading table">
      <div className="flex h-8 items-center gap-6 border-b border-slate-200/70 px-3">
        {Array.from({ length: columns }).map((_, i) => (
          <div key={i} className="h-2 w-14 animate-pulse rounded-sm bg-slate-200/70" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex h-8 items-center gap-6 border-b border-slate-100 px-3 last:border-0">
          {Array.from({ length: columns }).map((_, c) => (
            <div key={c} className={cn("h-2 animate-pulse rounded-sm bg-slate-100", c === 1 ? "w-64" : "w-12")} />
          ))}
        </div>
      ))}
    </div>
  );
}
