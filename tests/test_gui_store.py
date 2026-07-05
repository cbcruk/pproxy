import json

import pytest

from gui.store import RuleStore, RuleValidationError


@pytest.fixture
def store(tmp_path):
    return RuleStore(tmp_path / "rules.json")


class TestLoad:
    def test_missing_file_returns_empty(self, store):
        assert store.load() == []

    def test_reads_existing_rules(self, store):
        store.path.write_text('[{"url_pattern": "*/api/*"}]')
        assert store.load() == [{"url_pattern": "*/api/*"}]

    def test_invalid_json_raises(self, store):
        store.path.write_text("{ not json")
        with pytest.raises(RuleValidationError):
            store.load()

    def test_non_array_raises(self, store):
        store.path.write_text('{"url_pattern": "*"}')
        with pytest.raises(RuleValidationError):
            store.load()


class TestSave:
    def test_creates_file_and_parent(self, tmp_path):
        store = RuleStore(tmp_path / "nested" / "rules.json")
        store.save([{"url_pattern": "*/api/*"}])
        assert store.path.exists()
        assert json.loads(store.path.read_text()) == [{"url_pattern": "*/api/*"}]

    def test_preserves_unicode(self, store):
        store.save([{"url_pattern": "*", "body": {"name": "홍길동"}}])
        assert "홍길동" in store.path.read_text()

    def test_rejects_rule_without_pattern(self, store):
        with pytest.raises(RuleValidationError):
            store.save([{"status_code": 200}])

    def test_bad_rule_leaves_file_untouched(self, store):
        store.save([{"url_pattern": "*/keep/*"}])
        with pytest.raises(RuleValidationError):
            store.save([{"url_pattern": "*/ok/*"}, {"status_code": 500}])
        assert store.load() == [{"url_pattern": "*/keep/*"}]


class TestAdd:
    def test_appends(self, store):
        store.add({"url_pattern": "*/a/*"})
        store.add({"url_pattern": "*/b/*"})
        assert [r["url_pattern"] for r in store.load()] == ["*/a/*", "*/b/*"]

    def test_invalid_rejected(self, store):
        with pytest.raises(RuleValidationError):
            store.add({"status_code": 200})


class TestUpdate:
    def test_replaces_in_place(self, store):
        store.save([{"url_pattern": "*/old/*"}, {"url_pattern": "*/b/*"}])
        store.update(0, {"url_pattern": "*/new/*"})
        assert [r["url_pattern"] for r in store.load()] == ["*/new/*", "*/b/*"]

    def test_out_of_range_raises(self, store):
        store.save([{"url_pattern": "*/a/*"}])
        with pytest.raises(IndexError):
            store.update(5, {"url_pattern": "*/x/*"})


class TestDelete:
    def test_removes(self, store):
        store.save([{"url_pattern": "*/a/*"}, {"url_pattern": "*/b/*"}])
        removed = store.delete(0)
        assert removed == {"url_pattern": "*/a/*"}
        assert [r["url_pattern"] for r in store.load()] == ["*/b/*"]

    def test_out_of_range_raises(self, store):
        with pytest.raises(IndexError):
            store.delete(0)


class TestMove:
    def test_reorders(self, store):
        store.save([
            {"url_pattern": "*/a/*"},
            {"url_pattern": "*/b/*"},
            {"url_pattern": "*/c/*"},
        ])
        store.move(2, 0)
        assert [r["url_pattern"] for r in store.load()] == ["*/c/*", "*/a/*", "*/b/*"]

    def test_target_clamped(self, store):
        store.save([{"url_pattern": "*/a/*"}, {"url_pattern": "*/b/*"}])
        store.move(0, 99)
        assert [r["url_pattern"] for r in store.load()] == ["*/b/*", "*/a/*"]

    def test_out_of_range_raises(self, store):
        with pytest.raises(IndexError):
            store.move(3, 0)
