import pytest

from tray.config import DEFAULT_EDITOR, Config


@pytest.fixture
def cfg_path(tmp_path):
    return tmp_path / "config.json"


class TestEditorResolution:
    def test_default_when_no_config(self, cfg_path, monkeypatch):
        monkeypatch.delenv("PPROXY_EDITOR", raising=False)
        assert Config(cfg_path).editor == DEFAULT_EDITOR

    def test_reads_from_config_file(self, cfg_path, monkeypatch):
        monkeypatch.delenv("PPROXY_EDITOR", raising=False)
        cfg_path.write_text('{"editor": "subl"}')
        assert Config(cfg_path).editor == "subl"

    def test_env_var_wins_over_file(self, cfg_path, monkeypatch):
        cfg_path.write_text('{"editor": "subl"}')
        monkeypatch.setenv("PPROXY_EDITOR", "vim")
        assert Config(cfg_path).editor == "vim"

    def test_blank_config_falls_back_to_default(self, cfg_path, monkeypatch):
        monkeypatch.delenv("PPROXY_EDITOR", raising=False)
        cfg_path.write_text('{"editor": "  "}')
        assert Config(cfg_path).editor == DEFAULT_EDITOR

    def test_malformed_file_falls_back(self, cfg_path, monkeypatch):
        monkeypatch.delenv("PPROXY_EDITOR", raising=False)
        cfg_path.write_text("{ not json")
        assert Config(cfg_path).editor == DEFAULT_EDITOR


class TestSetEditor:
    def test_persists_and_reloads(self, cfg_path, monkeypatch):
        monkeypatch.delenv("PPROXY_EDITOR", raising=False)
        Config(cfg_path).set_editor("subl -w")
        assert Config(cfg_path).editor == "subl -w"

    def test_creates_parent_dirs(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PPROXY_EDITOR", raising=False)
        nested = tmp_path / "a" / "b" / "config.json"
        Config(nested).set_editor("code")
        assert nested.exists()

    def test_trims_whitespace(self, cfg_path, monkeypatch):
        monkeypatch.delenv("PPROXY_EDITOR", raising=False)
        Config(cfg_path).set_editor("  code  ")
        assert Config(cfg_path).editor == "code"

    def test_blank_rejected(self, cfg_path):
        with pytest.raises(ValueError):
            Config(cfg_path).set_editor("   ")
