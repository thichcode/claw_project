import requests
from typing import Callable, List, Optional, Tuple

BASE_URL = "http://127.0.0.1:8000"

session = requests.Session()
results: List[Tuple[str, str, Optional[str]]] = []
auth_header = {}


def _record(name: str, status: str, message: Optional[str] = None):
    results.append((name, status, message))


def run_test(name: str, func: Callable[[], None]):
    try:
        func()
        _record(name, "PASS", None)
    except Exception as exc:
        _record(name, "FAIL", str(exc))


def assert_status(resp: requests.Response, expected: int = 200):
    if resp.status_code != expected:
        raise AssertionError(f"{resp.status_code} != {expected} ({resp.text})")


def require_auth():
    if not auth_header:
        raise AssertionError("Missing auth header after login")
    return auth_header


run_test("healthz", lambda: assert_status(session.get(f"{BASE_URL}/healthz")))
run_test("readyz", lambda: assert_status(session.get(f"{BASE_URL}/readyz")))


def invalid_login():
    resp = session.post(f"{BASE_URL}/auth/login", json={"username": "foo", "password": "bar"})
    assert_status(resp, 401)

run_test("login-invalid", invalid_login)


def valid_login():
    resp = session.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin"})
    assert_status(resp, 200)
    token = resp.json().get("access_token")
    if not token:
        raise AssertionError("missing token in login response")
    auth_header["Authorization"] = f"Bearer {token}"

run_test("login-valid", valid_login)


def list_alerts():
    resp = session.get(f"{BASE_URL}/alerts", headers=require_auth())
    assert_status(resp)
    data = resp.json()
    if not isinstance(data, list):
        raise AssertionError("alerts payload not a list")

run_test("alerts-list", list_alerts)


def alerts_filter():
    resp = session.get(
        f"{BASE_URL}/alerts",
        headers=require_auth(),
        params={"location_code": "hcm-dc1"},
    )
    assert_status(resp)

run_test("alerts-filter", alerts_filter)


def ack_open_alert():
    resp = session.post(
        f"{BASE_URL}/alerts/6/ack",
        headers=require_auth(),
        json={"ack_note": "QA ack"},
    )
    assert_status(resp)
    if resp.json().get("status") != "acked":
        raise AssertionError("alert did not transition to acked")

run_test("alert-ack-open", ack_open_alert)


def ack_again():
    resp = session.post(
        f"{BASE_URL}/alerts/6/ack",
        headers=require_auth(),
        json={},
    )
    assert_status(resp)

run_test("alert-ack-again", ack_again)


def ack_not_found():
    resp = session.post(
        f"{BASE_URL}/alerts/9999/ack",
        headers=require_auth(),
        json={"ack_note": "should 404"},
    )
    assert_status(resp, 404)

run_test("alert-ack-missing", ack_not_found)

incident_id: Optional[int] = None


def create_incident():
    global incident_id
    payload = {
        "title": "QA test incident",
        "severity": "critical",
        "service_id": 1,
        "location_code": "hcm-dc1",
    }
    resp = session.post(f"{BASE_URL}/incidents", headers=require_auth(), json=payload)
    assert_status(resp)
    data = resp.json()
    incident_id = data.get("id")
    if not incident_id:
        raise AssertionError("incident creation response missing id")

run_test("incident-create", create_incident)


def list_incidents():
    resp = session.get(
        f"{BASE_URL}/incidents",
        headers=require_auth(),
        params={"location_code": "hcm-dc1"},
    )
    assert_status(resp)

run_test("incidents-list", list_incidents)


def assign_incident():
    if not incident_id:
        raise AssertionError("missing incident id")
    resp = session.post(
        f"{BASE_URL}/incidents/{incident_id}/assign",
        headers=require_auth(),
        json={"assignee_id": 2},
    )
    assert_status(resp)
    if resp.json().get("assignee_id") != 2:
        raise AssertionError("assignee_id not updated")

