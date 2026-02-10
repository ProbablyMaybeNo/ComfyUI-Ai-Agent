"""Tests for comfy_builder.cli module — argument parsing and command routing."""

import json
import pytest
from unittest.mock import patch, MagicMock
from comfy_builder.cli import main


class TestArgumentParsing:
    """Verify argparse parses commands correctly."""

    def test_status_command(self):
        with patch("comfy_builder.cli.cmd_status", return_value=0) as mock:
            main(["status"])
            mock.assert_called_once()

    def test_schema_refresh(self):
        with patch("comfy_builder.cli.cmd_schema_refresh", return_value=0) as mock:
            main(["schema", "refresh"])
            mock.assert_called_once()

    def test_schema_search(self):
        with patch("comfy_builder.cli.cmd_schema_search", return_value=0) as mock:
            main(["schema", "search", "KSampler"])
            args = mock.call_args[0][0]
            assert args.query == "KSampler"

    def test_schema_search_with_limit(self):
        with patch("comfy_builder.cli.cmd_schema_search", return_value=0) as mock:
            main(["schema", "search", "KSampler", "--limit", "5"])
            args = mock.call_args[0][0]
            assert args.limit == 5

    def test_build_text2img(self):
        with patch("comfy_builder.cli.cmd_build", return_value=0) as mock:
            main(["build", "text2img", "--prompt", "a cat", "--steps", "20"])
            args = mock.call_args[0][0]
            assert args.template == "text2img"
            assert args.prompt == "a cat"
            assert args.steps == 20

    def test_build_lora_scenes(self):
        with patch("comfy_builder.cli.cmd_build", return_value=0) as mock:
            main(["build", "lora_scenes", "--lora", "test.safetensors",
                  "--scenes", "beach|forest", "--count", "2"])
            args = mock.call_args[0][0]
            assert args.template == "lora_scenes"
            assert args.lora == "test.safetensors"
            assert args.scenes == "beach|forest"
            assert args.count == 2

    def test_build_img2vid(self):
        with patch("comfy_builder.cli.cmd_build", return_value=0) as mock:
            main(["build", "img2vid", "--prompt", "a cat walking",
                  "--seconds", "1.5", "--fps", "12"])
            args = mock.call_args[0][0]
            assert args.template == "img2vid"
            assert args.seconds == 1.5
            assert args.fps == 12

    def test_run_default(self):
        with patch("comfy_builder.cli.cmd_run", return_value=0) as mock:
            main(["run"])
            args = mock.call_args[0][0]
            assert args.workflow == "current"

    def test_run_named(self):
        with patch("comfy_builder.cli.cmd_run", return_value=0) as mock:
            main(["run", "my_workflow"])
            args = mock.call_args[0][0]
            assert args.workflow == "my_workflow"

    def test_show_default(self):
        with patch("comfy_builder.cli.cmd_show", return_value=0) as mock:
            main(["show"])
            args = mock.call_args[0][0]
            assert args.workflow == "current"

    def test_list_command(self):
        with patch("comfy_builder.cli.cmd_list_workflows", return_value=0) as mock:
            main(["list"])
            mock.assert_called_once()

    def test_export_command(self):
        with patch("comfy_builder.cli.cmd_export", return_value=0) as mock:
            main(["export", "current", "--name", "my_export"])
            args = mock.call_args[0][0]
            assert args.name == "my_export"

    def test_install_check(self):
        with patch("comfy_builder.cli.cmd_install_check", return_value=0) as mock:
            main(["install", "check"])
            mock.assert_called_once()

    def test_install_nodes(self):
        with patch("comfy_builder.cli.cmd_install_nodes", return_value=0) as mock:
            main(["install", "nodes", "ComfyUI-AnimateDiff-Evolved"])
            args = mock.call_args[0][0]
            assert args.source == "ComfyUI-AnimateDiff-Evolved"

    def test_install_nodes_force_allow(self):
        with patch("comfy_builder.cli.cmd_install_nodes", return_value=0) as mock:
            main(["install", "nodes", "https://github.com/foo/bar", "--force-allow"])
            args = mock.call_args[0][0]
            assert args.force_allow is True

    def test_refine_command(self):
        with patch("comfy_builder.cli.cmd_refine", return_value=0) as mock:
            main(["refine", "set steps to 30"])
            args = mock.call_args[0][0]
            assert args.instruction == "set steps to 30"

    def test_logs_last(self):
        with patch("comfy_builder.cli.cmd_logs_last", return_value=0) as mock:
            main(["logs", "last"])
            mock.assert_called_once()

    def test_run_scenes_command(self):
        with patch("comfy_builder.cli.cmd_run_scenes", return_value=0) as mock:
            main(["run-scenes", "huffle_scenes_main", "--seed", "42"])
            args = mock.call_args[0][0]
            assert args.workflow == "huffle_scenes_main"
            assert args.seed == 42

    def test_run_scenes_with_character(self):
        with patch("comfy_builder.cli.cmd_run_scenes", return_value=0) as mock:
            main(["run-scenes", "my_wf", "--character", "a big red dog"])
            args = mock.call_args[0][0]
            assert args.character == "a big red dog"


