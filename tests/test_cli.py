"""Tests for the ``indikit`` CLI."""

from __future__ import annotations

import asyncio
import logging
import os
import runpy
import sys
import warnings

import pytest
import typer
import uvicorn
from typer.testing import CliRunner

import indikit.cli
import indikit.logging_config as logging_config
import indikit.web
from examples.demo_device import Demo
from examples.flat_panel import FlatPanel
from indikit.cli import app, load_device
from indikit.client import PropertyEvent
from indikit.driver import Device
from indikit.logging_config import WIRE_LOGGER
from indikit.protocol import IPState, Number, NumberVector
from indikit.settings import settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """Run every CLI test against an empty ``INDIKIT_*`` environment.

    The CLI reads the whole of it through :func:`indikit.settings.settings`,
    which is cached for the life of the process, so without this a developer with
    ``INDIKIT_TOKEN`` set would see the access-control tests pass or fail on
    their shell, and the cache would carry one test's variables into the next.
    ``monkeypatch`` restores whatever was there afterwards, so a deliberate
    ``INDIKIT_UPDATE_GOLDEN=1 uv run pytest`` still reaches the tests that
    read it.
    """
    for name in [key for key in dict(os.environ) if key.startswith("INDIKIT_")]:
        monkeypatch.delenv(name, raising=False)
    settings.cache_clear()
    yield
    settings.cache_clear()


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
        load_device("indikit.does_not_exist:Thing")


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
    """`run` resolves the spec, instantiates it, and serves it over stdio."""
    served: list[list[Device]] = []
    monkeypatch.setattr(indikit.cli, "run_devices", served.append)
    result = runner.invoke(app, ["run", "examples.demo_device:Demo"])
    assert result.exit_code == 0
    assert [type(device) for device in served[0]] == [Demo]
    # The name=None path a bare spec takes: the class-level device name stands.
    assert served[0][0].device == Demo.name


def test_run_serves_several_drivers_on_one_stream(monkeypatch):
    """`run` with several specs puts every named device on one runtime."""
    served: list[list[Device]] = []
    monkeypatch.setattr(indikit.cli, "run_devices", served.append)
    result = runner.invoke(
        app, ["run", "examples.demo_device:Demo", "examples.flat_panel:FlatPanel"]
    )
    assert result.exit_code == 0
    assert [type(device) for device in served[0]] == [Demo, FlatPanel]


def test_serve_hands_the_app_to_uvicorn(monkeypatch):
    """`serve` builds the web app and passes host/port to uvicorn.run."""
    captured: dict[str, object] = {}

    def fake_run(application, *, host, port, log_level):
        """Capture the app and bind options uvicorn.run was given."""
        captured["app"] = application
        captured["host"] = host
        captured["port"] = port
        captured["log_level"] = log_level

    monkeypatch.setattr(uvicorn, "run", fake_run)
    result = runner.invoke(
        app,
        ["serve", "--host", "127.0.0.2", "--port", "9123", "--indi-host", "up", "--indi-port", "7"],
    )
    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.2"
    assert captured["port"] == 9123
    assert captured["log_level"] == "info"
    assert captured["app"].title == "INDIkit web bridge"


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


