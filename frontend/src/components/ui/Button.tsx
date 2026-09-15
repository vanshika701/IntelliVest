import * as React from "react"
import { cn } from "../../lib/utils"

const sizes = {
  default: "h-10 py-2 px-4",
  sm: "h-8 px-3 text-xs",
  lg: "h-12 px-6 text-base",
}

const Button = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "default" | "outline" | "ghost" | "danger" | "success"
    size?: keyof typeof sizes
  }
>(({ className, variant = "default", size = "default", ...props }, ref) => {
  const variants = {
    default: "bg-[var(--color-brand)] text-white hover:bg-[var(--color-brand-hover)] border-transparent",
    outline: "bg-transparent text-[var(--color-text-primary)] border-[var(--color-border-strong)] hover:bg-[var(--color-background-tertiary)]",
    ghost: "bg-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-background-tertiary)] border-transparent",
    danger: "bg-[var(--color-losses)] text-white hover:bg-[var(--color-losses-hover)] border-transparent",
    success: "bg-[var(--color-gains)] text-white hover:bg-[var(--color-gains-hover)] border-transparent"
  }

  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none ring-offset-background border interactive-element",
        sizes[size],
        variants[variant],
        className
      )}
      {...props}
    />
  )
})
Button.displayName = "Button"

export { Button }
