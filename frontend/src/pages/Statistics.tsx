import type { ReactNode } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { useStats } from "@/hooks/useStats"
import { duration, money } from "@/lib/format"
import { cn } from "@/lib/utils"

const STOCK_FALLBACK = "#6c757d"

function marginPct(profit: number, revenue: number): string {
  return revenue > 0 ? `${((profit / revenue) * 100).toFixed(1)} %` : "—"
}

const tooltipProps = {
  contentStyle: {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    color: "var(--popover-foreground)",
    fontSize: 13,
  },
  labelStyle: { color: "var(--popover-foreground)", fontWeight: 600 },
  itemStyle: { color: "var(--popover-foreground)" },
}
const axisTick = { fill: "var(--muted-foreground)", fontSize: 12 }

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  accent?: "success" | "destructive" | "primary" | "info"
}) {
  const valueColor =
    accent === "success"
      ? "text-success"
      : accent === "destructive"
        ? "text-destructive"
        : accent === "primary"
          ? "text-primary"
          : accent === "info"
            ? "text-[var(--chart-4)]"
            : ""
  const borderColor =
    accent === "success"
      ? "border-success/40"
      : accent === "destructive"
        ? "border-destructive/40"
        : accent === "primary"
          ? "border-primary/40"
          : accent === "info"
            ? "border-[var(--chart-4)]/40"
            : ""
  return (
    <Card className={cn("gap-1 p-4", borderColor)}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("text-2xl font-bold tabular-nums", valueColor)}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </Card>
  )
}

function Panel({
  title,
  hint,
  children,
}: {
  title: ReactNode
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <Card className="h-full gap-0 overflow-hidden py-0">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 font-medium">
        {title}
        {hint && (
          <span className="text-xs font-normal text-muted-foreground">{hint}</span>
        )}
      </div>
      {children}
    </Card>
  )
}

function ListRow({
  label,
  value,
  muted,
}: {
  label: ReactNode
  value: ReactNode
  muted?: boolean
}) {
  return (
    <li
      className={cn(
        "flex items-center justify-between gap-2 px-4 py-2.5 text-sm",
        muted && "bg-muted/50"
      )}
    >
      <span className="text-muted-foreground">{label}</span>
      <strong className="tabular-nums">{value}</strong>
    </li>
  )
}

