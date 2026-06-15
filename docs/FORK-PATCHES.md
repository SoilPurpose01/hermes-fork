# IKARUS fork patches

This fork (`SoilPurpose01/hermes-fork`) is vendored into IKARUS as the `hermes-core`
submodule and driven through the AIKernel port (ADR-007). Patches carried on top of
upstream (`NousResearch/hermes-agent`) are tracked here so they stay **additive, isolated,
documented, and upstream-able**, and survive rebases on upstream.

**Hygiene rules**
- Every patch defaults to a no-op (a new optional param defaulting to `None`), so an unused
  patch is byte-identical to upstream — no existing test changes, no API break.
- IKARUS governance/policy logic lives in the IKARUS adapter, **never** in the fork. The fork
  only exposes a minimal hook.
- Each patch ships a fork-side test that travels with it (mergeability proof + rebase guard).
- Each fork edit is marked in-code with the comment `IKARUS additive patch #N`.

| # | Title | Files | Hook | Test |
|---|-------|-------|------|------|
| 1 | Pre-tool approval seam | `run_agent.py`, `agent/agent_init.py`, `agent/tool_executor.py` | optional `tool_approval_callback(name, tool_call_id, args) -> 'allow'\|'deny'` consulted before each tool dispatch; a `'deny'` reuses the existing block path (synthetic tool_result error) | `tests/run_agent/test_tool_approval_callback.py` |

## Patch #1 — Pre-tool approval seam (ADR-012 addendum, IKR-415f)

Lets an embedder gate each tool call before it runs, so IKARUS can surface an in-run
edit/command approval through its governed validation queue (ADR-011) without modifying the
engine's decision logic.

- `run_agent.py` — `AIAgent.__init__` accepts `tool_approval_callback` and forwards it to
  `init_agent`.
- `agent/agent_init.py` — `init_agent` accepts the param and stores it as
  `agent.tool_approval_callback` (next to the other callbacks).
- `agent/tool_executor.py` — `_approval_block_message(agent, name, id, args)` consults the
  callback; both the sequential and concurrent executors call it right after the existing
  block/guardrail computation, and a denial sets the same block message the plugin/guardrail
  path already uses. The callback MAY block (the embedder waits there for a human/policy
  decision — that blocking is the pause). Fail-open: no callback or any callback error leaves
  behaviour identical to upstream, so a buggy embedder can never crash a Hermès run.
