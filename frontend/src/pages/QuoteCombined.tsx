import type { ReactNode } from "react"
import { Link, useSearchParams } from "react-router-dom"

import { PriceBox, QuoteFrame } from "@/components/QuoteFrame"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { useCombinedQuote } from "@/hooks/useQuote"
import { formatDate, money } from "@/lib/format"

function ErrorFrame({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-3 py-8">
      <Alert variant="destructive">
        <AlertTitle>Combined quote</AlertTitle>
        <AlertDescription>{children}</AlertDescription>
      </Alert>
    </div>
  )
}

export default function QuoteCombined() {
  const [params] = useSearchParams()
  const ids = (params.get("ids") || "")
    .split(",")
    .map((x) => Number(x.trim()))
    .filter((n) => Number.isFinite(n) && n > 0)

  const { data, isLoading, isError } = useCombinedQuote(ids)

  if (ids.length === 0) {
    return (
      <ErrorFrame>
        Select at least one order to combine.{" "}
        <Link to="/orders" className="underline">
          Back to orders
        </Link>
        .
      </ErrorFrame>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner className="size-6 text-muted-foreground" />
      </div>
    )
  }
  if (isError || !data) {
    return (
      <ErrorFrame>
        Couldn’t load these orders — they may have been deleted.{" "}
        <Link to="/orders" className="underline">
          Back to orders
        </Link>
        .
      </ErrorFrame>
    )
  }

  const { currency, orders, subtotal, vat_total, total, has_any_vat, vat_rates } =
    data
  const billable = orders.filter((o) => !o.is_internal)
  const personalCount = orders.length - billable.length
  const customers = [
    ...new Set(orders.map((o) => o.customer).filter((c): c is string => !!c)),
  ]
  const vatLabel =
    vat_rates.length === 1
      ? `(${vat_rates[0]} %)`
      : vat_rates.length > 1
        ? `(mixed: ${vat_rates.join(" / ")} %)`
        : ""
  const firstDate = formatDate(orders[0]?.created_at ?? null)

  return (
    <QuoteFrame
      eyebrow="Combined quote"
      meta={`${orders.length} item${orders.length !== 1 ? "s" : ""} · ${firstDate}`}
      backTo="/orders"
      backLabel="Orders"
      footerDate={firstDate}
      width="max-w-3xl"
    >
      {customers.length === 1 && (
        <p className="mb-6 text-muted-foreground">
          Prepared for <strong>{customers[0]}</strong>
        </p>
      )}

      {/* item table */}
      <Card className="mb-6 overflow-hidden py-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-3 text-left font-medium">Qty</th>
                <th className="px-4 py-3 text-left font-medium">Item</th>
                <th className="px-4 py-3 text-right font-medium">
                  Unit (excl. VAT)
                </th>
                <th className="px-4 py-3 text-right font-medium">
                  Total (excl. VAT)
                </th>
              </tr>
            </thead>
            <tbody>
              {billable.map((o) => (
                <tr key={o.id} className="border-b border-border/60 last:border-0">
                  <td className="px-4 py-3 align-middle">{o.quantity} ×</td>
                  <td className="px-4 py-3 align-middle">
                    <div className="font-semibold">{o.name}</div>
                    {o.has_vat && (
                      <div className="text-xs text-muted-foreground">
                        VAT {o.vat_rate_pct} %
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right align-middle tabular-nums">
                    {money(o.unit_sell_price, currency)}
                  </td>
                  <td className="px-4 py-3 text-right align-middle tabular-nums">
                    {money(o.sell_price, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* totals */}
      <PriceBox>
        {has_any_vat ? (
          <>
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm opacity-85">Subtotal (excl. VAT)</div>
              <div className="font-semibold tabular-nums">
                {money(subtotal, currency)}
              </div>
            </div>
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm opacity-85">VAT {vatLabel}</div>
              <div className="font-semibold tabular-nums">
                {money(vat_total, currency)}
              </div>
            </div>
            <div className="mt-3 border-t border-white/25 pt-3">
              <div className="text-[0.7rem] uppercase tracking-wide opacity-75">
                Total (incl. VAT)
              </div>
              <div className="text-4xl font-bold tabular-nums">
                {money(total, currency)}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="text-[0.7rem] uppercase tracking-wide opacity-75">
              Total price
            </div>
            <div className="text-4xl font-bold tabular-nums">
              {money(total, currency)}
            </div>
          </>
        )}
      </PriceBox>

      {personalCount > 0 && (
        <Alert>
          <AlertDescription>
            {personalCount} personal-use order{personalCount !== 1 ? "s" : ""}{" "}
            excluded from totals.
          </AlertDescription>
        </Alert>
      )}
    </QuoteFrame>
  )
}
