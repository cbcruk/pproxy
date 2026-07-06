import signal
import subprocess
import sys

import pytest

from tray.daemon import ProxyDaemon


@pytest.fixture
def daemon(tmp_path):
    return ProxyDaemon(
        "intercept.py",
        pidfile=tmp_path / "proxy.pid",
        logfile=tmp_path / "proxy.log",
    )


class FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid


class TestState:
    def test_not_running_without_pidfile(self, daemon):
        assert daemon.is_running() is False

    def test_running_reflects_alive_pid(self, daemon, tmp_path, monkeypatch):
        (tmp_path / "proxy.pid").write_text("4242")
        monkeypatch.setattr("tray.daemon._alive", lambda pid: pid == 4242)
        assert daemon.is_running() is True

    def test_stale_pidfile_reads_as_stopped(self, daemon, tmp_path, monkeypatch):
        (tmp_path / "proxy.pid").write_text("4242")
        monkeypatch.setattr("tray.daemon._alive", lambda pid: False)
        assert daemon.is_running() is False


class TestStart:
    def test_spawns_detached_and_records_pid(self, daemon, tmp_path, monkeypatch):
        captured = {}

        def fake_popen(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return FakeProc(4242)

        monkeypatch.setattr("tray.daemon.subprocess.Popen", fake_popen)
        daemon.start()
        assert captured["argv"] == ["mitmdump", "-s", "intercept.py"]
        assert captured["kwargs"]["start_new_session"] is True
        assert (tmp_path / "proxy.pid").read_text() == "4242"

    def test_idempotent_when_running(self, daemon, monkeypatch):
        monkeypatch.setattr(ProxyDaemon, "is_running", lambda self: True)
        calls = []
        monkeypatch.setattr("tray.daemon.subprocess.Popen", lambda *a, **k: calls.append(a))
        daemon.start()
        assert calls == []

    def test_missing_executable_propagates(self, daemon, monkeypatch):
        def boom(argv, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr("tray.daemon.subprocess.Popen", boom)
        with pytest.raises(FileNotFoundError):
            daemon.start()


class TestStop:
    def _wire_signals(self, monkeypatch):
        sent = []
        monkeypatch.setattr("tray.daemon.os.getpgid", lambda pid: pid)
        monkeypatch.setattr("tray.daemon.os.killpg", lambda pgid, sig: sent.append((pgid, sig)))
        monkeypatch.setattr("tray.daemon.time.sleep", lambda s: None)
        return sent

    def test_terminates_and_clears_pidfile(self, daemon, tmp_path, monkeypatch):
        (tmp_path / "proxy.pid").write_text("4242")
        alive = iter([True, False])  # alive at first check, gone after SIGTERM
        monkeypatch.setattr("tray.daemon._alive", lambda pid: next(alive))
        sent = self._wire_signals(monkeypatch)
        daemon.stop()
        assert sent == [(4242, signal.SIGTERM)]
        assert not (tmp_path / "proxy.pid").exists()

    def test_escalates_to_kill(self, daemon, tmp_path, monkeypatch):
        (tmp_path / "proxy.pid").write_text("4242")
        monkeypatch.setattr("tray.daemon._alive", lambda pid: True)  # never dies
        sent = self._wire_signals(monkeypatch)
        daemon.stop()
        assert (4242, signal.SIGTERM) in sent
        assert (4242, signal.SIGKILL) in sent

    def test_noop_when_not_running(self, daemon):
        daemon.stop()  # must not raise


@pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX process groups")
def test_real_detached_lifecycle(tmp_path, monkeypatch):
    real = subprocess.Popen
    monkeypatch.setattr(
        "tray.daemon.subprocess.Popen",
        lambda argv, **kwargs: real(["sleep", "30"], **kwargs),
    )
    d = ProxyDaemon("intercept.py", pidfile=tmp_path / "p.pid", logfile=tmp_path / "p.log")
    d.start()
    assert d.is_running()
    d.stop()
    assert not d.is_running()
