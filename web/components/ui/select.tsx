"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
}

/** Compact single-select built on Radix Select. Use value "all" for no filter. */
export function Select({
  value,
  onValueChange,
  options,
  label,
  className,
  ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  label?: string;
  className?: string;
  ariaLabel?: string;
}) {
  const current = options.find((o) => o.value === value);
  const active = value !== "all";
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger
        aria-label={ariaLabel ?? label}
        className={cn(
          "inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35",
          active ? "border-zinc-300 bg-white text-zinc-900" : "border-slate-200 bg-white text-slate-600 hover:text-zinc-900",
          className,
        )}
      >
        {label && <span className="text-slate-500">{label}</span>}
        <span className={cn("max-w-[160px] truncate", active && "font-medium")}>
          <SelectPrimitive.Value>{current?.label}</SelectPrimitive.Value>
        </span>
        <ChevronDown className="size-3 text-slate-400" aria-hidden />
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-72 min-w-[160px] overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm animate-fade-in"
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className="relative flex cursor-default select-none items-center rounded-sm py-1 pl-6 pr-2 text-xs text-zinc-800 outline-none data-[highlighted]:bg-slate-100"
              >
                <SelectPrimitive.ItemIndicator className="absolute left-1.5">
                  <Check className="size-3" />
                </SelectPrimitive.ItemIndicator>
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
