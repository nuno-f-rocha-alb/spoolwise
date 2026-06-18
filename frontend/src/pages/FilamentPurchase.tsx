import * as React from "react"
import { ArrowLeft, ShoppingCart, TriangleAlert } from "lucide-react"
import { Link, useParams } from "react-router-dom"

import { FilamentSwatch } from "@/components/FilamentSwatch"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  styledCancel,
} from "@/components/ui/alert-dialog"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Spinner } from "@/components/ui/spinner"
import {
  useAdjustFilament,
  useFilamentDetail,
  usePurchaseFilament,
} from "@/hooks/useFilaments"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import { formatDateTime, money } from "@/lib/format"

export default function FilamentPurchase() {
  const { id } = useParams()
  const fid = Number(id)
  const { data, isLoading, isError } = useFilamentDetail(fid)
  const purchase = usePurchaseFilament(fid)
  const adjust = useAdjustFilament(fid)

  const [qty, setQty] = React.useState("")
  const [price, setPrice] = React.useState("")
  const [purchaseMsg, setPurchaseMsg] = React.useState<string | null>(null)
  const [purchaseErr, setPurchaseErr] = React.useState<string | null>(null)

  const [adjStock, setAdjStock] = React.useState("")
  const [confirmAdjust, setConfirmAdjust] = React.useState(false)
  const [adjustMsg, setAdjustMsg] = React.useState<string | null>(null)

  const initialised = React.useRef(false)
  React.useEffect(() => {
    if (data && !initialised.current) {
      setAdjStock(String(Math.round(data.filament.stock_g)))
      initialised.current = true
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
        <AlertTitle>Couldn’t load filament</AlertTitle>
        <AlertDescription>
          It may have been deleted.{" "}
          <Link to="/filaments" className="underline">
            Back to filaments
          </Link>
          .
        </AlertDescription>
      </Alert>
    )
  }

  const { currency, filament: f, purchases } = data

  function submitPurchase(e: React.FormEvent) {
    e.preventDefault()
    setPurchaseErr(null)
    setPurchaseMsg(null)
    purchase.mutate(
      { quantity_g: Number(qty), price_per_kg: Number(price) },
      {
        onSuccess: (res) => {
          setPurchaseMsg(
            `Added ${qty} g. New weighted average: ${res.filament.avg_price_per_kg.toFixed(2)} ${currency}/kg.`
          )
          setQty("")
          setPrice("")
        },
        onError: (err) =>
          setPurchaseErr(
            err instanceof ApiError ? err.message : "Could not register purchase."
          ),
      }
    )
  }

  function runAdjust() {
    setAdjustMsg(null)
    adjust.mutate(
      { stock_g: Number(adjStock) },
      {
        onSuccess: (res) =>
          setAdjustMsg(`Stock set to ${Math.round(res.filament.stock_g)} g.`),
      }
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            {f.name}
            <span className="text-base font-normal text-muted-foreground">
              {f.material} ·
            </span>
            <FilamentSwatch hex={f.color_hex} color={f.color} />
            <span className="text-base font-normal text-muted-foreground">
              {f.color}
            </span>
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Current stock <strong className="text-foreground">{Math.round(f.stock_g)} g</strong> ·
            Avg price{" "}
            <strong className="text-foreground">
              {money(f.avg_price_per_kg, currency)}/kg
            </strong>
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to="/filaments">
            <ArrowLeft className="size-4" /> Back
          </Link>
        </Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[2fr_3fr]">
        {/* Register purchase */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShoppingCart className="size-5 text-primary" /> Register purchase
            </CardTitle>
          </CardHeader>
          <form onSubmit={submitPurchase}>
            <CardContent className="space-y-4">
              {purchaseMsg && (
                <Alert variant="success">
                  <AlertDescription>{purchaseMsg}</AlertDescription>
                </Alert>
              )}
              {purchaseErr && (
                <Alert variant="destructive">
                  <AlertDescription>{purchaseErr}</AlertDescription>
                </Alert>
              )}
              <div className="space-y-2">
                <Label htmlFor="qty">Quantity (g)</Label>
                <Input
                  id="qty"
                  type="number"
                  step="0.01"
                  min="0.01"
                  required
                  placeholder="e.g. 1000"
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="price">Price ({currency}/kg)</Label>
                <Input
                  id="price"
                  type="number"
                  step="0.0001"
                  min="0.0001"
                  required
                  placeholder="e.g. 13.00"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  The weighted average is recalculated automatically. Current avg:{" "}
                  <strong>{money(f.avg_price_per_kg, currency)}/kg</strong>.
                </p>
              </div>
            </CardContent>
            <CardFooter className="justify-end border-t border-border pt-4">
              <Button type="submit" disabled={purchase.isPending}>
                {purchase.isPending ? <Spinner /> : null}
                Register purchase
              </Button>
            </CardFooter>
          </form>
        </Card>

        {/* Purchase history */}
        <Card className="overflow-hidden py-0">
          <div className="border-b border-border px-5 py-3">
            <h2 className="font-semibold">Purchase history</h2>
          </div>
          {purchases.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              No purchases recorded yet.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-right">Qty (g)</TableHead>
                  <TableHead className="text-right">{currency}/kg</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {purchases.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(p.purchased_at)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {Math.round(p.quantity_g)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.price_per_kg.toFixed(2)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>
      </div>

      {/* Inventory correction */}
      <div className="grid gap-5 lg:grid-cols-[2fr_3fr]">
        <Card className="h-fit border-warning/40">
          <CardHeader className="flex-row items-center gap-2 border-b border-border pb-4">
            <TriangleAlert className="size-5 text-warning" />
            <CardTitle className="text-base">Adjust stock</CardTitle>
            <span className="ml-auto rounded-md bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning">
              Does NOT change avg price
            </span>
          </CardHeader>
          <CardContent className="space-y-3 pt-4">
            {adjustMsg && (
              <Alert variant="success">
                <AlertDescription>{adjustMsg}</AlertDescription>
              </Alert>
            )}
            <p className="text-sm text-muted-foreground">
              Use this <strong>only</strong> to correct a counting error. It sets
              stock directly and does <strong>not</strong> affect the weighted
              average price.
            </p>
            <div className="space-y-2">
              <Label htmlFor="adj">New stock value (g)</Label>
              <Input
                id="adj"
                type="number"
                step="0.01"
                min="0"
                value={adjStock}
                onChange={(e) => setAdjStock(e.target.value)}
              />
              <p className="text-xs text-warning">
                Enter the <strong>total</strong> amount in stock, not the difference.
              </p>
            </div>
          </CardContent>
          <CardFooter className="justify-end border-t border-border pt-4">
            <Button
              variant="filament"
              disabled={
                adjStock === "" ||
                Number.isNaN(Number(adjStock)) ||
                Number(adjStock) < 0
              }
              onClick={() => setConfirmAdjust(true)}
            >
              Set stock
            </Button>
          </CardFooter>
        </Card>

        <Alert className="h-fit">
          <AlertTitle>When to use Adjust vs Purchase?</AlertTitle>
          <AlertDescription>
            <ul className="mt-1 list-disc space-y-1 pl-4">
              <li>
                <strong>Register purchase</strong> — you bought new filament.
                Updates stock <em>and</em> average price.
              </li>
              <li>
                <strong>Adjust stock</strong> — you found a counting error.
                Updates stock only.
              </li>
            </ul>
          </AlertDescription>
        </Alert>
      </div>

      <AlertDialog open={confirmAdjust} onOpenChange={setConfirmAdjust}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Set stock to {adjStock} g?</AlertDialogTitle>
            <AlertDialogDescription>
              This sets the stock directly and does not affect the average price.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className={styledCancel()}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={cn(buttonVariants({ variant: "filament" }))}
              onClick={runAdjust}
            >
              Set stock
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
