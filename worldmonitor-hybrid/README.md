# WorldMonitor Hybrid

Hybrid monitoring project with FastAPI + Next.js + Postgres + Redis (Docker Compose).

## Stack
- **API**: FastAPI (Python 3.12)
- **Web**: Next.js 14 (App Router)
- **DB**: PostgreSQL 16
- **Cache/Event bus placeholder**: Redis 7

## Backend API
- Health: `GET /healthz`, `GET /readyz`
- Auth: `POST /auth/login`
- Ingest:
  - `POST /ingest/zabbix`
  - `POST /ingest/alertmanager`
  - `POST /ingest/uptimerobot`
- Alerts:
  - `GET /alerts`
  - `POST /alerts/{id}/ack`
- Incidents:
  - `POST /incidents`
  - `GET /incidents`
  - `GET /incidents/{id}`
  - `POST /incidents/{id}/assign`
  - `POST /incidents/{id}/comment`
  - `POST /incidents/{id}/resolve`
- Dashboard: `GET /summary`

## Frontend routes
- `/` Dashboard (API + fallback mock)
- `/alerts` Alerts inbox (API + fallback mock)
- `/incidents` Incidents list (API + fallback mock)
- `/incidents/[id]` Incident detail + **assign / comment / resolve** actions
- `/executive` Executive preview screen
- `/topology` Topology preview screen
- `/rca` RCA preview screen

UI theme: unified dark NOC style with reusable components:
- `StatusBadge`
- `PanelCard`
- `KPI`
- `HotspotTable`

## Run with Docker Compose

```bash
docker compose up --build
```

Services:
- Web: http://localhost:3000
- API: http://localhost:8000
- Postgres: localhost:5432
- Redis: localhost:6379

## Seed demo data

```bash
docker compose exec api python scripts/seed.py
```

Seed includes data for dashboard + executive/topology/rca demo stories.

Demo login:
- username: `admin`
- password: `admin`

## Quick tests

```bash
# health
curl http://localhost:8000/healthz

# login
curl -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin"}'

# alert ACK
curl -X POST http://localhost:8000/alerts/1/ack -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"ack_note":"NOC acknowledged"}'

# incident actions
curl -X POST http://localhost:8000/incidents/1/assign -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"assignee_id":2}'
curl -X POST http://localhost:8000/incidents/1/comment -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"comment":"Investigating"}'
curl -X POST http://localhost:8000/incidents/1/resolve -H "Authorization: Bearer <TOKEN>"
```

## Notes
- Mock auth + plain-text password are for demo only.
- Next.js pages gracefully fallback to local mock when API is unavailable.
