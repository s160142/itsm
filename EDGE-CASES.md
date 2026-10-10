---
lab2_edge_cases:
  E1: {rule: R-08, count: 3}
  E2: {rule: R-06, count: 2}
  E3: {rule: R-09, count: 4}
  E4: {rule: R-10, count: 4}
  E5: {rule: R-12, count: 1}
  E6: {rule: R-13, count: 11}
---
<!-- ai-generated: 70% - drafted by AI from METRIC-SPEC.md and the practice fixture; reviewed -->

# Edge cases in the practice event log

## E1 - clock skew produces a negative lead time

- What the log contains: Three commit timestamps occur after the successful production deployments that carried those commits, so the raw lead-time subtraction is negative.
- What a default definition would have done: Dropping those pairs hides shipped work, while retaining negative durations can pull the median below zero and make delivery look faster than it was.
- Why the rule is defensible: Clamping each anomalous pair to zero keeps the delivered changes represented without claiming negative elapsed time; the anomaly count makes clock skew visible for investigation.

## E2 - a revert of a revert

- What the log contains: Two commits have a non-null `reverts`; one of those reversions itself reverts a prior revert, so resolution must follow the chain back to its original change.
- What a default definition would have done: Treating every commit as a separate change would count the revert chain as extra delivery and distort both the change count and the ground-truth lead-time calculation.
- Why the rule is defensible: A revert changes the state of an existing change rather than introducing independent work, so resolving the chain transitively preserves the original change identity.

## E3 - a hotfix that never touched `main`

- What the log contains: Four distinct commits on branches other than `main` are carried by production deployments in the observation window.
- What a default definition would have done: Filtering to `main` would omit production work that users actually received, understating the commits and their delivery lead times.
- Why the rule is defensible: Production deployment is the evidence that work reached users; branch names describe workflow, not whether a change was delivered.

## E4 - a deployment with zero linked commits

- What the log contains: Four in-window production deployments have an empty `commits` list; they still have deployment events and outcomes.
- What a default definition would have done: Dropping them as empty would lower deployment frequency and remove real deployments from the denominators of the instability rates.
- Why the rule is defensible: A release can occur without linked commits, and the deployment event still happened. It should affect deployment-level metrics but cannot create a commit-level lead-time pair.

## E5 - a deployment that failed and never recovered

- What the log contains: One failed production deployment has no covering incident with a resolution, so its recovery duration is unknown at the end of the available record.
- What a default definition would have done: Treating the observation-window end as a recovery time invents a resolution; excluding the failure entirely makes the service appear more reliable.
- Why the rule is defensible: The median recovery time should include only known recoveries, while the open failure remains visible in its count and in the change fail rate until evidence of recovery exists.

## E6 - overlapping incidents

- What the log contains: Eleven unordered pairs of distinct incident intervals overlap; these are counted independently of each deployment's recovery calculation.
- What a default definition would have done: Merging intervals or adding incident durations would turn concurrent incidents into artificial extra elapsed time and could assign the wrong recovery to a deployment.
- Why the rule is defensible: Recovery is measured per failed deployment using its earliest covering incident. Keeping incident intervals separate preserves what the log says and makes concurrency countable without summing overlapping time.

## Gaming demonstration

The selected metric is `deployment_frequency_per_day` (R-11). The demonstration adds 18 empty successful production deployment events and moves eligible base successful deployments carrying commits two days later. The service reports frequency increasing from 2.000000 to 2.619048 deployments per day, a 30.95% relative improvement. For R-21, the checker isolates the original commits but retains deployment events: the median true change lead time rises from 539452 to 705559 seconds, while changes delivered fall from 65 to 58. The original work therefore reached users later or did not reach production within the window. In a real team, a target or bonus based on deployment frequency could encourage ceremonial no-op releases and batching substantive work. The team or manager rewarded for higher frequency would benefit on paper, while users wait longer for changes. This is a constructed demonstration permitted by the exercise, not a claim that these synthetic deployments occurred in the real service.
