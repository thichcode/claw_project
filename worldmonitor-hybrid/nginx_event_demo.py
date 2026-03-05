import json
from datetime import datetime, timezone
import requests

API = "http://127.0.0.1:8000"

# Demo metrics (normally parsed from nginx log or exporter)
metrics = {
    "domain": "api.example.com",
    "upstream": "app-api-1:8000",
    "status_code": 504,
    "error_rate_5xx": 7.2,
    "p95_upstream_ms": 2300,
    "requests_1m": 1540,
}

severity = "high" if metrics["error_rate_5xx"] >= 5 else "warning"

event = {
    "source": "nginx-rp",
    "fingerprint": f"nginx:lb-public-1:timeout:{metrics['domain']}",
    "service_name": "lb-public-1",
    "severity": severity,
    "title": f"Nginx upstream timeout on {metrics['domain']}",
    "payload": {
        **metrics,
        "event_time": datetime.now(timezone.utc).isoformat(),
        "kind": "reverse-proxy-anomaly",
    },
}

print("=== Payload sent to WorldMonitor ===")
print(json.dumps(event, indent=2, ensure_ascii=False))

resp = requests.post(f"{API}/ingest/alertmanager", json=event, timeout=10)
print("\n=== API response ===")
print(resp.status_code)
try:
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
except Exception:
    print(resp.text)
