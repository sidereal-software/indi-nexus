import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-all outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        // DEVIATION from the shadcn registry: `dark:bg-destructive/60` is dropped, so
        // the dark fill is the token itself. The registry draws the dark destructive
        // at 60% over the card, and that composite is the defect CONCERNS.md recorded:
        // it rendered #973030 at 2.48:1 under the old palette, and would render
        // #7a1719 at 1.75:1 under this one - the most dangerous button in the product
        // reading weakest in the scheme an operator uses at night. `--destructive` is
        // now chosen for that job directly (6.15:1 under this variant's hardcoded
        // `text-white`, 3.05:1 against the card, and 15.44 CIEDE2000 from
        // `--state-alert` so danger is never confusable with an instrument in Alert).
        // Not fixable from `theme.css`: `background-color` is a real property, so an
        // unlayered rule would also beat `hover:bg-destructive/90`. Keep this on the
        // next `shadcn add button`.
        destructive:
          "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40",
        // DEVIATION from the shadcn registry: `border-input` in light mode too.
        // The registry emits a bare `border` here, which takes `--border` - and
        // `--border` is decorative in this theme, a hairline that separates one
        // surface from another. SC 1.4.11 asks 3:1 of the thing that tells you
        // where a *control* is, and this variant's edge is exactly that: it is
        // the Cancel beside a destructive confirm, and the only thing drawing it.
        // Dark already hooked `--input` for this reason; light was relying on the
        // decorative token and measured 1.24:1.
        //
        // Raising `--border` instead was tried and shipped and was wrong: it put
        // a 3.78:1 line around every card, sidebar and strip on the page to fix
        // one control, and the panel read as a wireframe. Fix the control.
        // Keep this on the next `shadcn add button`.
        outline:
          "border border-input bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 rounded-md px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-md px-3 has-[>svg]:px-2.5",
        lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
        icon: "size-9",
        "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
