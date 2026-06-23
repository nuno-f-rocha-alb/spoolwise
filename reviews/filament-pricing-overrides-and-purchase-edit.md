# Gate — filament-pricing-overrides-and-purchase-edit

## Result: PASS

## Feature 1 — price override on order plate filaments
| Spec requirement | Status | Evidence |
|---|---|---|
| Nullable `PlateFilament.price_per_kg_override` (Numeric(12,4)) | MET | `app/models.py`; column live (additive migration) |
| `_parse_plates_payload` threads optional override | MET | `app/api.py` — 3-tuple `(fid, w, override)` |
| `order_create`/`order_update`: `snapshot = override or snapshot_price(f)`, persist override | MET | POST /api/orders → line w/ override: snap=20, cost=4 (0.2kg×20); line w/o: snap=9.8208, override=null |
| Override in order-detail serializer; NOT in Quote serializers | MET | serializer returns `price_per_kg_override`; Quote untouched |
| OrderForm optional override input + prefill on edit | MET | /orders/6/edit auto-expanded override input shows "20"; null line stays collapsed |
| Invalid override rejected (>0, like price_per_kg) | MET | override -5 and 0 → 400 "override price must be a positive number" |
| Additive ALTER TABLE migration | MET | `_run_additive_migrations` in `app/__init__.py` |

## Feature 2 — edit/delete FilamentPurchase rows
| Spec requirement | Status | Evidence |
|---|---|---|
| `_recompute_avg_price`, `edit_purchase`, `delete_purchase` | MET | `app/models.py` |
| stock delta-adjusted; avg recomputed from log | MET | edit 1000g price→9.00 gave avg 9.82, stock unchanged |
| Negative-stock guard → 409 | MET | DELETE w/ stock 100 < log 1500 → 409, data unchanged |
| All-deleted → stock/avg = 0 | MET | cleanup deletes drove stock 0, avg 0, 0 purchases |
| model-layer qty/price > 0 validation | MET | CodeRabbit fix; raises ValueError |
| PUT/DELETE routes scoped to current_user | MET | `app/api.py` `_user_purchase_or_404` |
| FilamentPurchase.tsx edit/delete UI + 409 inline | MET | inline edit + AlertDialog confirm; rowErr Alert |
| mutation hooks invalidate query keys | MET | `useEditPurchase`/`useDeletePurchase` |

## Gate commands
- `npx tsc --noEmit` → EXIT 0
- CodeRabbit (`coderabbit review --agent`) → first pass 4 findings (2 major model/api validation, 1 major a11y, 1 minor double-submit), all fixed → re-run **0 findings**
- Live verification → both features exercised against running Flask+Vite (see evidence above)
