"""Fixtures for the interop suite: a real ``indiserver`` and real libindi drivers.

Every other test in this repository feeds our serializer into our own parser, which
is self-consistent by construction and so cannot catch a deviation from the spec.
These tests put libindi on the other side of the wire instead: real drivers whose
XML we did not write, and libindi's own client tools as an oracle for ours.

The whole package skips when ``indiserver`` is not on the PATH, so a contributor
without libindi installed still gets a green ``pytest``. CI installs it nightly; see
``.github/workflows/interop.yml``.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

INDISERVER = shutil.which("indiserver")
INDI_GETPROP = shutil.which("indi_getprop")
INDI_SETPROP = shutil.which("indi_setprop")

if INDISERVER is None:  # pragma: no cover - depends on the machine, not the code
    pytest.skip(
        "libindi is not installed (no indiserver on PATH); see tests/interop/README.md",
        allow_module_level=True,
    )

REPO_ROOT = Path(__file__).resolve().parents[2]

# Long enough for a C++ driver to start and define its properties on a loaded CI
# runner, short enough that a genuine hang still fails the job rather than hitting
# the workflow timeout with no useful output.
STARTUP_TIMEOUT = 20.0


def free_port() -> int:
    """Return a TCP port that is free right now.

    Returns
    -------
    port : int
        A port number nothing is listening on.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class Server:
    """A running ``indiserver`` and the port it listens on."""

    port: int
    process: subprocess.Popen[bytes]
    log: Path

    def stop(self) -> None:
        """Terminate the server, escalating to a kill if it ignores SIGTERM."""
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - only on a wedged server
            self.process.kill()
            self.process.wait(timeout=5)

    def output(self) -> str:
        """Return whatever the server wrote to stdout and stderr so far."""
        return self.log.read_text(errors="replace") if self.log.exists() else ""


def _wait_until_listening(port: int, server: Server) -> None:
    """Block until the server accepts a connection, or fail the test.

    Parameters
    ----------
    port : int
        The port to poll.
    server : Server
        The server being waited on, used for its log if it dies early.

    Raises
    ------
    AssertionError
        If the server exits or never starts listening within the timeout.
    """
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if server.process.poll() is not None:
            raise AssertionError(f"indiserver exited early:\n{server.output()}")
        with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.25):
            return
        time.sleep(0.1)
    raise AssertionError(f"indiserver never listened on {port}:\n{server.output()}")


@pytest.fixture
def indi_server(tmp_path: Path) -> Iterator[Callable[..., Server]]:
    """Return a factory that starts ``indiserver`` with the given drivers.

    Parameters
    ----------
    tmp_path : Path
        Per-test temporary directory, used for the server log.

    Yields
    ------
    start : callable
        ``start(*drivers)`` runs ``indiserver`` with those driver executables and
        returns a :class:`Server` once it is accepting connections.
    """
    servers: list[Server] = []

    def start(*drivers: str) -> Server:
        """Start indiserver with the named drivers and wait for it to listen."""
        port = free_port()
        log = tmp_path / f"indiserver-{port}.log"
        handle = log.open("wb")
        # A libindi driver persists some properties the moment a client writes
        # them - INDI::CCD saves CCD_TRANSFER_FORMAT and CCD_COMPRESSION itself -
        # into $HOME/.indi/<device>_config.xml, and loads them again at startup.
        # Shared, that makes one test's write the next test's starting state
        # across a fresh indiserver and a fresh driver process, which is order
        # dependence with nothing in either test to point at. A per-test HOME is
        # what keeps every server here starting from the driver's own defaults.
        home = tmp_path / f"home-{port}"
        home.mkdir()
        env = dict(os.environ, HOME=str(home))
        # -v gives one line per driver event, which is what makes a failure here
        # diagnosable from CI logs alone.
        process = subprocess.Popen(
            [str(INDISERVER), "-v", "-p", str(port), *drivers],
            stdout=handle,
            stderr=subprocess.STDOUT,
            cwd=REPO_ROOT,
            env=env,
        )
        server = Server(port=port, process=process, log=log)
        servers.append(server)
        _wait_until_listening(port, server)
        return server

    yield start

    for server in servers:
        server.stop()


