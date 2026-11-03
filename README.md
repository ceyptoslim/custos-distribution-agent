# CUSTOS-Governed Social Distribution Agent

A governed distribution agent for social media platforms. Every action the agent
drafts must pass three gates before it touches any platform:

```
draft action -> CUSTOS policy gate (fail-closed) -> HUMAN approval -> execute -> hash-chained audit
```

**Status: pre-alpha scaffold.** The governed pattern is implemented and tested
(policy gate, approval flow, audit chain). Platform execution is intentionally
BLOCKED until owner OAuth credentials are connected — the executor refuses to
act without credentials, and the gate refuses to proceed without a live CUSTOS
decision. No action is ever taken autonomously.

## Platforms

The core (gate, approver, audit, pipeline) is platform-agnostic. Each platform
integrates as an executor adapter implementing the same contract (see
[ADAPTERS.md](ADAPTERS.md)):

| Platform | Adapter status |
| --- | --- |
| YouTube | Scaffolded — executor stubbed, execution blocked pending owner OAuth |
| TikTok | Roadmap — not built |
| Instagram | Roadmap — not built |
| X | Roadmap — not built |
| Facebook | Roadmap — not built |
| LinkedIn | Roadmap — not built |

Adapter status must never be overstated: **no platform adapter executes anything
today.**

## Governance rules

1. **Fail-closed gate** — if CUSTOS is unreachable or returns anything but an
   explicit ALLOW, the action is denied and audited. No silent fallback.
2. **Human approval** — an ALLOW from CUSTOS still requires explicit `y`
   confirmation from the channel owner before execution.
3. **Hash-chained audit** — every event (drafted, allowed, denied, approved,
   rejected, blocked, executed) is appended to a tamper-evident chain
   (`audit_log.jsonl`), mirroring the CUSTOS-CORE audit design.

## What this proves, and what it does not

The gate decides; this process performs the effect. That is a **governed**
agent, not an enforced one, and the distinction belongs at the top rather than
in a footnote: nothing here prevents an action that skips the gate, because the
code that would skip it is the code doing the acting.

What it does establish: every action that *does* pass through the pipeline
carries the `trace_id` and `audit_record_hash` of the CUSTOS decision that
allowed it, written next to the local log line. So the local chain is not a
standalone claim about what happened; each entry points at a record CUSTOS holds
in its own hash-chained store, and a reader can follow one action from one ledger
into the other. Evidence worth having if the local log is ever questioned, which
is why the join matters more than the local hash chain alone.

Enforcement in the strong sense requires the call itself to be forwarded by the
gate (the `/v1/execute` assembly in CUSTOS Enterprise), so that no execution
path exists which skips it. Until this agent runs through that, treat its
records as joined evidence, not as proof of mediation.

## Client contract

`CUSTOSGate` sends `X-CUSTOS-Version` on every request and takes the value from
`CUSTOS_API_VERSION`, defaulting to the release it was written against. It is
deliberately not hardcoded in the call site: a stale version in a client makes
server-side logs lie about which contract produced a request.

## Setup

```bash
python -m pytest tests/          # run the test suite (stdlib + pytest only)
export CUSTOS_URL=http://localhost:8000   # your CUSTOS-CORE /v1/evaluate
export CUSTOS_JWT=<tenant-jwt>            # tenant token
```

Execution requires per-platform OAuth credentials (e.g. YouTube scopes:
`youtube.readonly`, `youtube.force-ssl`, `yt-analytics.readonly`) — connect them
in the executor once authorized.

## License

AGPL-3.0 (uniform with CUSTOS-CORE).
