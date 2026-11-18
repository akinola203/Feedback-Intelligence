import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider transition-colors",
  {
    variants: {
      variant: {
        default: "border-black bg-black text-white shadow-sm",
        urgent: "border-black bg-black text-white shadow-sm",
        high: "border-neutral-800 bg-neutral-800 text-white",
        medium: "border-neutral-300 bg-neutral-200/80 text-black",
        secondary: "border-black/10 bg-black/[0.04] text-neutral-800",
        outline: "border-black/25 bg-white/60 text-black backdrop-blur-md",
        muted: "border-neutral-200 bg-neutral-100 text-neutral-500",
        inverted: "border-white bg-white text-black",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, children, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props}>
      {variant === "urgent" && (
        <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
      )}
      {children}
    </div>
  );
}

export { Badge, badgeVariants };
