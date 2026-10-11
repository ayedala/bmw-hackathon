import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { LoaderCircle } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[13px] font-medium transition-all duration-150 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35 focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-45 disabled:active:scale-100 [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground hover:bg-brand-hover",
        secondary: "border border-slate-200 bg-white text-zinc-900 hover:bg-slate-50",
        ghost: "text-zinc-700 hover:bg-slate-100 hover:text-zinc-900",
        destructive: "border border-slate-200 bg-white text-red-700 hover:border-red-200 hover:bg-red-50",
        link: "h-auto px-0 py-0 text-zinc-900 underline-offset-2 hover:underline",
      },
      size: {
        sm: "h-7 px-2.5 text-xs",
        md: "h-8 px-3 py-1.5",
        icon: "h-7 w-7",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild = false, loading = false, children, disabled, ...props }, ref) => {
  const classes = cn(buttonVariants({ variant, size }), className);
  if (asChild) return <Slot ref={ref} className={classes} {...props}>{children}</Slot>;
  return <button ref={ref} className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
    {loading && <LoaderCircle aria-hidden className="animate-spin" />}{children}
  </button>;
});
Button.displayName = "Button";

export { buttonVariants };
