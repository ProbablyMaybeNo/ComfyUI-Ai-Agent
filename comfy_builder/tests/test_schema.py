"""Tests for comfy_builder.schema module."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from comfy_builder import schema, config


class TestLoad:
    def test_load_returns_cached(self, tmp_path):
        schema_file = tmp_path / "node_schema.json"
        data = {"KSampler": {"name": "KSampler"}}
        schema_file.write_text(json.dumps(data))

        with patch.object(config, "SCHEMA_FILE", schema_file):
            schema._invalidate_cache()
            result = schema.load()
            assert "KSampler" in result
            schema._invalidate_cache()

    def test_load_returns_empty_when_missing(self, tmp_path):
        with patch.object(config, "SCHEMA_FILE", tmp_path / "missing.json"):
            schema._invalidate_cache()
            result = schema.load()
            assert result == {}
            schema._invalidate_cache()


class TestNodeExists:
    def test_exists(self, mock_schema):
        assert schema.node_exists("KSampler") is True

    def test_not_exists(self, mock_schema):
        assert schema.node_exists("FakeNode") is False


class TestGetNode:
    def test_found(self, mock_schema):
        node = schema.get_node("KSampler")
        assert node is not None
        assert node["name"] == "KSampler"

    def test_not_found(self, mock_schema):
        assert schema.get_node("FakeNode") is None


class TestSearch:
    def test_search_by_class_type(self, mock_schema):
        results = schema.search("KSampler")
        assert any(r["class_type"] == "KSampler" for r in results)

    def test_search_by_display_name(self, mock_schema):
        results = schema.search("Load Checkpoint")
        assert any(r["class_type"] == "CheckpointLoaderSimple" for r in results)

    def test_search_by_category(self, mock_schema):
        results = schema.search("sampling")
        assert any(r["class_type"] == "KSampler" for r in results)

    def test_search_case_insensitive(self, mock_schema):
        results = schema.search("ksampler")
        assert any(r["class_type"] == "KSampler" for r in results)

    def test_search_no_results(self, mock_schema):
        results = schema.search("zzz_nonexistent_zzz")
        assert results == []

    def test_search_limit(self, mock_schema):
        results = schema.search("", limit=3)
        assert len(results) <= 3


class TestGetNodeInputs:
    def test_has_required(self, mock_schema):
        inputs = schema.get_node_inputs("KSampler")
        assert "required" in inputs
        assert "seed" in inputs["required"]

    def test_missing_node(self, mock_schema):
        inputs = schema.get_node_inputs("FakeNode")
        assert inputs == {}


class TestGetNodeOutputs:
    def test_outputs(self, mock_schema):
        outputs = schema.get_node_outputs("CheckpointLoaderSimple")
        assert outputs == ["MODEL", "CLIP", "VAE"]

    def test_missing_node(self, mock_schema):
        outputs = schema.get_node_outputs("FakeNode")
        assert outputs == []


class TestValidateClassType:
    def test_valid(self, mock_schema):
        assert schema.validate_class_type("KSampler") is True

    def test_invalid(self, mock_schema):
        assert schema.validate_class_type("FakeNode") is False


class TestValidateInputs:
    def test_valid_inputs(self, mock_schema):
        errors = schema.validate_inputs("KSampler", {
            "seed": 42, "steps": 20, "cfg": 7.0,
            "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
            "model": ["1", 0],  # connection — should be skipped
        })
        assert errors == []

    def test_invalid_input_key(self, mock_schema):
        errors = schema.validate_inputs("KSampler", {"bogus_key": 42})
        assert len(errors) == 1
        assert "Unknown input 'bogus_key'" in errors[0]

    def test_missing_node_in_schema(self, mock_schema):
        errors = schema.validate_inputs("FakeNode", {"x": 1})
        assert any("not found" in e for e in errors)
