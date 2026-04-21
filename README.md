# 3D Print Manager

Flask + Bootstrap 5 web app to manage 3D print orders, filament inventory, costs and business statistics. Backed by MariaDB, deployable via Docker.

## Features

- **Filament inventory** — stock in grams, weighted-average price updated on every purchase.
- **Multi-plate orders** — each plate has its own print time and filaments (multi-colour supported).
- **Automatic cost calculation** — filament cost, electricity cost, sale price and profit per order.
- **Price snapshots** — filament price and settings are captured at order creation; historical costs never change when you update prices later.
- **Stock management** — stock is deducted when an order is created and restored when it is deleted. Manual adjustment available without affecting the weighted average.
- **Personal use flag** — mark orders as personal use; they deduct stock and track costs but are excluded from revenue and profit statistics.
- **Statistics page** — revenue, cost, profit, margins, monthly breakdown, and filament stock charts.
- **Configurable currency** — change the currency symbol in Settings (default `€`).
- **Dark / light mode** — toggle in the navbar, persisted in `localStorage`.
- **MakerWorld / Printables / Thingiverse preview** — paste a model URL and the app fetches the title and cover image automatically.

## Running with Docker (recommended)

```bash
cp .env.example .env   # fill in your passwords and secret key
docker compose up -d
```

App at http://localhost:5000  
MariaDB exposed on port `3307` on the host (configurable in `.env`).

## Running locally (app only, DB from Docker)

```bash
docker compose up -d db
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

## Typical workflow

1. **Settings** → set electricity price, printer power, and default profit %.
2. **Filaments → + New filament** → register a filament with optional initial stock and price.
3. **Filaments → Buy / Adjust** → each new purchase updates the weighted average:  
   `new_avg = (current_stock_kg × current_avg + purchase_kg × purchase_price) / (current_stock_kg + purchase_kg)`
4. **+ New order** → choose filaments, weight per plate, print time, and profit %. Stock is deducted automatically.

## Cost model

```
filament_cost  = Σ (weight_g / 1000 × avg_price_per_kg)
electricity_cost = (printer_watts / 1000) × print_hours × price_per_kwh
total_cost     = filament_cost + electricity_cost
sale_price     = total_cost × (1 + profit_pct / 100)
```

## CI/CD

Pushing to `main` triggers a GitHub Actions workflow that builds the Docker image and pushes it to Docker Hub (`nunobifes/printing-app:latest`).

Required repository secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.
