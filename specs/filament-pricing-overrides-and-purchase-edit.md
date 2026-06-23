---
slug: filament-pricing-overrides-and-purchase-edit
---

# Spec: per-line price override + editable purchase log

Two independent features sharing the filament-pricing domain. Build both, gate both.

## Feature 1 — price override per plate-filament line

**Done when:**
- `PlateFilament.price_per_kg_override` (Numeric(12,4), nullable) exists, additive-migrated via
  `_run_additive_migrations` in `app/__init__.py` (same `_has_column` idempotent pattern already used there).
- `_parse_plates_payload` accepts optional `price_per_kg_override` per filament item; tuple becomes
  `(filament_id, weight_g, override_or_None)`. Override must be `> 0` if present, else ignored (treated as None) — no hard 400, just don't apply a non-positive override.
- `order_create` / `order_update`: `PlateFilament.price_per_kg_snapshot = override if override else snapshot_price(f)`; always store `price_per_kg_override` (None if not given). Applies to every order (internal, retail, VAT — no special-casing).
- `serialize_plate_item` includes `price_per_kg_override` (float or None).
- Quote/QuoteCombined serializers: unchanged (they don't read plate items directly).
- `OrderForm.tsx`: each filament row gets an optional override €/kg input, collapsed by default, off unless set. Submitted only when filled. Prefill on edit from `plate.items[].price_per_kg_override`.
- Gate: `docker compose restart app` boots clean (migration applied without error), creating/editing an order with and without an override produces the expected `price_per_kg_snapshot` via `GET /api/orders/<id>`.

## Feature 2 — edit/delete `FilamentPurchase` rows

**Done when:**
- `Filament` gains `_recompute_avg_price()` (from-scratch weighted avg over remaining `self.purchases`), `edit_purchase(purchase, quantity_g, price_per_kg)`, `delete_purchase(purchase)`.
- Stock is delta-adjusted (`stock_g += new_qty - old_qty` on edit, `stock_g -= qty` on delete) — never resummed from the purchase log. Avg price IS resummed from the log.
- Guard: if the resulting `stock_g` would go negative, raise `ValueError` (caught in the route, returned as 409) — no mutation happens.
- Routes: `PUT /api/filaments/<fid>/purchases/<pid>` `{quantity_g, price_per_kg}`, `DELETE /api/filaments/<fid>/purchases/<pid>`. Both scoped to `current_user` (404 if purchase/filament not owned), return `{filament, purchases}` like `filament_detail`. 409 with `{"error": "..."}` on the negative-stock guard.
- `FilamentPurchase.tsx`: inline edit (qty/price inputs, Save/Cancel) + delete (reuse existing AlertDialog pattern) per row. 409 surfaced inline, not predicted client-side.
- New hooks `useEditPurchase(fid)`, `useDeletePurchase(fid)` in the filament hooks file, invalidating the same query key as purchase/adjust.
- Gate: editing a purchase recomputes avg correctly; deleting the only purchase zeroes stock+avg; attempting to shrink/delete a purchase below already-consumed stock returns 409 and changes nothing.

## Out of scope
FIFO/lot tracking, customer-facing override visibility, retroactive recompute of past orders.
