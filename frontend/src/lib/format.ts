// Display helpers. Currency symbol comes from the user's settings (server),
// so these take it as an argument rather than hardcoding a locale currency.

export function money(value: number, currency: string, digits = 2): string {
  return `${value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} ${currency}`
}

export function grams(value: number, digits = 0): string {
  return `${value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} g`
}

export function kilos(value: number, digits = 2): string {
  return `${value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} kg`
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

// Render `print_time_hours` (decimal hours) as "Hh MMm", matching the Jinja
// `duration` filter.
export function duration(hours: number): string {
  const h = Math.floor(hours)
  let m = Math.round((hours - h) * 60)
  let hh = h
  if (m === 60) {
    hh += 1
    m = 0
  }
  return `${hh}h ${String(m).padStart(2, "0")}m`
}
