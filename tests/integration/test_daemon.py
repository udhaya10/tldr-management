"""
Daemon startup integration test.

Starts the tldr daemon, inspects what it creates in $TMPDIR, parses the
filename to extract the session hash, and records all captured values as a
DaemonInfo dataclass so downstream tests can use them.

Daemon files created in $TMPDIR:
  tldr-<8hex>.sock   Unix socket
  tldr-<8hex>.pid    PID file (plain integer)

Start response (JSON):
  { "status": "ok", "pid": <int>, "socket": "<path>", "message": "..." }
"""

import dataclasses
import json
import os
import re
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import sh

from tests.conftest import msg, requires_tldr

pytestmark = [pytest.mark.integration, requires_tldr]

TMPDIR = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
FILENAME_RE = re.compile(r"^tldr-(?P<hash>[0-9a-f]{8})\.(?P<ext>pid|sock)$")

_tldr = sh.Command("tldr")


@dataclasses.dataclass(frozen=True)
class DaemonFilename:
    hash: str
    ext: str


def parse_daemon_filename(name: str) -> DaemonFilename | None:
    """Parse a daemon filename; returns DaemonFilename or None if it doesn't match."""
    match = FILENAME_RE.match(name)
    if not match:
        return None
    return DaemonFilename(hash=match.group("hash"), ext=match.group("ext"))


# ── data model ────────────────────────────────────────────────────────────

@dataclasses.dataclass
class DaemonInfo:
    """All values captured from daemon start + filesystem inspection."""

    # from JSON start response
    status:      str
    pid:         int
    socket_path: Path
    message:     str

    # parsed from filename
    session_hash: str

    @property
    def sock_file(self) -> Path:
        return self.socket_path

    @property
    def pid_file(self) -> Path:
        return self.socket_path.with_suffix(".pid")

    @property
    def pid_from_file(self) -> int:
        return int(self.pid_file.read_text().strip())


# ── fixture ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def daemon_info() -> Generator[DaemonInfo, None, None]:
    """Start the daemon, yield DaemonInfo, stop cleanly on teardown."""
    raw      = _tldr("daemon", "start", "--format", "json")
    data     = json.loads(str(raw))
    socket   = Path(data["socket"])
    parsed   = parse_daemon_filename(socket.name)

    info = DaemonInfo(
        status=data["status"],
        pid=data["pid"],
        socket_path=socket,
        message=data["message"],
        session_hash=parsed.hash if parsed else "",
    )

    yield info

    try:
        _tldr("daemon", "stop")
    except sh.ErrorReturnCode:
        pass


# ── tests ─────────────────────────────────────────────────────────────────

class TestDaemonStartup:
    """Validates daemon startup response, file creation, and filename structure."""

    def test_start_status_is_ok(self, daemon_info):
        assert daemon_info.status == "ok", msg(
            "Daemon start did not return ok",
            status=daemon_info.status,
            message=daemon_info.message,
        )

    def test_start_response_has_positive_pid(self, daemon_info):
        assert daemon_info.pid > 0, msg(
            "Daemon start returned invalid PID",
            pid=daemon_info.pid,
        )

    def test_sock_file_exists_in_tmpdir(self, daemon_info):
        assert daemon_info.sock_file.exists(), msg(
            "Daemon socket file not found",
            expected=daemon_info.sock_file,
            tmpdir=TMPDIR,
        )
        assert daemon_info.sock_file.parent == TMPDIR, msg(
            "Socket file is not inside $TMPDIR",
            actual=daemon_info.sock_file.parent,
            expected=TMPDIR,
        )

    def test_pid_file_exists_alongside_sock(self, daemon_info):
        assert daemon_info.pid_file.exists(), msg(
            "PID file not found alongside socket",
            expected=daemon_info.pid_file,
        )

    def test_filename_matches_pattern(self, daemon_info):
        assert parse_daemon_filename(daemon_info.sock_file.name) is not None, msg(
            "Socket filename does not match expected pattern",
            filename=daemon_info.sock_file.name,
            pattern=FILENAME_RE.pattern,
        )

    def test_session_hash_is_8_hex_chars(self, daemon_info):
        assert re.fullmatch(r"[0-9a-f]{8}", daemon_info.session_hash), msg(
            "Session hash is not 8 lowercase hex characters",
            session_hash=repr(daemon_info.session_hash),
        )

    def test_pid_file_matches_start_response(self, daemon_info):
        assert daemon_info.pid_from_file == daemon_info.pid, msg(
            "PID in file does not match PID from start response",
            from_file=daemon_info.pid_from_file,
            from_response=daemon_info.pid,
        )

    def test_captured_values(self, daemon_info, capsys):
        """Print all captured values — visible with pytest -s."""
        with capsys.disabled():
            print(f"\n  status        : {daemon_info.status}")
            print(f"  pid           : {daemon_info.pid}")
            print(f"  session_hash  : {daemon_info.session_hash}")
            print(f"  sock_file     : {daemon_info.sock_file}")
            print(f"  pid_file      : {daemon_info.pid_file}")
            print(f"  pid_from_file : {daemon_info.pid_from_file}")
