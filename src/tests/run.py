# ai-generated: 75% - test runner drafted from the published contract; reviewed by the student
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

BASE_URL = os.getenv("SVCDESK_URL", "http://svcdesk:8080").rstrip("/")
DEFAULT_CLOCK = "2026-09-28T10:00:00Z"


def request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    clock: str = DEFAULT_CLOCK,
) -> tuple[int, Any]:
    headers = {"X-Test-Clock": clock}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as response:
        status = response.code
        raw = response.read()
    parsed = json.loads(raw) if raw else None
    return status, parsed


def ticket_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": f"S3 test {uuid.uuid4().hex}",
        "reporter": {"name": "Lab test reporter"},
        "impact": 2,
        "urgency": 2,
    }
    payload.update(overrides)
    return payload


def create_ticket(
    *, impact: int = 2, urgency: int = 2, vip: bool = False, clock: str = DEFAULT_CLOCK
) -> dict[str, Any]:
    payload = ticket_payload(impact=impact, urgency=urgency)
    payload["reporter"] = {"name": "Lab test reporter", "vip": vip}
    status, response = request("POST", "/tickets", body=payload, clock=clock)
    assert status == 201, f"expected 201 when creating ticket, got {status}: {response}"
    return response


def assert_error(status: int, response: Any, allowed: set[int]) -> None:
    assert status in allowed, f"expected status in {allowed}, got {status}: {response}"
    assert isinstance(response, dict) and isinstance(response.get("error"), dict), (
        f"expected top-level error object, got {response!r}"
    )


def test_health() -> None:
    status, response = request("GET", "/health")
    assert status == 200
    assert response == {"status": "ok", "service": "svcdesk"}


def test_create_defaults_and_ignores_server_fields() -> None:
    payload = ticket_payload(
        impact=1,
        urgency=1,
        id="client-id",
        priority="P4",
        state="closed",
        created_at="2000-01-01T00:00:00Z",
        sla={"ack_due_at": "bad", "resolve_due_at": "bad"},
        extra_client_field="ignored",
    )
    status, ticket = request("POST", "/tickets", body=payload)
    assert status == 201
    assert ticket["id"] != "client-id"
    assert ticket["priority"] == "P1" and ticket["state"] == "new"
    assert ticket["description"] == ""
    assert ticket["reporter"] == {"name": "Lab test reporter", "email": None, "vip": False}
    assert ticket["created_at"] == DEFAULT_CLOCK
    assert ticket["acknowledged_at"] is None
    assert ticket["resolved_at"] is None and ticket["closed_at"] is None
    assert set(ticket["sla"]) == {"ack_due_at", "resolve_due_at"}


def test_ids_are_unique() -> None:
    first = create_ticket()
    second = create_ticket()
    assert first["id"] and second["id"] and first["id"] != second["id"]


def test_priority_matrix_and_vip_adjustment() -> None:
    expected = {
        (1, 1): "P1",
        (1, 2): "P2",
        (1, 3): "P3",
        (2, 1): "P2",
        (2, 2): "P3",
        (2, 3): "P4",
        (3, 1): "P3",
        (3, 2): "P4",
        (3, 3): "P4",
    }
    for (impact, urgency), priority in expected.items():
        ticket = create_ticket(impact=impact, urgency=urgency)
        assert ticket["priority"] == priority, (impact, urgency, ticket["priority"])
    assert create_ticket(impact=3, urgency=3, vip=True)["priority"] == "P2"
    assert create_ticket(impact=1, urgency=1, vip=True)["priority"] == "P1"


def test_get_and_exact_list_filters() -> None:
    ticket = create_ticket(impact=1, urgency=1)
    status, fetched = request("GET", f"/tickets/{ticket['id']}")
    assert status == 200 and fetched["id"] == ticket["id"]
    query = urllib.parse.urlencode({"state": "new", "priority": "P1"})
    status, matches = request("GET", f"/tickets?{query}")
    assert status == 200 and isinstance(matches, list)
    assert any(item["id"] == ticket["id"] for item in matches)
    assert all(item["state"] == "new" and item["priority"] == "P1" for item in matches)


