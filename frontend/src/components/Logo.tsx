import { cn } from "@/lib/utils"

// Spoolwise mark: a filament spool — blue side discs (brand) with an orange
// wound-filament core (filament accent).
export function Logo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("size-8", className)}
      aria-hidden="true"
    >
      <rect
        x="6"
        y="8"
        width="6"
        height="32"
        rx="3"
        fill="var(--color-brand)"
      />
      <rect
        x="36"
        y="8"
        width="6"
        height="32"
        rx="3"
        fill="var(--color-brand)"
      />
      <rect
        x="12"
        y="16"
        width="24"
        height="16"
        rx="3"
        fill="var(--color-filament)"
      />
      <line
        x1="17"
        y1="16"
        x2="17"
        y2="32"
        stroke="var(--color-filament-foreground)"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
      <line
        x1="24"
        y1="16"
        x2="24"
        y2="32"
        stroke="var(--color-filament-foreground)"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
      <line
        x1="31"
        y1="16"
        x2="31"
        y2="32"
        stroke="var(--color-filament-foreground)"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
    </svg>
  )
}
