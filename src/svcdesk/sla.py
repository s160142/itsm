# ai-generated: 75% - SLA calculations extracted from the approved behavior; reviewed by the student
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

UTC = timezone.utc
WARSAW = ZoneInfo("Europe/Warsaw")
OPENING = time(8, 0)
CLOSING = time(16, 0)
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
SLA_TARGETS = {
    "P1": (15, 4 * 60),
    "P2": (60, 8 * 60),
    "P3": (4 * 60, 24 * 60),
    "P4": (8 * 60, 72 * 60),
}


def format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_rfc3339(value: str) -> datetime:
    if not RFC3339_PATTERN.fullmatch(value):
        raise ValueError("Expected an RFC 3339 timestamp with a timezone.")
    normalized = value[:-1] + "+00:00" if value[-1] in "Zz" else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Expected a valid RFC 3339 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Expected an RFC 3339 timestamp with a timezone.")
    return parsed.astimezone(UTC)


def _next_business_opening(day: date) -> datetime:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, OPENING, tzinfo=WARSAW)


def add_business_time(start: datetime, minutes: int) -> datetime:
    local_start = start.astimezone(WARSAW)
    local_time = local_start.timetz().replace(tzinfo=None)

    if local_start.weekday() < 5 and local_time < OPENING:
        cursor = datetime.combine(local_start.date(), OPENING, tzinfo=WARSAW)
    elif local_start.weekday() < 5 and local_time < CLOSING:
        cursor = local_start
    else:
        cursor = _next_business_opening(local_start.date() + timedelta(days=1))

    remaining = timedelta(minutes=minutes)
    while remaining > timedelta(0):
        closing = datetime.combine(cursor.date(), CLOSING, tzinfo=WARSAW)
        available = closing - cursor
        # A target ending exactly at 16:00 is due at closing, not next opening.
        if remaining <= available:
            return (cursor + remaining).astimezone(UTC)
        remaining -= available
        cursor = _next_business_opening(cursor.date() + timedelta(days=1))

    return cursor.astimezone(UTC)


def is_business_time(value: datetime) -> bool:
    local_value = value.astimezone(WARSAW)
    local_time = local_value.timetz().replace(tzinfo=None)
    return local_value.weekday() < 5 and OPENING <= local_time < CLOSING


def calculate_due_times(priority: str, created_at: datetime) -> dict[str, str]:
    ack_minutes, resolve_minutes = SLA_TARGETS[priority]
    if priority == "P1":
        ack_due = created_at + timedelta(minutes=ack_minutes)
        resolve_due = created_at + timedelta(minutes=resolve_minutes)
    else:
        ack_due = add_business_time(created_at, ack_minutes)
        resolve_due = add_business_time(created_at, resolve_minutes)
    return {
        "ack_due_at": format_timestamp(ack_due),
        "resolve_due_at": format_timestamp(resolve_due),
    }


def sla_status(ticket: dict[str, Any], now: datetime) -> dict[str, Any]:
    ack_due = parse_rfc3339(ticket["sla"]["ack_due_at"])
    resolve_due = parse_rfc3339(ticket["sla"]["resolve_due_at"])

    acknowledged_at = ticket["acknowledged_at"]
    resolved_at = ticket["resolved_at"]
    # Strict comparisons make an event or outstanding target at the due instant on time.
    ack_breached = (
        parse_rfc3339(acknowledged_at) > ack_due
        if acknowledged_at is not None
        else now > ack_due
    )
    resolve_breached = (
        parse_rfc3339(resolved_at) > resolve_due
        if resolved_at is not None
        else now > resolve_due
    )

    priority = ticket["priority"]
    paused = (
        ticket["state"] not in {"resolved", "closed"}
        and priority != "P1"
        and not is_business_time(now)
    )
    return {
        "priority": priority,
        "ack_due_at": ticket["sla"]["ack_due_at"],
        "resolve_due_at": ticket["sla"]["resolve_due_at"],
        "ack_breached": ack_breached,
        "resolve_breached": resolve_breached,
        "paused": paused,
    }
