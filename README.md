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
