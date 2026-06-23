import * as React from "react"
import {
  ArrowLeft,
  Box,
  ExternalLink,
  FileText,
  Pencil,
  Plus,
  Trash2,
  Upload,
} from "lucide-react"
import { Link, useNavigate, useParams } from "react-router-dom"

import { FilamentSwatch } from "@/components/FilamentSwatch"
import { STLViewer } from "@/components/STLViewer"
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
import { Spinner } from "@/components/ui/spinner"
import {
  useDeleteOrderFile,
  useMarkDelivered,
  useMarkPrinted,
  useOrderDetail,
  useTogglePlatePrinted,
  useTogglePlateSkipped,
  useUploadOrderFile,
} from "@/hooks/useOrderDetail"
import { useDeleteOrder } from "@/hooks/useOrders"
import { duration, formatDateTime, grams, money } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Plate } from "@/types"

function SummaryRow({
  label,
  value,
  className,
  strong,
}: {
  label: React.ReactNode
  value: React.ReactNode
  className?: string
  strong?: boolean
}) {
  return (
    <li
      className={cn(
        "flex items-center justify-between gap-2 px-4 py-2.5 text-sm",
        className
      )}
    >
      <span className={cn(!strong && "text-muted-foreground")}>{label}</span>
      <strong className="tabular-nums">{value}</strong>
    </li>
  )
}

