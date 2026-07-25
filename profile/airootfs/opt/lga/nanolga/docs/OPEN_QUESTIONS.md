# Open design questions

These are intentionally not hidden behind defaults.

1. **UIMP authority:** freeze the canonical repository/wheel, release hash,
   schemas and compatibility policy.
2. **Specialized protocols:** freeze CSP/ASP/DSP expansions and their schemas.
3. **Memory authority:** define whether CCA may submit a bounded candidate to
   DeepBrain or must only return a verdict. It never writes LUSC or talks to an
   AGP directly.
4. **Evidence threshold:** the current three-confirmation threshold is a
   conservative laboratory value, not a validated universal rule.
5. **LTCA/LUSC deployment:** freeze the physical deployment boundary while
   preserving MMA as the only logical LUSC ingress/egress.
6. **V1 client identity:** define authentication, project identity, session
   binding and UIMP request/response transport for WorkSpace CLI.
7. **Load shedding:** define exact priority and lifecycle for delayed S2/S3
   tasks.
8. **Replanning:** decide the maximum CCA → DeepBrain revision count and token
   budget for a future modular release.
9. **Helper DeepBrain:** define activation, leases, task ownership,
   idempotency, bounded staleness and failover before parallel execution.
10. **Evaluation:** freeze a benchmark comparing NanoLGA against a monolithic
    baseline on success, unsupported claims, tokens, latency and interventions.
11. **RBAC:** define operators, roles, approval scopes, expiry and audit policy.
12. **Idle-Learning:** define which pattern extraction can happen automatically
    and which promotion always requires external evidence.
