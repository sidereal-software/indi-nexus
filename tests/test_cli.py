"""Tests for the ``indi-nexus`` CLI."""

from __future__ import annotations

import asyncio
import runpy
import sys
import warnings

import pytest
import typer
import uvicorn
from typer.testing import CliRunner

import indi_nexus.cli
from examples.demo_device import Demo
from indi_nexus.cli import app, load_device
from indi_nexus.client import PropertyEvent
from indi_nexus.protocol import IPState, Number, NumberVector

runner = CliRunner()


def test_load_device_resolves_a_device_subclass():
    """A valid module:attr spec resolves to the Device subclass."""
    assert load_device("examples.demo_device:Demo") is Demo


def test_load_device_rejects_bad_spec():
    """A spec without a colon is rejected."""
    with pytest.raises(typer.BadParameter):
        load_device("examples.demo_device")


def test_load_device_rejects_non_device():
    """A target that is not a Device subclass is rejected."""
    with pytest.raises(typer.BadParameter):
        load_device("examples.demo_device:Number")  # not defined / not a Device


def test_load_device_rejects_unimportable_module():
    """An unimportable module is reported as a bad parameter."""
    with pytest.raises(typer.BadParameter):
        load_device("indi_nexus.does_not_exist:Thing")


def test_help_lists_all_commands():
    """--help shows the serve, run, and monitor subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "run" in result.output
    assert "monitor" in result.output


def test_run_rejects_bad_spec_via_cli():
    """`run` with a malformed spec exits non-zero with a helpful message."""
    result = runner.invoke(app, ["run", "not-a-spec"])
    assert result.exit_code != 0


def test_run_invokes_the_device_entrypoint(monkeypatch):
    """`run` resolves the spec and calls the Device subclass's run()."""
    calls: list[str] = []
    monkeypatch.setattr(Demo, "run", classmethod(lambda cls, name=None: calls.append(cls.__name__)))
    result = runner.invoke(app, ["run", "examples.demo_device:Demo"])
    assert result.exit_code == 0
    assert calls == ["Demo"]


def test_serve_hands_the_app_to_uvicorn(monkeypatch):
    """`serve` builds the web app and passes host/port to uvicorn.run."""
    captured: dict[str, object] = {}

    def fake_run(application, *, host, port):
        """Capture the app and bind options uvicorn.run was given."""
        captured["app"] = application
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)
    result = runner.invoke(
        app,
        ["serve", "--host", "127.0.0.2", "--port", "9123", "--indi-host", "up", "--indi-port", "7"],
    )
    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.2"
    assert captured["port"] == 9123
    assert captured["app"].title == "INDINexus web bridge"


def test_serve_refuses_a_network_bind_with_no_token(monkeypatch):
    """A bind anything else can reach needs a token, or an explicit override.

    ``/ws`` is the whole write surface: a frame there becomes an INDI ``new*``
    that moves hardware. Binding it to the network unauthenticated is a choice,
    not a default, so the command names the flag and stops.
    """
    started: list[object] = []
    monkeypatch.setattr(uvicorn, "run", lambda application, **kw: started.append(application))

    refused = runner.invoke(app, ["serve", "--host", "0.0.0.0"])
    assert refused.exit_code != 0
    assert "--allow-insecure-bind" in refused.output
    assert started == []

    assert runner.invoke(app, ["serve", "--host", "0.0.0.0", "--token", "x"]).exit_code == 0
    assert (
        runner.invoke(app, ["serve", "--host", "0.0.0.0", "--allow-insecure-bind"]).exit_code == 0
    )
    assert runner.invoke(app, ["serve", "--host", "127.0.0.1"]).exit_code == 0
    assert len(started) == 3


class _FakeMonitorClient:
    """A stand-in IndiClient that replays two events into the subscriber."""

    def __init__(self, host, port, **kwargs):
        """Accept and ignore the connection arguments."""

    async def __aenter__(self):
        """Return the fake client unchanged."""
        return self

    async def __aexit__(self, *exc):
        """Do nothing on exit."""

    def subscribe(self, callback):
        """Deliver one vector-carrying event and one del event to ``callback``."""
        vec = NumberVector(
            device="CCD",
            name="EXPOSURE",
            state=IPState.OK,
            elements=[Number(name="secs", value=1.0)],
        )
        callback(PropertyEvent("set", "CCD", "EXPOSURE", vec))
        callback(PropertyEvent("del", "CCD", "EXPOSURE", None))


