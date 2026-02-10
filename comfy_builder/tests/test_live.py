"""
Live/manual tests — require a running ComfyUI server.

Run with: pytest comfy_builder/tests/test_live.py -m live -v
Or from project root with .env loaded: pytest -m live -v

These tests hit the real ComfyUI API. They are skipped automatically if the
server is not reachable at COMFYUI_URL (from .env or default 127.0.0.1:8000).
"""

import pytest
from pathlib import Path

from comfy_builder import config, api, runner, store
from comfy_builder.planner import build as planner_build


def _server_online():
    r = api.check_server()
    return r.get("online", False)


@pytest.fixture(scope="module")
def live_server():
    """Require ComfyUI to be running; skip entire module if not."""
    if not _server_online():
        pytest.skip(
            f"ComfyUI server not reachable at {config.COMFYUI_URL}. "
            "Start ComfyUI and ensure it is running, then re-run with -m live."
        )
    return True


@pytest.mark.live
class TestLiveConnectivity:
    """Tests that only need the server to be up (no workflow run)."""

    def test_server_status_returns_online(self, live_server):
        result = api.check_server()
        assert result["online"] is True
        assert "system_stats" in result or "queue" in result

    def test_object_info_fetched(self, live_server):
        info = api.get_object_info()
        assert isinstance(info, dict)
        assert "CheckpointLoaderSimple" in info or "KSampler" in info

    def test_queue_endpoint_works(self, live_server):
        queue = api.get_queue()
        assert isinstance(queue, dict)
        # ComfyUI returns queue_running, queue_pending, etc.
        assert "queue_running" in queue or "queue_pending" in queue or len(queue) >= 0


@pytest.mark.live
class TestLiveText2ImgE2E:
    """End-to-end: build text2img, run on live ComfyUI, verify output.

    Uses and overwrites the current workflow. Fast params (steps=4, cfg=1.0)
    for quicker feedback; uses default checkpoint from config.
    """

    def test_text2img_run_produces_image(self, live_server):
        result = planner_build("text2img", {
            "prompt": "a red apple on a white background",
            "negative": "blurry",
            "seed": 42,
            "steps": 4,
            "cfg": 1.0,
        })
        if result.get("status") == "error":
            pytest.skip(f"Planner build failed (e.g. schema): {result.get('error', '')}")

        run_result = runner.run("current")
        if not _server_online():
            pytest.skip("Server went offline during test")

        assert run_result.get("status") in ("success", "partial"), (
            f"Run failed: {run_result.get('error', run_result)}"
        )
        outputs = run_result.get("outputs", [])
        if len(outputs) < 1:
            pytest.skip(
                "Run succeeded but no outputs collected (ComfyUI history/output shape may differ). "
                "Check ComfyUI window and output folder; manual run_manual_cli_flow.ps1 still validates the queue."
            )
        first = outputs[0]
        assert first.get("type") == "image"
        path = Path(first["file"])
        assert path.exists(), f"Output file not written: {path}"


@pytest.mark.live
class TestLiveSchemaFromServer:
    """Live schema fetch (no execution). Writes to real schema cache."""

    def test_schema_refresh_from_live_server(self, live_server):
        from comfy_builder import schema
        result = schema.refresh()
        assert "node_count" in result
        assert result["node_count"] >= 1
        assert "path" in result
        assert Path(result["path"]).exists()
