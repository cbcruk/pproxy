import pytest

from tray.config import BACKENDS, DEFAULT_BACKEND, DEFAULT_EDITOR, Config


@pytest.fixture
def cfg_path(tmp_path):
    return tmp_path / "config.json"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for name in ("PPROXY_EDITOR", "PPROXY_BACKEND", "PPROXY_COMMAND"):
        monkeypatch.delenv(name, raising=False)


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


class TestBackendResolution:
    def test_defaults_to_mitmproxy(self, cfg_path):
        assert Config(cfg_path).backend == DEFAULT_BACKEND

    def test_reads_from_config_file(self, cfg_path):
        cfg_path.write_text('{"backend": "node"}')
        assert Config(cfg_path).backend == "node"

    def test_env_var_wins_over_file(self, cfg_path, monkeypatch):
        cfg_path.write_text('{"backend": "node"}')
        monkeypatch.setenv("PPROXY_BACKEND", "mitmproxy")
        assert Config(cfg_path).backend == "mitmproxy"

    def test_unknown_value_falls_back(self, cfg_path):
        cfg_path.write_text('{"backend": "deno"}')
        assert Config(cfg_path).backend == DEFAULT_BACKEND

    def test_unknown_env_falls_back_to_the_file(self, cfg_path, monkeypatch):
        cfg_path.write_text('{"backend": "node"}')
        monkeypatch.setenv("PPROXY_BACKEND", "deno")
        assert Config(cfg_path).backend == "node"

    def test_every_backend_round_trips(self, cfg_path):
        for name in BACKENDS:
            Config(cfg_path).set_backend(name)
            assert Config(cfg_path).backend == name

    def test_unknown_backend_rejected(self, cfg_path):
        with pytest.raises(ValueError):
            Config(cfg_path).set_backend("deno")

    def test_editor_and_backend_coexist(self, cfg_path):
        Config(cfg_path).set_editor("subl")
        Config(cfg_path).set_backend("node")
        config = Config(cfg_path)
        assert (config.editor, config.backend) == ("subl", "node")


class TestProxyCommand:
    def test_unset_by_default(self, cfg_path):
        assert Config(cfg_path).proxy_command is None

    def test_reads_from_config_file(self, cfg_path):
        cfg_path.write_text('{"proxy_command": "npx pproxy"}')
        assert Config(cfg_path).proxy_command == "npx pproxy"

    def test_env_var_wins_over_file(self, cfg_path, monkeypatch):
        cfg_path.write_text('{"proxy_command": "npx pproxy"}')
        monkeypatch.setenv("PPROXY_COMMAND", "mitmweb")
        assert Config(cfg_path).proxy_command == "mitmweb"

    def test_blank_ignored(self, cfg_path):
        cfg_path.write_text('{"proxy_command": "   "}')
        assert Config(cfg_path).proxy_command is None
