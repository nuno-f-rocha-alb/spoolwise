import { cn } from "@/lib/utils"

// Renders the filament colour dot. Prefers the hex; a valid CSS named colour in
// `color` still works as a fallback, otherwise a neutral grey (matches the
// Jinja `color_hex or color` behaviour).
export function FilamentSwatch({
  hex,
  color,
  className,
}: {
  hex?: string | null
  color?: string | null
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-block size-3.5 shrink-0 rounded-full border border-black/15",
        className
      )}
      style={{ backgroundColor: hex || color || "#888888" }}
      aria-hidden
    />
  )
}
