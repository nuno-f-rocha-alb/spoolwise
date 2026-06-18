import * as React from "react"
import { ArrowDown, ArrowUp, ArrowUpDown, Plus, Trash2 } from "lucide-react"
import { Link } from "react-router-dom"

import { FilamentSwatch } from "@/components/FilamentSwatch"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Spinner } from "@/components/ui/spinner"
import { useDeleteFilament, useFilaments } from "@/hooks/useFilaments"
import { ApiError } from "@/lib/api"
import { money } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Filament } from "@/types"

type SortKey = "name" | "material" | "color" | "stock" | "price"
type Dir = "asc" | "desc"

function FilterChips({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: string[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-sm text-muted-foreground">{label}:</span>
      {["all", ...options].map((opt) => (
        <Button
          key={opt}
          size="sm"
          variant={value === opt ? "secondary" : "ghost"}
          className={cn("h-8", value === opt && "border border-border")}
          onClick={() => onChange(opt)}
        >
          {opt === "all" ? "All" : opt}
        </Button>
      ))}
    </div>
  )
}

function SortHeader({
  label,
  col,
  sort,
  dir,
  onSort,
  className,
}: {
  label: string
  col: SortKey
  sort: SortKey
  dir: Dir
  onSort: (c: SortKey) => void
  className?: string
}) {
  const active = sort === col
  const Icon = !active ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown
  return (
    <TableHead className={className}>
      <button
        onClick={() => onSort(col)}
        className="inline-flex cursor-pointer items-center gap-1 hover:text-foreground"
      >
        {label}
        <Icon className={cn("size-3.5", active ? "opacity-100" : "opacity-40")} />
      </button>
    </TableHead>
  )
}

export default function Filaments() {
  const { data, isLoading, isError } = useFilaments()
  const del = useDeleteFilament()

  const [brand, setBrand] = React.useState("all")
  const [material, setMaterial] = React.useState("all")
  const [sort, setSort] = React.useState<SortKey>("name")
  const [dir, setDir] = React.useState<Dir>("asc")
  const [toDelete, setToDelete] = React.useState<Filament | null>(null)
  const [deleteError, setDeleteError] = React.useState<string | null>(null)

  function onSort(col: SortKey) {
    if (col === sort) setDir((d) => (d === "asc" ? "desc" : "asc"))
    else {
      setSort(col)
      setDir("asc")
    }
  }

  const rows = React.useMemo(() => {
    if (!data) return []
    let list = data.filaments
    if (brand !== "all") list = list.filter((f) => f.name === brand)
    if (material !== "all") list = list.filter((f) => f.material === material)
    const dirMul = dir === "asc" ? 1 : -1
    const val = (f: Filament) =>
      sort === "name"
        ? f.name
        : sort === "material"
          ? f.material
          : sort === "color"
            ? f.color
            : sort === "stock"
              ? f.stock_g
              : f.avg_price_per_kg
    return [...list].sort((a, b) => {
      const va = val(a)
      const vb = val(b)
      if (typeof va === "number" && typeof vb === "number")
        return (va - vb) * dirMul
      return String(va).localeCompare(String(vb)) * dirMul
    })
  }, [data, brand, material, sort, dir])

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
        <AlertTitle>Couldn’t load filaments</AlertTitle>
        <AlertDescription>Please refresh and try again.</AlertDescription>
      </Alert>
    )
  }

  const { currency, brands, materials } = data

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Filaments</h1>
        <Button asChild>
          <Link to="/filaments/new">
            <Plus className="size-4" /> New filament
          </Link>
        </Button>
      </div>

      <div className="space-y-2">
        <FilterChips
          label="Brand"
          options={brands}
          value={brand}
          onChange={setBrand}
        />
        <FilterChips
          label="Material"
          options={materials}
          value={material}
          onChange={setMaterial}
        />
      </div>

      <Card className="overflow-hidden py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <SortHeader label="Brand" col="name" sort={sort} dir={dir} onSort={onSort} />
              <SortHeader label="Material" col="material" sort={sort} dir={dir} onSort={onSort} />
              <SortHeader label="Color" col="color" sort={sort} dir={dir} onSort={onSort} />
              <SortHeader label="Stock (kg)" col="stock" sort={sort} dir={dir} onSort={onSort} className="text-right" />
              <SortHeader label={`Avg price (${currency}/kg)`} col="price" sort={sort} dir={dir} onSort={onSort} className="text-right" />
              <TableHead className="text-right">Value</TableHead>
              <TableHead className="text-right" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No filaments{brand !== "all" || material !== "all" ? " match the filters" : " yet"}.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="font-medium">{f.name}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{f.material}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="flex items-center gap-2">
                      <FilamentSwatch hex={f.color_hex} color={f.color} />
                      {f.color}
                    </span>
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      f.stock_kg <= 0.1 && "font-bold text-destructive"
                    )}
                  >
                    {f.stock_kg.toLocaleString(undefined, {
                      minimumFractionDigits: 3,
                      maximumFractionDigits: 3,
                    })}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {f.avg_price_per_kg.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {money(f.stock_value, currency)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button asChild size="sm">
                        <Link to={`/filaments/${f.id}/purchase`}>Buy / Adjust</Link>
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive hover:bg-destructive/10"
                        onClick={() => setToDelete(f)}
                        aria-label={`Delete ${f.name} ${f.color}`}
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
        onOpenChange={(o) => {
          if (!o) {
            setToDelete(null)
            setDeleteError(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete filament?</AlertDialogTitle>
            <AlertDialogDescription>
              {toDelete && (
                <>
                  This permanently deletes{" "}
                  <strong>
                    {toDelete.name} {toDelete.material} {toDelete.color}
                  </strong>{" "}
                  and its purchase history. This cannot be undone.
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
            {/* plain Button (not AlertDialogAction) so the dialog stays open on error */}
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
                        : "Could not delete filament."
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
