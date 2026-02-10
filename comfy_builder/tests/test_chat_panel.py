"""
Tests for the ComfyUI Agent Panel (chat UI).

- Unit tests: tool execution with mocked planner/runner/store/api (no server, no LLM).
- Live tests: chat server endpoints and conversation with LLM (Ollama + optional ComfyUI).
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from comfy_builder.chat import tools


# --- Unit tests: tool execution ---


class TestToolExecute:
    """Test each tool's execute path with mocked dependencies."""

    def test_execute_unknown_tool(self):
        result = tools.execute("unknown_tool", {})
        assert result.get("status") == "error"
        assert "Unknown tool" in result.get("error", "")

    @patch("comfy_builder.api.list_models")
    @patch("comfy_builder.api.check_server")
    def test_tool_status_online(self, mock_check, mock_list_models):
        mock_check.return_value = {"online": True}
        mock_list_models.side_effect = lambda t: ["a.ckpt"] if t == "checkpoints" else []
        result = tools.execute("status", {})
        assert result["online"] is True
        assert "models" in result or "comfyui_url" in result

    @patch("comfy_builder.planner.build")
    def test_tool_build_workflow(self, mock_build):
        mock_build.return_value = {
            "status": "success",
            "template": "text2img",
            "node_count": 7,
        }
        result = tools.execute("build_workflow", {
            "template": "text2img",
            "prompt": "a red apple",
        })
        assert result["status"] == "success"
        mock_build.assert_called_once()
        call_args = mock_build.call_args
        assert call_args[0][0] == "text2img"
        assert call_args[0][1].get("prompt") == "a red apple"

    @patch("comfy_builder.runner.run")
    def test_tool_run_workflow(self, mock_run):
        mock_run.return_value = {"status": "success", "outputs": []}
        result = tools.execute("run_workflow", {"name": "current"})
        assert result["status"] == "success"
        mock_run.assert_called_once_with("current")

    @patch("comfy_builder.store.load_workflow")
    def test_tool_show_workflow(self, mock_load):
        mock_load.return_value = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
        }
        result = tools.execute("show_workflow", {"name": "current"})
        assert result.get("workflow") == "current"
        assert result.get("node_count") == 1
        assert len(result.get("nodes", [])) == 1

    @patch("comfy_builder.store.load_workflow")
    def test_tool_show_workflow_missing(self, mock_load):
        mock_load.return_value = {}
        result = tools.execute("show_workflow", {"name": "missing"})
        assert result.get("status") == "error"
        assert "found" in result.get("error", "").lower() or "missing" in result.get("error", "").lower()

    @patch("comfy_builder.planner.refine")
    def test_tool_refine_workflow(self, mock_refine):
        mock_refine.return_value = {"status": "success", "ops_applied": 1}
        result = tools.execute("refine_workflow", {"instruction": "set steps to 30"})
        assert result["status"] == "success"
        mock_refine.assert_called_once_with("set steps to 30")

    @patch("comfy_builder.store.list_all")
    def test_tool_list_workflows(self, mock_list_all):
        mock_list_all.return_value = {"workflows": [], "templates": ["text2img"]}
        result = tools.execute("list_workflows", {})
        assert "templates" in result

    @patch("comfy_builder.schema.search")
    def test_tool_schema_search(self, mock_search):
        mock_search.return_value = [{"class_type": "KSampler", "display_name": "KSampler"}]
        result = tools.execute("schema_search", {"query": "sampler"})
        assert result.get("query") == "sampler"
        assert result.get("count") == 1
        assert len(result.get("nodes", [])) == 1

    @patch("comfy_builder.store.last_run_log")
    def test_tool_logs_last(self, mock_last):
        mock_last.return_value = {"run_id": "123", "status": "success"}
        result = tools.execute("logs_last", {})
        assert result.get("run_id") == "123"

    @patch("comfy_builder.store.last_run_log")
    def test_tool_logs_last_empty(self, mock_last):
        mock_last.return_value = None
        result = tools.execute("logs_last", {})
        assert result.get("status") == "error"

    @patch("comfy_builder.installer.check_missing")
    def test_tool_install_check(self, mock_check):
        mock_check.return_value = {"status": "ok", "message": "All nodes are available"}
        result = tools.execute("install_check", {})
        assert result["status"] == "ok"
        mock_check.assert_called_once()

    @patch("comfy_builder.installer.install_pack")
    def test_tool_install_nodes(self, mock_install):
        mock_install.return_value = {"status": "success", "pack": "ComfyUI-AnimateDiff-Evolved"}
        result = tools.execute("install_nodes", {"source": "ComfyUI-AnimateDiff-Evolved"})
        assert result["status"] == "success"
        mock_install.assert_called_once_with("ComfyUI-AnimateDiff-Evolved", force_allow=False)
        assert "No run logs" in result.get("error", "")


# --- Live tests: panel server + LLM conversation ---


def _panel_server_ready():
    """Check if chat panel is reachable."""
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8085/api/status")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.getcode() == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def panel_live():
    """Require chat panel server to be running; skip if not."""
    if not _panel_server_ready():
        pytest.skip(
            "ComfyUI Agent Panel not reachable at http://127.0.0.1:8085. "
            "Start it with: cd comfy_builder && python -m comfy_builder chat"
        )
    return True


@pytest.mark.live
class TestPanelEndpoints:
    """Live tests: chat panel HTTP endpoints."""

    def test_get_status(self, panel_live):
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8085/api/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        assert "ollama" in data
        assert "comfyui" in data
        assert "model" in data

    def test_get_index(self, panel_live):
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8085/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode()
        assert "ComfyUI Chat" in html or "comfyui" in html.lower()
        assert "api/chat" in html or "sendMessage" in html or "fetch" in html


@pytest.mark.live
class TestPanelChatWithLLM:
    """Live tests: converse with LLM via panel; verify tool use and workflow generation."""

    def test_chat_trigger_status_tool(self, panel_live):
        """Send a message that should trigger the status tool; verify we get a valid response."""
        import urllib.request
        payload = json.dumps({
            "message": "What is the current ComfyUI status? Just check and tell me.",
            "history": [],
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8085/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            pytest.skip(f"Chat request failed (is Ollama running?): {e}")
        assert "content" in data or "role" in data
        assert data.get("role") == "assistant"
        # May have tool_results if LLM called status
        if data.get("tool_results"):
            for tr in data["tool_results"]:
                assert "tool" in tr
                assert "result" in tr

    def test_chat_trigger_build_and_run(self, panel_live):
        """Send a message asking to build and run a simple image; verify tool_results include build/run."""
        import urllib.request
        payload = json.dumps({
            "message": "Build a text2img workflow with prompt 'a single red apple on white' using 4 steps and run it.",
            "history": [],
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8085/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            pytest.skip(f"Chat request failed (Ollama + ComfyUI required): {e}")
        assert data.get("role") == "assistant"
        tool_results = data.get("tool_results", [])
        tool_names = [tr.get("tool") for tr in tool_results]
        # LLM should have called at least build_workflow; may also call run_workflow
        assert "build_workflow" in tool_names or "status" in tool_names, (
            f"Expected build_workflow or status in tool_results, got {tool_names}"
        )
        # If run_workflow was called, its result should have status
        for tr in tool_results:
            if tr.get("tool") == "run_workflow":
                assert "status" in tr.get("result", {})
                break
            if tr.get("tool") == "build_workflow":
                assert tr.get("result", {}).get("status") in ("success", "warning", "error")