@pytest.fixture
def python_driver(tmp_path: Path) -> Callable[[str], str]:
    """Return a factory wrapping one of our Python drivers for ``indiserver``.

    ``indiserver`` launches a driver as a child executable, so it needs a file it
    can exec. Going through the running interpreter rather than the driver's own
    shebang keeps the driver in whichever virtualenv the tests are using, instead
    of whichever ``python3`` happens to be first on PATH.

    Parameters
    ----------
    tmp_path : Path
        Per-test temporary directory, used for the wrapper script.

    Returns
    -------
    wrap : callable
        ``wrap("examples/flat_panel.py")`` returns a path to run as a driver.
    """

    def wrap(relative_path: str) -> str:
        """Write an executable shim that runs one driver under this interpreter."""
        driver = REPO_ROOT / relative_path
        script = tmp_path / f"run-{Path(relative_path).stem}.sh"
        script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{driver}"\n')
        script.chmod(script.stat().st_mode | 0o111)
        return str(script)

    return wrap


def getprop(port: int, *specs: str, timeout: float = 5.0) -> dict[str, str]:
    """Read properties from a server with libindi's own client tool.

    This is the oracle: it is the same code path every other INDI client uses, so
    agreement with it is evidence our wire output is right rather than merely
    self-consistent.

    Parameters
    ----------
    port : int
        The server's port.
    specs : str
        ``device.property.element`` patterns; all properties when empty.
    timeout : float, optional
        Seconds to let the tool wait for responses.

    Returns
    -------
    values : dict
        Fully qualified name to value, one entry per reported line.
    """
    assert INDI_GETPROP is not None, "indi_getprop missing but indiserver present"
    result = subprocess.run(
        [INDI_GETPROP, "-h", "127.0.0.1", "-p", str(port), "-t", str(int(timeout)), *specs],
        capture_output=True,
        text=True,
        timeout=timeout + 15,
    )
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, sep, value = line.partition("=")
        if sep:
            values[name.strip()] = value.strip()
    return values


def setprop(port: int, spec: str, kind: str = "-s", timeout: float = 5.0) -> None:
    """Write a property with libindi's own client tool.

    Parameters
    ----------
    port : int
        The server's port.
    spec : str
        ``device.property.element=value``.
    kind : str, optional
        Type flag: ``-s`` switch, ``-n`` number, ``-x`` text.
    timeout : float, optional
        Seconds to let the tool wait.

    Raises
    ------
    AssertionError
        If the tool reports a failure.
    """
    assert INDI_SETPROP is not None, "indi_setprop missing but indiserver present"
    result = subprocess.run(
        [INDI_SETPROP, "-h", "127.0.0.1", "-p", str(port), "-t", str(int(timeout)), kind, spec],
        capture_output=True,
        text=True,
        timeout=timeout + 15,
    )
    assert result.returncode == 0, f"indi_setprop failed for {spec!r}: {result.stderr}"


async def wait_until(predicate: Callable[[], bool], seconds: float = 20.0) -> bool:
    """Poll a predicate until it holds, or the timeout expires.

    Everything here waits on a real subprocess, so there is nothing to await on and
    no event to be signalled by: polling is the only option.

    Parameters
    ----------
    predicate : callable
        Called repeatedly; polling stops when it returns true.
    seconds : float, optional
        How long to keep trying.

    Returns
    -------
    satisfied : bool
        Whether the predicate held before the timeout.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline:  # noqa: ASYNC110 - external process, nothing to await
        if predicate():
            return True
        await asyncio.sleep(0.2)
    return predicate()


def env_without_display() -> dict[str, str]:
    """Return an environment safe for launching headless helpers.

    Returns
    -------
    env : dict
        A copy of the current environment with ``DISPLAY`` removed.
    """
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    return env
