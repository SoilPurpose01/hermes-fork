"""Pre-tool approval seam — IKARUS additive patch #1 (ADR-012 addendum).

Pins the additive ``tool_approval_callback`` hook so it survives rebases on upstream:
an embedder may register ``agent.tool_approval_callback(name, tool_call_id, args) ->
'allow' | 'deny'`` and a denial routes through the EXISTING block path (synthetic
tool_result error, tool not dispatched). Default (no callback) is byte-identical to
upstream, and a buggy callback fails open (the tool still runs) so it can never crash
a Hermès run.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from run_agent import AIAgent


def _make_tool_defs(*names):
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in names
    ]


def _mock_tool_call(name="write_file", arguments="{}", call_id=None):
    return SimpleNamespace(
        id=call_id or f"call_{uuid.uuid4().hex[:8]}",
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _make_agent(*tool_names):
    with (
        patch("run_agent.get_tool_definitions", return_value=_make_tool_defs(*tool_names)),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("hermes_cli.config.load_config", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        agent = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            max_iterations=10,
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
    agent.client = MagicMock()
    agent._cached_system_prompt = "You are helpful."
    agent._use_prompt_caching = False
    agent.tool_delay = 0
    agent.compression_enabled = False
    agent.save_trajectories = False
    return agent


def _run_one_tool(agent, call_id):
    tc = _mock_tool_call("write_file", json.dumps({"path": "f.py", "content": "x"}), call_id)
    msg = SimpleNamespace(content="", tool_calls=[tc])
    messages = []
    with patch("run_agent.handle_function_call", return_value=json.dumps({"ok": True})) as mock_hfc:
        agent._execute_tool_calls_sequential(msg, messages, "task-1")
    return mock_hfc, messages


def test_allow_executes_the_tool():
    agent = _make_agent("write_file")
    agent.tool_approval_callback = lambda name, tcid, args: "allow"
    mock_hfc, messages = _run_one_tool(agent, "c-allow")
    mock_hfc.assert_called_once()
    assert messages[0]["tool_call_id"] == "c-allow"


def test_deny_blocks_the_tool_with_a_synthetic_error():
    agent = _make_agent("write_file")
    agent.tool_approval_callback = lambda name, tcid, args: "deny"
    mock_hfc, messages = _run_one_tool(agent, "c-deny")
    mock_hfc.assert_not_called()
    assert messages[0]["role"] == "tool"
    assert messages[0]["tool_call_id"] == "c-deny"
    assert "denied" in messages[0]["content"].lower()


def test_no_callback_is_identical_to_upstream():
    agent = _make_agent("write_file")
    # No tool_approval_callback set → default None.
    mock_hfc, _ = _run_one_tool(agent, "c-none")
    mock_hfc.assert_called_once()


def test_callback_error_fails_open():
    agent = _make_agent("write_file")

    def _boom(name, tcid, args):
        raise RuntimeError("approval backend down")

    agent.tool_approval_callback = _boom
    mock_hfc, _ = _run_one_tool(agent, "c-boom")
    mock_hfc.assert_called_once()  # a buggy callback never blocks a run


def test_callback_receives_name_id_and_args():
    agent = _make_agent("write_file")
    seen = {}

    def _record(name, tcid, args):
        seen["name"], seen["id"], seen["args"] = name, tcid, args
        return "allow"

    agent.tool_approval_callback = _record
    _run_one_tool(agent, "c-args")
    assert seen["name"] == "write_file"
    assert seen["id"] == "c-args"
    assert seen["args"]["path"] == "f.py"
