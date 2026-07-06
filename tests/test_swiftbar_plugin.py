import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "swiftbar" / "pproxy.5s.py"


def run_plugin(args, tmp_path, **extra_env):
    env = {
        **os.environ,
        "PPROXY_HOME": str(REPO),
        "XDG_CONFIG_HOME": str(tmp_path),  # isolate runtime dir from real ~/.config
        **extra_env,
    }
    return subprocess.run(
        [sys.executable, str(PLUGIN), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )


@pytest.mark.skipif(not PLUGIN.exists(), reason="plugin not present")
class TestRender:
    def test_renders_menu_when_stopped(self, tmp_path):
        result = run_plugin([], tmp_path)
        assert result.returncode == 0
        out = result.stdout
        assert "pproxy" in out
        assert "---" in out              # SwiftBar title/body separator
        assert "Start proxy" in out      # stopped → offers Start
        assert "Edit rules" in out
        assert "Refresh" in out

    def test_action_lines_reinvoke_this_script(self, tmp_path):
        out = run_plugin([], tmp_path).stdout
        assert "param2=\"start\"" in out
        assert str(PLUGIN) in out         # actions point back at the plugin


@pytest.mark.skipif(not PLUGIN.exists(), reason="plugin not present")
class TestActions:
    def test_edit_action_runs_editor_and_exits(self, tmp_path):
        # `true` stands in for the editor: succeeds and produces no output.
        result = run_plugin(["edit"], tmp_path, PPROXY_EDITOR="true")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_unknown_action_falls_back_to_render(self, tmp_path):
        result = run_plugin(["bogus"], tmp_path)
        assert result.returncode == 0
        assert "pproxy" in result.stdout
