"""Tests for :mod:`indi_nexus.logging_config`.

The one that matters most is the stdout check: a driver's stdout *is* the INDI
wire, so a log line written there corrupts the stream ``indiserver`` parses, and
nothing else in the suite would notice.
"""

from __future__ import annotations

import logging

import pytest

import indi_nexus.logging_config as logging_config
from indi_nexus.logging_config import WIRE_LOGGER, configure_logging, log_wire
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    GetProperties,
    Number,
    NumberVector,
    SetVector,
)


@pytest.fixture(autouse=True)
def _restore_root_logging():
    """Put the root logger and the wire logger back after each test.

    :func:`configure_logging` mutates global state on purpose - it is an
    entrypoint's job - so a test that calls it has to undo it, or pytest's own
    capture and every later test inherit the level it chose.
    """
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    wire_level = logging.getLogger(WIRE_LOGGER).level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    logging.getLogger(WIRE_LOGGER).setLevel(wire_level)
    # The module remembers the handler it installed, and the line above has just
    # taken it back out; leaving the reference would stop the next test's call
    # from installing one at all.
    logging_config._handler = None


def _blobvec() -> BLOBVector:
    """Build a BLOB vector carrying a payload big enough to notice in a log."""
    payload = b"\xde\xad\xbe\xef" * 64
    return BLOBVector(
        device="CCD",
        name="CCD1",
        elements=[BLOB(name="image", data=payload, size=len(payload))],
    )


def test_logging_goes_to_stderr_and_never_to_stdout(capsys):
    """Anything on stdout would be read by indiserver as INDI XML."""
    configure_logging("INFO")
    logging.getLogger("indi_nexus.test").warning("hello")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello" in captured.err


def test_calling_it_twice_does_not_stack_handlers():
    """An entrypoint that configures twice must not double every line."""
    configure_logging("INFO")
    before = len(logging.getLogger().handlers)
    configure_logging("WARNING")
    assert len(logging.getLogger().handlers) == before
    # And the second call still took effect, which basicConfig alone would not do.
    assert logging.getLogger().level == logging.WARNING


def test_a_lowercase_level_is_accepted():
    """``--log-level debug`` and ``INDI_NEXUS_LOG_LEVEL=debug`` both arrive here."""
    configure_logging("debug")
    assert logging.getLogger().level == logging.DEBUG


def test_an_unknown_level_is_refused():
    """A typo is a startup error, not a silently ignored setting."""
    with pytest.raises(ValueError, match="NOPE"):
        configure_logging("NOPE")


def test_wire_turns_up_only_the_wire_logger():
    """``--wire`` gives wire traffic without the rest of the package's DEBUG."""
    configure_logging("INFO", wire=True)
    assert logging.getLogger(WIRE_LOGGER).isEnabledFor(logging.DEBUG)
    assert logging.getLogger().level == logging.INFO
    assert not logging.getLogger("indi_nexus.client.client").isEnabledFor(logging.DEBUG)


def test_without_wire_the_logger_inherits_the_root_level():
    """``--log-level DEBUG`` alone still shows the wire: it means everything."""
    configure_logging("DEBUG", wire=False)
    assert logging.getLogger(WIRE_LOGGER).isEnabledFor(logging.DEBUG)
    configure_logging("INFO", wire=False)
    assert not logging.getLogger(WIRE_LOGGER).isEnabledFor(logging.DEBUG)


def test_a_wire_line_names_the_direction_the_tag_and_the_property(caplog):
    """One line per message, readable without knowing the codec."""
    vector = NumberVector(device="CCD", name="EXPOSURE", elements=[Number(name="secs", value=1.0)])
    with caplog.at_level(logging.DEBUG, logger=WIRE_LOGGER):
        log_wire("->", SetVector(vector=vector), 142)
        log_wire("<-", GetProperties())
    assert caplog.messages == ["-> set CCD.EXPOSURE (142 bytes)", "<- getProperties"]


def test_a_blob_logs_its_size_and_not_its_payload(caplog):
    """One frame is megabytes; rendering it would make the log the bottleneck."""
    with caplog.at_level(logging.DEBUG, logger=WIRE_LOGGER):
        log_wire("<-", SetVector(vector=_blobvec()))
    (line,) = caplog.messages
    assert line == "<- set CCD.CCD1 [256 byte payload]"
    assert "dead" not in line.lower()


def test_nothing_is_logged_below_debug(caplog):
    """The ``isEnabledFor`` guard, which is what keeps the hot path free."""
    with caplog.at_level(logging.INFO, logger=WIRE_LOGGER):
        log_wire("<-", GetProperties())
    assert caplog.messages == []
