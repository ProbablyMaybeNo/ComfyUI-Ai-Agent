"""Tests for comfy_builder.runner module."""

import json
import copy
import pytest
from unittest.mock import patch, MagicMock, call
from comfy_builder import runner, config


@pytest.fixture
def runner_dirs(tmp_path):
    """Set up temporary dirs for runner tests."""
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    runs = tmp_path / "logs" / "runs"
    runs.mkdir(parents=True)
    out = tmp_path / "out"
    (out / "images").mkdir(parents=True)
    (out / "video").mkdir(parents=True)
    meta_file = out / "metadata.jsonl"

    current = workflows / "current.json"

    with patch.object(config, "WORKFLOWS_DIR", workflows), \
         patch.object(config, "CURRENT_WORKFLOW", current), \
         patch.object(config, "RUNS_DIR", runs), \
         patch.object(config, "OUT_DIR", out), \
         patch.object(config, "IMAGES_DIR", out / "images"), \
         patch.object(config, "VIDEO_DIR", out / "video"), \
         patch.object(config, "METADATA_FILE", meta_file):
        yield {
            "root": tmp_path,
            "workflows": workflows,
            "current": current,
            "runs": runs,
            "out": out,
        }


SAMPLE_WORKFLOW = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "test.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["1", 1]}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["1", 1]}},
    "5": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0,
          "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
          "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0]}},
    "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test", "images": ["6", 0]}},
}


class TestRunMissingWorkflow:
    def test_missing_workflow_returns_error(self, runner_dirs):
        result = runner.run("nonexistent")
        assert result["status"] == "error"
        assert "not found" in result["error"]


class TestRunServerDown:
    def test_server_down_returns_error(self, runner_dirs):
        # Save a workflow
        with open(runner_dirs["current"], "w") as f:
            json.dump(SAMPLE_WORKFLOW, f)

        with patch("comfy_builder.api.check_server", return_value={"online": False, "error": "refused"}):
            result = runner.run("current")
            assert result["status"] == "error"
            assert "not reachable" in result["error"]


class TestRunSingle:
    def test_successful_run(self, runner_dirs):
        with open(runner_dirs["current"], "w") as f:
            json.dump(SAMPLE_WORKFLOW, f)

        mock_history = {
            "abc-123": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {
                    "7": {"images": [{"filename": "test_00001_.png", "subfolder": "", "type": "output"}]}
                },
            }
        }

        with patch("comfy_builder.api.check_server", return_value={"online": True}), \
             patch("comfy_builder.api.post_prompt", return_value={"prompt_id": "abc-123"}), \
             patch("comfy_builder.api.get_history", return_value=mock_history), \
             patch("comfy_builder.api.get_image", return_value=b"\x89PNG fake image data"):
            result = runner.run("current")
            assert result["status"] == "success"
            assert len(result["outputs"]) == 1
            assert result["outputs"][0]["type"] == "image"
            assert result["prompt_id"] == "abc-123"

    def test_prompt_submission_failure(self, runner_dirs):
        with open(runner_dirs["current"], "w") as f:
            json.dump(SAMPLE_WORKFLOW, f)

        with patch("comfy_builder.api.check_server", return_value={"online": True}), \
             patch("comfy_builder.api.post_prompt", return_value={"error": "validation failed"}):
            result = runner.run("current")
            assert result["status"] == "error"

    def test_no_prompt_id_returns_error(self, runner_dirs):
        with open(runner_dirs["current"], "w") as f:
            json.dump(SAMPLE_WORKFLOW, f)

        with patch("comfy_builder.api.check_server", return_value={"online": True}), \
             patch("comfy_builder.api.post_prompt", return_value={"number": 1}):
            result = runner.run("current")
            assert result["status"] == "error"
            assert "prompt_id" in result["error"].lower()


class TestPollCompletion:
    def test_timeout(self):
        with patch("comfy_builder.api.get_history", return_value={}):
            result = runner._poll_completion("fake-id", timeout=0.1)
            assert result["status"] == "timeout"

    def test_error_status(self):
        error_history = {
            "fake-id": {
                "status": {"status_str": "error", "messages": ["node X failed"]},
            }
        }
        with patch("comfy_builder.api.get_history", return_value=error_history):
            result = runner._poll_completion("fake-id", timeout=5)
            assert result["status"] == "failed"
            assert len(result["errors"]) > 0

    def test_success_status(self):
        ok_history = {
            "fake-id": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {},
            }
        }
        with patch("comfy_builder.api.get_history", return_value=ok_history):
            result = runner._poll_completion("fake-id", timeout=5)
            assert result["status"] == "success"


