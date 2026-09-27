<!-- ai-generated: 70% - drafted by AI by comparing the receipted specification with the implementation; reviewed by the student -->
# Convergence report

This report compares the behavior in `spec.md` with `src/svcdesk/main.py` and the Docker configuration. The course requirements referenced by the specification include R-01, R-14, and R-25; this comparison uses the approved specification as the detailed behavioral source rather than adding new requirements.

The HTTP layer provides JSON health, create, list, retrieve, SLA, and action endpoints. Ticket input is validated, client-owned server fields are ignored, priorities are calculated from impact and urgency, and VIP adjustment follows C3. The persisted ticket state follows the specified forward path; resolved tickets can be reopened through the seven-day boundary, while closed tickets remain immutable. SQLite stores records under `/data` on the Compose named volume.

SLA deadlines are calculated once at creation and retained across reopening. P1 uses continuous UTC elapsed time under C1; P2–P4 count weekday business windows in `Europe/Warsaw`, including the closing-time tie behavior. Per-request test clocks do not impose monotonic ordering. The published Tier A run passed local checks for Compose startup, API conformance, decision structure, and C1/C2/C3 consistency. The checker skips L1-CORE-5 locally because receipt ancestry is verified by the course grader; that chronology must still be preserved in Git when the implementation is submitted.
