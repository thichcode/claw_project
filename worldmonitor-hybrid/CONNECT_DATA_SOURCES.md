# Connect Data Sources to WorldMonitor

This guide shows how to push events into WorldMonitor API from **Zabbix**, **UptimeRobot**, **ELK/Logstash**, and **Python scripts**.

Base API URL:
- Local: `http://localhost:8000`
- In Docker network: `http://api:8000`

## 1) Ingest endpoints

WorldMonitor currently supports:
- `POST /ingest/zabbix`
- `POST /ingest/uptimerobot`
- `POST /ingest/alertmanager`

Payload shape (`IngestEvent`):

```json
{
  "source": "zabbix",
  "fingerprint": "unique-key",
  "service_name": "app-api-1",
  "severity": "critical",
  "title": "DB connection failures",
  "payload": {
    "raw": "anything JSON"
  }
}
```

---

## 2) Zabbix → WorldMonitor

### Option A: Zabbix Webhook media type
Set webhook URL to:

`http://<worldmonitor-host>:8000/ingest/zabbix`

Body template example:

```json
{
  "source": "zabbix",
  "fingerprint": "{EVENT.ID}",
  "service_name": "{HOST.NAME}",
  "severity": "{EVENT.SEVERITY}",
  "title": "{ALERT.SUBJECT}",
  "payload": {
    "event_id": "{EVENT.ID}",
    "trigger": "{TRIGGER.NAME}",
    "message": "{ALERT.MESSAGE}",
    "status": "{EVENT.STATUS}"
  }
}
```

### Severity mapping suggestion
- Disaster/Critical -> `critical`
- High -> `high`
- Average -> `medium`
- Warning -> `warning`
- Information/Not classified -> `info`

---

## 3) UptimeRobot → WorldMonitor

In UptimeRobot, create **Alert Contact = Webhook**:
- URL: `http://<worldmonitor-host>:8000/ingest/uptimerobot`
- Method: `POST`
- Content-Type: `application/json`

Body example:

```json
{
  "source": "uptimerobot",
  "fingerprint": "{{alert_id}}",
  "service_name": "{{friendly_name}}",
  "severity": "critical",
  "title": "UptimeRobot: {{friendly_name}} DOWN",
  "payload": {
    "monitor_url": "{{monitor_url}}",
    "alert_type": "{{alert_type}}",
    "details": "{{alert_details}}"
  }
}
```

Recovery event example (`UP`):
- send same `fingerprint`
- set severity to `info` or `ok`
- set title e.g. `UptimeRobot: service recovered`

---

## 4) ELK / Logstash → WorldMonitor

Use Logstash `http` output plugin to post selected alerts.

Example `logstash.conf` snippet:

```conf
output {
  if [event][kind] == "worldmonitor_alert" {
    http {
      url => "http://worldmonitor-api:8000/ingest/alertmanager"
      http_method => "post"
      format => "json"
      content_type => "application/json"
      mapping => {
        "source" => "elk"
        "fingerprint" => "%{[event][hash]}"
        "service_name" => "%{[service][name]}"
        "severity" => "%{[event][severity]}"
        "title" => "%{[message]}"
        "payload" => "%{[@metadata][raw_json]}"
      }
    }
  }
}
```

Tip: if `payload` mapping as string is inconvenient in Logstash, keep key fields in top-level and include raw event text under one field.

---

## 5) Python push script (generic)

```python
import requests

API = "http://localhost:8000"

data = {
    "source": "python-agent",
    "fingerprint": "py-demo-001",
    "service_name": "app-api-1",
    "severity": "warning",
    "title": "Custom probe latency high",
    "payload": {
        "latency_ms": 1850,
        "threshold_ms": 800,
        "region": "ap-southeast"
    }
}

r = requests.post(f"{API}/ingest/zabbix", json=data, timeout=10)
print(r.status_code, r.text)
```

---

## 6) Quick validation

1. Send test event:
```bash
curl -X POST http://localhost:8000/ingest/zabbix \
  -H "Content-Type: application/json" \
  -d '{"source":"zabbix","fingerprint":"test-1","service_name":"app-api-1","severity":"critical","title":"test alert","payload":{"demo":true}}'
```

2. Login and fetch alerts:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin"}' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/alerts
```

3. Open UI:
- `http://localhost:3000/alerts`
- `http://localhost:3000/topology`
- `http://localhost:3000/rca`
