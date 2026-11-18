import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-2xl text-xs font-bold transition-all duration-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-black disabled:pointer-events-none disabled:opacity-45 active:scale-[0.99]",
  {
    variants: {
      variant: {
        default:
          "bg-black/90 text-white hover:bg-neutral-800 backdrop-blur-xl border border-white/15 shadow-[0_8px_24px_rgba(0,0,0,0.18)] hover:-translate-y-0.5",
        outline:
          "bg-white/55 backdrop-blur-md border border-black/15 text-black hover:bg-white/90 hover:border-black/35 shadow-sm",
        secondary:
          "bg-black/[0.05] text-black hover:bg-black/[0.1] border border-black/[0.06]",
        ghost:
          "text-neutral-600 hover:text-black hover:bg-black/[0.05]",
        inverted:
          "bg-white text-black hover:bg-neutral-200 shadow-sm",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-xl px-3 text-[11px]",
        lg: "h-11 rounded-2xl px-6 text-xs",
        icon: "h-9 w-9 rounded-xl",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
