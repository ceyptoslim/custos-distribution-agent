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

## The contract is now executable

The rules above are enforced by `custos_distribution_agent/adapters/`, not by this
document. `declarations.json` holds one entry per platform and, inside it, one
entry per action, because an unlisted upload and a public reply come from the same
adapter and are not the same kind of act. Each action declares its effect class,
its reversibility, and whether it is **enabled**; each platform declares its scopes,
its daily quota ceiling and whether human approval is required.

`AdapterRegistry.load()` validates the file and refuses it when it contradicts
itself:

- an irreversible action cannot be enabled unless a reversible action on the same
  platform is enabled too, so nothing permanent runs before something revocable has
  actually run;
- an irreversible action requires human approval and a declared daily quota;
- a platform that claims an executor must name it, and must declare at least one
  minimal scope, a quota, and a test suite;
- a platform with status `declared` must not name an adapter or claim scopes it has
  not been granted, so writing a platform down cannot make it look ready;
- file order must match the risk ranking the registry computes itself.

The generated policy is a deny-by-default allowlist built only from enabled
actions, and it cites the sha256 of the declarations it came from, so a policy in
force can be traced to the file that produced it.

Nothing here can grant permission. `check_declared()` can only refuse: an action
that is not declared and enabled is denied before a gate decision is spent, and an
action that passes still needs a live CUSTOS ALLOW and an explicit human `y`.

## Status (honest)

`youtube` is the only platform with an executor, and it is still a stub: it refuses
to act without owner OAuth credentials. Of its five declared actions, three are
enabled (unlisted upload, metadata update, playlist add) and two are declared but
disabled (public reply, comment moderation) because they are irreversible. The
remaining platforms — newsletter, x, tiktok, instagram — are declared with no
adapter, no scope and nothing enabled, and they appear in activation order from
cheapest-to-undo outward.

Adding a platform is still a deliberate owner decision; the change is that it is
now a reviewed diff to `declarations.json` rather than a new agent that grows its
own policy.
