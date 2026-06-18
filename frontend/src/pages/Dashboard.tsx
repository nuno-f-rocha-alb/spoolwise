import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, Boxes, PackageOpen, Wallet } from "lucide-react"
import { Link } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Spinner } from "@/components/ui/spinner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { formatDateTime, grams, kilos, money } from "@/lib/format"

interface DashFilament {
  id: number
  name: string
  material: string
  color: string
  color_hex: string | null
  stock_g: number
  stock_kg: number
  avg_price_per_kg: number
  stock_value: number
  is_zero_stock: boolean
  is_low_stock: boolean
}

interface DashOrder {
  id: number
  name: string
  customer: string | null
  created_at: string | null
  is_internal: boolean
  status: string
  total_cost: number
  sell_price: number
}

interface DashboardData {
  currency: string
  totals: {
    stock_kg: number
    stock_value: number
    filament_count: number
    low_stock_count: number
  }
  filaments: DashFilament[]
  recent_orders: DashOrder[]
}

function Swatch({ color }: { color: string | null }) {
  return (
    <span
      className="inline-block size-3.5 shrink-0 rounded-full border border-black/15"
      style={{ backgroundColor: color || "#888888" }}
      aria-hidden
    />
  )
}

function StatCard({
  label,
  value,
  icon,
  accent,
  badge,
}: {
  label: string
  value: string
  icon: React.ReactNode
  accent: string
  badge?: React.ReactNode
}) {
  return (
    <Card className="overflow-hidden py-0">
      <CardContent className="flex items-center gap-4 p-5">
        <div
          className={cn(
            "flex size-11 shrink-0 items-center justify-center rounded-lg",
            accent
          )}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-2xl font-semibold tabular-nums">
            {value}
            {badge}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function Dashboard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardData>("/api/dashboard"),
  })

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
        <AlertTriangle />
        <AlertTitle>Couldn’t load the dashboard</AlertTitle>
        <AlertDescription>Please refresh and try again.</AlertDescription>
      </Alert>
    )
  }

  const { currency, totals, filaments, recent_orders } = data

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Total stock"
          value={kilos(totals.stock_kg)}
          accent="bg-primary/10 text-primary"
          icon={<Boxes className="size-5" />}
        />
        <StatCard
          label="Inventory value"
          value={money(totals.stock_value, currency)}
          accent="bg-success/10 text-success"
          icon={<Wallet className="size-5" />}
        />
        <StatCard
          label="Distinct filaments"
          value={String(totals.filament_count)}
          accent="bg-filament/10 text-filament"
          icon={<PackageOpen className="size-5" />}
          badge={
            totals.low_stock_count > 0 ? (
              <Badge variant="warning" className="text-[0.7rem]">
                <AlertTriangle className="size-3" />
                {totals.low_stock_count} low
              </Badge>
            ) : undefined
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        {/* Inventory */}
        <Card className="gap-0 overflow-hidden py-0">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h2 className="font-semibold">Inventory</h2>
            <Link
              to="/filaments"
              className="text-sm text-primary hover:underline"
            >
              view all
            </Link>
          </div>
          {filaments.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              No filaments yet.{" "}
              <Link to="/filaments/new" className="text-primary hover:underline">
                Add one
              </Link>
              .
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Brand</TableHead>
                  <TableHead>Material</TableHead>
                  <TableHead>Color</TableHead>
                  <TableHead className="text-right">Stock</TableHead>
                  <TableHead className="text-right">Avg price</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filaments.map((f) => (
                  <TableRow
                    key={f.id}
                    className={cn(
                      f.is_zero_stock && "bg-destructive/5",
                      f.is_low_stock && "bg-warning/5"
                    )}
                  >
                    <TableCell className="font-medium">{f.name}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{f.material}</Badge>
                    </TableCell>
                    <TableCell>
                      <span className="flex items-center gap-2">
                        <Swatch color={f.color_hex || f.color} />
                        <span className="truncate">{f.color}</span>
                      </span>
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums",
                        f.is_zero_stock && "font-bold text-destructive",
                        f.is_low_stock && "font-semibold text-warning"
                      )}
                    >
                      {grams(f.stock_g)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {money(f.avg_price_per_kg, currency)}/kg
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* Recent orders */}
        <Card className="gap-0 overflow-hidden py-0">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h2 className="font-semibold">Recent orders</h2>
            <Link to="/orders" className="text-sm text-primary hover:underline">
              view all
            </Link>
          </div>
          {recent_orders.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              No orders yet.
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {recent_orders.map((o) => (
                <li
                  key={o.id}
                  className="flex items-center justify-between gap-3 px-5 py-3"
                >
                  <div className="min-w-0">
                    <Link
                      to={`/orders/${o.id}`}
                      className="font-medium hover:underline"
                    >
                      {o.name}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      {formatDateTime(o.created_at)}
                    </div>
                  </div>
                  {o.is_internal ? (
                    <Badge
                      variant="warning"
                      className="shrink-0 rounded-full"
                      title="Personal use — real cost"
                    >
                      {money(o.total_cost, currency)}
                    </Badge>
                  ) : (
                    <Badge className="shrink-0 rounded-full">
                      {money(o.sell_price, currency)}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
