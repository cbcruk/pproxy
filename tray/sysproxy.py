"""macOS system HTTP/HTTPS proxy toggling via ``networksetup``.

The menu bar app points the system proxy at the running mitmproxy while
the proxy is up, and clears it when the proxy stops — so turning pproxy
off (or quitting) restores normal internet access automatically.

Every call is *fail-soft*: if ``networksetup``/``route`` is missing or
returns an error (e.g. on a non-macOS host, or without permission), the
failure is logged and the call returns ``False`` rather than raising, so
it can never crash the app.
"""

import logging
import subprocess

logger = logging.getLogger("pproxy")

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
"""Defaults matching mitmproxy's listen address."""


def _run(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run ``networksetup <args>``, returning None (and logging) on failure."""
    try:
        return subprocess.run(
            ["networksetup", *args], capture_output=True, text=True, check=True
        )
    except FileNotFoundError:
        logger.warning("[pproxy] networksetup not found — system proxy unchanged")
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip() or e
        logger.warning("[pproxy] networksetup %s failed: %s", args[0], detail)
    return None


def _default_interface() -> str | None:
    """The interface carrying the default route (e.g. ``en0``), or None."""
    try:
        out = subprocess.run(
            ["route", "-n", "get", "default"], capture_output=True, text=True, check=True
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("interface:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _service_for_device(order_text: str, device: str) -> str | None:
    """Map a device (``en0``) to its service name from -listnetworkserviceorder."""
    lines = order_text.splitlines()
    for i, line in enumerate(lines):
        if f"Device: {device})" in line:
            for j in range(i - 1, -1, -1):
                prev = lines[j].strip()
                if prev.startswith("(") and ")" in prev:
                    return prev.split(")", 1)[1].strip()
    return None


def active_network_service() -> str | None:
    """Detect the active network service name (e.g. ``Wi-Fi``), or None.

    Resolves the default-route interface, then maps it to the service
    name ``networksetup`` uses. Returns None if detection fails.
    """
    interface = _default_interface()
    if interface is None:
        return None
    order = _run(["-listnetworkserviceorder"])
    if order is None:
        return None
    return _service_for_device(order.stdout, interface)


def enable(
    host: str = PROXY_HOST,
    port: int = PROXY_PORT,
    service: str | None = None,
) -> bool:
    """Route the system's HTTP and HTTPS proxy through ``host:port``.

    Args:
        host: Proxy host. Defaults to 127.0.0.1.
        port: Proxy port. Defaults to 8080.
        service: Network service to change. Auto-detected if omitted.

    Returns:
        True if the proxy was set, False if it could not be (logged).
    """
    service = service or active_network_service()
    if service is None:
        logger.warning("[pproxy] no active network service — system proxy unchanged")
        return False
    ok = _run(["-setwebproxy", service, host, str(port)]) is not None
    ok = _run(["-setsecurewebproxy", service, host, str(port)]) is not None and ok
    if ok:
        logger.info("[pproxy] system proxy → %s:%d on %s", host, port, service)
    return ok


def disable(service: str | None = None) -> bool:
    """Turn the system's HTTP and HTTPS proxy off.

    Args:
        service: Network service to change. Auto-detected if omitted.

    Returns:
        True if the proxy was cleared, False if it could not be (logged).
    """
    service = service or active_network_service()
    if service is None:
        logger.warning("[pproxy] no active network service — system proxy unchanged")
        return False
    ok = _run(["-setwebproxystate", service, "off"]) is not None
    ok = _run(["-setsecurewebproxystate", service, "off"]) is not None and ok
    if ok:
        logger.info("[pproxy] system proxy disabled on %s", service)
    return ok