def test_validation_errors_are_json() -> None:
    valid = ticket_payload()
    cases = [
        {},
        {**valid, "impact": 5},
        {**valid, "urgency": "high"},
        {**valid, "title": "x" * 201},
        {**valid, "reporter": {"name": ""}},
    ]
    for payload in cases:
        status, response = request("POST", "/tickets", body=payload)
        assert_error(status, response, {400, 422})


def test_state_machine_happy_path() -> None:
    ticket = create_ticket()
    ticket_id = ticket["id"]
    for action, expected_state in (
        ("ack", "acknowledged"),
        ("start", "in_progress"),
        ("resolve", "resolved"),
        ("close", "closed"),
    ):
        status, ticket = request("POST", f"/tickets/{ticket_id}/{action}")
        assert status == 200 and ticket["state"] == expected_state
    assert ticket["acknowledged_at"] == DEFAULT_CLOCK
    assert ticket["resolved_at"] == DEFAULT_CLOCK and ticket["closed_at"] == DEFAULT_CLOCK


def test_invalid_transitions_and_unknown_resources() -> None:
    ticket = create_ticket()
    ticket_id = ticket["id"]
    status, response = request("POST", f"/tickets/{ticket_id}/start")
    assert_error(status, response, {409})
    status, _ = request("POST", f"/tickets/{ticket_id}/ack")
    assert status == 200
    status, response = request("POST", f"/tickets/{ticket_id}/ack")
    assert_error(status, response, {409})
    status, response = request("POST", f"/tickets/{ticket_id}/resolve")
    assert_error(status, response, {409})
    status, response = request("GET", "/tickets/does-not-exist")
    assert_error(status, response, {404})
    status, response = request("GET", "/unknown-route")
    assert_error(status, response, {404})


def _resolve_ticket() -> dict[str, Any]:
    ticket = create_ticket()
    for action in ("ack", "start", "resolve"):
        status, ticket = request("POST", f"/tickets/{ticket['id']}/{action}")
        assert status == 200
    return ticket


def test_reopen_window_and_closed_immutability() -> None:
    ticket = _resolve_ticket()
    original_sla = ticket["sla"]
    status, reopened = request(
        "POST", f"/tickets/{ticket['id']}/reopen", clock="2026-10-05T10:00:00Z"
    )
    assert status == 200 and reopened["state"] == "in_progress"
    assert reopened["resolved_at"] is None and reopened["closed_at"] is None
    assert reopened["sla"] == original_sla

    too_late = _resolve_ticket()
    status, response = request(
        "POST", f"/tickets/{too_late['id']}/reopen", clock="2026-10-05T10:00:01Z"
    )
    assert_error(status, response, {409})

    closed = _resolve_ticket()
    status, closed = request("POST", f"/tickets/{closed['id']}/close")
    assert status == 200
    status, response = request(
        "POST", f"/tickets/{closed['id']}/reopen", clock="2026-09-29T10:00:00Z"
    )
    assert_error(status, response, {409})


def test_p1_wallclock_sla_and_strict_breach_boundary() -> None:
    friday = "2026-09-25T17:00:00+02:00"
    ticket = create_ticket(impact=1, urgency=1, clock=friday)
    assert ticket["sla"] == {
        "ack_due_at": "2026-09-25T15:15:00Z",
        "resolve_due_at": "2026-09-25T19:00:00Z",
    }
    status, sla = request(
        "GET", f"/tickets/{ticket['id']}/sla", clock="2026-09-25T19:00:00Z"
    )
    assert status == 200
    assert sla["ack_breached"] and not sla["resolve_breached"]
    assert not sla["paused"]
    status, sla = request(
        "GET", f"/tickets/{ticket['id']}/sla", clock="2026-09-25T19:00:01Z"
    )
    assert status == 200 and sla["ack_breached"] and sla["resolve_breached"]

    acknowledged = create_ticket(impact=1, urgency=1, clock=friday)
    status, _response = request(
        "POST",
        f"/tickets/{acknowledged['id']}/ack",
        clock="2026-09-25T15:15:00Z",
    )
    assert status == 200
    status, sla = request(
        "GET", f"/tickets/{acknowledged['id']}/sla", clock="2026-09-25T20:00:00Z"
    )
    assert status == 200 and not sla["ack_breached"]
    assert sla["resolve_breached"]


