import { Slot } from "@radix-ui/react-slot";
import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Mirrors care_fe/src/components/ui/button.tsx.
 *
 * Note the default variant is `primary` (CARE green), NOT stock shadcn's black `default`.
 * Keep these class lists in sync with the host when upgrading.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-colors focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-gray-950 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 aria-invalid:border-red-500 aria-invalid:ring-red-500/20",
  {
    variants: {
      variant: {
        primary:
          "bg-primary-700 text-white shadow-sm hover:bg-primary-700/90",
        outline_primary:
          "border border-primary-700 text-primary-700 bg-white shadow-xs hover:bg-primary-700 hover:text-white",
        primary_gradient:
          "text-white border border-primary-900 rounded-lg font-medium relative overflow-hidden bg-linear-to-b from-primary-700 to-primary-800 hover:from-primary-800 hover:to-primary-900 shadow-lg",
        default: "bg-gray-900 text-gray-50 shadow-sm hover:bg-gray-900/90",
        destructive: "bg-red-500 text-gray-50 shadow-xs hover:bg-red-500/90",
        outline:
          "border border-gray-400 bg-white shadow-sm hover:bg-gray-100 hover:text-gray-900",
        secondary:
          "bg-gray-100 text-gray-900 shadow-xs hover:bg-gray-100/80",
        ghost: "hover:bg-gray-100 hover:text-gray-900",
        link: "text-gray-900 underline-offset-4 hover:underline",
        white:
          "bg-white border border-secondary-400 text-gray-900 shadow-xs hover:bg-gray-100",
        warning:
          "bg-warning-100 text-warning-900 border border-warning-300 shadow-xs hover:bg-warning-100/80",
        alert:
          "bg-alert-100 text-alert-900 border border-alert-300 shadow-xs hover:bg-alert-100/80",
      },
      size: {
        default: "h-9 px-4 py-2",
        xs: "h-6 rounded-md px-2 text-xs",
        sm: "h-8 rounded-md px-3 text-xs",
        md: "h-9 rounded-md px-4 text-sm",
        lg: "h-10 rounded-md px-4",
        icon: "size-9",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { buttonVariants };
