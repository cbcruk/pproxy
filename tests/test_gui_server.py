import json
import threading
import urllib.error
import urllib.request

import pytest

from gui.server import GuiServer
from gui.store import RuleStore


@pytest.fixture
def server(tmp_path):
    store = RuleStore(tmp_path / "rules.json")
    srv = GuiServer(store, host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.address
    yield f"http://{host}:{port}"
    srv.shutdown()
    thread.join(timeout=2)


def req(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestApi:
    def test_get_empty(self, server):
        status, data = req(server, "GET", "/api/rules")
        assert status == 200
        assert data["rules"] == []

    def test_add_and_list(self, server):
        req(server, "POST", "/api/rules", {"url_pattern": "*/api/*"})
        status, data = req(server, "GET", "/api/rules")
        assert status == 200
        assert data["rules"] == [{"url_pattern": "*/api/*"}]

    def test_add_returns_full_list(self, server):
        status, data = req(server, "POST", "/api/rules", {"url_pattern": "*/api/*"})
        assert status == 200
        assert len(data["rules"]) == 1

    def test_add_invalid_returns_400(self, server):
        status, data = req(server, "POST", "/api/rules", {"status_code": 200})
        assert status == 400
        assert "error" in data

    def test_update(self, server):
        req(server, "POST", "/api/rules", {"url_pattern": "*/old/*"})
        status, data = req(server, "PUT", "/api/rules/0", {"url_pattern": "*/new/*"})
        assert status == 200
        assert data["rules"][0]["url_pattern"] == "*/new/*"

    def test_update_out_of_range_404(self, server):
        status, _ = req(server, "PUT", "/api/rules/9", {"url_pattern": "*/x/*"})
        assert status == 404

    def test_delete(self, server):
        req(server, "POST", "/api/rules", {"url_pattern": "*/a/*"})
        status, data = req(server, "DELETE", "/api/rules/0")
        assert status == 200
        assert data["rules"] == []

    def test_move(self, server):
        req(server, "POST", "/api/rules", {"url_pattern": "*/a/*"})
        req(server, "POST", "/api/rules", {"url_pattern": "*/b/*"})
        status, data = req(server, "POST", "/api/rules/1/move", {"to": 0})
        assert status == 200
        assert [r["url_pattern"] for r in data["rules"]] == ["*/b/*", "*/a/*"]

    def test_malformed_json_body_400(self, server):
        request = urllib.request.Request(
            server + "/api/rules", data=b"{ nope", method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request)
            assert False, "expected 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400


class TestStatic:
    def test_serves_spa(self, server):
        with urllib.request.urlopen(server + "/") as resp:
            assert resp.status == 200
            assert b"pproxy" in resp.read()

    def test_unknown_path_404(self, server):
        status, _ = req(server, "GET", "/nope")
        assert status == 404