def test_business_sla_weekend_and_closing_tie() -> None:
    saturday = "2026-09-26T10:00:00+02:00"
    ticket = create_ticket(impact=1, urgency=2, clock=saturday)
    assert ticket["sla"]["ack_due_at"] == "2026-09-28T07:00:00Z"
    assert ticket["sla"]["resolve_due_at"] == "2026-09-28T14:00:00Z"

    status, sla = request("GET", f"/tickets/{ticket['id']}/sla", clock=saturday)
    assert status == 200 and sla["paused"]
    status, sla = request(
        "GET", f"/tickets/{ticket['id']}/sla", clock="2026-09-28T08:00:00+02:00"
    )
    assert status == 200 and not sla["paused"]
    assert not sla["ack_breached"] and not sla["resolve_breached"]
    status, sla = request(
        "GET", f"/tickets/{ticket['id']}/sla", clock="2026-09-28T16:00:00+02:00"
    )
    assert status == 200 and sla["resolve_breached"] is False and sla["paused"]
    status, sla = request(
        "GET", f"/tickets/{ticket['id']}/sla", clock="2026-09-28T16:00:01+02:00"
    )
    assert status == 200 and sla["resolve_breached"] and sla["paused"]


def test_malformed_test_clock_is_rejected() -> None:
    status, response = request("GET", "/health", clock="not-a-timestamp")
    assert_error(status, response, {400, 422})


def test_rfc3339_lowercase_markers_are_accepted() -> None:
    ticket = create_ticket(
        impact=1, urgency=1, clock="2026-09-28t10:00:00z"
    )
    assert ticket["created_at"] == "2026-09-28T10:00:00Z"


def test_unhashable_dora_fields_return_json_errors() -> None:
    window = {"from": "2026-09-01T00:00:00Z", "to": "2026-09-22T00:00:00Z"}
    cases = [
        {"event_id": "bad-type", "type": [], "at": "2026-09-01T00:00:00Z"},
        {
            "event_id": "bad-outcome",
            "type": "deployment",
            "at": "2026-09-01T00:00:00Z",
            "deployment_id": "d1",
            "environment": "production",
            "outcome": {},
            "commits": [],
            "unplanned": False,
            "caused_by": None,
        },
        {
            "event_id": "bad-phase",
            "type": "incident",
            "at": "2026-09-01T00:00:00Z",
            "incident_id": "i1",
            "phase": [],
            "deployments": [],
        },
    ]
    for event in cases:
        status, response = request(
            "POST", "/dora/metrics", body={"window": window, "events": [event]}
        )
        assert_error(status, response, {400, 422})


TESTS = [
    ("health response", test_health),
    ("ticket defaults and ignored server fields", test_create_defaults_and_ignores_server_fields),
    ("unique ticket ids", test_ids_are_unique),
    ("priority matrix and VIP adjustment", test_priority_matrix_and_vip_adjustment),
    ("ticket retrieval and exact list filters", test_get_and_exact_list_filters),
    ("validation and JSON errors", test_validation_errors_are_json),
    ("valid state transition path", test_state_machine_happy_path),
    ("invalid transitions and unknown resources", test_invalid_transitions_and_unknown_resources),
    ("reopen boundary and immutable closed ticket", test_reopen_window_and_closed_immutability),
    ("P1 wall-clock SLA and strict breach boundary", test_p1_wallclock_sla_and_strict_breach_boundary),
    ("business SLA weekend and closing tie", test_business_sla_weekend_and_closing_tie),
    ("malformed test clock", test_malformed_test_clock_is_rejected),
    ("RFC 3339 lowercase markers", test_rfc3339_lowercase_markers_are_accepted),
    ("malformed DORA enum fields", test_unhashable_dora_fields_return_json_errors),
]


def main() -> int:
    passed = 0
    failed = 0
    for name, test in TESTS:
        try:
            test()
            passed += 1
            print(f"PASS {name}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}", flush=True)
    print(f"ITSMLAB-TESTS: passed={passed} failed={failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
