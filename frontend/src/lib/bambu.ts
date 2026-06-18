// Bambu color database helpers, ported from the Jinja filament_form.html.
// The JSON shape is: { "_aliases": {alias: target}, "<Brand>": { "<Material>":
// { "<ColorName>": "#hex" } } }.

import { useQuery } from "@tanstack/react-query"

export type BambuData = Record<string, unknown>

export function useBambuColors() {
  return useQuery({
    queryKey: ["bambu-colors"],
    queryFn: async (): Promise<BambuData> => {
      const res = await fetch("/static/bambu_colors.json")
      if (!res.ok) throw new Error("Failed to load Bambu colors")
      return res.json()
    },
    staleTime: Infinity,
    gcTime: Infinity,
  })
}

function aliases(bambu: BambuData): Record<string, string> {
  return (bambu._aliases as Record<string, string>) || {}
}

export function resolveAlias(bambu: BambuData | undefined, brand: string): string {
  if (!bambu) return brand
  const bl = brand.toLowerCase()
  for (const [a, t] of Object.entries(aliases(bambu))) {
    if (a.toLowerCase() === bl) return t
  }
  return brand
}

export function bambuMaterials(bambu: BambuData | undefined, brand: string): string[] {
  if (!bambu) return []
  const r = resolveAlias(bambu, brand).toLowerCase()
  for (const [k, v] of Object.entries(bambu)) {
    if (!k.startsWith("_") && k.toLowerCase() === r) {
      return Object.keys(v as Record<string, unknown>)
    }
  }
  return []
}

/** Returns [name, hex] pairs for the brand+material. */
export function bambuColors(
  bambu: BambuData | undefined,
  brand: string,
  material: string
): [string, string][] {
  if (!bambu) return []
  const r = resolveAlias(bambu, brand).toLowerCase()
  const ml = material.toLowerCase()
  for (const [bk, mats] of Object.entries(bambu)) {
    if (bk.startsWith("_") || bk.toLowerCase() !== r) continue
    for (const [mk, cols] of Object.entries(mats as Record<string, unknown>)) {
      if (mk.toLowerCase() === ml) {
        return Object.entries(cols as Record<string, string>)
      }
    }
  }
  return []
}

export function lookupHex(
  bambu: BambuData | undefined,
  brand: string,
  material: string,
  color: string
): string | null {
  const entries = bambuColors(bambu, brand, material)
  const cl = color.toLowerCase()
  for (const [n, h] of entries) {
    if (n.toLowerCase() === cl) return h
  }
  return null
}
