"""Tests for comfy_builder.planner module."""

import pytest
from unittest.mock import patch, MagicMock
from comfy_builder import planner, config
from comfy_builder.graph_ops import apply_ops


class TestBuildText2Img:
    def test_produces_valid_workflow(self, mock_schema):
        result = planner.build("text2img", {"prompt": "a cat", "seed": 42})
        assert result["status"] in ("success", "warning")
        assert result["node_count"] == 7
        assert result["parameters"]["prompt"] == "a cat"
        assert result["parameters"]["seed"] == 42

    def test_uses_defaults(self, mock_schema):
        result = planner.build("text2img", {"prompt": "test", "seed": 1})
        p = result["parameters"]
        assert p["checkpoint"] == config.DEFAULT_CHECKPOINT
        assert p["steps"] == config.DEFAULT_STEPS
        assert p["cfg"] == config.DEFAULT_CFG
        assert p["width"] == config.DEFAULT_WIDTH

    def test_custom_params_override_defaults(self, mock_schema):
        result = planner.build("text2img", {
            "prompt": "test", "steps": 50, "cfg": 12.0,
            "width": 512, "height": 768, "seed": 1,
        })
        p = result["parameters"]
        assert p["steps"] == 50
        assert p["cfg"] == 12.0
        assert p["width"] == 512
        assert p["height"] == 768

    def test_workflow_has_all_nodes(self, mock_schema, tmp_path):
        """Verify the generated workflow has the correct node types."""
        with patch.object(config, "CURRENT_WORKFLOW", tmp_path / "current.json"), \
             patch.object(config, "WORKFLOWS_DIR", tmp_path):
            ops, meta = planner._build_text2img({"prompt": "test", "seed": 1})
            wf = {}
            apply_ops(wf, ops)

            class_types = {n["class_type"] for n in wf.values()}
            assert "CheckpointLoaderSimple" in class_types
            assert "CLIPTextEncode" in class_types
            assert "EmptyLatentImage" in class_types
            assert "KSampler" in class_types
            assert "VAEDecode" in class_types
            assert "SaveImage" in class_types


class TestBuildLoraScenes:
    def test_requires_lora(self, mock_schema):
        result = planner.build("lora_scenes", {"prompt": "test"})
        assert result["status"] == "error"
        assert "lora" in result["error"].lower()

    def test_basic_lora_scene(self, mock_schema):
        result = planner.build("lora_scenes", {
            "lora": "test.safetensors",
            "scenes": "beach|forest",
            "count": 2,
            "seed": 100,
        })
        assert result["status"] in ("success", "warning")
        meta = result["parameters"]
        assert meta["total_images"] == 4
        assert len(meta["batch"]) == 4
        assert meta["scenes"] == ["beach", "forest"]

    def test_batch_has_correct_seeds(self, mock_schema):
        result = planner.build("lora_scenes", {
            "lora": "test.safetensors",
            "scenes": "a|b",
            "count": 2,
            "seed": 100,
        })
        batch = result["parameters"]["batch"]
        seeds = [j["seed"] for j in batch]
        assert seeds == [100, 101, 102, 103]

    def test_batch_prompts_contain_scenes(self, mock_schema):
        result = planner.build("lora_scenes", {
            "lora": "test.safetensors",
            "prompt": "photo of subject in {scene}",
            "scenes": "beach|forest",
            "count": 1,
            "seed": 1,
        })
        batch = result["parameters"]["batch"]
        assert "beach" in batch[0]["prompt"]
        assert "forest" in batch[1]["prompt"]

    def test_batch_size_limit(self, mock_schema):
        result = planner.build("lora_scenes", {
            "lora": "test.safetensors",
            "scenes": "|".join(f"scene{i}" for i in range(20)),
            "count": 10,
            "seed": 1,
        })
        assert result["status"] == "error"
        assert "exceeds limit" in result["error"]

    def test_workflow_has_lora_loader(self, mock_schema, tmp_path):
        with patch.object(config, "CURRENT_WORKFLOW", tmp_path / "current.json"), \
             patch.object(config, "WORKFLOWS_DIR", tmp_path):
            ops, meta = planner._build_lora_scenes({
                "lora": "test.safetensors",
                "scenes": "beach",
                "count": 1,
                "seed": 1,
            })
            wf = {}
            apply_ops(wf, ops)
            class_types = {n["class_type"] for n in wf.values()}
            assert "LoraLoader" in class_types