run_test("incident-assign", assign_incident)


def comment_incident():
    if not incident_id:
        raise AssertionError("missing incident id")
    resp = session.post(
        f"{BASE_URL}/incidents/{incident_id}/comment",
        headers=require_auth(),
        json={"comment": "QA comment"},
    )
    assert_status(resp)

run_test("incident-comment", comment_incident)


def ack_incident():
    if not incident_id:
        raise AssertionError("missing incident id")
    resp = session.post(
        f"{BASE_URL}/incidents/{incident_id}/ack",
        headers=require_auth(),
        json={"ack_note": "QA ack"},
    )
    assert_status(resp)
    if resp.json().get("status") != "acked":
        raise AssertionError("incident not acked")

run_test("incident-ack", ack_incident)


def ack_incident_again():
    if not incident_id:
        raise AssertionError("missing incident id")
    resp = session.post(
        f"{BASE_URL}/incidents/{incident_id}/ack",
        headers=require_auth(),
        json={"ack_note": "QA ack"},
    )
    assert_status(resp)

run_test("incident-ack-again", ack_incident_again)


def resolve_incident():
    if not incident_id:
        raise AssertionError("missing incident id")
    resp = session.post(f"{BASE_URL}/incidents/{incident_id}/resolve", headers=require_auth())
    assert_status(resp)
    if resp.json().get("status") != "resolved":
        raise AssertionError("incident not resolved")

run_test("incident-resolve", resolve_incident)


def ack_resolved_incident():
    if not incident_id:
        raise AssertionError("missing incident id")
    resp = session.post(
        f"{BASE_URL}/incidents/{incident_id}/ack",
        headers=require_auth(),
        json={"ack_note": "QA ack"},
    )
    assert_status(resp, 409)

run_test("incident-ack-after-resolve", ack_resolved_incident)


def incident_detail():
    if not incident_id:
        raise AssertionError("missing incident id")
    resp = session.get(f"{BASE_URL}/incidents/{incident_id}", headers=require_auth())
    assert_status(resp)

run_test("incident-detail", incident_detail)


def ingest_event():
    payload = {
        "source": "uptimerobot",
        "service_name": "qa-service",
        "severity": "high",
        "title": "QA alert",
        "service_name": "qa-service",
    }
    resp = session.post(
        f"{BASE_URL}/ingest/alertmanager",
        headers=require_auth(),
        json=payload,
    )
    assert_status(resp)
    if not resp.json().get("ok"):
        raise AssertionError("ingest endpoint returned ok false")

run_test("ingest-alert", ingest_event)


def summary():
    resp = session.get(f"{BASE_URL}/summary", headers=require_auth())
    assert_status(resp)
    data = resp.json()
    for key in ("open_alerts", "acked_alerts", "open_incidents", "resolved_incidents"):
        if key not in data:
            raise AssertionError(f"summary missing {key}")

run_test("summary", summary)


def locations():
    resp = session.get(f"{BASE_URL}/locations", headers=require_auth())
    assert_status(resp)
    if not isinstance(resp.json(), list):
        raise AssertionError("locations payload not list")

run_test("locations", locations)


def topology():
    resp = session.get(f"{BASE_URL}/topology", headers=require_auth())
    assert_status(resp)
    data = resp.json()
    if not data.get("nodes"):
        raise AssertionError("topology nodes empty")
    if not data.get("kpi"):
        raise AssertionError("topology missing kpi")

run_test("topology", topology)


def demo_reset():
    resp = session.post(f"{BASE_URL}/demo/reset", headers=require_auth())
    assert_status(resp)
    if resp.json().get("ok") is not True:
        raise AssertionError("demo reset not ok")

run_test("demo-reset", demo_reset)

for name, status, message in results:
    print(f"{name}: {status}" + (f" - {message}" if message else ""))

fails = [r for r in results if r[1] != "PASS"]
if fails:
    raise SystemExit("QA script encountered failing tests")
