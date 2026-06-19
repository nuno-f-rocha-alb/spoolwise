import * as React from "react"
import { FileText, Pencil, Plus, Trash2 } from "lucide-react"
import { Link } from "react-router-dom"

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  styledCancel,
} from "@/components/ui/alert-dialog"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Spinner } from "@/components/ui/spinner"
import { useDeleteOrder, useOrders } from "@/hooks/useOrders"
import { ApiError } from "@/lib/api"
import { duration, formatDateTime, money } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { OrderListItem } from "@/types"

type StatusFilter = "all" | "pending" | "printed" | "delivered"
type TypeFilter = "all" | "commercial" | "internal"

function Chips<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; activeVariant?: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex flex-wrap gap-1.5">
      {options.map((o) => (
        <Button
          key={o.value}
          size="sm"
          variant={value === o.value ? "secondary" : "ghost"}
          className={cn("h-8", value === o.value && "border border-border")}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </Button>
      ))}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === "delivered") return <Badge variant="success">Delivered</Badge>
  if (status === "printed") return <Badge variant="info">Printed</Badge>
  return <Badge variant="secondary">Pending</Badge>
}

export default function Orders() {
  const { data, isLoading, isError } = useOrders()
  const del = useDeleteOrder()

  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all")
  const [typeFilter, setTypeFilter] = React.useState<TypeFilter>("all")
  const [selected, setSelected] = React.useState<Set<number>>(new Set())
  const [toDelete, setToDelete] = React.useState<OrderListItem | null>(null)
  const [deleteError, setDeleteError] = React.useState<string | null>(null)

  const rows = React.useMemo(() => {
    if (!data) return []
    return data.orders.filter((o) => {
      if (statusFilter !== "all" && o.status !== statusFilter) return false
      if (typeFilter === "commercial" && o.is_internal) return false
      if (typeFilter === "internal" && !o.is_internal) return false
      return true
    })
  }, [data, statusFilter, typeFilter])

  // selectable = visible, non-internal
  const selectableIds = React.useMemo(
    () => rows.filter((o) => !o.is_internal).map((o) => o.id),
    [rows]
  )
  const selectedVisible = selectableIds.filter((id) => selected.has(id))
  const allSelected =
    selectableIds.length > 0 && selectedVisible.length === selectableIds.length

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
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
      <Alert variant="destructive">
        <AlertTitle>Couldn’t load orders</AlertTitle>
        <AlertDescription>Please refresh and try again.</AlertDescription>
      </Alert>
    )
  }

  const { currency } = data
  const quoteHref =
    selectedVisible.length === 1
      ? `/quote/${selectedVisible[0]}`
      : `/quote/combined?ids=${selectedVisible.join(",")}`

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Orders</h1>
        <Button asChild>
          <Link to="/orders/new">
            <Plus className="size-4" /> New order
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap gap-3">
        <Chips<StatusFilter>
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { value: "all", label: "All" },
            { value: "pending", label: "Pending" },
            { value: "printed", label: "Printed" },
            { value: "delivered", label: "Delivered" },
          ]}
        />
        <Chips<TypeFilter>
          value={typeFilter}
          onChange={setTypeFilter}
          options={[
            { value: "all", label: "All types" },
            { value: "commercial", label: "Commercial" },
            { value: "internal", label: "Personal use" },
          ]}
        />
      </div>

      {selectedVisible.length > 0 && (
        <Alert className="flex items-center justify-between gap-3 border-primary/30 bg-primary/5">
          <span className="text-sm">
            <strong>{selectedVisible.length}</strong> order
            {selectedVisible.length !== 1 ? "s" : ""} selected
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setSelected(new Set())}
            >
              Clear
            </Button>
            <Button asChild size="sm">
              <Link to={quoteHref}>
                {selectedVisible.length === 1
                  ? "Open quote →"
                  : "Generate combined quote →"}
              </Link>
            </Button>
          </div>
        </Alert>
      )}

      <Card className="overflow-hidden py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  checked={allSelected}
                  aria-label="Select all"
                  onCheckedChange={(v) =>
                    setSelected(v === true ? new Set(selectableIds) : new Set())
                  }
                />
              </TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Time</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead className="text-right">Sale price</TableHead>
              <TableHead className="text-right">Profit</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} className="py-10 text-center text-muted-foreground">
                  No orders.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((o) => (
                <TableRow key={o.id} className={cn(o.is_internal && "bg-warning/5")}>
                  <TableCell>
                    <Checkbox
                      checked={selected.has(o.id)}
                      disabled={o.is_internal}
                      aria-label={`Select ${o.name}`}
                      title={
                        o.is_internal
                          ? "Personal-use orders aren’t included in quotes"
                          : undefined
                      }
                      onCheckedChange={() => toggle(o.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <Link to={`/orders/${o.id}`} className="font-medium hover:underline">
                      {o.quantity > 1 && (
                        <span className="text-muted-foreground">{o.quantity} × </span>
                      )}
                      {o.name}
                    </Link>
                    <span className="ml-1 inline-flex gap-1 align-middle">
                      {o.is_internal && <Badge variant="warning">Personal</Badge>}
                      {o.skip_stock_deduction && <Badge variant="info">Quote</Badge>}
                      {o.has_vat && <Badge variant="success">VAT</Badge>}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {o.customer || "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDateTime(o.created_at)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {duration(o.total_print_time_hours)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {money(o.total_cost, currency)}
                  </TableCell>
                  {o.is_internal ? (
                    <>
                      <TableCell className="text-right text-muted-foreground">—</TableCell>
                      <TableCell className="text-right text-muted-foreground">—</TableCell>
                    </>
                  ) : (
                    <>
                      <TableCell className="text-right tabular-nums">
                        <div className="font-medium">
                          {money(
                            o.has_vat ? o.sell_price_with_vat : o.sell_price,
                            currency
                          )}
                        </div>
                        {o.has_vat && (
                          <div className="text-xs text-muted-foreground">incl. VAT</div>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-success">
                        +{money(o.profit_value, currency)}
                      </TableCell>
                    </>
                  )}
                  <TableCell>
                    <StatusBadge status={o.status} />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button asChild size="sm" variant="outline" title="View quote">
                        <Link to={`/quote/${o.id}`}>
                          <FileText className="size-4" />
                        </Link>
                      </Button>
                      <Button asChild size="sm" variant="outline" title="Edit">
                        <Link to={`/orders/${o.id}/edit`}>
                          <Pencil className="size-4" />
                        </Link>
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive hover:bg-destructive/10"
                        title="Delete"
                        onClick={() => setToDelete(o)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      <AlertDialog
        open={!!toDelete}
        onOpenChange={(open) => {
          if (!open) {
            setToDelete(null)
            setDeleteError(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete order?</AlertDialogTitle>
            <AlertDialogDescription>
              {toDelete && (
                <>
                  This deletes <strong>{toDelete.name}</strong>
                  {!toDelete.skip_stock_deduction
                    ? " and restores its filament stock."
                    : "."}{" "}
                  This cannot be undone.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && (
            <Alert variant="destructive">
              <AlertDescription>{deleteError}</AlertDescription>
            </Alert>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel className={styledCancel()}>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={del.isPending}
              onClick={() => {
                if (!toDelete) return
                setDeleteError(null)
                del.mutate(toDelete.id, {
                  onSuccess: () => setToDelete(null),
                  onError: (err) =>
                    setDeleteError(
                      err instanceof ApiError
                        ? err.message
                        : "Could not delete order."
                    ),
                })
              }}
            >
              {del.isPending ? <Spinner /> : null}
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
