import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-1.5 py-px text-2xs font-medium leading-4",
  {
    variants: {
      tone: {
        neutral: "bg-slate-100 text-slate-700",
        outline: "border border-slate-200 text-slate-600",
        solid: "bg-zinc-900 text-white",
        positive: "bg-emerald-50 text-emerald-800",
        caution: "bg-amber-50 text-amber-800",
        negative: "bg-red-50 text-red-800",
        info: "bg-sky-50 text-sky-800",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
