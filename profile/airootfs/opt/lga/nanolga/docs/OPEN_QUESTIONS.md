# Open design questions

These are intentionally not hidden behind defaults.

1. **CCA name:** Cognitive Choice Agent or Cognitive Choice Assistant?
2. **Core terminology:** keep `LGABrain` as the executive implementation inside
   `LGA Core`, or use one canonical name everywhere?
3. **Memory authority:** v0.1 uses Core curation plus MMA validation/persistence.
   Should a delegated CCA ever be allowed to submit semantic candidates directly?
4. **Evidence threshold:** the current three-confirmation threshold is a
   conservative test value, not a validated universal rule.
5. **Load shedding:** define exact priority and lifecycle for delayed S2/S3 tasks.
6. **Replanning:** decide the maximum CCA → Core revision count and token budget.
7. **Core-2:** define leader/helper activation, leases, task ownership,
   idempotency, bounded staleness and failover before parallel execution.
8. **Evaluation:** freeze a benchmark comparing NanoLGA against a monolithic
   baseline on success, unsupported claims, tokens, latency and interventions.
9. **RBAC:** define operators, roles, approval scopes, expiry and audit policy.
10. **Idle-Learning:** define which pattern extraction can happen automatically
    and which promotion always requires external evidence.