# --------------------------------------------------------------------------- #
# Access control: --token / --allow-origin / --allow-insecure-bind             #
# --------------------------------------------------------------------------- #
def _serve_capturing_create_app(monkeypatch, args):
    """Invoke ``serve`` with uvicorn and the app factory stubbed out.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The patcher to install the stubs with.
    args : list of str
        The arguments after ``serve``.

    Returns
    -------
    captured : dict
        The keyword arguments ``create_app`` was called with.
    """
    captured: dict[str, object] = {}

    def fake_create_app(**kwargs):
        """Record how the bridge was configured and stand in for the app."""
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(indikit.web, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", lambda application, **kw: None)
    result = runner.invoke(app, ["serve", *args])
    assert result.exit_code == 0, result.output
    return captured


def test_the_access_control_environment_is_read(monkeypatch):
    """The three ``serve`` options are ``Settings`` fields like everything else.

    They used to be Typer ``envvar=`` reads. This is the same environment
    reaching the same place through the one reader - and it proves the values
    are not baked into the option defaults at import time, since this module was
    imported long before the fixture emptied the environment.
    """
    monkeypatch.setenv("INDIKIT_TOKEN", "from-the-environment")
    monkeypatch.setenv("INDIKIT_ALLOWED_ORIGINS", "http://a http://b")
    captured = _serve_capturing_create_app(monkeypatch, [])
    assert captured["token"] == "from-the-environment"
    assert captured["allowed_origins"] == ("http://a", "http://b")


def test_an_explicit_flag_beats_the_environment(monkeypatch):
    """One rule for all three: the flag is this invocation, the variable is the box."""
    monkeypatch.setenv("INDIKIT_TOKEN", "from-the-environment")
    monkeypatch.setenv("INDIKIT_ALLOWED_ORIGINS", "http://a http://b")
    captured = _serve_capturing_create_app(
        monkeypatch,
        ["--token", "from-the-flag", "--allow-origin", "http://c"],
    )
    assert captured["token"] == "from-the-flag"
    assert captured["allowed_origins"] == ("http://c",)


def test_an_empty_token_flag_turns_a_configured_token_off(monkeypatch):
    """``--token ""`` is a choice, not a missing flag, so it wins.

    Without the ``None`` sentinel an empty string would be indistinguishable
    from "not given" and the environment would silently win instead.
    """
    monkeypatch.setenv("INDIKIT_TOKEN", "from-the-environment")
    captured = _serve_capturing_create_app(monkeypatch, ["--token", ""])
    assert captured["token"] == ""


def test_the_origin_flag_is_still_repeatable(monkeypatch):
    """Both forms survive: repeated on the command line, space separated in the box."""
    captured = _serve_capturing_create_app(
        monkeypatch, ["--allow-origin", "http://a", "--allow-origin", "http://b"]
    )
    assert captured["allowed_origins"] == ("http://a", "http://b")


def test_no_option_reads_the_environment_through_typer():
    """``Settings`` is the one reader, so no Click parameter may carry an envvar.

    Checked on the built Click command rather than on the Python signature,
    because that is where a stray ``envvar=`` would actually take effect - and
    it catches every subcommand, including ones added later.
    """
    command = typer.main.get_command(app)
    stack = [command]
    offenders = []
    while stack:
        current = stack.pop()
        offenders += [
            f"{current.name}.{param.name}={param.envvar}"
            for param in current.params
            if param.envvar is not None
        ]
        stack += list(getattr(current, "commands", {}).values())
    assert offenders == []


def test_the_logging_flags_default_to_the_environment(monkeypatch, restore_logging):
    """``--log-level`` and ``--wire`` go through ``Settings`` like everything else.

    They are the two a driver needs with no CLI in the loop, so they were always
    ``Settings`` fields; this is the CLI reading the same field instead of
    parsing the same variable a second time.
    """
    monkeypatch.setenv("INDIKIT_LOG_LEVEL", "error")
    monkeypatch.setenv("INDIKIT_WIRE_LOG", "1")
    _serve_capturing_uvicorn(monkeypatch, ["serve"])
    assert logging.getLogger().level == logging.ERROR
    assert logging.getLogger(WIRE_LOGGER).isEnabledFor(logging.DEBUG)


def test_serve_help_still_lists_the_access_control_flags():
    """Moving the reader must not move the options out of the help.

    An operator finds these by typing ``--help``, so each one names its variable
    there as well.
    """
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    output = " ".join(result.output.split())
    for flag, variable in [
        ("--token", "INDIKIT_TOKEN"),
        ("--allow-origin", "INDIKIT_ALLOWED_ORIGINS"),
        ("--allow-insecure-bind", "INDIKIT_ALLOW_INSECURE_BIND"),
    ]:
        assert flag in output
        assert variable in output


def test_the_help_reads_the_same_on_a_narrow_ci_terminal(monkeypatch):
    """The assertions above must not depend on how wide the developer's shell is.

    Typer sizes its help from the terminal and colours it whenever it believes it
    is on CI, and neither shows up locally. Wrapping splits a long flag mid-name
    and colour splits even a short one into escape-separated runs, so every
    assertion matching on rendered CLI output silently stops checking anything.
    A narrow width and CI's own marker together are the environment that broke it.
    """
    monkeypatch.setenv("COLUMNS", "40")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    output = runner.invoke(app, ["serve", "--help"]).output

    assert "\x1b" not in output, "Typer coloured its help into a pipe with no terminal"
    for flag in ("--token", "--allow-origin", "--allow-insecure-bind"):
        assert flag in output, f"{flag} was wrapped or styled apart"


def test_a_token_from_the_environment_satisfies_the_security_refusal(monkeypatch):
    """The refusal is a security control, and it now has a second way in.

    A token set in the environment authenticates the bind exactly as ``--token``
    does; anything else would mean a container configured entirely by
    environment could not serve on ``0.0.0.0`` at all.
    """
    monkeypatch.setattr(uvicorn, "run", lambda application, **kw: None)

    monkeypatch.setenv("INDIKIT_TOKEN", "x")
    settings.cache_clear()
    assert runner.invoke(app, ["serve", "--host", "0.0.0.0"]).exit_code == 0

    # And an empty one does not: the variable is present but says "no token".
    monkeypatch.setenv("INDIKIT_TOKEN", "")
    settings.cache_clear()
    refused = runner.invoke(app, ["serve", "--host", "0.0.0.0"])
    assert refused.exit_code != 0
    assert "--allow-insecure-bind" in refused.output


def test_the_insecure_bind_override_works_from_the_environment(monkeypatch):
    """``INDIKIT_ALLOW_INSECURE_BIND`` accepts the exposure as the flag does."""
    monkeypatch.setattr(uvicorn, "run", lambda application, **kw: None)
    monkeypatch.setenv("INDIKIT_ALLOW_INSECURE_BIND", "1")
    settings.cache_clear()
    assert runner.invoke(app, ["serve", "--host", "0.0.0.0"]).exit_code == 0


def test_an_empty_token_flag_does_not_smuggle_past_the_refusal(monkeypatch):
    """``--token ""`` beats the environment on the security check too.

    The check has to run on the resolved value, not on the flag: reading the
    flag alone would refuse a bind the environment had authenticated, and
    reading the environment alone would accept one the operator had just
    turned off.
    """
    monkeypatch.setattr(uvicorn, "run", lambda application, **kw: None)
    monkeypatch.setenv("INDIKIT_TOKEN", "x")
    settings.cache_clear()
    refused = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--token", ""])
    assert refused.exit_code != 0
    assert "--allow-insecure-bind" in refused.output


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
    monkeypatch.setattr("indikit.client.IndiClient", _FakeMonitorClient)
    monkeypatch.setattr(indikit.cli, "asyncio", _AsyncioProxy())
    result = runner.invoke(app, ["monitor", "--host", "h", "--port", "1"])
    assert result.exit_code == 0
    assert "[set] CCD.EXPOSURE (Ok)" in result.output
    assert "[del] CCD.EXPOSURE" in result.output


def test_module_entrypoint_runs_the_app(monkeypatch):
    """Executing the module as __main__ invokes the Typer app."""
    monkeypatch.setattr(sys, "argv", ["indikit", "--help"])
    with warnings.catch_warnings():
        # runpy warns that the module is already imported; expected here.
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as excinfo:
            runpy.run_module("indikit.cli", run_name="__main__")
    assert excinfo.value.code == 0


def test_new_scaffolds_a_runnable_driver(tmp_path):
    """`indikit new` writes an executable driver that actually serves.

    The generated file is imported and driven over an in-memory runtime -
    getProperties defines its properties and a switch write round-trips -
    so the template can never rot into a broken starting point.
    """
    import importlib.util

    from indikit.driver import Device, DriverRuntime
    from indikit.protocol import DefVector, parse_indi

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
    """`indikit new` never clobbers an existing file."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".py") as existing:
        result = runner.invoke(app, ["new", existing.name])
        assert result.exit_code != 0
        assert "refusing to overwrite" in result.output


# --------------------------------------------------------------------------- #
# Logging flags                                                                #
# --------------------------------------------------------------------------- #
@pytest.fixture
def restore_logging():
    """Undo what the app callback does to global logging state.

    Configuring logging is an entrypoint's job, so invoking the CLI genuinely
    mutates the process; a test that does it has to put it back or every later
    test inherits the level.
    """
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    wire_level = logging.getLogger(WIRE_LOGGER).level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    logging.getLogger(WIRE_LOGGER).setLevel(wire_level)
    logging_config._handler = None


def _serve_capturing_uvicorn(monkeypatch, args):
    """Invoke ``serve`` with uvicorn stubbed out, returning the captured kwargs.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The patcher to install the uvicorn stub with.
    args : list of str
        The full argument list, subcommand included.

    Returns
    -------
    captured : dict
        The keyword arguments ``uvicorn.run`` was called with.
    """
    captured: dict[str, object] = {}

    def fake_run(application, **kwargs):
        """Record what uvicorn.run was asked for."""
        captured.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return captured


def test_the_log_level_flag_applies_to_the_package(monkeypatch, restore_logging):
    """``--log-level`` is on the callback, so every subcommand carries it."""
    _serve_capturing_uvicorn(monkeypatch, ["--log-level", "DEBUG", "serve"])
    assert logging.getLogger().level == logging.DEBUG


def test_verbose_is_shorthand_for_debug(monkeypatch, restore_logging):
    """``-v`` is what somebody reaches for before reading the help."""
    _serve_capturing_uvicorn(monkeypatch, ["-v", "serve"])
    assert logging.getLogger().level == logging.DEBUG


def test_the_wire_flag_turns_up_the_wire_logger(monkeypatch, restore_logging):
    """``--wire`` gives the wire without the rest of the package's DEBUG."""
    _serve_capturing_uvicorn(monkeypatch, ["--wire", "serve"])
    assert logging.getLogger(WIRE_LOGGER).isEnabledFor(logging.DEBUG)
    assert logging.getLogger().level == logging.INFO


def test_the_environment_is_honoured_and_the_flag_wins(monkeypatch, restore_logging):
    """One vocabulary: the flag and the variable name the same setting."""
    monkeypatch.setenv("INDIKIT_LOG_LEVEL", "warning")
    _serve_capturing_uvicorn(monkeypatch, ["serve"])
    assert logging.getLogger().level == logging.WARNING

    _serve_capturing_uvicorn(monkeypatch, ["--log-level", "ERROR", "serve"])
    assert logging.getLogger().level == logging.ERROR


def test_uvicorn_is_started_at_the_same_level(monkeypatch, restore_logging):
    """Otherwise ``--log-level DEBUG`` silently leaves out the request log.

    That is usually the half an operator turning the level up was after, and
    uvicorn.Config defaults to info on its own.
    """
    captured = _serve_capturing_uvicorn(monkeypatch, ["--log-level", "DEBUG", "serve"])
    assert captured["log_level"] == "debug"


def test_an_unknown_log_level_is_rejected_by_the_parser():
    """A closed set, so a typo is a usage error rather than a uvicorn traceback."""
    result = runner.invoke(app, ["--log-level", "CHATTY", "serve"])
    assert result.exit_code != 0


def test_the_device_path_configures_uvicorn_at_the_same_level(monkeypatch, restore_logging):
    """``serve --device`` builds uvicorn.Config itself, so it needs the level too.

    Two call sites, and missing either one leaves uvicorn at ``info`` while
    ``indikit.*`` moved - which is the failure this passthrough exists for.
    """
    captured: dict[str, object] = {}

    def fake_config(application, **kwargs):
        """Record what uvicorn.Config was asked for."""
        captured.update(kwargs)
        return application

    class _FakeServer:
        """A uvicorn.Server that finishes immediately."""

        def __init__(self, config):
            """Ignore the config; the assertion is on what built it."""

        async def serve(self):
            """Return at once, so the command shuts the hub down and exits."""

    monkeypatch.setattr(uvicorn, "Config", fake_config)
    monkeypatch.setattr(uvicorn, "Server", _FakeServer)
    result = runner.invoke(
        app, ["--log-level", "WARNING", "serve", "--device", "examples.demo_device:Demo"]
    )
    assert result.exit_code == 0, result.output
    assert captured["log_level"] == "warning"
