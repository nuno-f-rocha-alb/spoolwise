import * as React from "react"
import { Copy, FileUp, Plus, X } from "lucide-react"
import { Link, Navigate, useNavigate, useParams } from "react-router-dom"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
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
import { FilamentSwatch } from "@/components/FilamentSwatch"
import { useFilaments } from "@/hooks/useFilaments"
import { useOrderDetail } from "@/hooks/useOrderDetail"
import { useCreateOrder, useSettings, useUpdateOrder } from "@/hooks/useOrders"
import { api, ApiError } from "@/lib/api"
import type { Filament, OrderFormPayload, Parse3mfResponse } from "@/types"

interface FilRow {
  brand: string
  material: string
  filamentId: string
  weight: string
  priceOverride: string
}
interface PlateForm {
  name: string
  hours: string
  minutes: string
  filaments: FilRow[]
}

const emptyRow = (): FilRow => ({
  brand: "",
  material: "",
  filamentId: "",
  weight: "",
  priceOverride: "",
})
const emptyPlate = (): PlateForm => ({
  name: "",
  hours: "",
  minutes: "",
  filaments: [emptyRow()],
})

function uniqSorted(xs: string[]): string[] {
  return [...new Set(xs)].sort()
}

function FilamentRowEditor({
  row,
  filaments,
  currency,
  onChange,
  onRemove,
  canRemove,
}: {
  row: FilRow
  filaments: Filament[]
  currency: string
  onChange: (r: FilRow) => void
  onRemove: () => void
  canRemove: boolean
}) {
  const brands = uniqSorted(filaments.map((f) => f.name))
  const materials = uniqSorted(
    filaments.filter((f) => f.name === row.brand).map((f) => f.material)
  )
  const colors = filaments.filter(
    (f) => f.name === row.brand && f.material === row.material
  )
  const selected = filaments.find((f) => String(f.id) === row.filamentId)
  const [showOverride, setShowOverride] = React.useState(row.priceOverride !== "")

  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_1fr_auto_auto] sm:items-end">
        <div>
          <Label className="mb-1 text-xs text-muted-foreground">Brand</Label>
          <Select
            value={row.brand}
            onValueChange={(v) =>
              onChange({ ...row, brand: v, material: "", filamentId: "" })
            }
          >
            <SelectTrigger size="sm">
              <SelectValue placeholder="— brand —" />
            </SelectTrigger>
            <SelectContent>
              {brands.map((b) => (
                <SelectItem key={b} value={b}>
                  {b}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1 text-xs text-muted-foreground">Material</Label>
          <Select
            value={row.material}
            disabled={!row.brand}
            onValueChange={(v) => onChange({ ...row, material: v, filamentId: "" })}
          >
            <SelectTrigger size="sm">
              <SelectValue placeholder="— material —" />
            </SelectTrigger>
            <SelectContent>
              {materials.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1 text-xs text-muted-foreground">Color</Label>
          <Select
            value={row.filamentId}
            disabled={!row.material}
            onValueChange={(v) => onChange({ ...row, filamentId: v })}
          >
            <SelectTrigger size="sm">
              <SelectValue placeholder="— color —" />
            </SelectTrigger>
            <SelectContent>
              {colors.map((f) => (
                <SelectItem key={f.id} value={String(f.id)}>
                  <span className="flex items-center gap-2">
                    <FilamentSwatch hex={f.color_hex} color={f.color} />
                    {f.color}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1 text-xs text-muted-foreground">Weight (g)</Label>
          <Input
            type="number"
            step="0.01"
            min="0.01"
            className="h-9 w-24"
            value={row.weight}
            onChange={(e) => onChange({ ...row, weight: e.target.value })}
          />
        </div>
        <Button
          type="button"
          size="icon"
          variant="outline"
          className="size-9 text-destructive hover:bg-destructive/10"
          disabled={!canRemove}
          aria-label="Remove filament"
          onClick={onRemove}
        >
          <X className="size-4" />
        </Button>
      </div>
      {selected && (
        <div className="flex items-center gap-2 pl-1 text-xs">
          <FilamentSwatch hex={selected.color_hex} color={selected.color} />
          <span
            className={
              selected.stock_g <= 0
                ? "rounded bg-destructive/15 px-1.5 py-0.5 text-destructive"
                : "rounded bg-muted px-1.5 py-0.5 text-muted-foreground"
            }
          >
            Stock: {selected.stock_g.toFixed(0)} g
            {selected.stock_g <= 0 ? " ⚠ none" : ""}
          </span>
          <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">
            {selected.avg_price_per_kg.toFixed(2)} {currency}/kg
          </span>
          {!showOverride && (
            <button
              type="button"
              className="text-primary underline-offset-2 hover:underline"
              onClick={() => setShowOverride(true)}
            >
              Override price/kg
            </button>
          )}
        </div>
      )}
      {selected && showOverride && (
        <div className="flex items-center gap-2 pl-1">
          <Label className="text-xs text-muted-foreground">Override price ({currency}/kg)</Label>
          <Input
            type="number"
            step="0.0001"
            min="0.0001"
            className="h-8 w-28"
            placeholder={selected.avg_price_per_kg.toFixed(2)}
            value={row.priceOverride}
            onChange={(e) => onChange({ ...row, priceOverride: e.target.value })}
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="size-7"
            aria-label="Clear override"
            onClick={() => {
              setShowOverride(false)
              onChange({ ...row, priceOverride: "" })
            }}
          >
            <X className="size-3.5" />
          </Button>
        </div>
      )}
    </div>
  )
}

export default function OrderForm() {
  const { id } = useParams()
  const editId = id ? Number(id) : null
  const editMode = editId !== null
  const navigate = useNavigate()

  const { data: filData } = useFilaments()
  const { data: settings } = useSettings()
  const { data: editData } = useOrderDetail(editMode ? editId! : NaN)

  const create = useCreateOrder()
  const update = useUpdateOrder(editId ?? 0)

  const retail = settings?.retail_mode_enabled ?? false
  const filaments = filData?.filaments ?? []
  const currency = filData?.currency ?? "€"

  const [name, setName] = React.useState("")
  const [customer, setCustomer] = React.useState("")
  const [notes, setNotes] = React.useState("")
  const [profitPct, setProfitPct] = React.useState("")
  const [quantity, setQuantity] = React.useState("1")
  const [isInternal, setIsInternal] = React.useState(false)
  const [skipStock, setSkipStock] = React.useState(false)
  const [hasVat, setHasVat] = React.useState(false)
  const [vatRate, setVatRate] = React.useState("")
  const [urls, setUrls] = React.useState<string[]>([""])
  const [plates, setPlates] = React.useState<PlateForm[]>([emptyPlate()])
  const [error, setError] = React.useState<string | null>(null)
  const [parseWarning, setParseWarning] = React.useState<string | null>(null)
  const [parsing, setParsing] = React.useState(false)
  const fileRef = React.useRef<HTMLInputElement>(null)

  // defaults for new order
  const seeded = React.useRef(false)
  React.useEffect(() => {
    if (!editMode && settings && !seeded.current) {
      setProfitPct(String(settings.default_profit_pct))
      setVatRate(String(settings.default_vat_rate_pct))
      seeded.current = true
    }
  }, [editMode, settings])

  // prefill edit — wait for filaments too, then mark prefill done so the form
  // body mounts only once the cascade Selects can be given valid values.
  const [prefillDone, setPrefillDone] = React.useState(!editMode)
  const prefilled = React.useRef(false)
  React.useEffect(() => {
    if (editMode && editData && filData && !prefilled.current) {
      const o = editData.order
      setName(o.name)
      setCustomer(o.customer ?? "")
      setNotes(o.notes ?? "")
      setProfitPct(String(o.profit_pct))
      setQuantity(String(o.quantity))
      setIsInternal(o.is_internal)
      setSkipStock(o.skip_stock_deduction)
      setHasVat(o.has_vat)
      setVatRate(String(o.vat_rate_pct ?? settings?.default_vat_rate_pct ?? 23))
      setUrls(o.links.length ? o.links.map((l) => l.url) : [""])
      setPlates(
        o.plates.map((p) => ({
          name: p.name ?? "",
          hours: String(Math.floor(p.print_time_hours)),
          minutes: String(Math.round((p.print_time_hours % 1) * 60)),
          filaments: p.items.map((it) => ({
            brand: it.filament?.name ?? "",
            material: it.filament?.material ?? "",
            filamentId: String(it.filament?.id ?? it.filament_id ?? ""),
            weight: String(it.weight_g),
            priceOverride:
              it.price_per_kg_override !== null && it.price_per_kg_override !== undefined
                ? String(it.price_per_kg_override)
                : "",
          })),
        }))
      )
      prefilled.current = true
      setPrefillDone(true)
    }
  }, [editMode, editData, filData, settings])

  const personal = isInternal
  const showVat = retail && !personal

  function updatePlate(i: number, patch: Partial<PlateForm>) {
    setPlates((ps) => ps.map((p, idx) => (idx === i ? { ...p, ...patch } : p)))
  }
  function duplicatePlate(i: number) {
    setPlates((ps) => {
      const src = ps[i]
      const copy: PlateForm = {
        ...src,
        filaments: src.filaments.map((f) => ({ ...f })),
      }
      return [...ps.slice(0, i + 1), copy, ...ps.slice(i + 1)]
    })
  }
  function updateRow(pi: number, ri: number, row: FilRow) {
    setPlates((ps) =>
      ps.map((p, idx) =>
        idx === pi
          ? { ...p, filaments: p.filaments.map((r, j) => (j === ri ? row : r)) }
          : p
      )
    )
  }

  async function on3mfPicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    setParsing(true)
    setParseWarning(null)
    setError(null)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const data = await api.upload<Parse3mfResponse>("/api/parse-3mf", fd)
      if (!data.plates?.length) {
        setParseWarning(data.warning || "No plate data found in this .3mf file.")
        return
      }
      const unmatched: string[] = []
      setPlates(
        data.plates.map((pl) => ({
          name: pl.name || "",
          hours: String(Math.floor(pl.print_time_hours || 0)),
          minutes: String(Math.round(((pl.print_time_hours || 0) % 1) * 60)),
          filaments:
            pl.filaments.map((fl) => {
              if (fl.matched) {
                return {
                  brand: fl.matched.brand,
                  material: fl.matched.material,
                  filamentId: String(fl.matched.id),
                  weight: String(fl.used_g),
                  priceOverride: "",
                }
              }
              unmatched.push(`${fl.type} (${fl.color}) — plate ${pl.index}`)
              return {
                brand: "",
                material: "",
                filamentId: "",
                weight: String(fl.used_g),
                priceOverride: "",
              }
            }) || [emptyRow()],
        }))
      )
      const msgs: string[] = []
      if (data.warning) msgs.push(data.warning)
      if (unmatched.length)
        msgs.push(`${unmatched.length} filament(s) not matched — select manually.`)
      if (msgs.length) setParseWarning(msgs.join(" "))
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to parse the .3mf file."
      )
    } finally {
      setParsing(false)
    }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const payload: OrderFormPayload = {
      name: name.trim(),
      customer: customer.trim() || null,
      notes: notes.trim() || null,
      model_urls: urls.map((u) => u.trim()).filter(Boolean),
      is_internal: isInternal,
      skip_stock_check: skipStock,
      profit_pct: Number(profitPct) || 0,
      quantity: Math.max(1, Number(quantity) || 1),
      has_vat: showVat && hasVat,
      vat_rate_pct: showVat && hasVat ? Number(vatRate) || 0 : null,
      plates: plates.map((p) => ({
        name: p.name.trim() || null,
        print_time_hours: (Number(p.hours) || 0) + (Number(p.minutes) || 0) / 60,
        filaments: p.filaments
          .filter((f) => f.filamentId && Number(f.weight) > 0)
          .map((f) => ({
            filament_id: Number(f.filamentId),
            weight_g: Number(f.weight),
            price_per_kg_override: f.priceOverride ? Number(f.priceOverride) : null,
          })),
      })),
    }

    const onError = (err: unknown) =>
      setError(err instanceof ApiError ? err.message : "Could not save the order.")
    const onSuccess = (res: { order: { id: number } }) =>
      navigate(`/orders/${res.order.id}`)

    if (editMode) update.mutate(payload, { onSuccess, onError })
    else create.mutate(payload, { onSuccess, onError })
  }

  const pending = create.isPending || update.isPending

  // Bad edit URL like /orders/abc/edit → don't hang on a spinner.
  if (id && Number.isNaN(editId)) {
    return <Navigate to="/orders" replace />
  }

  // Hold the form (and its cascade Selects) until every dependency is loaded AND
  // the edit prefill has been applied, so the Selects mount exactly once with
  // valid values whose options already exist.
  const ready = !!filData && !!settings && (!editMode || !!editData) && prefillDone
  if (!ready) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner className="size-6 text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          {editMode ? "Edit order" : "New order"}
        </h1>
        <Button asChild variant="ghost" size="sm">
          <Link to={editMode ? `/orders/${editId}` : "/orders"}>← Cancel</Link>
        </Button>
      </div>

      {editMode && editData && editData.order.status !== "pending" && (
        <Alert variant="warning">
          <AlertDescription>
            This order is <em>{editData.order.status}</em>. Editing re-snapshots
            filament prices from current averages.
          </AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <form onSubmit={submit} className="space-y-4">
        <Card>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Part / project name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="customer">Customer</Label>
              <Input id="customer" value={customer} onChange={(e) => setCustomer(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profit">Profit %</Label>
              <Input id="profit" type="number" step="0.01" min="0" value={profitPct} onChange={(e) => setProfitPct(e.target.value)} required />
            </div>
            {retail && (
              <div className="space-y-2">
                <Label htmlFor="qty">Quantity</Label>
                <Input id="qty" type="number" step="1" min="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
              </div>
            )}
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="notes">Notes</Label>
              <Input id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>

            {/* model links */}
            <div className="space-y-2 sm:col-span-2">
              <Label>
                Model links{" "}
                <span className="font-normal text-muted-foreground">
                  (MakerWorld, Printables…)
                </span>
              </Label>
              {urls.map((u, i) => (
                <div key={i} className="flex gap-2">
                  <Input
                    type="url"
                    placeholder="https://..."
                    value={u}
                    onChange={(e) =>
                      setUrls((us) => us.map((x, j) => (j === i ? e.target.value : x)))
                    }
                  />
                  <Button
                    type="button"
                    size="icon"
                    variant="outline"
                    aria-label="Remove link"
                    onClick={() =>
                      setUrls((us) => (us.length > 1 ? us.filter((_, j) => j !== i) : [""]))
                    }
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              ))}
              <Button type="button" size="sm" variant="outline" onClick={() => setUrls((us) => [...us, ""])}>
                <Plus className="size-4" /> Add link
              </Button>
            </div>

            {/* toggles */}
            <div className="space-y-3 border-t border-border pt-4 sm:col-span-2">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <Checkbox
                  checked={isInternal}
                  onCheckedChange={(v) => {
                    setIsInternal(v === true)
                    if (v === true) setHasVat(false)
                  }}
                />
                <span>
                  <strong>Personal use</strong>{" "}
                  <span className="text-muted-foreground">
                    — not counted toward revenue or profit
                  </span>
                </span>
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <Checkbox checked={skipStock} onCheckedChange={(v) => setSkipStock(v === true)} />
                <span>
                  <strong>Quote mode</strong>{" "}
                  <span className="text-muted-foreground">
                    — skip stock validation, no inventory deducted
                  </span>
                </span>
              </label>
              {showVat && (
                <div className="border-t border-border pt-3">
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <Checkbox checked={hasVat} onCheckedChange={(v) => setHasVat(v === true)} />
                    <span>
                      <strong>Apply VAT</strong>{" "}
                      <span className="text-muted-foreground">
                        — added on top of the sale price
                      </span>
                    </span>
                  </label>
                  {hasVat && (
                    <div className="mt-2 max-w-[200px] space-y-1">
                      <Label htmlFor="vat" className="text-xs text-muted-foreground">
                        VAT rate %
                      </Label>
                      <Input id="vat" type="number" step="0.01" min="0" max="100" value={vatRate} onChange={(e) => setVatRate(e.target.value)} />
                    </div>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* plates */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Plates</h2>
          <Button type="button" size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={parsing}>
            {parsing ? <Spinner /> : <FileUp className="size-4" />} Import .3mf
          </Button>
          <input ref={fileRef} type="file" accept=".3mf" className="hidden" onChange={on3mfPicked} />
        </div>

        {parseWarning && (
          <Alert variant="warning">
            <AlertDescription>{parseWarning}</AlertDescription>
          </Alert>
        )}

        {filaments.length === 0 && (
          <Alert variant="warning">
            <AlertDescription>
              No filaments yet.{" "}
              <Link to="/filaments/new" className="underline">
                Create one first
              </Link>
              .
            </AlertDescription>
          </Alert>
        )}

        {plates.map((plate, pi) => (
          <Card key={pi}>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">Plate {pi + 1}</span>
                  <Input
                    placeholder="Plate name (optional)"
                    className="h-8 w-56"
                    value={plate.name}
                    onChange={(e) => updatePlate(pi, { name: e.target.value })}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => duplicatePlate(pi)}
                  >
                    <Copy className="size-4" /> Duplicate
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="text-destructive hover:bg-destructive/10"
                    disabled={plates.length <= 1}
                    onClick={() => setPlates((ps) => ps.filter((_, j) => j !== pi))}
                  >
                    <X className="size-4" /> Remove plate
                  </Button>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Label className="text-sm">Print time</Label>
                <Input type="number" min="0" max="999" placeholder="0" className="h-9 w-20" value={plate.hours} onChange={(e) => updatePlate(pi, { hours: e.target.value })} required />
                <span className="text-sm text-muted-foreground">h</span>
                <Input type="number" min="0" max="59" placeholder="0" className="h-9 w-20" value={plate.minutes} onChange={(e) => updatePlate(pi, { minutes: e.target.value })} required />
                <span className="text-sm text-muted-foreground">m</span>
              </div>

              <div className="space-y-3 border-t border-border pt-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">Filaments</span>
                  <Button type="button" size="sm" variant="outline" onClick={() => updatePlate(pi, { filaments: [...plate.filaments, emptyRow()] })}>
                    <Plus className="size-4" /> Filament
                  </Button>
                </div>
                {plate.filaments.map((row, ri) => (
                  <FilamentRowEditor
                    key={ri}
                    row={row}
                    filaments={filaments}
                    currency={currency}
                    canRemove={plate.filaments.length > 1}
                    onChange={(r) => updateRow(pi, ri, r)}
                    onRemove={() =>
                      updatePlate(pi, {
                        filaments: plate.filaments.filter((_, j) => j !== ri),
                      })
                    }
                  />
                ))}
              </div>
            </CardContent>
          </Card>
        ))}

        <Button type="button" size="sm" variant="outline" onClick={() => setPlates((ps) => [...ps, emptyPlate()])}>
          <Plus className="size-4" /> Add plate
        </Button>

        <div className="flex justify-between border-t border-border pt-4">
          <Button asChild variant="ghost">
            <Link to={editMode ? `/orders/${editId}` : "/orders"}>Cancel</Link>
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? <Spinner /> : null}
            {editMode ? "Save changes" : "Create order"}
          </Button>
        </div>
      </form>
    </div>
  )
}
