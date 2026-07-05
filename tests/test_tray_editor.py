import sys

import pytest

from tray.editor import EditorError, open_in_editor


class TestOpenInEditor:
    def test_launches_command_with_path(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "tray.editor.subprocess.Popen", lambda argv: calls.append(argv)
        )
        target = tmp_path / "rules.json"
        open_in_editor(target, "code")
        assert calls == [["code", str(target)]]

    def test_splits_editor_flags(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "tray.editor.subprocess.Popen", lambda argv: calls.append(argv)
        )
        open_in_editor(tmp_path / "r.json", "subl -w")
        assert calls[0][:2] == ["subl", "-w"]
        assert calls[0][-1].endswith("r.json")

    def test_blank_command_raises(self, tmp_path):
        with pytest.raises(EditorError):
            open_in_editor(tmp_path / "r.json", "   ")

    def test_missing_editor_raises_friendly(self, tmp_path, monkeypatch):
        def boom(argv):
            raise FileNotFoundError()

        monkeypatch.setattr("tray.editor.subprocess.Popen", boom)
        with pytest.raises(EditorError) as e:
            open_in_editor(tmp_path / "r.json", "nonexistent-editor")
        assert "nonexistent-editor" in str(e.value)

    @pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX no-op binary")
    def test_real_launch(self, tmp_path):
        # `true` exits immediately; proves the happy path end-to-end.
        open_in_editor(tmp_path / "r.json", "true")
