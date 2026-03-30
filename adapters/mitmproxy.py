import logging
import time

from mitmproxy import http

from engine import RuleEngine
from cors import build_cors_headers
from loaders.json_loader import JsonLoader

logger = logging.getLogger("pproxy")


class MitmproxyAddon:
    """Thin adapter that bridges mitmproxy and the RuleEngine.

    Contains no business logic — only translates between mitmproxy's
    ``HTTPFlow`` objects and the engine's plain-Python types.

    Args:
        engine: The RuleEngine that holds interception rules.
        loader: Optional loader for hot-reloading rules on each request.
    """

    def __init__(self, engine: RuleEngine, loader: JsonLoader | None = None) -> None:
        self._engine = engine
        self._loader = loader

    def request(self, flow: http.HTTPFlow) -> None:
        """Called by mitmproxy for every incoming HTTP request.

        Handles three cases in order:
            1. Hot-reloads rules if a loader is configured.
            2. Responds to OPTIONS preflight requests with CORS headers.
            3. Matches the URL against rules and returns a mock response,
               or does nothing (pass-through to real server).

        Args:
            flow: The mitmproxy HTTP flow object.
        """
        if self._loader:
            self._loader.reload_if_changed()

        if flow.request.method == "OPTIONS":
            flow.response = http.Response.make(
                204, b"", build_cors_headers(flow.request.headers)
            )
            return

        url = flow.request.pretty_url
        mock = self._engine.match(url)

        if mock is not None:
            if mock.delay_ms > 0:
                time.sleep(mock.delay_ms / 1000)
            headers = {"content-type": mock.content_type}
            headers.update(build_cors_headers(flow.request.headers))
            headers.update(mock.headers)
            flow.response = http.Response.make(
                mock.status_code,
                self._engine.serialize_body(mock),
                headers,
            )
            logger.info(f"[pproxy] intercepted: {url} → {mock.status_code}")

    def response(self, flow: http.HTTPFlow) -> None:
        """Called by mitmproxy for every HTTP response (including pass-through).

        Injects CORS headers into all responses so the browser
        doesn't block cross-origin requests.

        Args:
            flow: The mitmproxy HTTP flow object.
        """
        cors = build_cors_headers(flow.request.headers)
        for k, v in cors.items():
            flow.response.headers[k] = v
