"""Rootless OCI sandbox executor (PRD §Data Plane, V11, P2 exit "rootless
filesystem/process/secret/network/quota/teardown/Broker-only boundary").

Runs an R1 code/shell tool intent inside a throwaway, locked-down container and
hands the Broker a clean result dict — never a container handle. Every effect a
runtime asks for still passes through the Broker; the Broker is the ONLY caller
of ``as_broker_executor`` (runtime/orchestrator never touch a container).

Isolation is expressed entirely as ``docker run`` flags (built by
``build_run_argv``, which is pure and unit-tested without a daemon): no network,
read-only rootfs, a size-quota'd ``/scratch`` tmpfs, all capabilities dropped, a
non-root user, ``no-new-privileges``, and memory/cpu/pids caps. There is never a
host bind mount and never the docker socket, so a compromised payload cannot
read host files or reach the daemon. The wall-clock bound wraps the subprocess
in ``asyncio.wait_for``; a timeout ``docker kill``s the container and reports
``timed_out``. Ordinary jobs use ``--rm``; output jobs freeze workload processes,
stream a bounded scratch archive, and are force-removed. Both paths verify
teardown — a container that
``docker inspect`` still finds marks the executor permanently unusable, because
an un-torn-down sandbox is an isolation breach, not a warning.

Honest boundary: on macOS + colima this yields DEVELOPMENT-grade evidence only.
A production isolation gate needs a dedicated Linux runner (cgroup v2 + rootless
+ seccomp/AppArmor). This module builds the same argv either way; only the
runtime underneath differs. Dependency rule: stdlib ``subprocess``/``asyncio``
calling the ``docker`` CLI — no docker-py, no new Python dependency.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import os
import re
import shlex
import shutil
import stat
import tarfile
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Awaitable, Callable

# Host-side environment keys the ``docker`` CLI itself needs to reach the daemon
# (colima socket, config dir). This is the *launcher* process env, NOT the
# container env — the container gets only the explicit ``-e`` whitelist.
_HOST_ENV_KEYS = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "XDG_RUNTIME_DIR", "DOCKER_CONTEXT")

# How long to wait reaping a killed container after a wall-clock timeout.
_REAP_TIMEOUT_S = 5

# Per-stream capture cap (bytes). The host reads at most this much of stdout and
# of stderr into memory; anything beyond is drained-and-discarded, not buffered —
# so a container spewing continuous output (a `yes`-style oversized-output DoS)
# can never grow the backend process's memory, independent of the container's own
# --memory bound (which limits the container, not the host reading its pipe).
_MAX_STREAM_CHARS = 64 * 1024

# Chunk size for the draining reader.
_READ_CHUNK = 64 * 1024
_OUTPUT_EXIT_MARKER = "/scratch/.simverse-executor-exit"
_OUTPUT_POLL_INTERVAL_S = 0.1
_OUTPUT_ARCHIVE_OVERHEAD_BYTES = 8 * 1024 * 1024
_MAX_OUTPUT_ARCHIVE_MEMBERS = 16_384


class ExecutorError(Exception):
    """A sandbox run could not be carried out (spawn failure, unusable executor)."""


class SandboxTeardownError(ExecutorError):
    """A container could not be confirmed removed after its run. The executor is
    marked unusable: leaving a sandbox alive is an isolation breach, not a retry."""

    def __init__(self, message: str, *, proof: dict | None = None) -> None:
        super().__init__(message)
        self.proof = dict(proof or {})


class SandboxOutputError(ExecutorError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass
class SandboxLimits:
    memory_mb: int = 256
    cpus: float = 0.5
    pids: int = 128
    wall_clock_s: int = 20
    scratch_mb: int = 64
    network: str = "none"          # default: no network at all


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    teardown_proof: dict = field(default_factory=dict)
    truncated: bool = False        # a captured stream exceeded _MAX_STREAM_CHARS
    output_files: tuple["SandboxOutputFile", ...] = ()
    output_snapshot: str | None = None
    output_error_code: str | None = None


@dataclass(frozen=True)
class SandboxOutputRequest:
    output_id: str
    relative_path: str
    max_bytes: int
    required: bool = True


@dataclass(frozen=True)
class SandboxOutputFile:
    output_id: str
    relative_path: str
    host_path: str
    byte_size: int
    sha256: str


async def _exec_run(argv: list[str], env: dict) -> asyncio.subprocess.Process:
    """Spawn the container run (module-level so tests can substitute a fake)."""
    return await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
    )


async def _read_capped(stream, limit: int) -> tuple[bytes, bool]:
    """Read ``stream`` to EOF but KEEP at most ``limit`` bytes. Bytes past the cap
    are read-and-discarded (bounded transient memory, never accumulated) so a
    runaway producer cannot balloon the host — while still draining the pipe so
    the container isn't blocked on a full stdout buffer. Returns
    ``(captured_bytes, truncated)``."""
    if stream is None:
        return b"", False
    buf = bytearray()
    truncated = False
    while True:
        chunk = await stream.read(_READ_CHUNK)
        if not chunk:
            break
        if len(buf) < limit:
            keep = chunk[: limit - len(buf)]
            buf += keep
            if len(chunk) > len(keep):
                truncated = True
        else:
            truncated = True
        # loop continues: beyond the cap we keep reading `chunk` only to drain it,
        # discarding immediately — `buf` never grows past `limit`.
    return bytes(buf), truncated


async def _exec_cmd(argv: list[str], env: dict) -> tuple[int, str, str]:
    """Run a short docker control command (inspect/kill/rm), returning
    ``(returncode, stdout, stderr)``. Module-level for the same reason."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
    )
    out, err = await proc.communicate()
    return (
        proc.returncode if proc.returncode is not None else -1,
        out.decode("utf-8", "replace"),
        err.decode("utf-8", "replace"),
    )


