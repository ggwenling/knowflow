import asyncio
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import MagicMock

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/local_backend_e2e.py"
spec = importlib.util.spec_from_file_location("local_backend_e2e", SCRIPT)
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)


@pytest.mark.parametrize(("unfinished", "cleanup", "error"), [
    (0, 0, None),
    (1, 0, "LOCAL_DATABASE_HAS_UNFINISHED_INDEX_TASKS"),
    (0, 1, "LOCAL_DATABASE_HAS_PENDING_CLEANUP"),
])
def test_replay_requires_an_idle_database(monkeypatch, unfinished, cleanup, error):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = (unfinished, cleanup)
    monkeypatch.setattr(e2e.psycopg, "connect", lambda *args, **kwargs: connection)

    if error:
        with pytest.raises(RuntimeError, match=error):
            e2e.require_idle_database("local-test-database")
    else:
        e2e.require_idle_database("local-test-database")


def test_replay_waits_for_document_cleanup_before_shutdown(monkeypatch):
    pending = {"chunk_rows": 1, "embedding_rows": 1, "cancellation_outbox_rows": 0,
               "storage_outbox_rows": 1, "index_outbox_rows": 1}
    cleared = dict.fromkeys(pending, 0)
    observations = iter([pending, cleared])
    monkeypatch.setattr(e2e, "db_counts", lambda *args: next(observations))

    assert e2e.wait_document_cleanup("database", "document", "task", timeout=2) == cleared


@pytest.mark.asyncio
async def test_blocking_synthetic_adapter_records_cancellation_before_close(monkeypatch, tmp_path):
    marker = tmp_path / "events"
    monkeypatch.setenv("KNOWFLOW_SYNTHETIC_STARTED_FILE", str(marker))
    adapter = e2e.SyntheticEmbedding()
    task = asyncio.create_task(adapter.embed([e2e.BLOCK_MARKER], request_id="test"))
    await asyncio.sleep(0)
    assert marker.read_text(encoding="utf-8").splitlines() == ["started"]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await adapter.aclose()
    assert marker.read_text(encoding="utf-8").splitlines() == ["started", "cancelled", "closed"]


@pytest.mark.skipif(os.name != "nt", reason="Windows taskkill exit handling")
@pytest.mark.parametrize("exited", [True, False])
def test_stop_handles_taskkill_error_after_process_exit(monkeypatch, exited):
    process = MagicMock()
    process.pid = 123
    process.poll.side_effect = [None, 0 if exited else None]

    def failed_taskkill(command, **kwargs):
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(255, command)
        return subprocess.CompletedProcess(command, 255)

    monkeypatch.setattr(e2e.subprocess, "run", failed_taskkill)
    if exited:
        e2e.stop(process)
        process.wait.assert_called_once()
    else:
        with pytest.raises(subprocess.CalledProcessError):
            e2e.stop(process)


@pytest.mark.skipif(os.name != "nt", reason="Windows launchers can leave child processes")
def test_stop_reaps_a_launcher_and_its_child(tmp_path):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    pid_file = tmp_path / "child.pid"
    launcher = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(120)"
    )
    parent = subprocess.Popen([sys.executable, "-c", launcher, str(pid_file)],
                              creationflags=subprocess.CREATE_NO_WINDOW)
    child_handle = None
    try:
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert pid_file.exists()
        child_handle = kernel.OpenProcess(0x100000 | 0x0001, False, int(pid_file.read_text()))
        assert child_handle
        e2e.stop(parent)
        assert kernel.WaitForSingleObject(child_handle, 3000) == 0
    finally:
        if child_handle:
            if kernel.WaitForSingleObject(child_handle, 0) != 0:
                kernel.TerminateProcess(child_handle, 1)
            kernel.CloseHandle(child_handle)
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
