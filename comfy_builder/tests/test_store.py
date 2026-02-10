"""Tests for comfy_builder.store module."""

import json
import pytest
from unittest.mock import patch
from pathlib import Path
from comfy_builder import store, config


@pytest.fixture
def store_dirs(tmp_path):
    """Set up temporary store directories."""
    workflows = tmp_path / "workflows"
    templates = workflows / "templates"
    drafts = workflows / "drafts"
    runs = tmp_path / "logs" / "runs"
    out = tmp_path / "out"

    for d in [templates, drafts, runs, out / "images", out / "video"]:
        d.mkdir(parents=True)

    current = workflows / "current.json"

    with patch.object(config, "WORKFLOWS_DIR", workflows), \
         patch.object(config, "CURRENT_WORKFLOW", current), \
         patch.object(config, "TEMPLATES_DIR", templates), \
         patch.object(config, "DRAFTS_DIR", drafts), \
         patch.object(config, "RUNS_DIR", runs), \
         patch.object(config, "OUT_DIR", out), \
         patch.object(config, "BUILDER_DIR", tmp_path):
        yield {
            "root": tmp_path,
            "workflows": workflows,
            "templates": templates,
            "drafts": drafts,
            "current": current,
            "runs": runs,
            "out": out,
        }


class TestSaveLoadCurrent:
    def test_save_and_load(self, store_dirs):
        wf = {"1": {"class_type": "KSampler", "inputs": {"steps": 20}}}
        store.save_current(wf)
        loaded = store.load_current()
        assert loaded == wf

    def test_load_empty(self, store_dirs):
        result = store.load_current()
        assert result == {}


class TestLoadWorkflow:
    def test_load_current(self, store_dirs):
        wf = {"1": {"class_type": "X", "inputs": {}}}
        store.save_current(wf)
        assert store.load_workflow("current") == wf

    def test_load_template(self, store_dirs):
        wf = {"1": {"class_type": "T", "inputs": {}}}
        path = store_dirs["templates"] / "text2img_sdxl.json"
        path.write_text(json.dumps(wf))
        assert store.load_workflow("text2img_sdxl") == wf

    def test_load_draft(self, store_dirs):
        wf = {"1": {"class_type": "D", "inputs": {}}}
        store.save_draft("my_draft", wf)
        assert store.load_workflow("my_draft") == wf

    def test_load_missing_returns_empty(self, store_dirs):
        assert store.load_workflow("nonexistent") == {}


class TestListAll:
    def test_list_empty(self, store_dirs):
        result = store.list_all()
        assert result["current"] is False
        assert result["templates"] == []
        assert result["drafts"] == []

    def test_list_with_items(self, store_dirs):
        store.save_current({"1": {}})
        store.save_draft("draft1", {"2": {}})
        (store_dirs["templates"] / "tmpl1.json").write_text("{}")

        result = store.list_all()
        assert result["current"] is True
        assert "tmpl1" in result["templates"]
        assert "draft1" in result["drafts"]


class TestSaveDraftTemplate:
    def test_save_draft(self, store_dirs):
        store.save_draft("test_draft", {"x": 1})
        assert (store_dirs["drafts"] / "test_draft.json").exists()

    def test_save_template(self, store_dirs):
        store.save_template("test_tmpl", {"x": 1})
        assert (store_dirs["templates"] / "test_tmpl.json").exists()


class TestExportWorkflow:
    def test_export_creates_directory(self, store_dirs):
        store.save_current({"1": {"class_type": "X", "inputs": {}}})
        result = store.export_workflow("current", "my_export")
        assert result["status"] == "success"
        export_dir = Path(result["export_path"])
        assert (export_dir / "workflow.json").exists()

    def test_export_missing_workflow(self, store_dirs):
        result = store.export_workflow("nonexistent", "export1")
        assert result["status"] == "error"


class TestRunLogs:
    def test_save_and_load_run_log(self, store_dirs):
        log = {"status": "success", "outputs": []}
        store.save_run_log(log)
        loaded = store.last_run_log()
        assert loaded["status"] == "success"

    def test_last_run_log_empty(self, store_dirs):
        assert store.last_run_log() is None
