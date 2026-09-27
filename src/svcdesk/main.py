# ai-generated: 75% - HTTP API drafted from the receipted spec; reviewed by the student
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .sla import (
    UTC,
    calculate_due_times,
    format_timestamp,
    parse_rfc3339,
    sla_status,
)
from .storage import DB_LOCK, all_tickets, get_ticket, initialize_database, save_ticket

PRIORITIES = {
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


def _clock_enabled() -> bool:
    return os.getenv("SVCDESK_TEST_CLOCK", "").strip().lower() in {"1", "true"}


def request_now(
    x_test_clock: str | None = Header(default=None, alias="X-Test-Clock"),
) -> datetime:
    # Test time applies to this request only; it is never persisted as service state.
    if _clock_enabled() and x_test_clock is not None:
        try:
            return parse_rfc3339(x_test_clock)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return datetime.now(UTC)


def _priority_for(impact: int, urgency: int, vip: bool) -> str:
    priority = PRIORITIES[(impact, urgency)]
    if vip and priority in {"P3", "P4"}:
        return "P2"
    return priority


def _validate_ticket_payload(
    payload: Any,
) -> tuple[str, str, dict[str, Any], int, int, str | None]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The request body must be a JSON object.")

    title = payload.get("title")
    if not isinstance(title, str) or not 1 <= len(title) <= 200:
        raise HTTPException(status_code=400, detail="title must be a string of 1 to 200 characters.")

    reporter = payload.get("reporter")
    if not isinstance(reporter, dict):
        raise HTTPException(status_code=400, detail="reporter must be an object with a name.")
    reporter_name = reporter.get("name")
    if not isinstance(reporter_name, str) or not 1 <= len(reporter_name) <= 100:
        raise HTTPException(status_code=400, detail="reporter.name must be a string of 1 to 100 characters.")

    reporter_email = reporter.get("email")
    if reporter_email is not None and not isinstance(reporter_email, str):
        raise HTTPException(status_code=400, detail="reporter.email must be a string or null.")
    reporter_vip = reporter.get("vip", False)
    if not isinstance(reporter_vip, bool):
        raise HTTPException(status_code=400, detail="reporter.vip must be a boolean.")

    impact = payload.get("impact")
    urgency = payload.get("urgency")
    if type(impact) is not int or impact not in {1, 2, 3}:
        raise HTTPException(status_code=400, detail="impact must be an integer from 1 to 3.")
    if type(urgency) is not int or urgency not in {1, 2, 3}:
        raise HTTPException(status_code=400, detail="urgency must be an integer from 1 to 3.")

    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > 4000:
        raise HTTPException(status_code=400, detail="description must be a string of at most 4000 characters.")

    related_to = payload.get("related_to")
    if related_to is not None and not isinstance(related_to, str):
        raise HTTPException(status_code=400, detail="related_to must be a string or null.")

    normalized_reporter = {
        "name": reporter_name,
        "email": reporter_email,
        "vip": reporter_vip,
    }
    return title, description, normalized_reporter, impact, urgency, related_to


def _ticket_or_404(ticket_id: str) -> dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def _transition(ticket_id: str, action: str, now: datetime) -> dict[str, Any]:
    expected_states = {
        "ack": "new",
        "start": "acknowledged",
        "resolve": "in_progress",
        "close": "resolved",
        "reopen": "resolved",
    }
    target_states = {
        "ack": "acknowledged",
        "start": "in_progress",
        "resolve": "resolved",
        "close": "closed",
        "reopen": "in_progress",
    }
    timestamp_fields = {"ack": "acknowledged_at", "resolve": "resolved_at", "close": "closed_at"}

    # Keep the read-check-write sequence atomic so concurrent actions cannot skip states.
    with DB_LOCK:
        ticket = get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        if ticket["state"] != expected_states[action]:
            raise HTTPException(status_code=409, detail=f"Action {action} is invalid from state {ticket['state']}.")

        if action == "reopen":
            resolved_at = parse_rfc3339(ticket["resolved_at"])
            if now > resolved_at + timedelta(days=7):
                raise HTTPException(status_code=409, detail="The ticket can no longer be reopened.")
            ticket["resolved_at"] = None
            ticket["closed_at"] = None
        else:
            timestamp_field = timestamp_fields.get(action)
            if timestamp_field is not None:
                ticket[timestamp_field] = format_timestamp(now)

        ticket["state"] = target_states[action]
        save_ticket(ticket)
    return ticket


initialize_database()
app = FastAPI(title="svcdesk", docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    code = "not_found" if exc.status_code == 404 else "http_error"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_request", "message": "The request is invalid."}},
    )


@app.get("/health")
def health(now: datetime = Depends(request_now)) -> dict[str, str]:
    return {"status": "ok", "service": "svcdesk"}


@app.post("/tickets", status_code=201)
def create_ticket(
    payload: Any = Body(...), now: datetime = Depends(request_now)
) -> dict[str, Any]:
    title, description, reporter, impact, urgency, related_to = _validate_ticket_payload(payload)
    priority = _priority_for(impact, urgency, reporter["vip"])
    ticket = {
        "id": uuid.uuid4().hex,
        "title": title,
        "description": description,
        "reporter": reporter,
        "impact": impact,
        "urgency": urgency,
        "priority": priority,
        "state": "new",
        "created_at": format_timestamp(now),
        "acknowledged_at": None,
        "resolved_at": None,
        "closed_at": None,
        "related_to": related_to,
        "sla": calculate_due_times(priority, now),
    }
    save_ticket(ticket)
    return ticket


@app.get("/tickets")
def list_tickets(
    state: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    now: datetime = Depends(request_now),
) -> list[dict[str, Any]]:
    tickets = all_tickets()
    if state is not None:
        tickets = [ticket for ticket in tickets if ticket["state"] == state]
    if priority is not None:
        tickets = [ticket for ticket in tickets if ticket["priority"] == priority]
    return tickets


@app.get("/tickets/{ticket_id}")
def get_ticket_route(ticket_id: str, now: datetime = Depends(request_now)) -> dict[str, Any]:
    return _ticket_or_404(ticket_id)


@app.get("/tickets/{ticket_id}/sla")
def get_ticket_sla(
    ticket_id: str, now: datetime = Depends(request_now)
) -> dict[str, Any]:
    return sla_status(_ticket_or_404(ticket_id), now)


def _action_handler(action: str):
    def handler(ticket_id: str, now: datetime = Depends(request_now)) -> dict[str, Any]:
        return _transition(ticket_id, action, now)

    return handler


app.add_api_route("/tickets/{ticket_id}/ack", _action_handler("ack"), methods=["POST"], status_code=200)
app.add_api_route("/tickets/{ticket_id}/start", _action_handler("start"), methods=["POST"], status_code=200)
app.add_api_route("/tickets/{ticket_id}/resolve", _action_handler("resolve"), methods=["POST"], status_code=200)
app.add_api_route("/tickets/{ticket_id}/close", _action_handler("close"), methods=["POST"], status_code=200)
app.add_api_route("/tickets/{ticket_id}/reopen", _action_handler("reopen"), methods=["POST"], status_code=200)
