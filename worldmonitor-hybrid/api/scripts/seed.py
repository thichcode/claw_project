import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wm:wm@localhost:5432/worldmonitor")


def run():
    conn = psycopg2.connect(DATABASE_URL)
    with conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING", ("admin", "admin", "admin"))
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING", ("alice", "alice", "operator"))
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING", ("iam-oncall", "iam", "operator"))

            for s in [
                ("api-gateway", "prod", "platform"),
                ("payment", "prod", "finops"),
                ("keycloak", "prod", "iam"),
                ("data-pipeline", "prod", "data"),
                ("redis-cluster", "prod", "platform"),
            ]:
                cur.execute("INSERT INTO services (name, environment, owner) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING", s)

            cur.execute(
                """
                INSERT INTO alert_events(source, fingerprint, service_id, severity, title, payload, status)
                SELECT v.source, v.fp, s.id, v.severity, v.title, v.payload::jsonb, v.status
                FROM (VALUES
                    ('zabbix','seed-kc-latency','critical','Keycloak latency p95 > 2s','{"p95":"2.1s"}','open'),
                    ('alertmanager','seed-kafka-backlog','warning','Kafka backlog increased','{"backlog":"120k"}','open'),
                    ('uptimerobot','seed-api-5xx','high','API gateway 5xx above SLO','{"error_rate":"3.8%"}','acked')
                ) v(source, fp, severity, title, payload, status)
                JOIN services s ON (s.name = CASE
                    WHEN v.fp='seed-kc-latency' THEN 'keycloak'
                    WHEN v.fp='seed-kafka-backlog' THEN 'data-pipeline'
                    ELSE 'api-gateway' END)
                ON CONFLICT DO NOTHING
                """
            )

            cur.execute(
                """
                WITH svc AS (SELECT id FROM services WHERE name='keycloak' LIMIT 1),
                     usr AS (SELECT id FROM users WHERE username='admin' LIMIT 1)
                INSERT INTO incidents(title, severity, service_id, status, created_by)
                SELECT 'Login failures & latency spike', 'critical', svc.id, 'open', usr.id
                FROM svc, usr
                WHERE NOT EXISTS (SELECT 1 FROM incidents WHERE title='Login failures & latency spike')
                """
            )

            cur.execute(
                """
                WITH svc AS (SELECT id FROM services WHERE name='data-pipeline' LIMIT 1),
                     usr AS (SELECT id FROM users WHERE username='admin' LIMIT 1)
                INSERT INTO incidents(title, severity, service_id, status, created_by)
                SELECT 'Queue lag on data platform', 'high', svc.id, 'acked', usr.id
                FROM svc, usr
                WHERE NOT EXISTS (SELECT 1 FROM incidents WHERE title='Queue lag on data platform')
                """
            )

            cur.execute(
                """
                INSERT INTO incident_events(incident_id, event_type, actor_id, payload)
                SELECT i.id, 'created', u.id, '{"message":"incident created by seed"}'::jsonb
                FROM incidents i JOIN users u ON u.username='admin'
                WHERE i.title='Login failures & latency spike'
                  AND NOT EXISTS (SELECT 1 FROM incident_events e WHERE e.incident_id=i.id)
                """
            )
            cur.execute(
                """
                INSERT INTO incident_events(incident_id, event_type, actor_id, payload)
                SELECT i.id, 'commented', u.id, '{"comment":"Investigating cache saturation"}'::jsonb
                FROM incidents i JOIN users u ON u.username='iam-oncall'
                WHERE i.title='Login failures & latency spike'
                  AND NOT EXISTS (SELECT 1 FROM incident_events e WHERE e.incident_id=i.id AND e.event_type='commented')
                """
            )
    conn.close()
    print("Seed complete")


if __name__ == "__main__":
    run()