export default function OrderDetail() {
  const { id } = useParams()
  const oid = Number(id)
  const { data, isLoading, isError } = useOrderDetail(oid)
  const navigate = useNavigate()

  const togglePrinted = useTogglePlatePrinted(oid)
  const toggleSkipped = useTogglePlateSkipped(oid)
  const markPrinted = useMarkPrinted(oid)
  const markDelivered = useMarkDelivered(oid)
  const uploadFile = useUploadOrderFile(oid)
  const deleteFile = useDeleteOrderFile(oid)
  const delOrder = useDeleteOrder()

  const [viewer, setViewer] = React.useState<{ url: string; title: string } | null>(
    null
  )
  const [uploadOpen, setUploadOpen] = React.useState(false)
  const [uploadWarning, setUploadWarning] = React.useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = React.useState(false)

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
        <AlertTitle>Couldn’t load order</AlertTitle>
        <AlertDescription>
          It may have been deleted.{" "}
          <Link to="/orders" className="underline">
            Back to orders
          </Link>
          .
        </AlertDescription>
      </Alert>
    )
  }

  const { currency, order: o } = data
  const plateThumbs = o.files.filter((f) => f.is_plate_thumb)
  const regularFiles = o.files.filter((f) => !f.is_plate_thumb)
  const threemf = regularFiles.find((f) => f.file_type === "3mf")

  function openFileViewer(fileId: number, fileType: string, title: string) {
    const url = fileType === "3mf" ? `/files/${fileId}/stl` : `/files/${fileId}`
    setViewer({ url, title })
  }

  function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadWarning(null)
    uploadFile.mutate(file, {
      onSuccess: (res) => {
        const w = (res as { warning?: string | null })?.warning
        if (w) setUploadWarning(w)
      },
    })
    e.target.value = ""
  }

  return (
    <div className="space-y-4">
      {/* header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            {o.quantity > 1 && (
              <span className="text-muted-foreground">{o.quantity} ×</span>
            )}
            {o.name}
            {o.is_internal && <Badge variant="warning">Personal use</Badge>}
            {o.skip_stock_deduction && <Badge variant="info">Quote</Badge>}
            {o.has_vat && <Badge variant="success">VAT {o.vat_rate_pct}%</Badge>}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {formatDateTime(o.created_at)}
            {o.customer ? ` · Customer: ${o.customer}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link to={`/quote/${o.id}`}>
              <FileText className="size-4" /> Quote
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link to={`/orders/${o.id}/edit`}>
              <Pencil className="size-4" /> Edit order
            </Link>
          </Button>
          <Button asChild variant="ghost">
            <Link to="/orders">
              <ArrowLeft className="size-4" /> Back
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[7fr_5fr]">
        {/* LEFT */}
        <div className="space-y-4">
          {o.plates.map((plate) => (
            <PlateCard
              key={plate.id}
              plate={plate}
              currency={currency}
              onTogglePrinted={() => togglePrinted.mutate(plate.id)}
              onToggleSkipped={() => toggleSkipped.mutate(plate.id)}
              busy={togglePrinted.isPending || toggleSkipped.isPending}
            />
          ))}

          {/* links */}
          {o.links.map((link) => (
            <a
              key={link.id}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block"
            >
              <Card className="overflow-hidden py-0 transition-colors hover:border-primary/40">
                {link.image && (
                  <img
                    src={link.image}
                    alt=""
                    className="max-h-48 w-full object-cover"
                  />
                )}
                <div className="px-4 py-2.5">
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    {link.title || link.url}
                    <ExternalLink className="size-3.5 text-muted-foreground" />
                  </div>
                  {link.title && (
                    <div className="truncate text-xs text-muted-foreground">
                      {link.url}
                    </div>
                  )}
                </div>
              </Card>
            </a>
          ))}

          {/* files */}
          <Card className="gap-0 overflow-hidden py-0">
            <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
              <span className="font-medium">
                Files
                {regularFiles.length > 0 && (
                  <Badge variant="secondary" className="ml-2">
                    {regularFiles.length}
                  </Badge>
                )}
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setUploadOpen((v) => !v)}
              >
                <Plus className="size-4" /> Upload
              </Button>
            </div>

            {uploadOpen && (
              <div className="border-b border-border px-4 py-3">
                <label className="flex cursor-pointer items-center gap-2">
                  <span className="inline-flex h-9 items-center gap-2 rounded-md border border-input px-3 text-sm">
                    {uploadFile.isPending ? <Spinner /> : <Upload className="size-4" />}
                    Choose file
                  </span>
                  <input
                    type="file"
                    accept=".stl,.3mf,.obj,.png,.jpg,.jpeg,.gif,.webp"
                    className="hidden"
                    onChange={onUpload}
                  />
                  <span className="text-xs text-muted-foreground">
                    STL, 3MF, OBJ, PNG, JPG · 3MF plate thumbnails extracted
                    automatically
                  </span>
                </label>
                {uploadWarning && (
                  <Alert variant="warning" className="mt-2">
                    <AlertDescription>{uploadWarning}</AlertDescription>
                  </Alert>
                )}
              </div>
            )}

            {/* plate thumbnails */}
            {plateThumbs.length > 0 && (
              <div className="border-b border-border px-4 py-3">
                <div className="mb-2 text-xs text-muted-foreground">
                  Plate thumbnails
                </div>
                <div className="flex flex-wrap gap-2">
                  {plateThumbs.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      className="group relative cursor-pointer text-center"
                      title={`View Plate ${t.plate_index} in 3D`}
                      onClick={() =>
                        threemf &&
                        setViewer({
                          url: `/files/${threemf.id}/plate/${t.plate_index}/stl`,
                          title: `Plate ${t.plate_index}`,
                        })
                      }
                    >
                      <img
                        src={`/files/${t.id}`}
                        alt=""
                        className="h-[72px] w-auto rounded border border-border object-cover"
                      />
                      {threemf && (
                        <span className="absolute bottom-1 right-1 rounded bg-primary px-1 text-[0.6rem] font-medium text-primary-foreground">
                          3D
                        </span>
                      )}
                      <div className="mt-0.5 text-[0.7rem] text-muted-foreground">
                        Plate {t.plate_index}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* regular files */}
            {regularFiles.length > 0 ? (
              <ul className="divide-y divide-border">
                {regularFiles.map((f) => (
                  <li
                    key={f.id}
                    className="flex items-center justify-between gap-2 px-4 py-2"
                  >
                    <a
                      href={`/files/${f.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="truncate text-sm hover:underline"
                      title={f.original_name}
                    >
                      {f.original_name}
                    </a>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <Badge variant="secondary" className="uppercase">
                        {f.file_type}
                      </Badge>
                      {f.is_viewable_3d && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            openFileViewer(f.id, f.file_type, f.original_name)
                          }
                        >
                          <Box className="size-4" /> 3D
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive hover:bg-destructive/10"
                        aria-label={`Delete ${f.original_name}`}
                        onClick={() => deleteFile.mutate(f.id)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              plateThumbs.length === 0 && (
                <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                  No files attached.
                </div>
              )
            )}
          </Card>

          {viewer && (
            <STLViewer
              url={viewer.url}
              title={viewer.title}
              onClose={() => setViewer(null)}
            />
          )}

          {o.notes && (
            <Card className="gap-0 overflow-hidden py-0">
              <div className="border-b border-border px-4 py-2.5 font-medium">
                Notes
              </div>
              <div className="whitespace-pre-wrap px-4 py-3 text-sm">{o.notes}</div>
            </Card>
          )}
        </div>

        {/* RIGHT */}
        <div className="space-y-4">
          {/* status */}
          <Card className="gap-0 overflow-hidden py-0">
            <div className="border-b border-border px-4 py-2.5 font-medium">
              Status
            </div>
            <div className="space-y-3 px-4 py-3">
              <div>
                {o.status === "delivered" ? (
                  <Badge variant="success">Delivered</Badge>
                ) : o.status === "printed" ? (
                  <Badge variant="info">Printed</Badge>
                ) : o.status === "partially_printed" ? (
                  <Badge variant="warning">Partially printed</Badge>
                ) : (
                  <Badge variant="secondary">Pending</Badge>
                )}
              </div>
              <div className="flex flex-col gap-2">
                {o.printed_at ? (
                  <>
                    <p className="text-xs text-muted-foreground">
                      Printed on {formatDateTime(o.printed_at)}
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => markPrinted.mutate(false)}
                    >
                      Unmark printed
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => markPrinted.mutate(true)}
                  >
                    Mark as printed
                  </Button>
                )}
                {o.delivered_at ? (
                  <>
                    <p className="text-xs text-muted-foreground">
                      Delivered on {formatDateTime(o.delivered_at)}
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => markDelivered.mutate(false)}
                    >
                      Unmark delivered
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => markDelivered.mutate(true)}
                  >
                    Mark as delivered
                  </Button>
                )}
              </div>
            </div>
          </Card>

          {/* summary */}
          <Card className="gap-0 overflow-hidden py-0">
            <div className="border-b border-border px-4 py-2.5 font-medium">
              Summary
            </div>
            <ul className="divide-y divide-border">
              <SummaryRow label="Plates" value={o.plates.length} strong />
              {o.quantity > 1 && (
                <SummaryRow label="Quantity" value={`× ${o.quantity}`} strong />
              )}
              <SummaryRow
                label="Total print time"
                value={duration(o.total_print_time_hours)}
                strong
              />
              <SummaryRow
                label={`Filament used${o.quantity > 1 ? ` (× ${o.quantity})` : ""}`}
                value={grams(
                  o.plates.reduce(
                    (sum, pl) => sum + pl.items.reduce((s, it) => s + it.weight_g, 0),
                    0
                  ) * o.quantity
                )}
                strong
              />
              <SummaryRow
                label="Printer power"
                value={`${o.printer_power_watts} W`}
                strong
              />
              <SummaryRow
                label="Electricity price"
                value={`${o.electricity_price_per_kwh.toFixed(4)} ${currency}/kWh`}
                strong
              />
              <SummaryRow
                label={`Filament cost${o.quantity > 1 ? ` (× ${o.quantity})` : ""}`}
                value={money(o.filament_cost, currency)}
                strong
              />
              <SummaryRow
                label={`Electricity cost${o.quantity > 1 ? ` (× ${o.quantity})` : ""}`}
                value={money(o.electricity_cost, currency)}
                strong
              />
              <SummaryRow
                label="Total cost"
                value={money(o.total_cost, currency)}
                className="bg-muted/50"
                strong
              />
              {o.is_internal ? (
                <li className="bg-warning/10 px-4 py-2.5 text-sm">
                  <Badge variant="warning">Personal use</Badge>{" "}
                  <span className="text-muted-foreground">
                    Not counted toward revenue or profit
                  </span>
                </li>
              ) : (
                <>
                  <SummaryRow
                    label="Profit %"
                    value={`${o.profit_pct} %`}
                    strong
                  />
                  <SummaryRow
                    label="Profit"
                    value={`+${money(o.profit_value, currency)}`}
                    className="text-success"
                    strong
                  />
                  {o.has_vat ? (
                    <>
                      <SummaryRow
                        label="Subtotal (excl. VAT)"
                        value={money(o.sell_price, currency)}
                        strong
                      />
                      <SummaryRow
                        label={`VAT (${o.vat_rate_pct} %)`}
                        value={money(o.vat_amount, currency)}
                        strong
                      />
                      <SummaryRow
                        label="Sale price (incl. VAT)"
                        value={money(o.sell_price_with_vat, currency)}
                        className="bg-primary text-primary-foreground"
                        strong
                      />
                      {o.quantity > 1 && (
                        <SummaryRow
                          label="Per unit (incl. VAT)"
                          value={money(o.sell_price_with_vat / o.quantity, currency)}
                          className="text-muted-foreground"
                        />
                      )}
                    </>
                  ) : (
                    <>
                      <SummaryRow
                        label="Sale price"
                        value={money(o.sell_price, currency)}
                        className="bg-primary text-primary-foreground"
                        strong
                      />
                      {o.quantity > 1 && (
                        <SummaryRow
                          label="Per unit"
                          value={money(o.unit_sell_price, currency)}
                          className="text-muted-foreground"
                        />
                      )}
                    </>
                  )}
                </>
              )}
            </ul>
          </Card>

          <Button
            variant="outline"
            className="w-full text-destructive hover:bg-destructive/10"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="size-4" /> Delete order
          </Button>
        </div>
      </div>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete order?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes <strong>{o.name}</strong>
              {!o.skip_stock_deduction
                ? " and restores its filament stock."
                : "."}{" "}
              This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className={styledCancel()}>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={delOrder.isPending}
              onClick={() =>
                delOrder.mutate(o.id, {
                  onSuccess: () => navigate("/orders"),
                })
              }
            >
              {delOrder.isPending ? <Spinner /> : null}
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function PlateCard({
  plate,
  currency,
  onTogglePrinted,
  onToggleSkipped,
  busy,
}: {
  plate: Plate
  currency: string
  onTogglePrinted: () => void
  onToggleSkipped: () => void
  busy: boolean
}) {
  return (
    <Card className={cn("gap-0 overflow-hidden py-0", plate.is_skipped && "opacity-60")}>
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-3">
          <span className="font-semibold">
            Plate {plate.position}
            {plate.name ? ` — ${plate.name}` : ""}
          </span>
          {plate.is_skipped ? (
            <Badge variant="warning">Skipped</Badge>
          ) : (
            <label className="flex cursor-pointer items-center gap-1.5 text-sm">
              <Checkbox
                checked={!!plate.printed_at}
                disabled={busy}
                onCheckedChange={onTogglePrinted}
              />
              Printed
            </label>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={plate.is_skipped ? "filament" : "outline"}
            disabled={busy}
            onClick={onToggleSkipped}
          >
            {plate.is_skipped ? "Unskip" : "Skip"}
          </Button>
          <span className="text-sm text-muted-foreground">
            {duration(plate.print_time_hours)} · {money(plate.total_cost, currency)}
          </span>
        </div>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase text-muted-foreground">
            <th className="px-4 py-2 text-left font-medium">Filament</th>
            <th className="px-4 py-2 text-right font-medium">Weight (g)</th>
            <th className="px-4 py-2 text-right font-medium">{currency}/kg</th>
            <th className="px-4 py-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {plate.items.map((it) => (
            <tr key={it.id} className="border-b border-border/60">
              <td className="px-4 py-2">
                {it.filament ? (
                  <span className="flex items-center gap-2">
                    {it.filament.name}
                    <FilamentSwatch
                      hex={it.filament.color_hex}
                      color={it.filament.color}
                    />
                    <span className="text-xs text-muted-foreground">
                      {it.filament.color}
                    </span>
                  </span>
                ) : (
                  <span className="text-muted-foreground">(removed)</span>
                )}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {it.weight_g.toFixed(2)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {it.price_per_kg_snapshot.toFixed(2)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {money(it.cost, currency)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="text-xs text-muted-foreground">
            <td colSpan={3} className="px-4 py-1.5 text-right">
              Filaments
            </td>
            <td className="px-4 py-1.5 text-right tabular-nums">
              {money(plate.filament_cost, currency)}
            </td>
          </tr>
          <tr className="text-xs text-muted-foreground">
            <td colSpan={3} className="px-4 py-1.5 text-right">
              Electricity
            </td>
            <td className="px-4 py-1.5 text-right tabular-nums">
              {money(plate.electricity_cost, currency)}
            </td>
          </tr>
        </tfoot>
      </table>
    </Card>
  )
}