export default function Statistics() {
  const { data, isLoading, isError } = useStats()

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
        <AlertTitle>Couldn’t load statistics</AlertTitle>
        <AlertDescription>Please try again.</AlertDescription>
      </Alert>
    )
  }

  const { currency, retail_mode_enabled: retail, totals: t, counts, monthly } = data
  const m = (v: number) => money(v, currency)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Business statistics</h1>
        <span className="text-sm text-muted-foreground">
          Only delivered commercial orders count toward revenue and profit
        </span>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Total revenue"
          value={m(t.revenue)}
          sub={`${counts.delivered} orders delivered`}
          accent="success"
        />
        <StatCard
          label="Total cost (commercial)"
          value={m(t.total_cost_commercial)}
          sub={`Filaments ${m(t.filament_cost_commercial)} · Electricity ${m(
            t.electricity_cost_commercial
          )}`}
          accent="destructive"
        />
        <StatCard
          label="Net profit"
          value={`${t.profit >= 0 ? "+" : ""}${m(t.profit)}`}
          sub={t.revenue > 0 ? `Margin ${marginPct(t.profit, t.revenue)}` : undefined}
          accent={t.profit >= 0 ? "primary" : "destructive"}
        />
        <StatCard
          label="Orders"
          value={counts.total}
          sub={`${counts.commercial} commercial · ${counts.internal} personal`}
        />
      </div>

      {/* Retail / VAT row */}
      {retail && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="VAT collected"
            value={m(t.vat_collected)}
            sub={`${t.delivered_retail_count} retail order${
              t.delivered_retail_count !== 1 ? "s" : ""
            } delivered`}
            accent="success"
          />
          <StatCard
            label="Revenue — retail (excl. VAT)"
            value={m(t.revenue_retail)}
            sub="Subject to VAT"
          />
          <StatCard
            label="Revenue — particular"
            value={m(t.revenue_particular)}
            sub="No VAT applied"
          />
          <StatCard
            label="Total invoiced (incl. VAT)"
            value={m(t.revenue + t.vat_collected)}
            sub="What customers actually paid"
            accent="info"
          />
        </div>
      )}

      {/* print time · personal · inventory */}
      <div className="grid gap-3 md:grid-cols-3">
        <Panel title="Print time">
          <ul className="divide-y divide-border">
            <ListRow label="Total (all)" value={duration(t.print_hours_all)} />
            <ListRow label="Commercial" value={duration(t.print_hours_commercial)} />
            <ListRow label="Personal use" value={duration(t.print_hours_internal)} />
          </ul>
        </Panel>

        <Panel title="Personal use" hint="— real cost, not invoiced">
          <ul className="divide-y divide-border">
            <ListRow label="Filaments" value={m(t.filament_cost_internal)} />
            <ListRow label="Electricity" value={m(t.electricity_cost_internal)} />
            <ListRow
              label="Total"
              value={m(t.filament_cost_internal + t.electricity_cost_internal)}
              muted
            />
            <ListRow label="Personal prints" value={counts.internal} />
          </ul>
        </Panel>

        <Panel title="Filament inventory">
          <ul className="divide-y divide-border">
            <ListRow label="Stock value" value={m(t.stock_value)} />
            <ListRow
              label="Stock weight"
              value={`${t.stock_kg.toFixed(3)} kg`}
            />
            <ListRow
              label="Total purchased (historical)"
              value={m(t.filament_purchased_spend)}
            />
            <ListRow label="Distinct references" value={t.filament_count} />
          </ul>
        </Panel>
      </div>

      {/* monthly chart */}
      {monthly.length > 0 && (
        <Panel title="Revenue and profit by month">
          <div className="p-4">
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart
                data={monthly}
                margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                maxBarSize={64}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--border)"
                  vertical={false}
                />
                <XAxis dataKey="label" tick={axisTick} />
                <YAxis tick={axisTick} tickFormatter={(v) => `${v}`} width={48} />
                <Tooltip
                  {...tooltipProps}
                  formatter={(v: number) => m(v)}
                />
                <Legend wrapperStyle={{ fontSize: 13 }} />
                <Bar
                  dataKey="revenue"
                  name="Revenue"
                  fill="var(--success)"
                  radius={[4, 4, 0, 0]}
                />
                <Bar
                  dataKey="cost"
                  name="Cost"
                  fill="var(--destructive)"
                  radius={[4, 4, 0, 0]}
                />
                <Line
                  type="monotone"
                  dataKey="profit"
                  name="Profit"
                  stroke="var(--primary)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}

      {/* stock chart */}
      {data.stock.length > 0 && (
        <Panel title={`Stock by filament (${currency})`}>
          <div className="p-4">
            <ResponsiveContainer
              width="100%"
              height={Math.max(data.stock.length * 36, 200)}
            >
              <BarChart
                data={data.stock}
                layout="vertical"
                margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid
                  horizontal={false}
                  stroke="var(--border)"
                  strokeDasharray="3 3"
                />
                <XAxis
                  type="number"
                  tick={axisTick}
                  tickFormatter={(v) => `${v}`}
                />
                <YAxis
                  type="category"
                  dataKey={(f) => `${f.name} ${f.material} ${f.color}`}
                  width={150}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                />
                <Tooltip {...tooltipProps} formatter={(v: number) => m(v)} />
                <Bar dataKey="stock_value" radius={[0, 4, 4, 0]}>
                  {data.stock.map((f) => (
                    <Cell key={f.id} fill={f.color_hex || STOCK_FALLBACK} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}

      {/* monthly table */}
      {monthly.length > 0 && (
        <Panel
          title="Revenue and profit by month"
          hint="Delivered commercial orders"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase text-muted-foreground">
                  <th className="px-4 py-2 text-left font-medium">Month</th>
                  <th className="px-4 py-2 text-right font-medium">Orders</th>
                  <th className="px-4 py-2 text-right font-medium">Cost</th>
                  <th className="px-4 py-2 text-right font-medium">Revenue</th>
                  {retail && (
                    <th className="px-4 py-2 text-right font-medium">VAT</th>
                  )}
                  <th className="px-4 py-2 text-right font-medium">Profit</th>
                  <th className="px-4 py-2 text-right font-medium">Margin</th>
                </tr>
              </thead>
              <tbody>
                {[...monthly].reverse().map((row) => (
                  <tr key={row.key} className="border-b border-border/60">
                    <td className="px-4 py-2">{row.label}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{row.orders}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-destructive">
                      {m(row.cost)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-success">
                      {m(row.revenue)}
                    </td>
                    {retail && (
                      <td className="px-4 py-2 text-right tabular-nums text-[var(--chart-4)]">
                        {m(row.vat)}
                      </td>
                    )}
                    <td
                      className={cn(
                        "px-4 py-2 text-right tabular-nums",
                        row.profit >= 0 ? "text-primary" : "text-destructive"
                      )}
                    >
                      {row.profit >= 0 ? "+" : ""}
                      {m(row.profit)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                      {marginPct(row.profit, row.revenue)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border font-semibold">
                  <td className="px-4 py-2">Total</td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {counts.delivered}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-destructive">
                    {m(t.total_cost_commercial)}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-success">
                    {m(t.revenue)}
                  </td>
                  {retail && (
                    <td className="px-4 py-2 text-right tabular-nums text-[var(--chart-4)]">
                      {m(t.vat_collected)}
                    </td>
                  )}
                  <td
                    className={cn(
                      "px-4 py-2 text-right tabular-nums",
                      t.profit >= 0 ? "text-primary" : "text-destructive"
                    )}
                  >
                    {t.profit >= 0 ? "+" : ""}
                    {m(t.profit)}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                    {marginPct(t.profit, t.revenue)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </Panel>
      )}

      {/* top filaments + inventory */}
      {data.top_filaments.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          <Panel title="Top filaments — cost in commercial orders">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs uppercase text-muted-foreground">
                    <th className="px-4 py-2 text-left font-medium">Filament</th>
                    <th className="px-4 py-2 text-right font-medium">
                      Weight used (g)
                    </th>
                    <th className="px-4 py-2 text-right font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_filaments.map((f, i) => (
                    <tr key={i} className="border-b border-border/60">
                      <td className="px-4 py-2">
                        {f.name}
                        {(f.material || f.color) && (
                          <span className="ml-1 text-xs text-muted-foreground">
                            {f.material}
                            {f.color ? ` · ${f.color}` : ""}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {f.weight_g.toFixed(0)} g
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">{m(f.cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Current inventory by filament">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs uppercase text-muted-foreground">
                    <th className="px-4 py-2 text-left font-medium">Filament</th>
                    <th className="px-4 py-2 text-right font-medium">Stock (kg)</th>
                    <th className="px-4 py-2 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {data.stock.map((f) => (
                    <tr key={f.id} className="border-b border-border/60">
                      <td className="px-4 py-2">
                        {f.name}
                        <span className="ml-1 text-xs text-muted-foreground">
                          {f.material} · {f.color}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {f.stock_kg.toFixed(3)}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {m(f.stock_value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-border font-semibold">
                    <td className="px-4 py-2">Total</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {t.stock_kg.toFixed(3)} kg
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {m(t.stock_value)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {/* order status */}
      <div className="grid gap-3 md:grid-cols-3">
        <Panel title="Order status">
          <ul className="divide-y divide-border">
            <ListRow
              label={<Badge variant="secondary">Pending</Badge>}
              value={counts.pending}
            />
            <ListRow
              label={<Badge variant="info">Printed</Badge>}
              value={counts.printed}
            />
            <ListRow
              label={<Badge variant="success">Delivered</Badge>}
              value={counts.delivered}
            />
            <ListRow label="Total" value={counts.total} muted />
          </ul>
        </Panel>
      </div>
    </div>
  )
}
