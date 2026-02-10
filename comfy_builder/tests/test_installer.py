"""Tests for comfy_builder.installer module."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from comfy_builder import installer, config


SAMPLE_ALLOWLIST = {
    "packs": {
        "ComfyUI-AnimateDiff-Evolved": {
            "repo": "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved",
            "provides": ["ADE_AnimateDiffLoaderWithContext", "ADE_UseEvolvedSampling"],
        },
        "ComfyUI-VideoHelperSuite": {
            "repo": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite",
            "provides": ["VHS_VideoCombine", "VHS_LoadVideo"],
        },
    }
}


@pytest.fixture
def installer_dirs(tmp_path):
    """Set up temporary dirs for installer tests."""
    installs = tmp_path / "installs"
    installs.mkdir()
    custom_nodes = tmp_path / "custom_nodes"
    custom_nodes.mkdir()

    allowlist = installs / "allowlist.json"
    allowlist.write_text(json.dumps(SAMPLE_ALLOWLIST))

    node_packs = installs / "node_packs.json"
    node_packs.write_text("{}")

    install_log = installs / "install.log"

    workflows = tmp_path / "workflows"
    workflows.mkdir()
    current = workflows / "current.json"

    schema_file = tmp_path / "schema" / "node_schema.json"
    schema_file.parent.mkdir()

    with patch.object(config, "ALLOWLIST_FILE", allowlist), \
         patch.object(config, "NODE_PACKS_FILE", node_packs), \
         patch.object(config, "INSTALL_LOG", install_log), \
         patch.object(config, "CUSTOM_NODES_DIR", custom_nodes), \
         patch.object(config, "COMFYUI_PATH", tmp_path), \
         patch.object(config, "CURRENT_WORKFLOW", current), \
         patch.object(config, "SCHEMA_FILE", schema_file), \
         patch.object(config, "WORKFLOWS_DIR", workflows):
        yield {
            "root": tmp_path,
            "installs": installs,
            "custom_nodes": custom_nodes,
            "allowlist": allowlist,
            "node_packs": node_packs,
            "current": current,
            "schema_file": schema_file,
        }


class TestLoadAllowlist:
    def test_loads_packs(self, installer_dirs):
        al = installer.load_allowlist()
        assert "ComfyUI-AnimateDiff-Evolved" in al["packs"]

    def test_empty_when_missing(self, tmp_path):
        with patch.object(config, "ALLOWLIST_FILE", tmp_path / "nope.json"):
            al = installer.load_allowlist()
            assert al == {}


class TestInstallPack:
    def test_known_pack_clones(self, installer_dirs):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = installer.install_pack("ComfyUI-AnimateDiff-Evolved")
            assert result["status"] == "success"
            assert result["pack"] == "ComfyUI-AnimateDiff-Evolved"
            # Verify git clone was called
            clone_args = mock_run.call_args[0][0]
            assert clone_args[0] == "git"
            assert clone_args[1] == "clone"

    def test_unknown_pack_returns_error(self, installer_dirs):
        result = installer.install_pack("NonExistentPack")
        assert result["status"] == "error"
        assert "Not in allowlist" in result["error"]

    def test_url_without_force_returns_blocked(self, installer_dirs):
        result = installer.install_pack("https://github.com/foo/bar")
        assert result["status"] == "blocked"
        assert "allowlist" in result["error"].lower()

    def test_url_with_force_allow_clones(self, installer_dirs):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = installer.install_pack("https://github.com/foo/bar", force_allow=True)
            assert result["status"] == "success"
            assert result["pack"] == "bar"

    def test_non_github_url_rejected(self, installer_dirs):
        result = installer.install_pack("https://evil.com/repo", force_allow=True)
        assert result["status"] == "error"
        assert "GitHub and GitLab" in result["error"]

    def test_already_installed_returns_status(self, installer_dirs):
        # Create the target dir to simulate existing install
        target = installer_dirs["custom_nodes"] / "ComfyUI-AnimateDiff-Evolved"
        target.mkdir()
        result = installer.install_pack("ComfyUI-AnimateDiff-Evolved")
        assert result["status"] == "already_installed"

    def test_git_clone_failure(self, installer_dirs):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="fatal: repo not found")
            result = installer.install_pack("ComfyUI-AnimateDiff-Evolved")
            assert result["status"] == "error"
            assert "git clone failed" in result["error"]

    def test_git_clone_timeout(self, installer_dirs):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 120)):
            result = installer.install_pack("ComfyUI-AnimateDiff-Evolved")
            assert result["status"] == "error"
            assert "timed out" in result["error"]

    def test_git_not_found(self, installer_dirs):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = installer.install_pack("ComfyUI-AnimateDiff-Evolved")
            assert result["status"] == "error"
            assert "git not found" in result["error"]

    def test_pip_install_runs_for_requirements(self, installer_dirs):
        call_log = []

        def mock_run(cmd, **kwargs):
            call_log.append(cmd[0])
            result = MagicMock(returncode=0, stderr="")
            return result

        with patch("subprocess.run", side_effect=mock_run):
            # Pre-create the target dir's requirements.txt
            # The install will clone first, creating the dir, then check for requirements
            # We need to make requirements.txt exist after clone
            target = installer_dirs["custom_nodes"] / "ComfyUI-AnimateDiff-Evolved"

            original_run = mock_run
            call_count = {"n": 0}

            def clone_then_reqs(cmd, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    # git clone — create dir + requirements.txt
                    target.mkdir(parents=True, exist_ok=True)
                    (target / "requirements.txt").write_text("numpy\n")
                return MagicMock(returncode=0, stderr="")

            with patch("subprocess.run", side_effect=clone_then_reqs):
                result = installer.install_pack("ComfyUI-AnimateDiff-Evolved")
                assert result["status"] == "success"
                # Should have called subprocess twice: git clone + pip install
                assert call_count["n"] == 2

    def test_updates_node_packs_json(self, installer_dirs):
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="")):
            installer.install_pack("ComfyUI-AnimateDiff-Evolved")
        installed = json.loads(installer_dirs["node_packs"].read_text())
        assert "ComfyUI-AnimateDiff-Evolved" in installed


class TestCheckMissing:
    def test_no_workflow_returns_error(self, installer_dirs):
        import comfy_builder.schema as schema_mod
        schema_mod._invalidate_cache()
        result = installer.check_missing()
        assert result["status"] == "error"

    def test_no_schema_returns_error(self, installer_dirs):
        # Save a workflow but no schema
        installer_dirs["current"].write_text(json.dumps({
            "1": {"class_type": "KSampler", "inputs": {}}
        }))
        import comfy_builder.schema as schema_mod
        schema_mod._invalidate_cache()
        result = installer.check_missing()
        assert result["status"] == "error"
        assert "schema" in result["error"].lower()

    def test_all_nodes_present(self, installer_dirs):
        installer_dirs["current"].write_text(json.dumps({
            "1": {"class_type": "KSampler", "inputs": {}}
        }))
        schema = {"KSampler": {"name": "KSampler"}}
        installer_dirs["schema_file"].write_text(json.dumps(schema))

        import comfy_builder.schema as schema_mod
        schema_mod._invalidate_cache()
        result = installer.check_missing()
        assert result["status"] == "ok"
        schema_mod._invalidate_cache()

    def test_missing_node_with_suggestion(self, installer_dirs):
        installer_dirs["current"].write_text(json.dumps({
            "1": {"class_type": "KSampler", "inputs": {}},
            "2": {"class_type": "ADE_AnimateDiffLoaderWithContext", "inputs": {}},
        }))
        schema = {"KSampler": {"name": "KSampler"}}
        installer_dirs["schema_file"].write_text(json.dumps(schema))

        import comfy_builder.schema as schema_mod
        schema_mod._invalidate_cache()
        result = installer.check_missing()
        assert result["status"] == "missing_nodes"
        assert "ADE_AnimateDiffLoaderWithContext" in result["missing"]
        assert "ADE_AnimateDiffLoaderWithContext" in result["suggestions"]
        schema_mod._invalidate_cache()

    def test_missing_node_unsupported(self, installer_dirs):
        installer_dirs["current"].write_text(json.dumps({
            "1": {"class_type": "TotallyFakeNode", "inputs": {}},
        }))
        schema = {"KSampler": {"name": "KSampler"}}
        installer_dirs["schema_file"].write_text(json.dumps(schema))

        import comfy_builder.schema as schema_mod
        schema_mod._invalidate_cache()
        result = installer.check_missing()
        assert "TotallyFakeNode" in result["unsupported"]
        schema_mod._invalidate_cache()


class TestCheckModel:
    def test_model_exists(self, tmp_path):
        ckpt_dir = tmp_path / "models" / "checkpoints"
        ckpt_dir.mkdir(parents=True)
        (ckpt_dir / "test.safetensors").write_text("fake")

        with patch.object(config, "CHECKPOINTS_DIR", ckpt_dir):
            result = installer.check_model("checkpoint", "test.safetensors")
            assert result["exists"] is True

    def test_model_missing(self, tmp_path):
        ckpt_dir = tmp_path / "models" / "checkpoints"
        ckpt_dir.mkdir(parents=True)

        with patch.object(config, "CHECKPOINTS_DIR", ckpt_dir):
            result = installer.check_model("checkpoint", "missing.safetensors")
            assert result["exists"] is False

    def test_unknown_model_type(self):
        result = installer.check_model("faketype", "test.safetensors")
        assert result["exists"] is False
        assert "Unknown model type" in result.get("error", "")