class OciExecutor:
    def __init__(self, *, image: str, limits: SandboxLimits, runner: str = "docker",
                 user: str = "65534:65534") -> None:
        self.image = image
        self.limits = limits
        self.runner = runner
        self.user = user
        # Flipped true if a teardown cannot be confirmed — the executor then
        # refuses every further run (a leaked sandbox must not be reused).
        self._broken = False

    # ── pure argv assembly (the isolation contract; no I/O) ───────────

    def build_run_argv(self, *, name: str, argv: list[str],
                       scratch_files: dict[str, str] | None = None,
                       env: dict | None = None,
                       limits: SandboxLimits | None = None,
                       auto_remove: bool = True) -> list[str]:
        _validate_container_name(name)
        L = limits or self.limits
        cmd = [
            self.runner, "run",
            "--name", name,
            "--network", L.network,
            "--read-only",
            "--tmpfs", f"/scratch:size={L.scratch_mb}m,mode=1777",
            "--memory", f"{L.memory_mb}m",
            "--cpus", str(L.cpus),
            "--pids-limit", str(L.pids),
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            "--user", self.user,
            "--workdir", "/scratch",
        ]
        if auto_remove:
            cmd.insert(2, "--rm")
        for key, value in (env or {}).items():
            cmd += ["-e", f"{key}={value}"]
        cmd.append(self.image)
        if scratch_files:
            # Materialise files into the tmpfs from inside the container — never a
            # host bind mount. base64 keeps arbitrary content shell-safe.
            cmd += ["sh", "-c", self._scratch_prologue(scratch_files, argv)]
        else:
            cmd += list(argv)
        return cmd

    @staticmethod
    def _scratch_prologue(scratch_files: dict[str, str], argv: list[str]) -> str:
        steps: list[str] = []
        for path, content in scratch_files.items():
            target = path if path.startswith("/") else f"/scratch/{path}"
            b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
            steps.append(f"printf %s {shlex.quote(b64)} | base64 -d > {shlex.quote(target)}")
        steps.append(" ".join(shlex.quote(a) for a in argv))
        return " && ".join(steps)

    # ── execution ─────────────────────────────────────────────────────

    async def run(
        self,
        *,
        argv: list[str],
        scratch_files: dict[str, str] | None = None,
        env: dict | None = None,
        container_name: str | None = None,
        limits: SandboxLimits | None = None,
        stdout_limit: int | None = None,
        stderr_limit: int | None = None,
        on_started: Callable[[str], Awaitable[None] | None] | None = None,
        on_teardown_pending: Callable[[str], Awaitable[None] | None] | None = None,
        output_requests: tuple[SandboxOutputRequest, ...] = (),
        output_root: str | os.PathLike[str] | None = None,
    ) -> SandboxResult:
        if self._broken:
            raise ExecutorError("executor is unusable after an unverified teardown")
        stdout_limit = _MAX_STREAM_CHARS if stdout_limit is None else stdout_limit
        stderr_limit = _MAX_STREAM_CHARS if stderr_limit is None else stderr_limit
        if (
            type(stdout_limit) is not int
            or type(stderr_limit) is not int
            or stdout_limit <= 0
            or stderr_limit <= 0
        ):
            raise ValueError("stdout/stderr capture limits must be positive integers")
        self._validate_output_requests(output_requests, output_root=output_root)

        name = container_name or f"lab-oci-{uuid.uuid4().hex[:12]}"
        _validate_container_name(name)
        effective_limits = limits or self.limits
        container_argv = (
            self._output_supervisor_argv(argv) if output_requests else argv
        )
        docker_argv = self.build_run_argv(
            name=name,
            argv=container_argv,
            scratch_files=scratch_files,
            env=env,
            limits=effective_limits,
            auto_remove=not output_requests,
        )
        host_env = self._host_env()

        timed_out = False
        out_b = err_b = b""
        truncated = False
        proc = await _exec_run(docker_argv, host_env)
        try:
            if on_started is not None:
                started = on_started(name)
                if inspect.isawaitable(started):
                    await started
        except BaseException:
            await self._docker(["kill", name])
            await self._docker(["rm", "-f", name])
            await self.verify_teardown(name)
            raise
        if output_requests:
            return await self._run_with_outputs(
                proc=proc,
                name=name,
                effective_limits=effective_limits,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
                on_teardown_pending=on_teardown_pending,
                output_requests=output_requests,
                output_root=Path(output_root),
            )
        try:
            # Read stdout + stderr concurrently (both must be drained or a full
            # pipe would block the container), each capped at _MAX_STREAM_CHARS so
            # the host memory stays bounded no matter how much the container emits.
            (out_b, out_trunc), (err_b, err_trunc) = await asyncio.wait_for(
                asyncio.gather(
                    _read_capped(proc.stdout, stdout_limit),
                    _read_capped(proc.stderr, stderr_limit),
                ),
                timeout=effective_limits.wall_clock_s,
            )
            truncated = out_trunc or err_trunc
            await asyncio.wait_for(proc.wait(), timeout=_REAP_TIMEOUT_S)
            exit_code = proc.returncode if proc.returncode is not None else -1
        except asyncio.TimeoutError:
            timed_out = True
            await self._docker(["kill", name])   # TERM the runaway container
            try:
                await asyncio.wait_for(proc.wait(), timeout=_REAP_TIMEOUT_S)
            except Exception:
                pass
            exit_code = proc.returncode if proc.returncode is not None else -1
        except BaseException:
            await self._docker(["kill", name])
            await self._docker(["rm", "-f", name])
            await self.verify_teardown(name)
            raise

        try:
            if on_teardown_pending is not None:
                pending = on_teardown_pending(name)
                if inspect.isawaitable(pending):
                    await pending
        finally:
            # ``--rm`` reaps ordinary jobs after their streams reach EOF.
            await self._docker(["rm", "-f", name])
            teardown_proof = await self.verify_teardown(name)

        return SandboxResult(
            exit_code=exit_code,
            stdout=self._decode(out_b),
            stderr=self._decode(err_b),
            timed_out=timed_out,
            teardown_proof=teardown_proof,
            truncated=truncated,
        )

    @staticmethod
    def _output_supervisor_argv(argv: list[str]) -> list[str]:
        script = (
            f"umask 077; rm -f {_OUTPUT_EXIT_MARKER}; "
            '"$@"; executor_status=$?; '
            f"printf '%s\\n' \"$executor_status\" > {_OUTPUT_EXIT_MARKER}; "
            "while :; do sleep 3600; done"
        )
        return ["sh", "-c", script, "simverse-output-supervisor", *argv]

    async def _wait_for_output_exit(self, name: str) -> int:
        while True:
            return_code, stdout, _stderr = await self._docker(
                ["exec", name, "cat", _OUTPUT_EXIT_MARKER]
            )
            if return_code == 0:
                value = stdout.strip()
                if not value.isdigit() or not 0 <= int(value) <= 255:
                    raise SandboxOutputError("output_exit_marker_invalid")
                return int(value)
            await asyncio.sleep(_OUTPUT_POLL_INTERVAL_S)

    async def _run_with_outputs(
        self,
        *,
        proc: asyncio.subprocess.Process,
        name: str,
        effective_limits: SandboxLimits,
        stdout_limit: int,
        stderr_limit: int,
        on_teardown_pending: Callable[[str], Awaitable[None] | None] | None,
        output_requests: tuple[SandboxOutputRequest, ...],
        output_root: Path,
    ) -> SandboxResult:
        stdout_task = asyncio.create_task(_read_capped(proc.stdout, stdout_limit))
        stderr_task = asyncio.create_task(_read_capped(proc.stderr, stderr_limit))
        process_task = asyncio.create_task(proc.wait())
        marker_task = asyncio.create_task(self._wait_for_output_exit(name))
        timed_out = False
        exit_code = -1
        output_files: tuple[SandboxOutputFile, ...] = ()
        output_snapshot: str | None = None
        output_error_code: str | None = None
        teardown_proof: dict = {}
        stream_results: tuple[tuple[bytes, bool], tuple[bytes, bool]]
        try:
            done, _pending = await asyncio.wait(
                {marker_task, process_task},
                timeout=effective_limits.wall_clock_s,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                timed_out = True
            elif marker_task in done:
                try:
                    exit_code = marker_task.result()
                except SandboxOutputError as exc:
                    output_error_code = exc.error_code
            else:
                exit_code = process_task.result()
                output_error_code = "output_supervisor_terminated"

            if on_teardown_pending is not None:
                pending = on_teardown_pending(name)
                if inspect.isawaitable(pending):
                    await pending

            if exit_code == 0 and output_error_code is None:
                try:
                    output_files, snapshot = await self._collect_outputs(
                        name,
                        requests=output_requests,
                        output_root=output_root,
                        scratch_limit_bytes=(
                            int(effective_limits.scratch_mb) * 1024 * 1024
                        ),
                        snapshot_timeout_seconds=max(
                            1.0, float(effective_limits.wall_clock_s)
                        ),
                    )
                    output_snapshot = str(snapshot)
                except SandboxOutputError as exc:
                    output_error_code = exc.error_code
        finally:
            await self._docker(["rm", "-f", name])
            marker_task.cancel()
            if not process_task.done():
                try:
                    await asyncio.wait_for(process_task, timeout=_REAP_TIMEOUT_S)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    proc.kill()
                    await proc.wait()
            await asyncio.gather(marker_task, return_exceptions=True)
            stream_results = await asyncio.gather(stdout_task, stderr_task)
            teardown_proof = await self.verify_teardown(name)

        (out_b, out_trunc), (err_b, err_trunc) = stream_results
        return SandboxResult(
            exit_code=exit_code,
            stdout=self._decode(out_b),
            stderr=self._decode(err_b),
            timed_out=timed_out,
            teardown_proof=teardown_proof,
            truncated=out_trunc or err_trunc,
            output_files=output_files,
            output_snapshot=output_snapshot,
            output_error_code=output_error_code,
        )

    @staticmethod
    def _validate_output_requests(
        requests: tuple[SandboxOutputRequest, ...],
        *,
        output_root: str | os.PathLike[str] | None,
    ) -> None:
        if not requests:
            if output_root is not None:
                raise ValueError("output_root requires declared output requests")
            return
        if output_root is None:
            raise ValueError("declared outputs require an Executor-owned output root")
        output_ids: set[str] = set()
        paths: set[str] = set()
        for request in requests:
            parts = request.relative_path.split("/")
            if (
                not request.output_id
                or request.output_id in output_ids
                or request.relative_path in paths
                or request.relative_path.startswith("/")
                or "\\" in request.relative_path
                or any(part in {"", ".", ".."} for part in parts)
                or type(request.max_bytes) is not int
                or request.max_bytes <= 0
            ):
                raise ValueError("invalid sandbox output request")
            output_ids.add(request.output_id)
            paths.add(request.relative_path)

    async def _collect_outputs(
        self,
        container_name: str,
        *,
        requests: tuple[SandboxOutputRequest, ...],
        output_root: Path,
        scratch_limit_bytes: int,
        snapshot_timeout_seconds: float,
    ) -> tuple[tuple[SandboxOutputFile, ...], Path]:
        try:
            output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if output_root.is_symlink() or not output_root.is_dir():
                raise SandboxOutputError("output_root_invalid")
            os.chmod(output_root, 0o700)
            snapshot = Path(
                tempfile.mkdtemp(
                    prefix=f"{hashlib.sha256(container_name.encode()).hexdigest()[:16]}-",
                    dir=output_root,
                )
            )
        except SandboxOutputError:
            raise
        except OSError as exc:
            raise SandboxOutputError("output_snapshot_unavailable") from exc
        archive_path = output_root / f".{snapshot.name}.tar"
        try:
            # Docker's archive API does not expose tmpfs contents consistently
            # across runtimes (notably Docker-on-Colima). Freeze every process the
            # unprivileged workload user can signal, then stream the mounted
            # scratch tree from inside the still-running container.
            freeze_code, _freeze_stdout, _freeze_stderr = await self._docker(
                [
                    "exec",
                    "--user",
                    self.user,
                    container_name,
                    "/bin/sh",
                    "-c",
                    "kill -STOP -1",
                ]
            )
            if freeze_code != 0:
                raise SandboxOutputError("output_snapshot_freeze_failed")
            try:
                await asyncio.wait_for(
                    self._capture_output_archive(
                        container_name,
                        archive_path=archive_path,
                        max_bytes=(
                            max(1, scratch_limit_bytes)
                            + _OUTPUT_ARCHIVE_OVERHEAD_BYTES
                        ),
                    ),
                    timeout=snapshot_timeout_seconds,
                )
            except TimeoutError as exc:
                raise SandboxOutputError("output_snapshot_timeout") from exc
            await asyncio.to_thread(
                self._extract_declared_output_members,
                archive_path,
                snapshot,
                requests,
            )
            inspected = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        self._inspect_output_file,
                        snapshot,
                        request,
                    )
                    for request in requests
                )
            )
            files = tuple(item for item in inspected if item is not None)
            return files, snapshot
        except SandboxOutputError:
            shutil.rmtree(snapshot, ignore_errors=True)
            raise
        except (OSError, EOFError, tarfile.TarError) as exc:
            shutil.rmtree(snapshot, ignore_errors=True)
            raise SandboxOutputError("output_snapshot_invalid") from exc
        except BaseException:
            shutil.rmtree(snapshot, ignore_errors=True)
            raise
        finally:
            archive_path.unlink(missing_ok=True)

    async def _capture_output_archive(
        self,
        container_name: str,
        *,
        archive_path: Path,
        max_bytes: int,
    ) -> None:
        proc = await _exec_run(
            [
                self.runner,
                "exec",
                "--user",
                self.user,
                container_name,
                "/bin/tar",
                "-C",
                "/scratch",
                "-cf",
                "-",
                ".",
            ],
            self._host_env(),
        )
        stderr_task = asyncio.create_task(
            _read_capped(proc.stderr, _MAX_STREAM_CHARS)
        )
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(archive_path, flags, 0o600)
            except OSError as exc:
                raise SandboxOutputError("output_snapshot_unavailable") from exc
            observed = 0
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as archive_handle:
                    while True:
                        chunk = await proc.stdout.read(_READ_CHUNK)
                        if not chunk:
                            break
                        observed += len(chunk)
                        if observed > max_bytes:
                            raise SandboxOutputError("output_snapshot_too_large")
                        archive_handle.write(chunk)
                    archive_handle.flush()
                    os.fsync(archive_handle.fileno())
            finally:
                os.close(descriptor)
            await proc.wait()
            await stderr_task
            if proc.returncode != 0:
                raise SandboxOutputError("output_snapshot_failed")
        except BaseException:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            if not stderr_task.done():
                stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)
            raise

    @classmethod
    def _extract_declared_output_members(
        cls,
        archive_path: Path,
        snapshot: Path,
        requests: tuple[SandboxOutputRequest, ...],
    ) -> None:
        try:
            archive = tarfile.open(archive_path, mode="r:")
        except (OSError, tarfile.TarError) as exc:
            raise SandboxOutputError("output_snapshot_invalid") from exc

        with archive:
            members: dict[str, tarfile.TarInfo] = {}
            hardlink_targets: set[str] = set()
            try:
                for index, member in enumerate(archive):
                    if index >= _MAX_OUTPUT_ARCHIVE_MEMBERS:
                        raise SandboxOutputError("output_snapshot_too_many_files")
                    name = cls._normalize_archive_path(member.name)
                    if name is None:
                        continue
                    if name in members:
                        raise SandboxOutputError("output_snapshot_duplicate_path")
                    members[name] = member
                    if member.islnk():
                        target = cls._normalize_archive_path(member.linkname)
                        if target is not None:
                            hardlink_targets.add(target)
            except tarfile.TarError as exc:
                raise SandboxOutputError("output_snapshot_invalid") from exc

            for request in requests:
                cls._extract_declared_output_member(
                    archive,
                    snapshot,
                    request,
                    members=members,
                    hardlink_targets=hardlink_targets,
                )

    @staticmethod
    def _normalize_archive_path(value: str) -> str | None:
        if not value or value.startswith("/") or "\\" in value:
            raise SandboxOutputError("output_snapshot_invalid_path")
        normalized = value
        while normalized.startswith("./"):
            normalized = normalized[2:]
        normalized = normalized.rstrip("/")
        if normalized in {"", "."}:
            return None
        if any(part in {"", ".", ".."} for part in normalized.split("/")):
            raise SandboxOutputError("output_snapshot_invalid_path")
        return normalized

    @classmethod
    def _extract_declared_output_member(
        cls,
        archive: tarfile.TarFile,
        snapshot: Path,
        request: SandboxOutputRequest,
        *,
        members: dict[str, tarfile.TarInfo],
        hardlink_targets: set[str],
    ) -> None:
        parts = request.relative_path.split("/")
        for index in range(1, len(parts)):
            parent = members.get("/".join(parts[:index]))
            if parent is None:
                continue
            if parent.issym():
                raise SandboxOutputError("declared_output_symlink")
            if not parent.isdir():
                raise SandboxOutputError("declared_output_parent_invalid")

        member = members.get(request.relative_path)
        if member is None:
            if request.required:
                raise SandboxOutputError("declared_output_missing")
            return
        if member.issym():
            raise SandboxOutputError("declared_output_symlink")
        if member.islnk() or request.relative_path in hardlink_targets:
            raise SandboxOutputError("declared_output_linked")
        if not member.isreg():
            raise SandboxOutputError("declared_output_not_regular")
        if member.size < 0 or member.size > request.max_bytes:
            raise SandboxOutputError("declared_output_too_large")

        source = archive.extractfile(member)
        if source is None:
            raise SandboxOutputError("declared_output_unreadable")
        target = snapshot.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags, 0o600)
        except OSError as exc:
            raise SandboxOutputError("declared_output_unreadable") from exc
        observed = 0
        try:
            with source, os.fdopen(descriptor, "wb", closefd=False) as target_handle:
                while chunk := source.read(_READ_CHUNK):
                    observed += len(chunk)
                    if observed > request.max_bytes:
                        raise SandboxOutputError("declared_output_too_large")
                    target_handle.write(chunk)
                target_handle.flush()
                os.fsync(target_handle.fileno())
        finally:
            os.close(descriptor)
        if observed != member.size:
            raise SandboxOutputError("output_snapshot_invalid")

    @staticmethod
    def _inspect_output_file(
        snapshot: Path,
        request: SandboxOutputRequest,
    ) -> SandboxOutputFile | None:
        current = snapshot
        parts = request.relative_path.split("/")
        for index, part in enumerate(parts):
            current = current / part
            try:
                current_stat = current.lstat()
            except FileNotFoundError as exc:
                if not request.required:
                    return None
                raise SandboxOutputError("declared_output_missing") from exc
            if stat.S_ISLNK(current_stat.st_mode):
                raise SandboxOutputError("declared_output_symlink")
            if index < len(parts) - 1:
                if not stat.S_ISDIR(current_stat.st_mode):
                    raise SandboxOutputError("declared_output_parent_invalid")
            elif not stat.S_ISREG(current_stat.st_mode):
                raise SandboxOutputError("declared_output_not_regular")
        if current_stat.st_nlink != 1:
            raise SandboxOutputError("declared_output_linked")
        if current_stat.st_size > request.max_bytes:
            raise SandboxOutputError("declared_output_too_large")

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(current, flags)
        except OSError as exc:
            raise SandboxOutputError("declared_output_unreadable") from exc
        digest = hashlib.sha256()
        observed = 0
        try:
            opened_stat = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened_stat.st_mode)
                or opened_stat.st_dev != current_stat.st_dev
                or opened_stat.st_ino != current_stat.st_ino
            ):
                raise SandboxOutputError("declared_output_changed")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                while chunk := handle.read(_READ_CHUNK):
                    observed += len(chunk)
                    if observed > request.max_bytes:
                        raise SandboxOutputError("declared_output_too_large")
                    digest.update(chunk)
            final_stat = os.fstat(descriptor)
            if observed != final_stat.st_size or observed != current_stat.st_size:
                raise SandboxOutputError("declared_output_changed")
        finally:
            os.close(descriptor)
        return SandboxOutputFile(
            output_id=request.output_id,
            relative_path=request.relative_path,
            host_path=str(current),
            byte_size=observed,
            sha256=digest.hexdigest(),
        )

    def as_broker_executor(self):
        """Return an ``async (tool_name, args) -> dict`` matching the Broker's
        ``execute_action`` executor slot. Only code/shell tools reach here; the
        Broker redacts and stores the returned dict. A container handle is never
        exposed — the caller sees only exit code + captured streams + teardown
        proof."""
        async def _execute(tool_name: str, args: dict) -> dict:
            command = _command_from_args(args)
            if command is None:
                return {"tool": tool_name, "ok": False,
                        "summary": f"{tool_name}: no executable command in args"}
            res = await self.run(argv=["sh", "-c", command])
            ok = res.exit_code == 0 and not res.timed_out
            return {
                "tool": tool_name,
                "ok": ok,
                "exit_code": res.exit_code,
                "timed_out": res.timed_out,
                "stdout": res.stdout,   # already capped at capture time
                "stderr": res.stderr,
                "truncated": res.truncated,
                "summary": f"executed {tool_name} in oci sandbox (exit {res.exit_code})",
                "teardown": res.teardown_proof,
            }
        return _execute

    # ── helpers ───────────────────────────────────────────────────────

    async def _docker(self, subargv: list[str]) -> tuple[int, str, str]:
        return await _exec_cmd([self.runner] + subargv, self._host_env())

    async def inspect_container(self, name: str) -> dict:
        """Return the exact durable container state without guessing on errors."""
        _validate_container_name(name)
        rc, out, err = await self._docker(
            ["inspect", "--format", "{{json .State}}", name]
        )
        if rc == 0:
            return {"exists": True, "name": name, "state_json": out.strip()}
        if _stderr_confirms_absent(err):
            return {"exists": False, "name": name}
        raise ExecutorError(f"container inspect failed for {name}")

    async def control_container(self, name: str, action: str) -> dict:
        """Stop one deterministic job container and prove that it was removed.

        Docker control operations are deliberately idempotent: an already absent
        container is still verified through a fresh inspect before success.
        """
        _validate_container_name(name)
        if action == "cancel":
            await self._docker(["stop", "--time", "2", name])
        elif action == "terminate":
            await self._docker(["kill", "--signal", "TERM", name])
        elif action == "kill":
            await self._docker(["kill", "--signal", "KILL", name])
        else:
            raise ValueError("executor control action must be cancel, terminate, or kill")
        await self._docker(["rm", "-f", name])
        proof = await self.verify_teardown(name)
        return {**proof, "control_action": action}

    async def verify_teardown(self, name: str) -> dict:
        _validate_container_name(name)
        rc, _out, err = await self._docker(["inspect", name])
        # inspect succeeding (rc==0) always means the container is still there.
        # A non-zero rc is only "removed" when stderr confirms the object is
        # actually gone — any OTHER non-zero (daemon unresponsive, inspect
        # itself erroring) must NOT be read as "removed": that would fail-open
        # a still-live sandbox as torn down. Fall through to quarantine instead.
        removed = rc != 0 and _stderr_confirms_absent(err)
        proof = {"removed": removed, "name": name, "checked_at": datetime.now(UTC).isoformat()}
        if not removed:
            self._broken = True
            proof["error"] = "teardown_unverified"
            raise SandboxTeardownError(
                f"container {name} still present after run", proof=proof
            )
        return proof

    async def ready(self) -> bool:
        """Fail-closed OCI daemon probe used by the Executor readiness endpoint."""
        if self._broken:
            return False
        rc, _out, _err = await self._docker(["info", "--format", "{{.ServerVersion}}"])
        if rc != 0:
            return False
        image_rc, _image_out, _image_err = await self._docker(
            ["image", "inspect", self.image]
        )
        return image_rc == 0

    @property
    def broken(self) -> bool:
        return self._broken

    @property
    def configured_image_digest(self) -> str | None:
        match = re.search(r"(?:@|^)(sha256:[0-9a-f]{64})\Z", self.image)
        return None if match is None else match.group(1)

    @staticmethod
    def _host_env() -> dict:
        return {k: os.environ[k] for k in _HOST_ENV_KEYS if k in os.environ}

    @staticmethod
    def _decode(data: bytes) -> str:
        return (data or b"").decode("utf-8", "replace")


_ABSENT_MARKERS = ("no such object", "no such container")
_CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


def _stderr_confirms_absent(stderr: str) -> bool:
    """True only when ``docker inspect``'s stderr explicitly says the
    container doesn't exist. Any other non-zero (daemon down, inspect itself
    failing) is NOT confirmation of removal — see ``_verify_teardown``."""
    lowered = (stderr or "").lower()
    return any(marker in lowered for marker in _ABSENT_MARKERS)


def deterministic_container_name(job_id: str) -> str:
    """Map an externally durable job id to one bounded OCI locator."""
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job_id is required")
    return f"lab-oci-{hashlib.sha256(job_id.encode('utf-8')).hexdigest()[:24]}"


def _validate_container_name(name: str) -> None:
    if not isinstance(name, str) or _CONTAINER_NAME_RE.fullmatch(name) is None:
        raise ValueError("invalid OCI container name")


def command_from_args(args: dict) -> str | None:
    """Extract the shell command a code/shell tool wants to run."""
    if not isinstance(args, dict):
        return None
    for key in ("command", "code", "script", "cmd"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


# Backward-compatible private name retained for existing imports and tests.
_command_from_args = command_from_args
