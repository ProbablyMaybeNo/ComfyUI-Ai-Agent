"""Tests for comfy_builder.graph_ops module."""

import copy
import pytest
from comfy_builder.graph_ops import apply_ops, validate_workflow, workflow_summary


class TestAddNode:
    def test_add_basic_node(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "KSampler",
             "inputs": {"steps": 20}},
        ])
        assert "1" in wf
        assert wf["1"]["class_type"] == "KSampler"
        assert wf["1"]["inputs"]["steps"] == 20

    def test_add_node_no_inputs(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "VAEDecode", "inputs": {}},
        ])
        assert wf["1"]["inputs"] == {}

    def test_add_node_missing_inputs_key(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "VAEDecode"},
        ])
        assert wf["1"]["inputs"] == {}

    def test_add_duplicate_node_raises(self):
        wf = {}
        apply_ops(wf, [{"op": "add_node", "id": "1", "class_type": "X", "inputs": {}}])
        with pytest.raises(ValueError, match="already exists"):
            apply_ops(wf, [{"op": "add_node", "id": "1", "class_type": "Y", "inputs": {}}])

    def test_add_multiple_nodes(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "A", "inputs": {}},
            {"op": "add_node", "id": "2", "class_type": "B", "inputs": {}},
            {"op": "add_node", "id": "3", "class_type": "C", "inputs": {}},
        ])
        assert len(wf) == 3


class TestConnect:
    def test_basic_connection(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "A", "inputs": {}},
            {"op": "add_node", "id": "2", "class_type": "B", "inputs": {}},
            {"op": "connect", "from_id": "1", "from_output": 0,
             "to_id": "2", "to_input": "model"},
        ])
        assert wf["2"]["inputs"]["model"] == ["1", 0]

    def test_connect_different_output_index(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "A", "inputs": {}},
            {"op": "add_node", "id": "2", "class_type": "B", "inputs": {}},
            {"op": "connect", "from_id": "1", "from_output": 2,
             "to_id": "2", "to_input": "vae"},
        ])
        assert wf["2"]["inputs"]["vae"] == ["1", 2]

    def test_connect_missing_source_raises(self):
        wf = {}
        apply_ops(wf, [{"op": "add_node", "id": "2", "class_type": "B", "inputs": {}}])
        with pytest.raises(ValueError, match="Source node"):
            apply_ops(wf, [{"op": "connect", "from_id": "99", "from_output": 0,
                            "to_id": "2", "to_input": "x"}])

    def test_connect_missing_target_raises(self):
        wf = {}
        apply_ops(wf, [{"op": "add_node", "id": "1", "class_type": "A", "inputs": {}}])
        with pytest.raises(ValueError, match="Target node"):
            apply_ops(wf, [{"op": "connect", "from_id": "1", "from_output": 0,
                            "to_id": "99", "to_input": "x"}])


class TestSetInput:
    def test_set_existing_input(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "K", "inputs": {"steps": 20}},
            {"op": "set_input", "id": "1", "key": "steps", "value": 30},
        ])
        assert wf["1"]["inputs"]["steps"] == 30

    def test_set_new_input(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "K", "inputs": {}},
            {"op": "set_input", "id": "1", "key": "cfg", "value": 8.5},
        ])
        assert wf["1"]["inputs"]["cfg"] == 8.5

    def test_set_input_missing_node_raises(self):
        wf = {}
        with pytest.raises(ValueError, match="not found"):
            apply_ops(wf, [{"op": "set_input", "id": "99", "key": "x", "value": 1}])


class TestDeleteNode:
    def test_delete_node(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "A", "inputs": {}},
            {"op": "add_node", "id": "2", "class_type": "B", "inputs": {}},
            {"op": "delete_node", "id": "1"},
        ])
        assert "1" not in wf
        assert "2" in wf

    def test_delete_cleans_connections(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "A", "inputs": {}},
            {"op": "add_node", "id": "2", "class_type": "B", "inputs": {}},
            {"op": "connect", "from_id": "1", "from_output": 0,
             "to_id": "2", "to_input": "model"},
            {"op": "delete_node", "id": "1"},
        ])
        assert "model" not in wf["2"]["inputs"]

    def test_delete_missing_raises(self):
        with pytest.raises(ValueError, match="not found"):
            apply_ops({}, [{"op": "delete_node", "id": "99"}])


class TestReplaceNode:
    def test_replace_node_class(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "VAEDecode", "inputs": {}},
            {"op": "replace_node", "id": "1", "class_type": "VAEDecodeTiled",
             "inputs": {"tile_size": 512}},
        ])
        assert wf["1"]["class_type"] == "VAEDecodeTiled"
        assert wf["1"]["inputs"]["tile_size"] == 512

    def test_replace_missing_raises(self):
        with pytest.raises(ValueError, match="not found"):
            apply_ops({}, [{"op": "replace_node", "id": "99", "class_type": "X"}])


class TestUnknownOp:
    def test_unknown_op_raises(self):
        with pytest.raises(ValueError, match="Unknown op type"):
            apply_ops({}, [{"op": "foobar"}])


class TestOpsApplyOrder:
    def test_ops_are_sequential(self):
        wf = {}
        apply_ops(wf, [
            {"op": "add_node", "id": "1", "class_type": "A", "inputs": {"x": 1}},
            {"op": "set_input", "id": "1", "key": "x", "value": 2},
            {"op": "set_input", "id": "1", "key": "x", "value": 3},
        ])
        assert wf["1"]["inputs"]["x"] == 3


class TestValidateWorkflow:
    def test_valid_workflow(self, mock_schema, sample_text2img_workflow):
        errors = validate_workflow(sample_text2img_workflow, strict=False)
        assert errors == []

    def test_unknown_class_type(self, mock_schema):
        wf = {"1": {"class_type": "NonExistentNode", "inputs": {}}}
        errors = validate_workflow(wf)
        assert any("unknown class_type" in e for e in errors)

    def test_missing_class_type(self, mock_schema):
        wf = {"1": {"inputs": {}}}
        errors = validate_workflow(wf)
        assert any("missing class_type" in e for e in errors)

    def test_dangling_connection(self, mock_schema):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"model": ["99", 0]}},
        }
        errors = validate_workflow(wf, strict=False)
        assert any("missing node '99'" in e for e in errors)

    def test_strict_validates_inputs(self, mock_schema):
        wf = {
            "1": {"class_type": "KSampler",
                  "inputs": {"bogus_key": 42}},
        }
        errors = validate_workflow(wf, strict=True)
        assert any("Unknown input 'bogus_key'" in e for e in errors)


class TestWorkflowSummary:
    def test_summary_structure(self, sample_text2img_workflow):
        summary = workflow_summary(sample_text2img_workflow)
        assert summary["node_count"] == 7
        assert len(summary["nodes"]) == 7
        assert len(summary["connections"]) > 0

    def test_summary_separates_values_and_connections(self):
        wf = {
            "1": {"class_type": "KSampler",
                  "inputs": {"steps": 20, "model": ["0", 0]}},
        }
        summary = workflow_summary(wf)
        node = summary["nodes"][0]
        assert "steps" in node["value_inputs"]
        assert "model" not in node["value_inputs"]
        assert any(c["to_input"] == "model" for c in summary["connections"])
