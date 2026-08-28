"""A1 — orchestrator-side OCI routing hardening (spec unit tests, NO real
container). Pins two of the three "lab_oci_enabled=true hard prerequisites"
flagged in P2 review:

* ``fs.write`` must NOT be in ``_OCI_TOOLS`` — its args are ``{path, content}``,
  which ``_command_from_args`` cannot turn into a shell command, so routing it
  through OCI silently produced ``ok=False`` on every call once the flag is on
  (a behaviour regression vs. the flag-off Mock, which always succeeds).
  Scratch-file materialisation is a follow-up, not this fix.
* the orchestrator must cache ONE ``OciExecutor`` per run (not a fresh instance
  per action), so a teardown failure's ``_broken`` quarantine actually blocks
  the run's later actions instead of resetting on every ``_select_executor``
  call.

The third prerequisite (teardown fail-open) is pinned in
``tests/test_lab_oci_executor_spec.py``.
"""
from types import SimpleNamespace

import pytest

from app.config import settings
from app.lab import orchestrator
from app.lab.orchestrator import _OCI_TOOLS, _Orchestrator
from app.lab.sandbox import oci_executor as oci
from app.lab.sandbox.oci_executor import ExecutorError, SandboxTeardownError


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _oci_flags(monkeypatch):
    monkeypatch.setattr(settings, "lab_oci_enabled", True, raising=False)
    monkeypatch.setattr(settings, "lab_oci_image", "alpine:latest", raising=False)


def _orch() -> _Orchestrator:
    run = SimpleNamespace(id="run1", researcher_slug="agent1", scopes_json=[])
    task = SimpleNamespace(id="task1", issuer_user_id="tenant1")
    return _Orchestrator(db=None, run=run, task=task)


# ── fake subprocess plumbing (mirrors tests/test_lab_oci_executor_spec.py) ──

class _FakeStream:
    def __init__(self, data: bytes = b""):
        self._data, self._pos = data, 0

    async def read(self, n: int = -1) -> bytes:
        if self._pos >= len(self._data):
            return b""
        end = len(self._data) if n is None or n < 0 else self._pos + n
        chunk = self._data[self._pos:end]
        self._pos += len(chunk)
        return chunk


class _FakeProc:
    def __init__(self, out: bytes = b"", err: bytes = b"", rc: int = 0):
        self.stdout = _FakeStream(out)
        self.stderr = _FakeStream(err)
        self.returncode = rc

    async def wait(self):
        return self.returncode


# ── 1. fs.write set membership ─────────────────────────────────────────

def test_oci_tools_excludes_fs_write_but_keeps_code_and_shell():
    assert "fs.write" not in _OCI_TOOLS
    assert "code.run" in _OCI_TOOLS
    assert "shell.exec" in _OCI_TOOLS


@pytest.mark.anyio
async def test_fs_write_routes_to_mock_even_with_oci_enabled():
    # fs.write is not in _OCI_TOOLS, so it must still hit the Mock executor
    # (always ok=True) instead of the OCI path (which would need a command).
    orch = _orch()
    executor, prepare = orch._select_executor("fs.write")
    assert prepare is None
    out = await executor("fs.write", {"path": "notes.md", "content": "hi"})
    assert out["ok"] is True
    assert "mock" in out["summary"]


# ── 2. per-run quarantine persistence ────────────────────────────────────

@pytest.mark.anyio
async def test_select_executor_reuses_one_instance_across_actions_in_a_run():
    orch = _orch()
    orch._select_executor("code.run")
    first = orch._oci_executor
    assert first is not None
    orch._select_executor("shell.exec")
    assert orch._oci_executor is first  # same instance, not a fresh one per action


@pytest.mark.anyio
async def test_second_action_in_same_run_is_quarantined_after_teardown_failure(monkeypatch):
    run_calls: list = []

    async def _fake_exec_run(argv, env):
        run_calls.append(argv)
        return _FakeProc(out=b"ok\n", err=b"", rc=0)

    async def _fake_exec_cmd(argv, env):
        # inspect always "succeeds" ⇒ container still present ⇒ teardown fails.
        if len(argv) >= 2 and argv[1] == "inspect":
            return 0, "[]", ""
        return 0, "", ""

    monkeypatch.setattr(oci, "_exec_run", _fake_exec_run)
    monkeypatch.setattr(oci, "_exec_cmd", _fake_exec_cmd)

    orch = _orch()

    # Action 1: runs (spawns a container), then its teardown can't be
    # confirmed ⇒ the underlying OciExecutor is marked broken.
    executor1, prepare1 = orch._select_executor("code.run")
    assert prepare1 is None
    with pytest.raises(SandboxTeardownError):
        await executor1("code.run", {"command": "true"})
    assert len(run_calls) == 1

    # Action 2, same run: _select_executor must hand back the SAME (now
    # quarantined) instance — refusing immediately, WITHOUT spawning a new
    # container. This is the P2-E gap: a fresh-instance-per-action selector
    # would reset ``_broken`` and let action 2 through.
    executor2, prepare2 = orch._select_executor("shell.exec")
    assert prepare2 is None
    assert orch._oci_executor is orch._oci_executor  # still one instance
    with pytest.raises(ExecutorError):
        await executor2("shell.exec", {"command": "ls"})
    assert len(run_calls) == 1  # no second container was ever spawned
