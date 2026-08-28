# R6E1R-FINAL Open Issues

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Current status: **R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED**

This is not `R6E1R_ANALYTICS_VERIFIED_DEPLOYMENT_BLOCKED`. The mandatory
six-session all-nine-schedule run did not reach a terminal acceptance summary,
so final analytics, deployment, and the verification tag remain unverified.

## Terminal blocking condition

- Persistent full-six v9 was runtime-masked at **20:39:00.999 IST**. Its
  journal records SIGINT at **20:39:01** and SIGTERM at **20:39:06**, both on
  client request.
- The process had consumed **2h15m44.789 CPU**, reached a **14.5G** cgroup
  peak, used **0 swap**, and produced no OOM event. This was not an analytical
  assertion failure or a resource-limit termination.
- The one-record-per-increment schedule was interrupted at approximately
  **96,650 / 543,329** selected records. It published no marker-last atomic
  schedule bundle.
- Root `pts/1` logged in at **20:37:18 IST** from `169.254.0.1`. Exact
  attribution for the later control and deletion actions is unavailable; the
  login chronology is not proof of actor identity.
- An operator then deleted:
  - `/home/codexuser/mp-history-v9`
  - `/home/codexuser/mp-history-v9-control`
  - `/opt/banknifty/research/vpoc_oi_price_response_v2/historical_callback_acceptance_v9`
- An exhaustive read-only search found zero surviving
  `equivalence_summary`, `schedule_resume_contract`, or `schedule_bundle`
  artifacts. No v9 partial output is eligible for promotion or resume.
- This repeats the external stop/deletion condition across v2-v8. Further
  automatic relaunches would not make safe progress and must not attempt to
  evade root controls.

## Verified work that remains valid

- Current analytical repair commit:
  `e1d67c534bea5c61b0e3d379db7f599de7e1c445`.
- Complete post-repair regression: **660/660 passed**, zero failures and zero
  skips.
- Fresh post-repair focused August 19 all-nine result: 21/21 canonical
  components, 8/8 analytical ledgers, 9/9 causality groups, 9/9 schedules,
  72/72 checkpoint rows, 2/2 recovery probes, and 8/8 source hashes passed;
  summary SHA-256
  `f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
- Before deletion, v9 had immutably sealed fresh canonical A and independent
  chronological B, and observed comparisons passed 21/21 components, 8/8
  ledgers, 9/9 causality groups, R6C2R 30/30, and R6D 180/180. These recorded
  intermediate observations do not replace the missing all-schedule terminal
  evidence.
- The authoritative raw root
  `/opt/banknifty-collector/data-prod-v4` remains present and readable.

## Repository and protected-host state

- Branch: `fix/r6e1r-final-live-shadow`.
- Local and remote head before these scratchpad edits:
  `92673323d3523b3338a39743063299d491ff4d08`.
- Verified tag `r6e1r-live-shadow-verified`: **not created**.
- Port 8803 PID/start identity: `380743 / 46015771`, unchanged.
- Port 8804 PID/start identity: `465394 / 51980337`, unchanged.
- Collector PID/start identity: `1430352 / 81242549`, unchanged.
- Collector script SHA-256:
  `0dbd270ba3a1fedc63f4ed8c8eff1947a7c14d08e412b3f82a890cb5500a4a4a`,
  unchanged.
- Ports 8805 and 18805 are unbound. No deployment is active and no deployed
  URL is verified.

## Required recovery

1. Obtain an explicit uninterrupted, root-agreed execution window that covers
   the full mandatory run and evidence retention. Do not evade root service or
   filesystem controls.
2. Rebuild from authoritative raw bytes in fresh roots and rerun the actual
   R6E checkpoint/callback path through all nine schedules. Require a terminal
   summary plus marker-last schedule bundles and every mandated zero gate.
3. Only after terminal full-six acceptance, perform preload validation,
   isolated deployment, replay/browser/API/health/restart tests, final
   regression and security scans, report refresh, push, and remote closeout.
4. Create `r6e1r-live-shadow-verified` only if every analytical and deployment
   gate, including independent public reachability, passes.

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**
