"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  title,
  description,
  children,
  footer,
  className,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-zinc-950/20 animate-fade-in" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-[8vh] z-50 flex max-h-[84vh] w-[min(560px,calc(100vw-32px))] -translate-x-1/2 flex-col rounded-md border border-slate-200 bg-white shadow-lg animate-fade-in focus-visible:outline-none",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200/60 px-4 py-3">
          <div>
            <DialogPrimitive.Title className="text-sm font-semibold tracking-tight text-zinc-900">{title}</DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="mt-0.5 text-xs text-slate-500">{description}</DialogPrimitive.Description>
            ) : (
              <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
            )}
          </div>
          <DialogPrimitive.Close className="rounded-sm p-0.5 text-slate-400 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35" aria-label="Close">
            <X className="size-4" />
          </DialogPrimitive.Close>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
        {footer && <div className="flex items-center justify-end gap-2 border-t border-slate-200/60 px-4 py-2.5">{footer}</div>}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

/** Right-hand detail panel (Radix Dialog, non-blocking look). */
export function SidePanel({
  open,
  onOpenChange,
  title,
  eyebrow,
  children,
  footer,
  width = "w-[min(560px,100vw)]",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  eyebrow?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange} modal={false}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Content
          onInteractOutside={(event) => event.preventDefault()}
          className={cn(
            "fixed inset-y-0 right-0 z-40 flex flex-col border-l border-slate-200 bg-white shadow-[-8px_0_24px_-12px_rgba(9,9,11,0.12)] animate-slide-in focus-visible:outline-none",
            width,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-slate-200/60 px-4 py-3">
            <div className="min-w-0">
              {eyebrow && <div className="mb-1 text-2xs text-slate-500">{eyebrow}</div>}
              <DialogPrimitive.Title className="text-sm font-semibold leading-snug tracking-tight text-zinc-900">{title}</DialogPrimitive.Title>
              <DialogPrimitive.Description className="sr-only">Detail panel</DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close className="rounded-sm p-0.5 text-slate-400 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35" aria-label="Close panel">
              <X className="size-4" />
            </DialogPrimitive.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
          {footer && <div className="flex items-center gap-2 border-t border-slate-200/60 px-4 py-2.5">{footer}</div>}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
