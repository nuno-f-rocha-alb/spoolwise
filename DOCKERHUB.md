# Spoolwise

A self-hosted web app to manage 3D print orders, filament inventory, costs and business statistics.

**Source:** [github.com/nuno-f-rocha-alb/spoolwise](https://github.com/nuno-f-rocha-alb/spoolwise)

---

## Quick start

### 1. Create a `.env` file

```env
MARIADB_ROOT_PASSWORD=your_root_password
MARIADB_USER=printing
MARIADB_PASSWORD=your_db_password
DATABASE_URL=mysql+pymysql://printing:your_db_password@db:3306/printing_app
SECRET_KEY=a_long_random_secret

# Initial admin (created automatically on first start).
# Leave ADMIN_PASSWORD empty to have one generated and printed to the logs.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
ADMIN_EMAIL=
ADMIN_GROUP=admins

# Set to true only behind a trusted reverse proxy that handles SSO.
TRUST_PROXY_AUTH=false
```

### 2. Create a `docker-compose.yml`

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
      - "3307:3306"
    volumes:
      - db_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 5s
      retries: 10

  app:
    image: nunobifes/spoolwise:latest
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: ${DATABASE_URL}
      SECRET_KEY: ${SECRET_KEY}
      FLASK_DEBUG: "0"
      ADMIN_USERNAME: ${ADMIN_USERNAME:-admin}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:-}
      ADMIN_EMAIL: ${ADMIN_EMAIL:-}
      ADMIN_GROUP: ${ADMIN_GROUP:-admins}
      TRUST_PROXY_AUTH: ${TRUST_PROXY_AUTH:-false}
    ports:
      - "5000:5000"

volumes:
  db_data:
```

### 3. Run

```bash
docker compose up -d
```

App available at **http://localhost:5000**. Tables are created automatically on first start.

On first start an admin user is created automatically from `ADMIN_USERNAME`
(default `admin`). If `ADMIN_PASSWORD` is left empty, a random password is
generated and printed once to the container logs (`docker compose logs app`) —
sign in and change it immediately.

---

## Features

- Filament inventory with weighted-average price tracking
- Multi-plate orders with per-plate filament and print time
- Automatic cost calculation: filaments + electricity → sale price
- Price snapshots — historical order costs never change
- Personal use flag — track your own prints separately from revenue
- Statistics page with monthly charts (Chart.js)
- MakerWorld / Printables / Thingiverse model preview
- Configurable currency symbol
- Dark / light mode

---

## Environment variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection string (use `db` as hostname inside compose) |
| `SECRET_KEY` | Flask secret key — use a long random string in production |
| `MARIADB_ROOT_PASSWORD` | MariaDB root password |
| `MARIADB_USER` | App database user |
| `MARIADB_PASSWORD` | App database password |
