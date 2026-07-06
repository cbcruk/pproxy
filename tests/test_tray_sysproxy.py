import subprocess
import types

from tray import sysproxy

SAMPLE_ORDER = """An asterisk (*) denotes that a network service is disabled.
(1) Wi-Fi
(Hardware Port: Wi-Fi, Device: en0)

(2) Thunderbolt Bridge
(Hardware Port: Thunderbolt Bridge, Device: bridge0)
"""


class FakeRun:
    """Stand-in for subprocess.run that fakes `route` and `networksetup`."""

    def __init__(self, interface="en0", order=SAMPLE_ORDER, fail=(), not_found=False):
        self.calls = []
        self._interface = interface
        self._order = order
        self._fail = set(fail)
        self._not_found = not_found

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if self._not_found:
            raise FileNotFoundError()
        cmd = args[0]
        if cmd == "route":
            out = f"   interface: {self._interface}\n" if self._interface else ""
            return types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        if cmd == "networksetup":
            sub = args[1]
            if sub in self._fail:
                raise subprocess.CalledProcessError(1, args, stderr="boom")
            out = self._order if sub == "-listnetworkserviceorder" else ""
            return types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        raise FileNotFoundError()

    def networksetup_calls(self):
        return [c for c in self.calls if c and c[0] == "networksetup"]


class TestParsing:
    def test_service_for_device(self):
        assert sysproxy._service_for_device(SAMPLE_ORDER, "en0") == "Wi-Fi"
        assert sysproxy._service_for_device(SAMPLE_ORDER, "bridge0") == "Thunderbolt Bridge"

    def test_service_for_unknown_device(self):
        assert sysproxy._service_for_device(SAMPLE_ORDER, "en9") is None


class TestActiveService:
    def test_resolves_interface_to_service(self, monkeypatch):
        monkeypatch.setattr("tray.sysproxy.subprocess.run", FakeRun())
        assert sysproxy.active_network_service() == "Wi-Fi"

    def test_none_when_no_default_route(self, monkeypatch):
        monkeypatch.setattr("tray.sysproxy.subprocess.run", FakeRun(interface=None))
        assert sysproxy.active_network_service() is None


class TestEnable:
    def test_issues_http_and_https(self, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr("tray.sysproxy.subprocess.run", fake)
        assert sysproxy.enable() is True
        subs = [c[1] for c in fake.networksetup_calls()]
        assert "-setwebproxy" in subs
        assert "-setsecurewebproxy" in subs
        webproxy = next(c for c in fake.networksetup_calls() if c[1] == "-setwebproxy")
        assert webproxy == ["networksetup", "-setwebproxy", "Wi-Fi", "127.0.0.1", "8080"]

    def test_explicit_service_skips_detection(self, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr("tray.sysproxy.subprocess.run", fake)
        sysproxy.enable(service="Ethernet")
        assert not any(c[0] == "route" for c in fake.calls)  # no auto-detect
        assert all(c[2] == "Ethernet" for c in fake.networksetup_calls())

    def test_custom_host_port(self, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr("tray.sysproxy.subprocess.run", fake)
        sysproxy.enable(host="10.0.0.1", port=9090, service="Wi-Fi")
        webproxy = next(c for c in fake.networksetup_calls() if c[1] == "-setwebproxy")
        assert webproxy[3:] == ["10.0.0.1", "9090"]

    def test_returns_false_when_no_service(self, monkeypatch):
        monkeypatch.setattr("tray.sysproxy.subprocess.run", FakeRun(interface=None))
        assert sysproxy.enable() is False

    def test_fail_soft_on_networksetup_error(self, monkeypatch):
        fake = FakeRun(fail={"-setwebproxy", "-setsecurewebproxy"})
        monkeypatch.setattr("tray.sysproxy.subprocess.run", fake)
        assert sysproxy.enable(service="Wi-Fi") is False  # logged, not raised

    def test_fail_soft_when_networksetup_missing(self, monkeypatch):
        monkeypatch.setattr("tray.sysproxy.subprocess.run", FakeRun(not_found=True))
        assert sysproxy.enable(service="Wi-Fi") is False  # no exception


class TestDisable:
    def test_turns_both_off(self, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr("tray.sysproxy.subprocess.run", fake)
        assert sysproxy.disable() is True
        calls = {(c[1], c[3]) for c in fake.networksetup_calls() if len(c) >= 4}
        assert ("-setwebproxystate", "off") in calls
        assert ("-setsecurewebproxystate", "off") in calls

    def test_fail_soft_when_missing(self, monkeypatch):
        monkeypatch.setattr("tray.sysproxy.subprocess.run", FakeRun(not_found=True))
        assert sysproxy.disable(service="Wi-Fi") is False
