import * as React from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { useSettings, useUpdateSettings } from "@/hooks/useOrders"

function Section({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <Card className="gap-0 overflow-hidden py-0">
      <div className="border-b border-border px-5 py-3 font-semibold">{title}</div>
      <CardContent className="space-y-4 py-5">{children}</CardContent>
    </Card>
  )
}

export default function Settings() {
  const { data, isLoading, isError } = useSettings()
  const update = useUpdateSettings()

  const [elec, setElec] = React.useState("")
  const [watts, setWatts] = React.useState("")
  const [profit, setProfit] = React.useState("")
  const [currency, setCurrency] = React.useState("€")
  const [retail, setRetail] = React.useState(false)
  const [vat, setVat] = React.useState("")
  const [saved, setSaved] = React.useState(false)

  const seeded = React.useRef(false)
  React.useEffect(() => {
    if (data && !seeded.current) {
      setElec(String(data.electricity_price_per_kwh))
      setWatts(String(data.printer_power_watts))
      setProfit(String(data.default_profit_pct))
      setCurrency(data.currency_symbol)
      setRetail(data.retail_mode_enabled)
      setVat(String(data.default_vat_rate_pct))
      seeded.current = true
    }
  }, [data])

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner className="size-6 text-muted-foreground" />
      </div>
    )
  }
  if (isError || !data) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Couldn’t load settings</AlertTitle>
        <AlertDescription>Please refresh and try again.</AlertDescription>
      </Alert>
    )
  }

  function save(e: React.FormEvent) {
    e.preventDefault()
    setSaved(false)
    update.mutate(
      {
        electricity_price_per_kwh: Number(elec) || 0,
        printer_power_watts: Number(watts) || 0,
        default_profit_pct: Number(profit) || 0,
        currency_symbol: currency.trim() || "€",
        retail_mode_enabled: retail,
        // PT tool — 23 is the app's standard default (matches the backend + UI helptext).
        default_vat_rate_pct: Number(vat) || 23,
      },
      { onSuccess: () => setSaved(true) }
    )
  }

  return (
    <form onSubmit={save} className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Global settings</h1>

      {saved && (
        <Alert variant="success">
          <AlertDescription>Settings saved.</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Electricity & printer">
          <div className="space-y-2">
            <Label htmlFor="elec">Electricity price ({currency}/kWh)</Label>
            <Input
              id="elec"
              type="number"
              step="0.0001"
              min="0"
              value={elec}
              onChange={(e) => setElec(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="watts">Printer power (W)</Label>
            <Input
              id="watts"
              type="number"
              step="0.01"
              min="0"
              value={watts}
              onChange={(e) => setWatts(e.target.value)}
              required
            />
            <p className="text-xs text-muted-foreground">
              Electricity cost = W × print hours ÷ 1000 × price/kWh.
            </p>
          </div>
        </Section>

        <Section title="Business defaults">
          <div className="space-y-2">
            <Label htmlFor="profit">Default profit %</Label>
            <Input
              id="profit"
              type="number"
              step="0.01"
              min="0"
              className="max-w-[180px]"
              value={profit}
              onChange={(e) => setProfit(e.target.value)}
              required
            />
            <p className="text-xs text-muted-foreground">
              Pre-filled when creating a new order.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="currency">Currency symbol</Label>
            <Input
              id="currency"
              maxLength={5}
              className="max-w-[100px]"
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              required
            />
            <p className="text-xs text-muted-foreground">
              Shown throughout the app (e.g. €, $, £).
            </p>
          </div>
        </Section>
      </div>

      <Section title="Retail mode">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <Checkbox
            checked={retail}
            onCheckedChange={(v) => setRetail(v === true)}
          />
          <span>
            <strong>Enable retail mode</strong>{" "}
            <span className="text-muted-foreground">
              — show VAT and quantity options on orders, quotes and stats
            </span>
          </span>
        </label>
        <div className="space-y-2">
          <Label htmlFor="vat">Default VAT rate %</Label>
          <Input
            id="vat"
            type="number"
            step="0.01"
            min="0"
            max="100"
            className="max-w-[180px]"
            value={vat}
            onChange={(e) => setVat(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Pre-filled on new retail orders. Standard PT rate is 23.
          </p>
        </div>
      </Section>

      <div>
        <Button type="submit" disabled={update.isPending}>
          {update.isPending ? <Spinner /> : null}
          Save settings
        </Button>
      </div>
    </form>
  )
}
