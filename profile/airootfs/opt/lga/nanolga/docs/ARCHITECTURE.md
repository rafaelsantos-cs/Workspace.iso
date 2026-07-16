# NanoLGA v0.1 architecture

## Authority boundaries

| Module | May do | Must not do |
| --- | --- | --- |
| LGA Core / LGABrain | interpret objectives, budget, plan, delegate, synthesize, curate semantic-memory proposals | bypass Safety Supervisor or consume raw sensors directly |
| AGP | execute one scoped specialist task and return a structured report | read/write MMA, broaden its own permission scope or authorize execution |
| CCA | deliberate when invoked and return a bounded verdict | run continuously, grant missing permission or replace deterministic safety |
| MMA | validate, persist, retrieve, classify and version memory | silently turn one model statement into an active rule |
| Safety Supervisor | deterministically allow, block or demand approval | accept a model instruction to weaken S0/S1 policy |
| Runtime | enforce states, budgets, timeouts, sequencing and audit events | reinterpret semantic results as if it were the Core |

The Runtime may append immutable telemetry. Only the Core writer role may create
semantic-memory records. This resolves the distinction between raw logging and
curated knowledge.

## Task lifecycle

1. Runtime receives a `TaskRequest`, assigns identity and enters Pre-Awake.
2. MMA retrieves a bounded active-memory context from the objective.
3. Core creates a budgeted plan using only registered AGPs.
4. Runtime activates CCA only when the plan is ambiguous, risky or explicitly
   recommends deliberation.
5. Safety Supervisor evaluates each proposed action independently.
6. The selected AGP receives only its action plus bounded task metadata.
7. AGP returns `AGPReport`; it cannot write memory or execute another AGP.
8. Core synthesizes from reports and proposes at most three candidate memories.
9. MMA persists candidates with provenance and confirmation counters.
10. Task Finalization logs the outcome; Idle-Learning reports pending deltas;
    Runtime returns to Deep Standby.

## Safety behavior

- S0/S1 with a missing critical heartbeat fail closed.
- immutable bypass capabilities remain blocked even if the Core includes them in
  the task permission set;
- high/critical risk requires the external `human.approved` capability;
- an AGP recommendation is data, never automatic authorization;
- NanoLGA v0.1 contains no physical execution AGP.

## Data contracts

Core → AGP carries a bounded `ActionProposal`: specialist name, instruction,
expected output, parameters, risk, safety class, required permissions, estimated
cost and rationale.

AGP → Core returns an `AGPReport`: status, output, evidence, risk, constraints,
recommended next actions, measured/estimated cost and error.

Core ↔ CCA carries the complete plan and receives a verdict, confidence,
short reasoning summary and human-approval requirement. Hidden chain-of-thought
is neither requested nor stored.

MMA → Core returns only active memories inside an item and character budget,
including provenance, confidence and status.

## Scale boundary

v0.1 is intentionally single-Core and sequential. A secondary Core must not be
added until the system has task ownership, leases, idempotency keys, resource
locks, bounded staleness and recovery tests. Logical single-writer semantics can
later be backed by replicated infrastructure without giving two Cores authority
over the same action.