class TestBuildImg2Vid:
    def test_animatediff_strategy_with_nodes(self, mock_schema):
        result = planner.build("img2vid", {
            "prompt": "a cat walking",
            "seconds": 1,
            "fps": 8,
            "seed": 42,
        })
        assert result["status"] in ("success", "warning")
        assert result["parameters"]["strategy"] == "2A_animatediff"
        assert result["parameters"]["total_frames"] == 8

    def test_keyframes_fallback_without_nodes(self):
        """When AnimateDiff nodes are missing, fall back to keyframes."""
        empty_schema = {}
        with patch("comfy_builder.schema.load", return_value=empty_schema):
            result = planner.build("img2vid", {
                "prompt": "test", "seconds": 1, "fps": 8, "seed": 42,
            })
            assert result["parameters"]["strategy"] == "2B_keyframes"

    def test_style_appended_to_prompt(self, mock_schema):
        result = planner.build("img2vid", {
            "prompt": "a cat", "style": "cinematic",
            "seconds": 1, "fps": 8, "seed": 42,
        })
        assert "cinematic" in result["parameters"]["prompt"]


class TestBuildUnknownTemplate:
    def test_unknown_template(self, mock_schema):
        result = planner.build("nonexistent", {})
        assert result["status"] == "error"
        assert "Unknown template" in result["error"]


class TestRefine:
    def test_refine_steps(self, mock_schema, sample_text2img_workflow, tmp_path):
        wf_path = tmp_path / "current.json"
        import json
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        with open(wf_path, "w") as f:
            json.dump(sample_text2img_workflow, f)

        with patch.object(config, "CURRENT_WORKFLOW", wf_path):
            result = planner.refine("set steps to 30")
            assert result["status"] == "success"
            assert result["ops_applied"] > 0
            # Verify the op
            assert any(
                op["key"] == "steps" and op["value"] == 30
                for op in result["ops"]
            )

    def test_refine_cfg(self, mock_schema, sample_text2img_workflow, tmp_path):
        wf_path = tmp_path / "current.json"
        import json
        with open(wf_path, "w") as f:
            json.dump(sample_text2img_workflow, f)

        with patch.object(config, "CURRENT_WORKFLOW", wf_path):
            result = planner.refine("change cfg to 8.5")
            assert result["status"] == "success"
            assert any(
                op["key"] == "cfg" and op["value"] == 8.5
                for op in result["ops"]
            )

    def test_refine_prompt(self, mock_schema, sample_text2img_workflow, tmp_path):
        wf_path = tmp_path / "current.json"
        import json
        with open(wf_path, "w") as f:
            json.dump(sample_text2img_workflow, f)

        with patch.object(config, "CURRENT_WORKFLOW", wf_path):
            result = planner.refine("change prompt to a dog on the moon")
            assert result["status"] == "success"
            assert any(
                op["key"] == "text" and "dog on the moon" in op["value"]
                for op in result["ops"]
            )

    def test_refine_no_workflow(self, mock_schema, tmp_path):
        with patch.object(config, "CURRENT_WORKFLOW", tmp_path / "nonexistent.json"):
            result = planner.refine("set steps to 10")
            assert result["status"] == "error"

    def test_refine_unparseable(self, mock_schema, sample_text2img_workflow, tmp_path):
        wf_path = tmp_path / "current.json"
        import json
        with open(wf_path, "w") as f:
            json.dump(sample_text2img_workflow, f)

        with patch.object(config, "CURRENT_WORKFLOW", wf_path):
            result = planner.refine("make it more artistic")
            assert result["status"] == "error"
            assert "Could not parse" in result["error"]
