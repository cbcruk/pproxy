import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from gui.store import RuleStore, RuleValidationError

logger = logging.getLogger("pproxy")

STATIC_DIR = Path(__file__).parent / "static"

_RULE_INDEX_RE = re.compile(r"^/api/rules/(\d+)$")

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class _Handler(BaseHTTPRequestHandler):
    """Serves the SPA and a small REST API over the rules file.

    Routes:
        GET    /                → static SPA (index.html)
        GET    /api/rules       → {"rules": [...], "path": "..."}
        POST   /api/rules       → append a rule
        PUT    /api/rules/{i}   → replace rule at index i
        DELETE /api/rules/{i}   → delete rule at index i
        POST   /api/rules/{i}/move  {"to": n} → reorder rule
    """

    server_version = "pproxy-gui"
    store: RuleStore  # injected via the server instance

    # ── Routing ────────────────────────────────────────────

    def do_GET(self) -> None:
        if self.path == "/api/rules":
            self._get_rules()
        elif self.path in ("/", "/index.html"):
            self._serve_static("index.html")
        elif self.path.startswith("/static/"):
            self._serve_static(self.path[len("/static/"):])
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        move = re.match(r"^/api/rules/(\d+)/move$", self.path)
        if self.path == "/api/rules":
            self._add_rule()
        elif move:
            self._move_rule(int(move.group(1)))
        else:
            self._send_json(404, {"error": "not found"})

    def do_PUT(self) -> None:
        m = _RULE_INDEX_RE.match(self.path)
        if m:
            self._update_rule(int(m.group(1)))
        else:
            self._send_json(404, {"error": "not found"})

    def do_DELETE(self) -> None:
        m = _RULE_INDEX_RE.match(self.path)
        if m:
            self._delete_rule(int(m.group(1)))
        else:
            self._send_json(404, {"error": "not found"})

    # ── API handlers ───────────────────────────────────────

    def _get_rules(self) -> None:
        try:
            rules = self.store.load()
        except RuleValidationError as e:
            self._send_json(400, {"error": str(e)})
            return
        self._send_json(200, {"rules": rules, "path": str(self.store.path)})

    def _add_rule(self) -> None:
        rule = self._read_json_body()
        if rule is None:
            return
        try:
            self.store.add(rule)
        except RuleValidationError as e:
            self._send_json(400, {"error": str(e)})
            return
        self._get_rules()

    def _update_rule(self, index: int) -> None:
        rule = self._read_json_body()
        if rule is None:
            return
        try:
            self.store.update(index, rule)
        except IndexError as e:
            self._send_json(404, {"error": str(e)})
        except RuleValidationError as e:
            self._send_json(400, {"error": str(e)})
        else:
            self._get_rules()

    def _delete_rule(self, index: int) -> None:
        try:
            self.store.delete(index)
        except IndexError as e:
            self._send_json(404, {"error": str(e)})
        else:
            self._get_rules()

    def _move_rule(self, index: int) -> None:
        body = self._read_json_body()
        if body is None:
            return
        to = body.get("to")
        if not isinstance(to, int):
            self._send_json(400, {"error": "'to' must be an integer"})
            return
        try:
            self.store.move(index, to)
        except IndexError as e:
            self._send_json(404, {"error": str(e)})
        else:
            self._get_rules()

    # ── Static files ───────────────────────────────────────

    def _serve_static(self, rel: str) -> None:
        # Prevent path traversal — resolve and confirm it stays under STATIC_DIR.
        target = (STATIC_DIR / rel).resolve()
        if not target.is_file() or STATIC_DIR.resolve() not in target.parents:
            self._send_json(404, {"error": "not found"})
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── Low-level helpers ──────────────────────────────────

    def _read_json_body(self) -> dict | None:
        """Read and parse a JSON request body, or send 400 and return None."""
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"invalid JSON body: {e}"})
            return None
        if not isinstance(data, dict):
            self._send_json(400, {"error": "request body must be a JSON object"})
            return None
        return data

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("[pproxy-gui] %s", format % args)


class GuiServer:
    """A running GUI server bound to a rules file.

    Args:
        store: The RuleStore backing the API.
        host: Interface to bind. Defaults to 127.0.0.1 (local only).
        port: TCP port. Defaults to 8765.
    """

    def __init__(self, store: RuleStore, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.store = store
        handler = type("BoundHandler", (_Handler,), {"store": store})
        self._httpd = ThreadingHTTPServer((host, port), handler)

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._httpd.server_address[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def serve(rules_path: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the GUI server and block until interrupted.

    Args:
        rules_path: Path to the JSON rules file to manage.
        host: Interface to bind.
        port: TCP port.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    server = GuiServer(RuleStore(rules_path), host, port)
    bound_host, bound_port = server.address
    logger.info("[pproxy-gui] managing %s", rules_path)
    logger.info("[pproxy-gui] open http://%s:%d", bound_host, bound_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[pproxy-gui] shutting down")
    finally:
        server.shutdown()