class TestCollectOutputs:
    def test_collect_images(self, runner_dirs):
        history = {
            "prompt-1": {
                "outputs": {
                    "7": {"images": [
                        {"filename": "img_001.png", "subfolder": "", "type": "output"},
                        {"filename": "img_002.png", "subfolder": "", "type": "output"},
                    ]}
                }
            }
        }
        with patch("comfy_builder.api.get_history", return_value=history), \
             patch("comfy_builder.api.get_image", return_value=b"\x89PNG data"):
            outputs = runner._collect_outputs("prompt-1", "run_001")
            assert len(outputs) == 2
            assert all(o["type"] == "image" for o in outputs)

    def test_collect_videos(self, runner_dirs):
        history = {
            "prompt-1": {
                "outputs": {
                    "60": {"gifs": [
                        {"filename": "vid_001.mp4", "subfolder": ""},
                    ]}
                }
            }
        }
        with patch("comfy_builder.api.get_history", return_value=history), \
             patch("comfy_builder.api.get_image", return_value=b"\x00\x00 video data"):
            outputs = runner._collect_outputs("prompt-1", "run_001")
            assert len(outputs) == 1
            assert outputs[0]["type"] == "video"

    def test_collect_handles_download_failure(self, runner_dirs):
        history = {
            "prompt-1": {
                "outputs": {
                    "7": {"images": [
                        {"filename": "fail.png", "subfolder": "", "type": "output"},
                    ]}
                }
            }
        }
        with patch("comfy_builder.api.get_history", return_value=history), \
             patch("comfy_builder.api.get_image", side_effect=Exception("network error")):
            outputs = runner._collect_outputs("prompt-1", "run_001")
            assert len(outputs) == 0  # failed download is skipped


class TestRunBatch:
    def test_batch_runs_all_jobs(self, runner_dirs):
        with open(runner_dirs["current"], "w") as f:
            json.dump(SAMPLE_WORKFLOW, f)

        meta = {
            "batch": [
                {"scene": "beach", "index": 0, "seed": 100,
                 "prompt": "a cat at the beach", "filename_prefix": "batch_0"},
                {"scene": "forest", "index": 0, "seed": 101,
                 "prompt": "a cat in the forest", "filename_prefix": "batch_1"},
            ]
        }

        mock_history = lambda pid: {
            pid: {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {"7": {"images": [{"filename": f"{pid}.png", "subfolder": "", "type": "output"}]}}
            }
        }
        call_count = {"n": 0}

        def mock_post(wf):
            call_count["n"] += 1
            return {"prompt_id": f"p-{call_count['n']}"}

        with patch("comfy_builder.api.check_server", return_value={"online": True}), \
             patch("comfy_builder.api.post_prompt", side_effect=mock_post), \
             patch("comfy_builder.api.get_history", side_effect=lambda pid: mock_history(pid)), \
             patch("comfy_builder.api.get_image", return_value=b"\x89PNG data"), \
             patch.object(config, "WORKFLOWS_DIR", runner_dirs["workflows"]):
            # Write meta
            meta_path = runner_dirs["workflows"] / "current_meta.json"
            with open(meta_path, "w") as f:
                json.dump(meta, f)

            result = runner.run("current")
            assert result["status"] == "success"
            assert result["batch_size"] == 2
            assert len(result["outputs"]) == 2

    def test_batch_partial_failure(self, runner_dirs):
        with open(runner_dirs["current"], "w") as f:
            json.dump(SAMPLE_WORKFLOW, f)

        meta = {
            "batch": [
                {"scene": "a", "index": 0, "seed": 1, "prompt": "ok", "filename_prefix": "b_0"},
                {"scene": "b", "index": 0, "seed": 2, "prompt": "fail", "filename_prefix": "b_1"},
            ]
        }
        call_count = {"n": 0}

        def mock_post(wf):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise Exception("server error")
            return {"prompt_id": f"p-{call_count['n']}"}

        ok_history = {
            "p-1": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {"7": {"images": [{"filename": "ok.png", "subfolder": "", "type": "output"}]}}
            }
        }

        with patch("comfy_builder.api.check_server", return_value={"online": True}), \
             patch("comfy_builder.api.post_prompt", side_effect=mock_post), \
             patch("comfy_builder.api.get_history", return_value=ok_history), \
             patch("comfy_builder.api.get_image", return_value=b"\x89PNG"), \
             patch.object(config, "WORKFLOWS_DIR", runner_dirs["workflows"]):
            meta_path = runner_dirs["workflows"] / "current_meta.json"
            with open(meta_path, "w") as f:
                json.dump(meta, f)

            result = runner.run("current")
            assert result["status"] == "partial"
            assert len(result["errors"]) == 1
            assert len(result["outputs"]) == 1


class TestLoadBuildMeta:
    def test_loads_existing_meta(self, runner_dirs):
        meta = {"batch": [{"scene": "test"}]}
        meta_path = runner_dirs["workflows"] / "current_meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        with patch.object(config, "WORKFLOWS_DIR", runner_dirs["workflows"]):
            result = runner._load_build_meta()
            assert result["batch"][0]["scene"] == "test"

    def test_returns_none_when_missing(self, runner_dirs):
        with patch.object(config, "WORKFLOWS_DIR", runner_dirs["workflows"]):
            result = runner._load_build_meta()
            assert result is None
