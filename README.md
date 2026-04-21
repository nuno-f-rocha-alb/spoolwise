# 3D Print Manager

A self-hosted web app to manage 3D print orders, filament inventory, costs and business statistics.

**Stack:** Python 3.12 · Flask 3 · Bootstrap 5 (Bootswatch Flatly) · MariaDB 11 · Docker

---

## Screenshots

| Light | Dark |
|---|---|
| ![Dashboard](docs/screenshots/dashboard_lightmode.png) | ![Dashboard](docs/screenshots/dashboard_darkmode.png) |
| ![Orders](docs/screenshots/orders_lightmode.png) | ![Orders](docs/screenshots/orders_darkmode.png) |
| ![Order detail](docs/screenshots/order-details_lightmode.png) | ![Order detail](docs/screenshots/order-details_darkmode.png) |
| ![Statistics](docs/screenshots/statistics_lightmode.png) | ![Statistics](docs/screenshots/statistics_darkmode.png) |
| ![Filaments](docs/screenshots/filaments_lightmode.png) | ![Filaments](docs/screenshots/filaments_darkmode.png) |
| ![New order](docs/screenshots/new-order_lightmode.png) | ![New order](docs/screenshots/new-order_darkmode.png) |
| ![Settings](docs/screenshots/settings_lightmode.png) | ![Settings](docs/screenshots/settings_darkmode.png) |

---

## Features

| Area | Details |
|---|---|
| **Filament inventory** | Stock in grams, weighted-average price recalculated on every purchase |
| **Multi-plate orders** | Each plate has its own print time and filaments (multi-colour supported) |
| **Cost calculation** | Filament cost + electricity cost → total cost → sale price with configurable profit % |
| **Price snapshots** | Prices are captured at order creation — historical costs never drift |
| **Stock tracking** | Auto-deducted on order creation, restored on deletion; manual adjustment available |
| **Personal use flag** | Track your own prints without polluting revenue and profit stats |
| **Statistics** | Revenue, cost, profit, monthly breakdown, filament stock charts (Chart.js) |
| **Model preview** | Paste a MakerWorld / Printables / Thingiverse URL → title and cover image fetched automatically |
| **Currency** | Configurable symbol in Settings (default `€`) |
| **Dark / light mode** | Toggle in the navbar, persisted in `localStorage` |

---

## Getting started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2

### 1. Clone and configure

```bash
git clone https://github.com/nunobifes/printing-app.git
cd printing-app
cp .env.example .env
```

Edit `.env` with your own values:

```env
MARIADB_ROOT_PASSWORD=your_root_password
MARIADB_USER=printing
MARIADB_PASSWORD=your_db_password
DATABASE_URL=mysql+pymysql://printing:your_db_password@db:3306/printing_app
SECRET_KEY=a_long_random_secret
```

### 2. Start

```bash
docker compose up -d
```

The app waits for MariaDB to be healthy before starting, then creates all tables automatically.

| Service | URL / host |
|---|---|
| Web app | http://localhost:5000 |
| MariaDB | `localhost:3307` (external port) |

### 3. First run

1. Open http://localhost:5000/settings and set your electricity price, printer wattage and default profit %.
2. Go to **Filaments → + New filament** and add your spools.
3. Create your first order with **+ New order**.

---

## Docker Compose reference

```yaml
services:
  db:
    image: mariadb:11
    restart: unless-stopped
    environment:
      MARIADB_ROOT_PASSWORD: ${MARIADB_ROOT_PASSWORD}
      MARIADB_DATABASE: printing_app
      MARIADB_USER: ${MARIADB_USER}
      MARIADB_PASSWORD: ${MARIADB_PASSWORD}
    ports:
      - "3306:3306"
    volumes:
      - db_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 5s
      retries: 10

  app:
    image: nunobifes/printing-app
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: ${DATABASE_URL}
      SECRET_KEY: ${SECRET_KEY}
    ports:
      - "5000:5000"

volumes:
  db_data:
```

---

## Running without Docker (development)

```bash
# Start only the database
docker compose up -d db

# Set up Python environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env               # edit DATABASE_URL to point to localhost:3307

# Run
python run.py
```

---

## Deploying with Portainer

1. In Portainer, go to **Stacks → + Add stack**.
2. Paste the contents of `docker-compose.yml`.
3. Under **Environment variables**, add all variables from `.env.example` with your values.
4. Click **Deploy the stack**.

To update after a new image is pushed to Docker Hub:  
**Stacks → your stack → Editor → Update the stack** (Portainer pulls the latest image).

---

## CI/CD

Pushing to `main` triggers a GitHub Actions workflow (`.github/workflows/docker.yml`) that builds the Docker image and pushes it to Docker Hub as `nunobifes/printing-app:latest`.

**Required repository secrets** (GitHub → Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | Your Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token (Account Settings → Security → New Access Token) |

---

## Cost model

```
filament_cost    = Σ (weight_g / 1000 × avg_price_per_kg)   [snapshotted at order creation]
electricity_cost = (printer_watts / 1000) × print_hours × price_per_kwh
total_cost       = filament_cost + electricity_cost
sale_price       = total_cost × (1 + profit_pct / 100)
```

Weighted-average price on new filament purchase:

```
new_avg = (current_stock_kg × current_avg + purchase_kg × purchase_price)
          ─────────────────────────────────────────────────────────────────
                          (current_stock_kg + purchase_kg)
```

---

## Project structure

```
printing-app/
├── app/
│   ├── __init__.py       # app factory, DB retry loop, additive migrations
│   ├── models.py         # SQLAlchemy models and business logic
│   ├── routes.py         # all routes (single blueprint)
│   └── templates/        # Jinja2 templates
├── .env.example          # environment variable template
├── .github/workflows/    # CI/CD (Docker Hub push on push to main)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── run.py
```

---

## License

MIT
