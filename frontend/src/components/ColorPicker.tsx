import * as React from "react"
import { Check } from "lucide-react"

import { Input } from "@/components/ui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"

// Common filament colours for quick selection — no native OS colour picker.
const PRESETS: [string, string][] = [
  ["Black", "#1a1a1a"],
  ["Charcoal", "#3f3f46"],
  ["Gray", "#9e9e9e"],
  ["Silver", "#c4c7cc"],
  ["White", "#f5f5f5"],
  ["Beige", "#d7ccc8"],
  ["Red", "#e53935"],
  ["Orange", "#fd7e14"],
  ["Amber", "#ffb300"],
  ["Yellow", "#fdd835"],
  ["Lime", "#c0ca33"],
  ["Green", "#43a047"],
  ["Teal", "#009688"],
  ["Cyan", "#00acc1"],
  ["Blue", "#0d6efd"],
  ["Navy", "#1f2a8a"],
  ["Purple", "#8e24aa"],
  ["Pink", "#ec407a"],
]

const HEX_RE = /^#?[0-9a-fA-F]{6}$/

function normalize(hex: string): string | null {
  const h = hex.trim()
  if (!HEX_RE.test(h)) return null
  return (h.startsWith("#") ? h : `#${h}`).toLowerCase()
}

export function ColorPicker({
  value,
  onChange,
  id,
}: {
  value: string
  onChange: (hex: string) => void
  id?: string
}) {
  const [open, setOpen] = React.useState(false)
  const [text, setText] = React.useState(value)

  React.useEffect(() => {
    setText(value)
  }, [value])

  function commitText(next: string) {
    setText(next)
    const norm = normalize(next)
    if (norm) onChange(norm)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          id={id}
          aria-label="Choose colour"
          className="size-11 cursor-pointer rounded-full border border-border shadow-sm outline-none transition-transform hover:scale-105 focus-visible:ring-[3px] focus-visible:ring-ring/40"
          style={{ backgroundColor: value }}
        />
      </PopoverTrigger>
      <PopoverContent align="start">
        <div className="space-y-3">
          <div className="grid grid-cols-6 gap-2">
            {PRESETS.map(([name, hex]) => {
              const active = normalize(value) === hex
              return (
                <button
                  key={hex}
                  type="button"
                  title={name}
                  aria-label={name}
                  onClick={() => {
                    onChange(hex)
                    setText(hex)
                  }}
                  className={cn(
                    "flex size-8 cursor-pointer items-center justify-center rounded-full border border-black/10 outline-none transition-transform hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring/50",
                    active && "ring-2 ring-ring ring-offset-2 ring-offset-popover"
                  )}
                  style={{ backgroundColor: hex }}
                >
                  {active && (
                    <Check
                      className="size-4 drop-shadow"
                      style={{
                        color: isLight(hex) ? "#111" : "#fff",
                      }}
                      strokeWidth={3}
                    />
                  )}
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-2">
            <span
              className="size-7 shrink-0 rounded-full border border-border"
              style={{ backgroundColor: normalize(text) ?? "transparent" }}
              aria-hidden
            />
            <Input
              value={text}
              spellCheck={false}
              autoCapitalize="off"
              className="h-9 font-mono"
              placeholder="#rrggbb"
              onChange={(e) => commitText(e.target.value)}
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}

// Rough perceived-lightness check so the check mark stays legible on the swatch.
function isLight(hex: string): boolean {
  const h = hex.replace("#", "")
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6
}
