"""Tests for the ``indi-nexus`` CLI."""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from examples.demo_device import Demo
from indi_nexus.cli import app, load_device

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
