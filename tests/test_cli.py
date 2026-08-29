import json

import pytest

from pproxy.cli import build_parser, check_command, load_engine, main
from pproxy.loaders import JsonLoader, YamlLoader, get_loader
from pproxy.engine import RuleEngine


RULES = [
    {"url_pattern": "*/api/users/*", "status_code": 200, "body": {"users": []}},
    {"url_pattern": r"/orders/\d+", "matcher": "regex", "name": "order", "status_code": 201},
]


@pytest.fixture
def json_rules(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(RULES))
    return path


@pytest.fixture
def yaml_rules(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("- url_pattern: '*/api/*'\n  status_code: 200\n")
    return path


class TestGetLoader:
    def test_json_extension(self, json_rules):
        assert isinstance(get_loader(json_rules, RuleEngine()), JsonLoader)

    @pytest.mark.parametrize("name", ["rules.yaml", "rules.yml", "rules.YAML"])
    def test_yaml_extensions(self, tmp_path, name):
        assert isinstance(get_loader(tmp_path / name, RuleEngine()), YamlLoader)

    def test_unknown_extension(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported rules file"):
            get_loader(tmp_path / "rules.toml", RuleEngine())


class TestLoadEngine:
    def test_loads_rules_from_json(self, json_rules):
        engine, loader = load_engine(str(json_rules))
        assert isinstance(loader, JsonLoader)
        assert [r.pattern for r in engine.rules] == [
            "*/api/users/*",
            r"/orders/\d+",
        ]

    def test_loads_rules_from_yaml(self, yaml_rules):
        engine, _ = load_engine(str(yaml_rules))
        assert engine.match("https://example.com/api/x") is not None


class TestParser:
    def test_run_defaults(self):
        args = build_parser().parse_args(["run", "rules.json"])
        assert (args.command, args.host, args.port, args.verbose) == (
            "run",
            "127.0.0.1",
            8080,
            False,
        )

    def test_run_overrides(self):
        args = build_parser().parse_args(
            ["run", "rules.json", "--host", "0.0.0.0", "--port", "9090", "-v"]
        )
        assert (args.host, args.port, args.verbose) == ("0.0.0.0", 9090, True)

    def test_command_is_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])


class TestCheckCommand:
    def test_valid_rules(self, json_rules, capsys):
        assert main(["check", str(json_rules)]) == 0
        out = capsys.readouterr().out
        assert "*/api/users/*" in out
        assert "(order)" in out
        assert "2 rules OK" in out

    def test_unknown_matcher(self, tmp_path, capsys):
        path = tmp_path / "rules.json"
        path.write_text(json.dumps([{"url_pattern": "*", "matcher": "nope"}]))
        assert main(["check", str(path)]) == 1
        assert "Unknown matcher" in capsys.readouterr().err

    def test_unsupported_extension(self, tmp_path, capsys):
        assert main(["check", str(tmp_path / "rules.toml")]) == 1
        assert "Unsupported rules file" in capsys.readouterr().err

    def test_missing_file(self, tmp_path, capsys):
        assert main(["check", str(tmp_path / "absent.json")]) == 1
        assert "no rules loaded" in capsys.readouterr().err

    def test_malformed_rule(self, tmp_path, capsys):
        path = tmp_path / "rules.json"
        path.write_text(json.dumps([{"status_code": 200}]))
        assert main(["check", str(path)]) == 1
        assert "failed to load" in capsys.readouterr().err
