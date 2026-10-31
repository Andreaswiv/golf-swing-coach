import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

/*
  Pill buttons that respond: they lift a pixel and deepen their shadow on hover, press in on click
  (active:scale), and ease every change over 200 ms. translate and scale are separate CSS properties
  in Tailwind 4, so the hover lift and the press compose. Reduced motion turns the movement off (index.css).
*/
const buttonVariants = cva(
  "relative inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-full text-sm font-medium whitespace-nowrap outline-none select-none transition-[translate,scale,background-color,color,box-shadow,border-color,opacity] duration-150 ease-[cubic-bezier(0.22,0.8,0.24,1)] active:scale-[0.97] active:duration-75 focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-45 aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:transition-transform [&_svg]:duration-200 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[inset_0_1px_0_rgb(255_255_255/0.14),0_1px_2px_rgb(0_0_0/0.18)] hover:-translate-y-px hover:bg-[#262626] hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.14),0_10px_24px_-10px_rgb(0_0_0/0.55)]",
        white:
          "bg-white text-[#111] shadow-[0_1px_2px_rgb(0_0_0/0.08)] hover:-translate-y-px hover:shadow-[0_10px_28px_-10px_rgb(0_0_0/0.35)]",
        glass:
          "border border-white/20 bg-white/10 text-white backdrop-blur-md hover:-translate-y-px hover:border-white/35 hover:bg-white/20",
        destructive:
          "bg-destructive text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.18)] hover:-translate-y-px hover:bg-destructive/90 hover:shadow-[0_10px_24px_-10px_rgb(196_55_43/0.6)] focus-visible:ring-destructive/30",
        outline:
          "border border-foreground/15 bg-transparent hover:-translate-y-px hover:border-foreground/30 hover:bg-foreground/[0.04]",
        secondary: "bg-secondary text-secondary-foreground hover:-translate-y-px hover:bg-[#d9d9d4]",
        ghost: "hover:bg-foreground/[0.06]",
        link: "rounded-md text-primary underline-offset-4 hover:underline active:scale-100",
      },
      size: {
        default: "h-10 px-5 has-[>svg]:px-4",
        xs: "h-7 gap-1 px-2.5 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 px-3.5 has-[>svg]:px-3",
        lg: "h-12 px-7 text-[15px] has-[>svg]:px-6",
        icon: "size-10",
        "icon-xs": "size-7 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-12",
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
