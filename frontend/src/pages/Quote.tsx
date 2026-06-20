import type { ReactNode } from "react"
import { ExternalLink } from "lucide-react"
import { Link, useParams } from "react-router-dom"

import { PriceBox, QuoteFrame } from "@/components/QuoteFrame"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { useOrderDetail } from "@/hooks/useOrderDetail"
import { duration, formatDate, money } from "@/lib/format"

function StatPill({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-border bg-card px-4 py-2.5">
      <span className="text-[0.7rem] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="text-lg font-semibold">{value}</span>
    </div>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <div className="text-sm/relaxed opacity-85">{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  )
}

export default function Quote() {
  const { id } = useParams()
  const oid = Number(id)
  const { data, isLoading, isError } = useOrderDetail(oid)

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner className="size-6 text-muted-foreground" />
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="mx-auto max-w-2xl px-3 py-8">
        <Alert variant="destructive">
          <AlertTitle>Couldn’t load quote</AlertTitle>
          <AlertDescription>
            The order may have been deleted.{" "}
            <Link to="/orders" className="underline">
              Back to orders
            </Link>
            .
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const { currency, order: o } = data
  const cover = o.links.find((l) => l.image) ?? null
  const extraLinks = o.links.filter((l) => l.url)
  const statusLabel =
    o.status === "delivered"
      ? "Delivered"
      : o.status === "printed"
        ? "Ready"
        : "Pending"
  const showLineItem = !o.is_internal && (o.quantity > 1 || o.has_vat)

  return (
    <QuoteFrame
      eyebrow="3D Print Quote"
      meta={`# ${o.id} · ${formatDate(o.created_at)}`}
      backTo={`/orders/${o.id}`}
      backLabel="Internal view"
      footerDate={formatDate(o.created_at)}
    >
      {/* title + customer */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">{o.name}</h1>
        {o.customer && (
          <p className="mt-1 text-muted-foreground">
            Prepared for <strong>{o.customer}</strong>
          </p>
        )}
      </div>

      {/* cover image */}
      {cover?.image && (
        <div className="mb-6">
          {cover.url ? (
            <a href={cover.url} target="_blank" rel="noopener noreferrer">
              <img
                src={cover.image}
                alt={cover.title || o.name}
                className="max-h-80 w-full rounded-lg object-cover shadow-sm"
              />
            </a>
          ) : (
            <img
              src={cover.image}
              alt={cover.title || o.name}
              className="max-h-80 w-full rounded-lg object-cover shadow-sm"
            />
          )}
          {cover.title && (
            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <ExternalLink className="size-3" /> {cover.title}
            </div>
          )}
        </div>
      )}

      {/* stats */}
      <div className="mb-6 grid grid-cols-3 gap-2">
        <StatPill label="Print time" value={duration(o.total_print_time_hours)} />
        <StatPill label="Plates" value={o.plates.length} />
        <StatPill label="Status" value={statusLabel} />
      </div>

      {/* line item breakdown */}
      {showLineItem && (
        <Card className="mb-4 overflow-hidden py-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 pt-3 pb-1 text-left font-medium">Qty</th>
                <th className="px-4 pt-3 pb-1 text-left font-medium">Item</th>
                <th className="px-4 pt-3 pb-1 text-right font-medium">
                  Unit (excl. VAT)
                </th>
                <th className="px-4 pt-3 pb-1 text-right font-medium">
                  Total (excl. VAT)
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-4 py-3">{o.quantity} ×</td>
                <td className="px-4 py-3 font-semibold">{o.name}</td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {money(o.unit_sell_price, currency)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {money(o.sell_price, currency)}
                </td>
              </tr>
            </tbody>
          </table>
        </Card>
      )}

      {/* price box */}
      {!o.is_internal && (
        <PriceBox>
          {o.has_vat ? (
            <>
              <Row
                label="Subtotal (excl. VAT)"
                value={money(o.sell_price, currency)}
              />
              <Row
                label={`VAT (${o.vat_rate_pct} %)`}
                value={money(o.vat_amount, currency)}
              />
              <div className="mt-3 border-t border-white/25 pt-3">
                <div className="text-[0.7rem] uppercase tracking-wide opacity-75">
                  Total (incl. VAT)
                </div>
                <div className="text-4xl font-bold tabular-nums">
                  {money(o.sell_price_with_vat, currency)}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="text-[0.7rem] uppercase tracking-wide opacity-75">
                Total price
              </div>
              <div className="text-4xl font-bold tabular-nums">
                {money(o.sell_price, currency)}
              </div>
            </>
          )}
        </PriceBox>
      )}

      {/* notes */}
      {o.notes && (
        <Card className="mb-6 gap-0 overflow-hidden py-0">
          <div className="px-4 pt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Notes
          </div>
          <div className="whitespace-pre-wrap px-4 pb-3 pt-2 text-sm">
            {o.notes}
          </div>
        </Card>
      )}

      {/* extra model links */}
      {extraLinks.length > 1 && (
        <div className="mb-6">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Model references
          </div>
          <div className="space-y-2">
            {extraLinks.map((link) => (
              <a
                key={link.id}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 rounded-md border border-border bg-card p-2 transition-colors hover:border-primary/40"
              >
                {link.image && (
                  <img
                    src={link.image}
                    alt=""
                    className="size-10 shrink-0 rounded object-cover"
                  />
                )}
                <span className="truncate text-sm">{link.title || link.url}</span>
                <ExternalLink className="ml-auto size-3 shrink-0 text-muted-foreground" />
              </a>
            ))}
          </div>
        </div>
      )}
    </QuoteFrame>
  )
}