class TestRunScenesLogic:
    """Verify run-scenes runtime behavior."""

    @patch("comfy_builder.store.save_run_log", return_value="/tmp/run.json")
    @patch("comfy_builder.api.get_history")
    @patch("comfy_builder.api.post_prompt")
    @patch("comfy_builder.api.check_server")
    @patch("comfy_builder.store.load_workflow")
    @patch("comfy_builder.config.WORKFLOWS_DIR")
    def test_run_scenes_counts_completed_scenes_not_images(
        self,
        mock_workflows_dir,
        mock_load_workflow,
        mock_check_server,
        mock_post_prompt,
        mock_get_history,
        mock_save_run_log,
        tmp_path,
    ):
        from argparse import Namespace
        from comfy_builder.cli import cmd_run_scenes

        scenes_path = tmp_path / "scenes.txt"
        scenes_path.write_text("sunrise\nforest")
        mock_workflows_dir.__truediv__.return_value = scenes_path

        mock_load_workflow.return_value = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt"}},
            "2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}},
            "3": {"class_type": "KSampler", "inputs": {"seed": 1}},
        }
        mock_check_server.return_value = {"online": True}
        mock_post_prompt.side_effect = [{"prompt_id": "p1"}, {"prompt_id": "p2"}]
        mock_get_history.side_effect = [
            {"p1": {"status": {"completed": True}, "outputs": {"7": {"images": [{"filename": "a.png"}, {"filename": "b.png"}]}}}},
            {"p2": {"status": {"completed": True}, "outputs": {"7": {"images": [{"filename": "c.png"}]}}}},
        ]

        args = Namespace(workflow="current", character=None, seed=100)
        rc = cmd_run_scenes(args)

        assert rc == 0
        saved = mock_save_run_log.call_args[0][0]
        assert saved["scenes_total"] == 2
        assert saved["scenes_completed"] == 2
        assert len(saved["outputs"]) == 3



class TestCommandRouting:
    """Verify commands return correct exit codes."""

    def test_status_returns_exit_code(self):
        with patch("comfy_builder.cli.cmd_status", return_value=1) as mock:
            result = main(["status"])
            assert result == 1

    def test_build_returns_zero_on_success(self):
        with patch("comfy_builder.cli.cmd_build", return_value=0) as mock:
            result = main(["build", "text2img", "--prompt", "test"])
            assert result == 0

    def test_missing_command_exits(self):
        with pytest.raises(SystemExit):
            main([])


class TestBuildParamExtraction:
    """Verify _parse_build_params extracts all expected parameters."""

    def test_all_build_params(self):
        from comfy_builder.cli import _parse_build_params
        from argparse import Namespace

        args = Namespace(
            prompt="test", negative="bad", checkpoint="ckpt.safetensors",
            lora="lora.safetensors", lora_strength=0.8,
            scenes="a|b", count=2, ref="ref.png",
            seconds=2.0, fps=12, style="cinematic",
            steps=25, cfg=7.0, width=1024, height=1024,
            seed=42, sampler="euler", scheduler="normal",
            denoise=0.8, batch_size=4,
        )
        params = _parse_build_params(args)
        assert params["prompt"] == "test"
        assert params["lora"] == "lora.safetensors"
        assert params["steps"] == 25
        assert params["seed"] == 42

    def test_none_params_excluded(self):
        from comfy_builder.cli import _parse_build_params
        from argparse import Namespace

        args = Namespace(prompt="test", negative=None, checkpoint=None,
                         lora=None, lora_strength=None, scenes=None,
                         count=None, ref=None, seconds=None, fps=None,
                         style=None, steps=None, cfg=None, width=None,
                         height=None, seed=None, sampler=None,
                         scheduler=None, denoise=None, batch_size=None)
        params = _parse_build_params(args)
        assert "prompt" in params
        assert "negative" not in params
