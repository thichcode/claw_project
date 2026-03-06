import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.db import execute, query_one  # noqa: E402


def run():
    users = [
        ("admin", "admin", "admin"),
        ("alice", "alice", "operator"),
        ("iam-oncall", "iam", "operator"),
    ]
    for u in users:
        execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING",
            u,
        )

    services = [
        ("api-gateway", "prod", "platform"),
        ("payment", "prod", "finops"),
        ("keycloak", "prod", "iam"),
        ("data-pipeline", "prod", "data"),
        ("redis-cluster", "prod", "platform"),
        ("app-api-1", "prod", "app"),
        ("db-main-1", "prod", "data"),
        ("cache-1", "prod", "platform"),
        ("lb-public-1", "prod", "platform"),
        ("fw-edge-1", "prod", "secops"),
    ]
    for s in services:
        execute(
            "INSERT INTO services (name, environment, owner) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING",
            s,
        )

    locations = [
        ("hcm-dc1", "HCM Datacenter 1", "site"),
        ("sgp-az1", "Singapore AZ1", "zone"),
        ("hn-edge", "Ha Noi Edge", "site"),
    ]
    for loc in locations:
        execute(
            "INSERT INTO locations(code, name, level) VALUES (%s, %s, %s) ON CONFLICT (code) DO NOTHING",
            loc,
        )

    keycloak = query_one("SELECT id FROM services WHERE name=%s", ("keycloak",))
    datapipe = query_one("SELECT id FROM services WHERE name=%s", ("data-pipeline",))
    api_gw = query_one("SELECT id FROM services WHERE name=%s", ("api-gateway",))

    hcm = query_one("SELECT id FROM locations WHERE code=%s", ("hcm-dc1",))
    sgp = query_one("SELECT id FROM locations WHERE code=%s", ("sgp-az1",))

    service_location_map = [
        (keycloak["id"], hcm["id"], True),
        (datapipe["id"], sgp["id"], True),
        (api_gw["id"], hcm["id"], True),
    ]
    for m in service_location_map:
        execute(
            "INSERT INTO service_locations(service_id, location_id, is_primary) VALUES (%s, %s, %s) ON CONFLICT (service_id, location_id) DO NOTHING",
            m,
        )

    alerts = [
        ("zabbix", "seed-kc-latency", keycloak["id"], hcm["id"], "critical", "Keycloak latency p95 > 2s", {"p95": "2.1s"}, "open"),
        ("alertmanager", "seed-kafka-backlog", datapipe["id"], sgp["id"], "warning", "Kafka backlog increased", {"backlog": "120k"}, "open"),
        ("uptimerobot", "seed-api-5xx", api_gw["id"], hcm["id"], "high", "API gateway 5xx above SLO", {"error_rate": "3.8%"}, "acked"),
    ]
    for a in alerts:
        execute(
            """
            INSERT INTO alert_events(source, fingerprint, service_id, location_id, severity, title, payload, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            (a[0], a[1], a[2], a[3], a[4], a[5], json.dumps(a[6]), a[7]),
        )

    admin = query_one("SELECT id FROM users WHERE username=%s", ("admin",))

    execute(
        """
        INSERT INTO incidents(title, severity, service_id, location_id, status, created_by)
        SELECT %s, %s, %s, %s, %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM incidents WHERE title=%s)
        """,
        ("Login failures & latency spike", "critical", keycloak["id"], hcm["id"], "open", admin["id"], "Login failures & latency spike"),
    )
    execute(
        """
        INSERT INTO incidents(title, severity, service_id, location_id, status, created_by)
        SELECT %s, %s, %s, %s, %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM incidents WHERE title=%s)
        """,
        ("Queue lag on data platform", "high", datapipe["id"], sgp["id"], "acked", admin["id"], "Queue lag on data platform"),
    )

    inc = query_one("SELECT id FROM incidents WHERE title=%s", ("Login failures & latency spike",))
    if inc:
        execute(
            """
            INSERT INTO incident_hypotheses(incident_id, hypothesis, confidence, rank, evidence)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT DO NOTHING
            """,
            (inc["id"], "DB bottleneck causing cascading timeout", 0.89, 1, json.dumps({"signal": "db latency"})),
        )
        execute(
            """
            INSERT INTO incident_hypotheses(incident_id, hypothesis, confidence, rank, evidence)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT DO NOTHING
            """,
            (inc["id"], "Cache pressure increasing auth response time", 0.63, 2, json.dumps({"signal": "cache memory"})),
        )

    print("Seed complete")


if __name__ == "__main__":
    run()
