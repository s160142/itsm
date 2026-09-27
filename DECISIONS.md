---
svcdesk_decisions:
  C1: wallclock      # wallclock | business
  C2: immutable      # reopen | immutable
  C3: vip            # matrix | vip
---
<!-- ai-generated: 40% - decision narratives drafted by AI from the specification's C1-C3 choices; reviewed and corrected by the student -->

# Decisions



## C1 - SLA clock for P1

**Decision:** Both P1 acknowledgement and resolution deadlines use continuous wall-clock time, including nights, weekends, and public holidays.

**Rejected alternative:** Use the Warsaw business-time clock (weekdays 08:00–16:00) for P1 deadlines, pausing it outside that window.

**Reason:** P1 represents the most urgent incidents, so its elapsed-time targets should remain predictable and should not pause overnight or over weekends.

**Service owner:** The incident-management service owner should approve this because it sets the response commitment for the highest-severity incidents.

**Customer outcome:** Reporters and responders can rely on P1 deadlines continuing at all times, while lower priorities retain business-hours calculations.

## C2 - Closed tickets and reopening

**Decision:** A resolved ticket may be reopened as in progress no later than seven days after its recorded `resolved_at`; a closed ticket cannot be reopened.

**Rejected alternative:** Permit reopening closed tickets within the seven-day period instead of treating closure as final.

**Reason:** Keeping closed records immutable preserves the audit trail; continued work on a closed issue can be tracked in a new ticket linked with `related_to`.

**Service owner:** The service owner responsible for ticket lifecycle and audit policy should approve this because it defines whether closure is final.

**Customer outcome:** Agents retain a short correction window for resolved work; for a closed case, they create a related ticket while keeping the original audit record intact.

## C3 - VIP reporters and the priority matrix

**Decision:** Apply the impact/urgency matrix first, then raise VIP tickets from P3 or P4 to P2; leave P1 and P2 unchanged.

**Rejected alternative:** Apply the matrix without any priority adjustment for tickets reported by VIP users.

**Reason:** The matrix continues to represent impact and urgency, while the limited adjustment for VIP reporters honours their support tier without changing P1 or P2 classifications.

**Service owner:** The service owner accountable for support policy and service tiers should approve this because it balances priority rules with VIP commitments.

**Customer outcome:** VIP reporters whose tickets would otherwise be P3 or P4 receive P2 priority; more urgent P1 and P2 tickets keep their existing priority.
