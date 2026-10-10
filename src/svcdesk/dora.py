# ai-generated: 60% - DORA rules translated from the published Lab 2 metric specification, reviewed
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, cast, Literal, NoReturn, TypedDict

from .sla import format_timestamp, parse_rfc3339

SECONDS_PER_DAY = Decimal(86400)
MICROSECONDS_PER_SECOND = 1_000_000


class IncidentRecord(TypedDict):
    opened: datetime | None
    resolved: datetime | None
    deployments: set[str]


def _invalid(message: str) -> NoReturn:
    raise ValueError(message)


def _required_string(value: Any, field: str, *, max_length: int | None = None) -> str:
    if (
        not isinstance(value, str)
        or not value
        or (max_length is not None and len(value) > max_length)
    ):
        _invalid(f"{field} must be a non-empty string.")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        _invalid(f"{field} must be an RFC 3339 timestamp.")
    try:
        return parse_rfc3339(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid RFC 3339 timestamp.") from exc


def _delta_microseconds(later: datetime, earlier: datetime) -> int:
    delta = later - earlier
    whole_seconds = delta.days * 86400 + delta.seconds
    return whole_seconds * MICROSECONDS_PER_SECOND + delta.microseconds


def _median_seconds(values_us: list[int]) -> int | None:
    if not values_us:
        return None
    ordered = sorted(values_us)
    middle = len(ordered) // 2
    # Keep a half-microsecond median exact until the final half-up rounding.
    median_twice_us = (
        ordered[middle] * 2
        if len(ordered) % 2
        else ordered[middle - 1] + ordered[middle]
    )
    return (median_twice_us + MICROSECONDS_PER_SECOND) // (2 * MICROSECONDS_PER_SECOND)


def _six_places(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(
        (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    )


def _window_frequency(count: int, window_us: int) -> float:
    per_day = Decimal(count) * SECONDS_PER_DAY * MICROSECONDS_PER_SECOND / Decimal(window_us)
    return float(per_day.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _read_events(raw_events: list[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()

    for raw in raw_events:
        if not isinstance(raw, dict):
            _invalid("Every event must be a JSON object.")
        event_id = _required_string(raw.get("event_id"), "event_id", max_length=64)
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)

        event_type = raw.get("type")
        if not isinstance(event_type, str) or event_type not in {"commit", "deployment", "incident"}:
            _invalid(f"Event {event_id} has an unsupported type.")
        event = dict(raw)
        event["_at"] = _timestamp(raw.get("at"), f"event {event_id}.at")

        if event_type == "commit":
            _required_string(raw.get("sha"), f"event {event_id}.sha")
            _required_string(raw.get("branch"), f"event {event_id}.branch")
            if "reverts" not in raw or "change_id" not in raw:
                _invalid(f"Commit {event_id} must include reverts and change_id fields.")
            reverts = raw["reverts"]
            change_id = raw["change_id"]
            if reverts is None:
                _required_string(change_id, f"event {event_id}.change_id")
            else:
                _required_string(reverts, f"event {event_id}.reverts")
                if change_id is not None:
                    _invalid(f"Revert commit {event_id} must have a null change_id.")
        elif event_type == "deployment":
            _required_string(raw.get("deployment_id"), f"event {event_id}.deployment_id")
            _required_string(raw.get("environment"), f"event {event_id}.environment")
            outcome = raw.get("outcome")
            if not isinstance(outcome, str) or outcome not in {"success", "failure"}:
                _invalid(f"Deployment {event_id}.outcome must be success or failure.")
            commits = raw.get("commits")
            if not isinstance(commits, list) or any(not isinstance(sha, str) or not sha for sha in commits):
                _invalid(f"Deployment {event_id}.commits must be an array of non-empty strings.")
            if not isinstance(raw.get("unplanned"), bool):
                _invalid(f"Deployment {event_id}.unplanned must be a boolean.")
            if "caused_by" not in raw:
                _invalid(f"Deployment {event_id} must include caused_by.")
            caused_by = raw["caused_by"]
            if caused_by is not None and (not isinstance(caused_by, str) or not caused_by):
                _invalid(f"Deployment {event_id}.caused_by must be a string or null.")
        else:
            _required_string(raw.get("incident_id"), f"event {event_id}.incident_id")
            phase = raw.get("phase")
            if not isinstance(phase, str) or phase not in {"opened", "resolved"}:
                _invalid(f"Incident {event_id}.phase must be opened or resolved.")
            deployments = raw.get("deployments")
            if not isinstance(deployments, list) or any(
                not isinstance(deployment_id, str) or not deployment_id for deployment_id in deployments
            ):
                _invalid(f"Incident {event_id}.deployments must be an array of non-empty strings.")
        events.append(event)

    return events


def _validate_references(
    events: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, IncidentRecord],
    dict[str, str],
]:
    commits: dict[str, dict[str, Any]] = {}
    deployments: dict[str, dict[str, Any]] = {}
    incidents: dict[str, IncidentRecord] = {}

    for event in events:
        kind = event["type"]
        if kind == "commit":
            sha = event["sha"]
            if sha in commits:
                _invalid(f"Commit sha {sha} is not unique.")
            commits[sha] = event
        elif kind == "deployment":
            deployment_id = event["deployment_id"]
            if deployment_id in deployments:
                _invalid(f"deployment_id {deployment_id} is not unique.")
            deployments[deployment_id] = event
        else:
            incident = incidents.setdefault(
                event["incident_id"], {"opened": None, "resolved": None, "deployments": set()}
            )
            phase = cast(Literal["opened", "resolved"], event["phase"])
            if incident[phase] is not None:
                _invalid(f"Incident {event['incident_id']} has more than one {phase} event.")
            incident[phase] = event["_at"]
            incident["deployments"].update(event["deployments"])

    for event in events:
        if (
            event["type"] == "commit"
            and event["reverts"] is not None
            and event["reverts"] not in commits
        ):
            _invalid(f"Commit {event['sha']} reverts an unknown sha.")
        if event["type"] == "deployment":
            if any(sha not in commits for sha in event["commits"]):
                _invalid(f"Deployment {event['deployment_id']} references an unknown commit.")
            if event["caused_by"] is not None and event["caused_by"] not in incidents:
                _invalid(f"Deployment {event['deployment_id']} references an unknown incident.")
        if event["type"] == "incident" and any(
            deployment_id not in deployments for deployment_id in event["deployments"]
        ):
            _invalid(f"Incident {event['incident_id']} references an unknown deployment.")

    for incident_id, incident in incidents.items():
        if incident["resolved"] is not None and incident["opened"] is None:
            _invalid(f"Incident {incident_id} is resolved but was never opened.")

    change_by_sha: dict[str, str] = {}
    resolving: set[str] = set()

    def resolve_change(sha: str) -> str:
        if sha in change_by_sha:
            return change_by_sha[sha]
        if sha in resolving:
            _invalid("The commit revert graph contains a cycle.")
        resolving.add(sha)
        commit = commits[sha]
        change_id = commit["change_id"] if commit["reverts"] is None else resolve_change(commit["reverts"])
        resolving.remove(sha)
        change_by_sha[sha] = change_id
        return change_id

    for sha in commits:
        resolve_change(sha)

    return commits, deployments, incidents, change_by_sha


def calculate_dora_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _invalid("The request body must be a JSON object.")
    body = cast(dict[str, Any], payload)
    window = body.get("window")
    if not isinstance(window, dict):
        _invalid("window must be an object with from and to timestamps.")
    window = cast(dict[str, Any], window)
    start = _timestamp(window.get("from"), "window.from")
    end = _timestamp(window.get("to"), "window.to")
    if end <= start:
        _invalid("window.to must be after window.from.")
    raw_events = body.get("events")
    if not isinstance(raw_events, list):
        _invalid("events must be an array.")

    events = _read_events(cast(list[Any], raw_events))
    commits, deployments_by_id, incidents, change_by_sha = _validate_references(events)

    in_window = [
        deployment
        for deployment in deployments_by_id.values()
        if deployment["environment"] == "production" and start <= deployment["_at"] < end
    ]
    in_window.sort(
        key=lambda deployment: (
            deployment["_at"],
            deployment["deployment_id"].encode("utf-8"),
        )
    )

    deployments_count = len(in_window)
    successful = [deployment for deployment in in_window if deployment["outcome"] == "success"]
    failures = [deployment for deployment in in_window if deployment["outcome"] == "failure"]
    no_commit_count = sum(not deployment["commits"] for deployment in in_window)
    rework_count = sum(
        deployment["unplanned"] and deployment["caused_by"] is not None
        for deployment in in_window
    )

    delivered_shas = {
        sha for deployment in in_window for sha in deployment["commits"]
    }
    off_main = sum(1 for sha in delivered_shas if commits[sha]["branch"] != "main")

    negative_lead_pairs = 0
    lead_durations: list[int] = []
    seen_lead_shas: set[str] = set()
    first_success_by_change: dict[str, datetime] = {}
    for deployment in successful:
        deployment_changes = {change_by_sha[sha] for sha in deployment["commits"]}
        for change_id in deployment_changes:
            first_success_by_change.setdefault(change_id, deployment["_at"])
        for sha in set(deployment["commits"]):
            if sha in seen_lead_shas:
                continue
            seen_lead_shas.add(sha)
            duration = _delta_microseconds(deployment["_at"], commits[sha]["_at"])
            if duration < 0:
                negative_lead_pairs += 1
                duration = 0
            lead_durations.append(duration)

    first_commit_by_change: dict[str, datetime] = {}
    for sha, commit in commits.items():
        change_id = change_by_sha[sha]
        first_commit_by_change[change_id] = min(
            first_commit_by_change.get(change_id, commit["_at"]), commit["_at"]
        )
    true_lead_durations: list[int] = []
    for change_id, delivered_at in first_success_by_change.items():
        duration = _delta_microseconds(delivered_at, first_commit_by_change[change_id])
        true_lead_durations.append(max(0, duration))

    covering_incidents: dict[str, list[tuple[datetime, bytes, IncidentRecord]]] = defaultdict(list)
    overlapping_incidents = [
        (incident_id, incident)
        for incident_id, incident in incidents.items()
        if incident["opened"] is not None
    ]
    for incident_id, incident in overlapping_incidents:
        opened = incident["opened"]
        if opened is None:
            continue
        for deployment_id in incident["deployments"]:
            covering_incidents[deployment_id].append(
                (opened, incident_id.encode("utf-8"), incident)
            )

    recovered_durations: list[int] = []
    open_failures = 0
    for deployment in failures:
        candidates = covering_incidents.get(deployment["deployment_id"], [])
        if not candidates:
            open_failures += 1
            continue
        _, _, incident = min(candidates, key=lambda item: (item[0], item[1]))
        if incident["resolved"] is None:
            open_failures += 1
            continue
        recovered_durations.append(
            max(0, _delta_microseconds(incident["resolved"], deployment["_at"]))
        )

    overlap_count = 0
    for index, (_, left) in enumerate(overlapping_incidents):
        left_opened = left["opened"]
        if left_opened is None:
            continue
        left_end = left["resolved"] if left["resolved"] is not None else end
        for _, right in overlapping_incidents[index + 1 :]:
            right_opened = right["opened"]
            if right_opened is None:
                continue
            right_end = right["resolved"] if right["resolved"] is not None else end
            if left_opened < right_end and right_opened < left_end:
                overlap_count += 1

    window_us = _delta_microseconds(end, start)
    changes = set(change_by_sha.values())
    return {
        "spec_version": "1.0.0",
        "window": {"from": format_timestamp(start), "to": format_timestamp(end)},
        "deployment_frequency_per_day": _window_frequency(deployments_count, window_us),
        "change_lead_time_seconds_p50": _median_seconds(lead_durations),
        "failed_deployment_recovery_time_seconds_p50": _median_seconds(recovered_durations),
        "change_fail_rate": _six_places(len(failures), deployments_count),
        "deployment_rework_rate": _six_places(rework_count, deployments_count),
        "counts": {
            "deployments": deployments_count,
            "successful_deployments": len(successful),
            "failed_deployments": len(failures),
            "recovered_failures": len(recovered_durations),
            "open_failures": open_failures,
            "rework_deployments": rework_count,
            "lead_time_pairs": len(lead_durations),
            "changes": len(changes),
        },
        "anomalies": {
            "negative_lead_time_pairs": negative_lead_pairs,
            "deployments_without_commits": no_commit_count,
            "commits_never_on_main": off_main,
            "revert_chains_collapsed": sum(commit["reverts"] is not None for commit in commits.values()),
            "overlapping_incident_pairs": overlap_count,
        },
        "ground_truth": {
            "changes_delivered": len(first_success_by_change),
            "true_change_lead_time_seconds_p50": _median_seconds(true_lead_durations),
        },
    }
