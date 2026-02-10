"""Tests for comfy_builder.healer module."""

import pytest
from unittest.mock import patch, MagicMock
from comfy_builder.healer import diagnose, auto_heal, Fix, _resolve_placeholders


class TestDiagnose:
    def test_node_not_found(self):
        with patch("comfy_builder.installer.check_missing", return_value={"suggestions": {}}):
            fix = diagnose("class_type not found: 'ADE_FakeNode'")
            assert fix.type == "install_required"
            assert "ADE_FakeNode" in fix.description

    def test_model_missing_with_path(self):
        fix = diagnose("FileNotFoundError: models/loras/test.safetensors not found")
        assert fix.type == "model_missing"
        assert "test.safetensors" in fix.description

    def test_model_missing_safetensors(self):
        fix = diagnose("'my_model.safetensors' not found in directory")
        assert fix.type == "model_missing"

    def test_input_mismatch(self):
        with patch("comfy_builder.schema.get_node_inputs", return_value={
            "required": {"steps": [], "cfg": []},
            "optional": {},
        }):
            fix = diagnose("Invalid input 'bogus' for node 'KSampler'")
            assert fix.type == "graph_op"

    def test_cuda_oom(self):
        fix = diagnose("CUDA out of memory. Tried to allocate 2.0 GiB")
        assert fix.type == "reduce_resources"
        assert len(fix.ops) > 0

    def test_torch_oom(self):
        fix = diagnose("torch.cuda.OutOfMemoryError: ...")
        assert fix.type == "reduce_resources"

    def test_connection_refused(self):
        fix = diagnose("Connection refused at http://127.0.0.1:8000")
        assert fix.type == "unfixable"

    def test_urlopen_error(self):
        fix = diagnose("urlopen error [Errno 111] Connection refused")
        assert fix.type == "unfixable"

    def test_unknown_error(self):
        fix = diagnose("Something completely unknown happened")
        assert fix.type == "unfixable"
        assert "Unrecognized" in fix.description


class TestFixToDict:
    def test_basic(self):
        fix = Fix("graph_op", "test fix", ops=[{"op": "set_input"}])
        d = fix.to_dict()
        assert d["type"] == "graph_op"
        assert d["description"] == "test fix"
        assert "ops" in d

    def test_without_optional_fields(self):
        fix = Fix("unfixable", "cannot fix")
        d = fix.to_dict()
        assert "ops" not in d
        assert "install" not in d
        assert "download" not in d

    def test_with_install_instructions(self):
        fix = Fix("install_required", "need install",
                  install_instructions={"pack": "test", "repo": "url"})
        d = fix.to_dict()
        assert d["install"]["pack"] == "test"


class TestResolvePlaceholders:
    def test_resolve_find_latent(self):
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "4": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": 1024, "height": 1024}},
        }
        ops = [{"op": "set_input", "id": "find_latent", "key": "width", "value": 768}]
        resolved = _resolve_placeholders(wf, ops)
        assert resolved[0]["id"] == "4"

    def test_resolve_find_sampler(self):
        wf = {
            "5": {"class_type": "KSampler", "inputs": {"steps": 20}},
        }
        ops = [{"op": "set_input", "id": "find_sampler", "key": "steps", "value": 10}]
        resolved = _resolve_placeholders(wf, ops)
        assert resolved[0]["id"] == "5"

    def test_no_placeholder(self):
        wf = {"1": {"class_type": "X", "inputs": {}}}
        ops = [{"op": "set_input", "id": "1", "key": "x", "value": 1}]
        resolved = _resolve_placeholders(wf, ops)
        assert resolved[0]["id"] == "1"


class TestAutoHeal:
    def test_heal_oom_reduces_resolution(self):
        wf = {
            "4": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        }
        result = auto_heal(wf, "CUDA out of memory", attempt=1)
        assert result is not None
        healed_wf, fix = result
        assert healed_wf["4"]["inputs"]["width"] == 768
        assert healed_wf["4"]["inputs"]["height"] == 768

    def test_heal_exceeds_max_retries(self):
        wf = {"4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024}}}
        result = auto_heal(wf, "CUDA out of memory", attempt=99)
        assert result is None

    def test_heal_unfixable_returns_none(self):
        wf = {}
        result = auto_heal(wf, "Connection refused", attempt=1)
        assert result is None

    def test_heal_install_required_returns_none(self):
        with patch("comfy_builder.installer.check_missing", return_value={"suggestions": {}}):
            wf = {}
            result = auto_heal(wf, "class_type not found: 'FakeNode'", attempt=1)
            assert result is None
