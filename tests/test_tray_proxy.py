import subprocess
import sys

import pytest

from tray.proxy import ProxyController


class FakeProc:
    """A stand-in for subprocess.Popen with controllable liveness."""

    def __init__(self, argv=None, dies_on_terminate=True):
        self.argv = argv
        self._alive = True
        self._dies_on_terminate = dies_on_terminate
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        if self._dies_on_terminate:
            self._alive = False

    def wait(self, timeout=None):
        if self._alive:
            raise subprocess.TimeoutExpired(cmd="proxy", timeout=timeout)
        return 0

    def kill(self):
        self.killed = True
        self._alive = False


def patch_popen(monkeypatch, proc):
    def spawn(argv):
        proc.argv = argv
        return proc
    monkeypatch.setattr("tray.proxy.subprocess.Popen", spawn)


class TestLifecycle:
    def test_starts_and_reports_running(self, monkeypatch):
        proc = FakeProc()
        patch_popen(monkeypatch, proc)
        c = ProxyController("intercept.py", "mitmdump")
        assert not c.is_running()
        c.start()
        assert c.is_running()
        assert proc.argv == ["mitmdump", "-s", "intercept.py"]

    def test_start_is_idempotent(self, monkeypatch):
        procs = []
        monkeypatch.setattr(
            "tray.proxy.subprocess.Popen",
            lambda argv: procs.append(FakeProc(argv)) or procs[-1],
        )
        c = ProxyController("intercept.py")
        c.start()
        c.start()
        assert len(procs) == 1

    def test_stop_terminates(self, monkeypatch):
        proc = FakeProc()
        patch_popen(monkeypatch, proc)
        c = ProxyController("intercept.py")
        c.start()
        c.stop()
        assert proc.terminated
        assert not c.is_running()

    def test_stop_when_not_running_is_noop(self):
        ProxyController("intercept.py").stop()  # must not raise

    def test_stop_escalates_to_kill_on_timeout(self, monkeypatch):
        proc = FakeProc(dies_on_terminate=False)
        patch_popen(monkeypatch, proc)
        c = ProxyController("intercept.py")
        c.start()
        c.stop()
        assert proc.terminated and proc.killed

    def test_toggle(self, monkeypatch):
        monkeypatch.setattr("tray.proxy.subprocess.Popen", lambda argv: FakeProc(argv))
        c = ProxyController("intercept.py")
        assert c.toggle() is True
        assert c.toggle() is False

    def test_missing_executable_propagates(self, monkeypatch):
        def boom(argv):
            raise FileNotFoundError()
        monkeypatch.setattr("tray.proxy.subprocess.Popen", boom)
        with pytest.raises(FileNotFoundError):
            ProxyController("intercept.py", "mitmdump").start()


@pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX `sleep`")
def test_real_process_lifecycle(monkeypatch):
    real = subprocess.Popen
    monkeypatch.setattr("tray.proxy.subprocess.Popen", lambda argv: real(["sleep", "5"]))
    c = ProxyController("intercept.py", "mitmdump")
    c.start()
    assert c.is_running()
    c.stop()
    assert not c.is_running()
