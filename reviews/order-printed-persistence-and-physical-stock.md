# Gate — order-printed-persistence-and-physical-stock

## Result: PASS

## Feature A — physical (on-hand) dual display
| Requirement | Status | Evidence |
|---|---|---|
| `_reserved_unprinted_map` aggregate (unprinted, non-skipped, non-quote) | MET | api.py |
| `serialize_filament` adds `physical_stock_g` | MET | wired into list/dashboard/detail + single-filament responses |
| `types.ts` Filament `physical_stock_g` | MET | — |
| UI shows on-hand primary + "after orders" secondary when differing | MET | Filaments list `1,708` / `1,408 after orders`; FilamentPurchase header |
| physical drops when plate marked printed | MET | before print physical=2008 stock=1408; after print Plate A → physical=1708 stock=1408 |

## Feature B — preserve plate printed/skip across edit (journal TODO §17)
| Requirement | Status | Evidence |
|---|---|---|
| capture {position:(printed_at,is_skipped)} pre-delete, restore on rebuild | MET | order_update |
| filament_usage excludes plates that stay skipped (stock math correct) | MET | re-deduction unchanged: stock_g stayed 1408 across edit |
| `_sync_order_printed` after rebuild | MET | order stays partially_printed post-edit |
| PUT order keeps printed plate | MET | edit (Plate B hrs 2→3) → Plate A still printed, status partially_printed |

## Feature C — partially_printed status
| Requirement | Status | Evidence |
|---|---|---|
| status property returns partially_printed | MET | models.py; order detail + toggle both report it |
| stats folds partial into pending (totals reconcile) | MET | api.py stats counts |
| Orders.tsx badge + filter; OrderDetail badge | MET | screenshot: amber "Partially printed" badge + filter chip |

## Gate commands
- `npx tsc --noEmit` → EXIT 0
- `docker compose restart app` → booted clean
- CodeRabbit → 1 minor (low-stock highlight used reserved while displaying physical) → fixed → re-run **0 findings**
- Live verification → API + UI + screenshot (above)

## Notes
- Chosen model: **dual display** (deduct-at-create kept). No migration/backfill — physical is derived live.
- Plate-state match is **position-keyed** (payload has no plate ids); reordering/deleting plates mid-edit can
  misattribute flags — marked with `ponytail:` comment, upgrade path noted.
