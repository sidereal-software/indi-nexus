"""The package's logging setup, and the shared ``indi_nexus.wire`` logger.

:func:`configure_logging` is the **only** place INDINexus installs a log handler,
and it is called from entrypoints alone - the CLI callback and
:func:`indi_nexus.driver.run`. A library import configures nothing, because a
library that installs a root handler on import steals the application's logging.

**Logs go to stderr, and that is a requirement rather than a default.** A
driver's *stdout is the INDI wire*: :func:`indi_nexus.driver.runtime._open_stdio`
writes serialised XML straight to ``sys.stdout.buffer``, so a log line there
corrupts the stream ``indiserver`` is parsing. ``indiserver`` relays a driver's
stderr into its own log, so stderr is also where the operator will find it.

**The wire logger.** ``indi_nexus.wire`` is one name for one question - "what is
actually on the wire" - and four call sites answer it: the client's reader and
writer, and the driver runtime's reader and writer. An operator should not have
to learn that those are different modules, which is why they do not log this on
their own module loggers. :func:`log_wire` guards on
:meth:`logging.Logger.isEnabledFor`, so a run with wire logging off pays one flag
check per message.

A BLOB's payload is **never** logged. One frame is megabytes, and rendering it
would make the log the slowest thing in the process; the line reports the payload
size read off the model instead, never off a copy made for the log.
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

from indi_nexus.protocol import BLOBVector, DefVector, IndiMessage, NewVector, SetVector

#: The one logger name for wire traffic, in both directions and on both sides.
WIRE_LOGGER = "indi_nexus.wire"

#: The line format used when INDINexus configures logging itself. Terse on
#: purpose: under ``indiserver`` these lines are re-prefixed by the hub's own log
#: format, and a second timestamp per line is noise.
_FORMAT = "%(levelname)-8s %(name)s: %(message)s"

_wire = logging.getLogger(WIRE_LOGGER)

#: The single handler this module installs, remembered so a second call
#: reconfigures it instead of adding another.
_handler: logging.StreamHandler[TextIO] | None = None


def configure_logging(level: str | int = "INFO", *, wire: bool = False) -> None:
    """Send INDINexus logging to stderr at ``level``. Call from an entrypoint only.

    Safe to call twice: the handler is installed once and kept, so a later call
    changes the levels without doubling every line.

    The handler is installed outright rather than through
    :func:`logging.basicConfig`, which defers to a root that already has a
    handler. Deferring reads well and is wrong here: under a test runner, or in
    any process that touched :mod:`logging` first, it would quietly install
    nothing and the stderr guarantee above - the one that keeps a driver's
    stdout clean - would hold only when nothing else got there first.

    Parameters
    ----------
    level : str or int, optional
        A standard :mod:`logging` level, by name (case-insensitive) or number.
    wire : bool, optional
        Whether to turn the shared ``indi_nexus.wire`` logger up to DEBUG. The
        root level is left alone, so ``--wire`` on its own gives wire traffic
        without the rest of the package's DEBUG output.

    Raises
    ------
    ValueError
        Raised if ``level`` is a string naming no known level.
    """
    global _handler
    if isinstance(level, str):
        level = level.upper()
    # Before installing anything: a bad level is a startup error, and it should
    # not leave a half-configured root behind on its way out.
    logging.getLogger().setLevel(level)
    if _handler is None:
        _handler = logging.StreamHandler(sys.stderr)
        _handler.setFormatter(logging.Formatter(_FORMAT))
        logging.getLogger().addHandler(_handler)
    # NOTSET rather than the root level: the wire logger then inherits, so
    # ``--log-level DEBUG`` without ``--wire`` still shows wire traffic, which is
    # what "show me everything" means.
    _wire.setLevel(logging.DEBUG if wire else logging.NOTSET)


def log_wire(direction: str, msg: IndiMessage, nbytes: int | None = None) -> None:
    """Log one INDI message on the shared wire logger, if wire logging is on.

    The message is named by its **model tag** (``def``, ``set``, ``new``,
    ``getProperties``, ...) rather than by the XML element it would serialise to.
    The same message travels as XML upstream and as JSON to a browser, so the
    XML element name would be wrong for half of what this logger reports, and
    reproducing the codec's tag-stem rule here would put a fourth copy of it in
    the package.

    Parameters
    ----------
    direction : str
        ``"<-"`` for a message that arrived, ``"->"`` for one being sent.
    msg : IndiMessage
        The message to describe.
    nbytes : int, optional
        The serialised size, where the caller knows it - the writers do, the
        readers do not, because the parser frames a chunk into several messages.
    """
    if not _wire.isEnabledFor(logging.DEBUG):
        return
    size = "" if nbytes is None else f" ({nbytes} bytes)"
    _wire.debug("%s %s%s", direction, _describe(msg), size)


def _describe(msg: IndiMessage) -> str:
    """Name one message compactly: its tag, and the property it is about.

    Parameters
    ----------
    msg : IndiMessage
        The message to describe.

    Returns
    -------
    text : str
        ``"<tag> <device>.<property>"`` for a message carrying a vector, with a
        BLOB's payload **size** appended, else the bare tag.
    """
    if not isinstance(msg, (DefVector, SetVector, NewVector)):
        return msg.tag
    vector = msg.vector
    text = f"{msg.tag} {vector.device}.{vector.name}"
    if isinstance(vector, BLOBVector):
        # The decoded payload where there is one, the wire's claimed size where
        # there is not (a `defBLOB` announces the channel and carries no data).
        payload = sum(
            len(element.data) if element.data is not None else (element.size or 0)
            for element in vector.elements
        )
        text += f" [{payload} byte payload]"
    return text
