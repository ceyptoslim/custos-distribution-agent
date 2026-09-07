# Platform Adapter Contract

Every platform adapter implements the same governed flow. The gate, approver,
and audit chain are shared; only the executor is platform-specific.

## The contract

```
DraftAction(platform, action_type, payload)
  -> CUSTOS policy gate     (fail-closed; anything but explicit ALLOW = deny + audit)
  -> human approval         (explicit `y` from the owner; anything else = reject + audit)
  -> Executor.execute()     (refuses without platform credentials; calls the platform API)
  -> audit append           (hash-chained event)
```

## Requirements for every adapter

1. **Minimal OAuth scopes** — request the narrowest scope set for the supported
   actions; never blanket scopes.
2. **No autonomous execution** — no adapter runs without BOTH a live CUSTOS
   ALLOW and an explicit human `y`.
3. **Fail-closed on missing credentials** — no credentials = blocked + audited,
   never a silent skip.
4. **Action allowlist** — each adapter declares the actions it supports (e.g.
   `post_video`, `update_description`); anything else is denied.
5. **Full audit coverage** — drafted, allowed, denied, approved, rejected,
   blocked, executed all append to the hash-chained audit log.
6. **Tests first** — an adapter lands only with a test suite mirroring
   `tests/test_governance.py`, proving the fail-closed behavior.

## Status (honest)

No adapter beyond the YouTube executor stub exists today. This document defines
the contract future adapters implement. Each platform's official API, scopes,
and credential configuration get documented when its adapter is actually built.
Adding an adapter is a deliberate owner decision — the trigger is a real,
consistent manual workflow first, automation second.
