# order-printed-persistence-and-physical-stock

Three linked changes. Stock model stays **deduct-at-create** (reservation); we *add* a derived
physical/on-hand number. No deduction-timing change, **no migration/backfill** (nothing stored changes).

## Feature A — Physical (on-hand) stock, dual display
Current `stock_g` = reserved (deducted at create for every non-skipped, non-quote plate, printed or not).
Add a derived **physical** number = what's actually on the shelf = `stock_g + reserved-but-not-yet-printed`.
Marking a plate/order printed makes that plate's grams leave "reserved-unprinted", so physical drops.

- [ ] `_reserved_unprinted_map(user_id) -> {filament_id: Decimal grams}`: aggregate
      `sum(PlateFilament.weight_g * PrintOrder.quantity)` joined PlateFilament·PrintPlate·PrintOrder,
      filtered `PrintOrder.user_id`, `skip_stock_deduction == False`, `PrintPlate.is_skipped == False`,
      `PrintPlate.printed_at IS NULL`, grouped by filament_id.
- [ ] `serialize_filament(f, reserved_unprinted=Decimal(0))` adds `"physical_stock_g": float(stock_g + reserved_unprinted)`.
- [ ] Wire the map into `filaments_list`, `dashboard`; `filament_detail` and the single-filament responses
      (`filament_create`, `filament_purchase`, `filament_adjust`, purchase edit/delete) pass that one
      filament's reserved (helper `_reserved_unprinted(f)` or map lookup). 0 is an acceptable default only
      where no order context matters, but detail/list/dashboard MUST show the real number.
- [ ] `types.ts` `Filament` gains `physical_stock_g: number`.
- [ ] Frontend shows both: **on-hand** (physical) as the primary number, `stock_g` as secondary
      "after pending orders" — Filaments list + FilamentPurchase header. Only show the secondary when it
      differs from physical (no orders → identical → one number).

## Feature B — Preserve plate printed/skip state across order edit (bug; journal TODO §17)
`order_update` deletes+recreates all plates, wiping `printed_at`/`is_skipped`.
- [ ] Before deleting, capture `{position: (printed_at, is_skipped)}` from existing plates.
- [ ] On rebuild at `pos`, restore both flags from the captured map (new positions → fresh/None).
- [ ] Recompute `filament_usage` to **exclude plates that stay skipped** (skipped plates aren't deducted),
      so the restore/re-deduct stock math stays correct. Printed plates stay deducted (non-skipped).
- [ ] Call `_sync_order_printed(order)` after rebuild so `order.printed_at` reflects restored plates.
- [ ] `ponytail:` comment — position-keyed match; reordering/deleting plates mid-edit can misattribute
      flags (payload carries no plate ids). Upgrade path: send plate ids.

## Feature C — "partially_printed" status
- [ ] `PrintOrder.status`: after delivered/printed checks, return `"partially_printed"` when any non-skipped
      plate is printed but not all (i.e. some `printed_at` set, `order.printed_at` is None).
- [ ] `stats` counts: fold `partially_printed` into the `pending` bucket (in-progress = not done) so
      pending+printed+delivered still sums to total. `ponytail:` note.
- [ ] Frontend `Orders.tsx`: `StatusFilter` + filter options + `StatusBadge` add partially_printed
      ("Partially printed", `variant="warning"`). `OrderDetail.tsx` status badge adds the same branch.

## Definition of done (objective gate)
- `npx tsc --noEmit` → exit 0
- `docker compose restart app` boots clean
- Live verify: (A) filament shows physical > reserved when an unprinted order reserves it; marking the
  plate printed drops physical to match reserved. (B) mark a plate printed, edit+save the order, plate stays
  printed. (C) order with one of two plates printed shows "partially printed" badge.
- CodeRabbit on the diff → 0 findings (or only deferred-with-reason)

## Out of scope
- No deduction-timing change, no stored `physical` column, no backfill (chosen: dual display).
- No plate-id payload threading (position match is enough for the reported flow).
