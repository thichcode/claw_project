import json
import os
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///C:/Users/Lenovo/.openclaw/workspace/worldmonitor-hybrid/worldmonitor.db")

from api.app.db import execute, query_one  # noqa: E402

services = [
    ("prod-azure-app-auth", "prod", "azure"),
    ("prod-azure-app-billing", "prod", "azure"),
    ("prod-onprem-app-erp", "prod", "onprem"),
    ("stag-fci-app-gateway", "stag", "fci"),
    ("dev-azure-app-notify", "dev", "azure"),
    ("prod-fci-lb-edge", "prod", "fci"),
]

for name, env, owner in services:
    execute(
        "INSERT OR IGNORE INTO services(name, environment, owner) VALUES (%s, %s, %s)",
        (name, env, owner),
    )

alert_templates = [
    ("zabbix", "critical", "HTTP 500 spike", "api.auth.example.com", "prod-azure-app-auth", "open"),
    ("zabbix", "high", "DB connection timeout", "billing.example.com", "prod-azure-app-billing", "open"),
    ("uptimerobot", "high", "Domain DOWN", "erp.example.com", "prod-onprem-app-erp", "open"),
    ("alertmanager", "warning", "CPU high", "gateway.stag.example.com", "stag-fci-app-gateway", "open"),
    ("elk", "warning", "Nginx 502 burst", "api.prod.example.com", "prod-fci-lb-edge", "open"),
    ("elk", "info", "Slow query detected", "notify.dev.example.com", "dev-azure-app-notify", "acked"),
    ("python-agent", "critical", "TLS handshake failures", "login.prod.example.com", "prod-azure-app-auth", "open"),
    ("zabbix", "warning", "Redis memory high", "cache.prod.example.com", "prod-azure-app-billing", "open"),
]

for idx, (source, severity, a_type, domain, service_name, status) in enumerate(alert_templates, start=1):
    svc = query_one("SELECT id FROM services WHERE name=%s", (service_name,))
    payload = {
        "type": a_type,
        "domain": domain,
        "env": service_name.split("-")[0],
        "location": service_name.split("-")[1],
        "time": datetime.now(timezone.utc).isoformat(),
    }
    title = f"[{payload['env'].upper()}/{payload['location'].upper()}] {a_type} · {domain}"
    execute(
        """
        INSERT INTO alert_events(source, fingerprint, service_id, severity, title, payload, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            source,
            f"bulk-{idx}-{service_name}-{domain}",
            svc["id"] if svc else None,
            severity,
            title,
            json.dumps(payload),
            status,
        ),
    )

# create a couple incidents so dashboard shifts
admin = query_one("SELECT id FROM users WHERE username=%s", ("admin",))
for title, sev, svc_name, st in [
    ("Auth outage on Azure prod", "critical", "prod-azure-app-auth", "open"),
    ("ERP latency on onprem", "high", "prod-onprem-app-erp", "acked"),
]:
    svc = query_one("SELECT id FROM services WHERE name=%s", (svc_name,))
    execute(
        """
        INSERT INTO incidents(title, severity, service_id, status, created_by)
        SELECT %s, %s, %s, %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM incidents WHERE title=%s)
        """,
        (title, sev, svc["id"] if svc else None, st, admin["id"] if admin else None, title),
    )

print("Bulk simulation inserted.")
