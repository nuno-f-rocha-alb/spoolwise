import * as React from "react"
import { Check } from "lucide-react"
import { Link, useNavigate } from "react-router-dom"

import { ColorPicker } from "@/components/ColorPicker"
import { FilamentSwatch } from "@/components/FilamentSwatch"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardFooter } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { useCreateFilament } from "@/hooks/useFilaments"
import { useFilaments } from "@/hooks/useFilaments"
import { bambuColors, bambuMaterials, lookupHex, useBambuColors } from "@/lib/bambu"
import { ApiError } from "@/lib/api"

const OTHER = "__other__"

/** A select whose options include an "Other…" item that reveals a text input. */
function ComboField({
  id,
  label,
  options,
  selectValue,
  onSelectChange,
  otherValue,
  onOtherChange,
  disabled,
  placeholder,
}: {
  id: string
  label: string
  options: string[]
  selectValue: string
  onSelectChange: (v: string) => void
  otherValue: string
  onOtherChange: (v: string) => void
  disabled?: boolean
  placeholder?: string
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select value={selectValue} onValueChange={onSelectChange} disabled={disabled}>
        <SelectTrigger id={id}>
          <SelectValue placeholder="— select —" />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
          <SelectItem value={OTHER}>Other…</SelectItem>
        </SelectContent>
      </Select>
      {selectValue === OTHER && (
        <Input
          autoFocus
          value={otherValue}
          placeholder={placeholder}
          onChange={(e) => onOtherChange(e.target.value)}
        />
      )}
    </div>
  )
}

export default function FilamentForm() {
  const navigate = useNavigate()
  const { data: bambu } = useBambuColors()
  const { data: filData } = useFilaments()
  const create = useCreateFilament()

  const dbBrands = filData?.brands ?? []
  const dbMaterials = filData?.materials ?? []

  const [brandSel, setBrandSel] = React.useState("")
  const [brandText, setBrandText] = React.useState("")
  const [materialSel, setMaterialSel] = React.useState("")
  const [materialText, setMaterialText] = React.useState("")
  const [colorSel, setColorSel] = React.useState("")
  const [colorText, setColorText] = React.useState("")
  const [hex, setHex] = React.useState("#808080")
  const [hexMatched, setHexMatched] = React.useState(false)
  const [stockG, setStockG] = React.useState("")
  const [pricePerKg, setPricePerKg] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)

  const brand = brandSel === OTHER ? brandText : brandSel
  const material = materialSel === OTHER ? materialText : materialSel

  const materialOptions = React.useMemo(() => {
    const set = new Set<string>([...dbMaterials, ...bambuMaterials(bambu, brand)])
    return [...set].sort()
  }, [dbMaterials, bambu, brand])

  const colorEntries = React.useMemo(
    () => bambuColors(bambu, brand, material),
    [bambu, brand, material]
  )
  const hasColorOptions = colorEntries.length > 0
  const color = hasColorOptions
    ? colorSel === OTHER
      ? colorText
      : colorSel
    : colorText

  // Auto-match the hex from the Bambu DB when brand/material/color resolve.
  React.useEffect(() => {
    if (!color) return
    const matched = lookupHex(bambu, brand, material, color)
    if (matched) {
      setHex(matched)
      setHexMatched(true)
    } else {
      setHexMatched(false)
    }
  }, [bambu, brand, material, color])

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!brand.trim()) {
      setError("Brand / name is required.")
      return
    }
    create.mutate(
      {
        name: brand.trim(),
        material: material.trim() || "PLA",
        color: color.trim(),
        color_hex: hex,
        stock_g: stockG ? Number(stockG) : undefined,
        price_per_kg: pricePerKg ? Number(pricePerKg) : undefined,
      },
      {
        onSuccess: () => navigate("/filaments"),
        onError: (err) =>
          setError(
            err instanceof ApiError ? err.message : "Could not create filament."
          ),
      }
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">New filament</h1>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <form onSubmit={onSubmit}>
        <Card>
          <CardContent className="space-y-5">
            <div className="grid gap-5 sm:grid-cols-2">
              <ComboField
                id="brand"
                label="Brand / Name"
                options={dbBrands}
                selectValue={brandSel}
                onSelectChange={(v) => {
                  setBrandSel(v)
                  setMaterialSel("")
                  setColorSel("")
                  setHex("#808080")
                  setHexMatched(false)
                }}
                otherValue={brandText}
                onOtherChange={setBrandText}
                placeholder="Brand name"
              />

              <ComboField
                id="material"
                label="Material"
                options={materialOptions}
                selectValue={materialSel}
                onSelectChange={(v) => {
                  setMaterialSel(v)
                  setColorSel("")
                }}
                otherValue={materialText}
                onOtherChange={setMaterialText}
                disabled={!brand}
                placeholder="e.g. PLA Basic"
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="color">Color</Label>
                {hasColorOptions ? (
                  <Select
                    value={colorSel}
                    onValueChange={setColorSel}
                    disabled={!material}
                  >
                    <SelectTrigger id="color">
                      <SelectValue placeholder="— select —" />
                    </SelectTrigger>
                    <SelectContent>
                      {colorEntries.map(([name, hexValue]) => (
                        <SelectItem key={name} value={name}>
                          <span className="flex items-center gap-2">
                            <FilamentSwatch hex={hexValue} />
                            {name}
                          </span>
                        </SelectItem>
                      ))}
                      <SelectItem value={OTHER}>Other…</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    id="color"
                    value={colorText}
                    disabled={!material}
                    placeholder="e.g. Black"
                    onChange={(e) => setColorText(e.target.value)}
                  />
                )}
                {hasColorOptions && colorSel === OTHER && (
                  <Input
                    autoFocus
                    value={colorText}
                    placeholder="e.g. Black"
                    onChange={(e) => setColorText(e.target.value)}
                  />
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="hex">Color hex</Label>
                <div className="flex items-center gap-3">
                  <ColorPicker
                    id="hex"
                    value={hex}
                    onChange={(h) => {
                      setHex(h)
                      setHexMatched(false)
                    }}
                  />
                  <span className="font-mono text-sm text-muted-foreground">
                    {hex}
                  </span>
                  {hexMatched && (
                    <span className="inline-flex items-center gap-1 text-sm text-success">
                      <Check className="size-4" /> Bambu color matched
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="stock">
                  Initial stock (g){" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id="stock"
                  type="number"
                  step="0.01"
                  min="0"
                  value={stockG}
                  onChange={(e) => setStockG(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="price">
                  Purchase price (/kg){" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id="price"
                  type="number"
                  step="0.0001"
                  min="0"
                  value={pricePerKg}
                  onChange={(e) => setPricePerKg(e.target.value)}
                />
              </div>
            </div>
          </CardContent>

          <CardFooter className="justify-between border-t border-border pt-6">
            <Button asChild variant="ghost">
              <Link to="/filaments">Cancel</Link>
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <Spinner /> : null}
              Create
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  )
}