class _InterruptingEvent:
    """An asyncio.Event stand-in whose wait raises KeyboardInterrupt."""

    async def wait(self):
        """Raise KeyboardInterrupt instead of blocking forever."""
        raise KeyboardInterrupt


class _AsyncioProxy:
    """A pass-through for the asyncio module that swaps in a fake Event."""

    def __getattr__(self, name):
        """Delegate to the real asyncio, except for Event."""
        if name == "Event":
            return _InterruptingEvent
        return getattr(asyncio, name)


def test_monitor_prints_events_until_interrupted(monkeypatch):
    """`monitor` subscribes, prints each event, and exits on interrupt."""
    monkeypatch.setattr("indi_nexus.client.IndiClient", _FakeMonitorClient)
    monkeypatch.setattr(indi_nexus.cli, "asyncio", _AsyncioProxy())
    result = runner.invoke(app, ["monitor", "--host", "h", "--port", "1"])
    assert result.exit_code == 0
    assert "[set] CCD.EXPOSURE (Ok)" in result.output
    assert "[del] CCD.EXPOSURE" in result.output


def test_module_entrypoint_runs_the_app(monkeypatch):
    """Executing the module as __main__ invokes the Typer app."""
    monkeypatch.setattr(sys, "argv", ["indi-nexus", "--help"])
    with warnings.catch_warnings():
        # runpy warns that the module is already imported; expected here.
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_module("indi_nexus.cli", run_name="__main__")
    assert excinfo.value.code == 0


def test_new_scaffolds_a_runnable_driver(tmp_path):
    """`indi-nexus new` writes an executable driver that actually serves.

    The generated file is imported and driven over an in-memory runtime -
    getProperties defines its properties and a switch write round-trips -
    so the template can never rot into a broken starting point.
    """
    import importlib.util

    from indi_nexus.driver import Device, DriverRuntime
    from indi_nexus.protocol import DefVector, parse_indi

    target = tmp_path / "roof_driver.py"
    result = runner.invoke(app, ["new", str(target)])
    assert result.exit_code == 0, result.output
    assert "roof_driver:RoofDriver" in result.output
    assert target.stat().st_mode & 0o111  # executable, ready for indiserver

    spec = importlib.util.spec_from_file_location("roof_driver", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    device = module.RoofDriver()
    assert isinstance(device, Device)
    assert device.device == "Roof Driver"

    async def scenario():
        """Serve the scaffolded driver over in-memory pipes."""
        inbox = asyncio.Queue()
        outputs = []

        async def read():
            return await inbox.get()

        async def write(data):
            outputs.append(data)

        inbox.put_nowait(b"<getProperties version='1.7'/>")
        inbox.put_nowait(
            b"<newSwitchVector device='Roof Driver' name='CONNECTION'>"
            b"<oneSwitch name='CONNECT'>On</oneSwitch></newSwitchVector>"
        )
        inbox.put_nowait(
            b"<newSwitchVector device='Roof Driver' name='POWER'>"
            b"<oneSwitch name='ON'>On</oneSwitch></newSwitchVector>"
        )
        inbox.put_nowait(b"")
        await DriverRuntime(device, read, write).serve()
        return parse_indi(b"".join(outputs))

    messages = asyncio.run(scenario())
    defined = {m.vector.name for m in messages if isinstance(m, DefVector)}
    assert {"CONNECTION", "TELEMETRY", "POWER"} <= defined
    assert device.connected is True
    assert b"Power turned on." in b"".join(
        m.message.encode() for m in messages if hasattr(m, "message") and m.message
    )


def test_new_refuses_to_overwrite():
    """`indi-nexus new` never clobbers an existing file."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".py") as existing:
        result = runner.invoke(app, ["new", existing.name])
        assert result.exit_code != 0
        assert "refusing to overwrite" in result.output
