<!-- ai-generated: 30% - drafted by AI from the course requirements, formatting -->
# svcdesk HTTP ticket service specification

## Purpose and scope

Build `svcdesk`, a JSON-only ticketing API for desk agents, monitoring and integrations. It assigns priority, calculates SLA targets, enforces ticket transitions and reports tickets. This behavioral specification covers `REQUIREMENTS.md` R-01–R-25; `API.md` is authoritative where it defines a detail more precisely.

## Decisions

- **C1 — `wallclock`:** Both P1 SLA targets run continuously, including nights and weekends; P2–P4 use business hours. This keeps urgent P1 deadlines round-the-clock. The rejected alternative is business-hours timing for P1.
- **C2 — `immutable`:** Resolved tickets may be reopened through seven days after resolution; closed tickets cannot be reopened. A continuing issue requires a new ticket linked with `related_to`. This preserves the closed record; the rejected alternative is reopening closed tickets within seven days.
- **C3 — `vip`:** Apply the impact/urgency matrix, then raise VIP tickets at P3 or P4 to P2; P1 and P2 remain unchanged. This makes VIP issues visible without allowing clients to set priority. The rejected alternative is applying the matrix alone.

The implementation and `DECISIONS.md` must use these same choices; the checker accepts any allowed combination if both agree.

## Tickets and priority

A ticket has a service-generated, unique, opaque, non-empty string `id`; required `title` (1–200 characters), `reporter.name` (1–100 characters), integer `impact` and `urgency` (each 1–3; impact 1/2/3 means organisation/team/one person, urgency 1/2/3 means work stopped/degraded/cosmetic); and optional `description` (default `""`, max 4000 characters), `reporter.email` (string or null, default `null`), `reporter.vip` (default `false`), and `related_to` (default `null`). `related_to` need not refer to an existing ticket in this lab.

The impact/urgency priority matrix is:

| Impact / urgency | 1 | 2 | 3 |
|---|---|---|---|
| 1 | P1 | P2 | P3 |
| 2 | P2 | P3 | P4 |
| 3 | P3 | P4 | P4 |

Apply C3 after the matrix. Ignore client-supplied server-owned fields (`id`, `priority`, `state`, timestamps and `sla`) and all unknown fields. Invalid required fields or values return 400 or 422 with a JSON body containing a top-level `error` object.

## HTTP contract

All request and response bodies are JSON. The service listens on port 8080 and exposes:

| Request | Behavior |
|---|---|
| `GET /health` | 200, `{"status":"ok","service":"svcdesk"}` |
| `POST /tickets` | Create; 201 with the full ticket |
| `GET /tickets` | 200 with every match in one array; optional exact `state` and `priority` filters; no pagination |
| `GET /tickets/{id}` | 200 with the ticket |
| `GET /tickets/{id}/sla` | 200 with current SLA status |
| `POST /tickets/{id}/ack`, `/start`, `/resolve`, `/close`, `/reopen` | 200 with the updated ticket; invalid transition 409 |

Unknown paths return 404; unsupported methods may return 404 or 405. Unknown IDs return 404 with a JSON body containing a top-level `error`. A ticket response includes its request/default fields, computed `priority`, `state`, `related_to`, `sla.ack_due_at`, `sla.resolve_due_at`, and RFC 3339 `created_at`, `acknowledged_at`, `resolved_at`, `closed_at` timestamps. Event timestamps are null until recorded. Timestamps are returned in UTC with `Z`. New tickets start in `new`.

## State transitions

The only forward transitions are `new` → `acknowledged` (`/ack`) → `in_progress` (`/start`) → `resolved` (`/resolve`) → `closed` (`/close`). Record `acknowledged_at`, `resolved_at` and `closed_at` when those actions occur. Any other transition returns 409; an unknown ID returns 404.

Under C2, `/reopen` changes `resolved` to `in_progress` only when `now <= resolved_at + 7 days`; otherwise return 409. Clear `resolved_at` and `closed_at` on a successful reopen. Closed tickets always return 409. Reopening does not change the original SLA deadlines.

## SLA and request clock

Targets are measured from creation:

| Priority | Acknowledge | Resolve |
|---|---:|---:|
| P1 | 15 min | 4 h |
| P2 | 1 h | 8 h |
| P3 | 4 h | 24 h |
| P4 | 8 h | 72 h |

Use wall-clock time for both P1 targets (C1). For P2–P4, count only Monday–Friday, 08:00 inclusive to 16:00 exclusive, in `Europe/Warsaw`; public holidays are business days. If creation is before opening, start at 08:00 that business day; if after closing or on a weekend, start at 08:00 on the next business day. Consume time across business windows. A target ending exactly at closing is due at that closing instant. Return due instants in UTC with `Z`.

`GET /tickets/{id}/sla` returns `priority`, `ack_due_at`, `resolve_due_at`, `ack_breached`, `resolve_breached` and `paused`. A target is breached if its event occurred strictly after its due instant, or it remains outstanding and `now` is strictly after the due instant; equality is not a breach. After reopening, the ticket is unresolved against its original resolution deadline. `paused` is true only for an unresolved, open ticket whose resolution clock uses business time when `now` is outside business hours; it is always false for P1 under C1.

When `SVCDESK_TEST_CLOCK` is `1` or `true`, a valid RFC 3339 `X-Test-Clock` header supplies `now` for that request only; a malformed value returns 400 or 422. Otherwise use real UTC time, and ignore the header if test-clock support is disabled. Do not compare clocks across requests or reject an action because its clock precedes a stored timestamp.

## Runtime and acceptance

Docker Compose must build a service named `svcdesk` from the repository, expose container port 8080 and set `SVCDESK_TEST_CLOCK`. No service may use a host-path bind mount or require network access at runtime. Tickets must survive a service-container restart using persistent storage. After `docker compose up`, `/health` must return 200 within 120 seconds.

Acceptance covers the published HTTP checks: health, create/get/list and validation; all matrix and VIP cases; valid and invalid transitions and reopen-window boundaries; every published SLA vector (including DST and closing-time ties), breach/pause behavior and test-clock handling. The observed C1/C2/C3 behavior must match `DECISIONS.md`.
