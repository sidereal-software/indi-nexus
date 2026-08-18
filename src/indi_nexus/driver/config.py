"""The file a device's saved configuration lives in, and how it is written.

A driver that has been pointed at a site, given a focuser offset or told which
filter sits in slot 3 should still know all of that after a power cut. libindi
solves this with ``CONFIG_PROCESS`` and an XML file under ``$HOME/.indi``; this
module is the same idea in the vocabulary the rest of the SDK uses.

Three decisions are worth reading before changing anything here.

**Values, never definitions.** The document holds element values and nothing
else - no labels, no permissions, no ``min``/``max``. A definition belongs to the
code, which is the only thing that knows what the current version of the driver
publishes; a saved definition is a stale copy that outranks it forever, and
restoring one would let yesterday's driver decide today's property shapes.

**JSON, not libindi's XML, and not libindi's directory.** The file is ours: a
different schema under the same name would put two frameworks in a fight over
one path with no way for either to tell whose file it found. So the directory is
``$XDG_CONFIG_HOME/indi-nexus`` (see :class:`~indi_nexus.settings.Settings`),
never ``~/.indi``.

**Whole-document replace, written atomically.** :func:`write_document` renders
the entire configuration each time, into a temporary file created ``0600`` in
the destination directory, and then renames it into place with
:func:`os.replace`. There
is no read-modify-write, so a second process holding the same file cannot lose
an update to an interleaving; there is no window in which the final name exists
half-written or world-readable; and a failure part-way through leaves the
previous configuration exactly as it was.

Nothing here knows what a :class:`~indi_nexus.driver.device.Device` is. It
imports :mod:`indi_nexus.protocol` and the standard library, and that is what
keeps ``tests/test_layering.py`` flat.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from indi_nexus.exceptions import ConfigError
from indi_nexus.protocol import (
    IndiTimestamp,
    Number,
    Switch,
    Text,
    Vector,
    indi_now,
)

logger = logging.getLogger(__name__)

#: The schema version written into every document. A reader that meets a version
#: it does not know refuses the file rather than guessing at its shape.
CONFIG_VERSION = 1

#: The largest configuration file that will be read at all, checked by ``stat``
#: before a byte is loaded. A configuration is element values for one device, so
#: a megabyte is already absurd; the cap is what stops a driver being asked to
#: parse an arbitrarily large file that happens to sit at the right path.
MAX_CONFIG_BYTES = 1024 * 1024

#: Characters a device name may consist of, as an **allowlist**. A denylist of
#: path separators is a running patch list - it has to know about ``/``, ``\``,
#: ``:``, NUL and the Windows device names, and it is wrong the moment it misses
#: one. Spaces are in here **deliberately**: real INDI device names have them
#: ("CCD Simulator", "Telescope Simulator"), so a stricter pattern would refuse
#: most of the ecosystem.
_NAME_ALLOWED = re.compile(r"[A-Za-z0-9 ._-]+")

#: Names Windows resolves to a device rather than a file, whatever the extension
#: - and whatever else follows the first dot, which is why :func:`_is_safe_name`
#: tests that component and not the whole name. Rejected case-insensitively, so
#: a configuration directory synced to a Windows machine cannot be the thing
#: that breaks.
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{digit}" for digit in range(1, 10)}
    | {f"LPT{digit}" for digit in range(1, 10)}
)


class ConfigDocument(BaseModel):
    """One device's saved configuration: element values, keyed by property.

    Attributes
    ----------
    version : int
        The schema version, :data:`CONFIG_VERSION` for anything written today.
    device : str
        The INDI device the configuration belongs to. Written for the benefit of
        somebody reading the file; the filename is what actually locates it.
    saved : datetime
        When the document was written, in UTC.
    properties : dict
        Property name to a mapping of element name to value. Switch values are
        the wire tokens ``"On"`` / ``"Off"``.
    """

    version: int = CONFIG_VERSION
    device: str
    saved: IndiTimestamp = Field(default_factory=indi_now)
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)


def values_of(vector: Vector) -> dict[str, Any]:
    """Return one vector's element values, reduced to JSON scalars.

    The conversion is explicit rather than left to the serialiser: a switch's
    :class:`~indi_nexus.protocol.ISState` has to reach the file as the wire token
    a client would send back, and a value that has no JSON form at all - a BLOB
    payload, most of it - must never get there by accident.

    Parameters
    ----------
    vector : Vector
        The vector to read.

    Returns
    -------
    values : dict
        Element name to value, holding only elements that can be persisted.
    """
    values: dict[str, Any] = {}
    for element in vector.elements:
        if isinstance(element, Number):
            values[element.name] = float(element.value)
        elif isinstance(element, Text):
            values[element.name] = element.value
        elif isinstance(element, Switch):
            values[element.name] = element.value.value
        # Lights and BLOBs fall through unpersisted. define_*(persist=True)
        # refuses both kinds, so this is unreachable through the SDK; skipping
        # rather than raising is what stops a hand-built vector turning a Save
        # into a failure.
    return values


def config_path(directory: Path, device: str) -> Path:
    """Return the configuration file for one device inside ``directory``.

    Parameters
    ----------
    directory : Path
        The configuration directory.
    device : str
        The INDI device name, which becomes the filename stem.

    Returns
    -------
    path : Path
        ``<directory>/<device>.json``.

    Raises
    ------
    ConfigError
        Raised if the device name cannot safely be a filename. Also an OSError.
    """
    if not _is_safe_name(device):
        raise ConfigError(f"{device!r} cannot be used as a configuration filename")
    return directory / f"{device}.json"


def _is_safe_name(device: str) -> bool:
    """Return whether a device name may be used as a filename stem.

    Parameters
    ----------
    device : str
        The INDI device name.

    Returns
    -------
    safe : bool
        ``True`` when the name is in the allowlist and is not one of the
        special forms a path-aware allowlist still lets through.
    """
    if not _NAME_ALLOWED.fullmatch(device):
        return False
    # The allowlist admits these, and every one of them is a path meaning
    # something other than "a file called that": the two relative directories,
    # and a name Windows silently trims to a different file.
    if device in {".", ".."} or device[-1] in ". ":
        return False
    # Windows reserves a name by the component before the **first** dot, with
    # trailing spaces trimmed - "aux.telescope" is the AUX device, not a file -
    # and the allowlist permits dots on purpose ("focuser_1.2"). Comparing the
    # whole name would let every reserved one back in behind a suffix.
    return device.partition(".")[0].rstrip(" ").upper() not in _RESERVED_NAMES


def read_document(path: Path) -> ConfigDocument:
    """Read and validate one device's configuration file.

    Parameters
    ----------
    path : Path
        The file to read.

    Returns
    -------
    document : ConfigDocument
        The parsed configuration.

    Raises
    ------
    ConfigError
        Raised if the file is absent, larger than :data:`MAX_CONFIG_BYTES`, not
        valid JSON, or not a configuration document this version understands.
        Also an OSError.
    """
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        raise ConfigError("no saved configuration") from None
    except OSError as exc:
        logger.error("cannot stat %s: %s", path, exc)
        raise ConfigError("saved configuration could not be read") from exc
    if size > MAX_CONFIG_BYTES:
        # Checked before a byte is read: the point is not to parse it at all.
        logger.error("%s is %d bytes, over the %d limit", path, size, MAX_CONFIG_BYTES)
        raise ConfigError("saved configuration is too large to read")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        logger.error("cannot read %s: %s", path, exc)
        raise ConfigError("saved configuration could not be read") from exc
    try:
        # RecursionError, not a ValueError: a deeply nested payload exhausts the
        # decoder's stack rather than failing its grammar, so catching
        # json.JSONDecodeError alone would let it out as a crash.
        payload = json.loads(raw)
        document = ConfigDocument.model_validate(payload)
    except (ValueError, RecursionError) as exc:
        logger.error("cannot parse %s: %s", path, exc)
        raise ConfigError("saved configuration is not readable") from exc
    if document.version != CONFIG_VERSION:
        raise ConfigError(
            f"saved configuration is version {document.version}, not {CONFIG_VERSION}"
        )
    return document


def write_document(path: Path, document: ConfigDocument) -> None:
    """Write one device's configuration, atomically and privately.

    The directory is created if it is missing - on the way out only, never on
    the way in, so a load cannot leave an empty directory behind on a machine
    that has never saved anything.

    Parameters
    ----------
    path : Path
        The destination file.
    document : ConfigDocument
        The configuration to write.

    Raises
    ------
    ConfigError
        Raised if the directory cannot be created or the file cannot be
        written. Also an OSError.
    """
    body = document.model_dump_json(indent=2) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # mkstemp creates 0600, and the mode is never widened afterwards: a
        # chmod after the rename would leave a window in which the final name
        # is readable by anyone on the machine.
        handle, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError:
            # The replace never happened, so the previous configuration is
            # still whole; all that is left is not to litter beside it.
            Path(temporary).unlink(missing_ok=True)
            raise
    except OSError as exc:
        logger.error("cannot write %s: %s", path, exc)
        raise ConfigError("configuration could not be saved") from exc


def remove_document(path: Path) -> None:
    """Delete one device's configuration file, if it is there.

    Deleting what is already gone is a success, not an error: purging is how an
    operator says "forget the saved configuration", and that is true whether or
    not a file was found. libindi's ``CONFIG_PURGE`` is a bare ``remove()`` for
    the same reason, and leaves no backup beside it.

    Parameters
    ----------
    path : Path
        The file to remove.

    Raises
    ------
    ConfigError
        Raised if the file exists and cannot be removed. Also an OSError.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.error("cannot remove %s: %s", path, exc)
        raise ConfigError("saved configuration could not be removed") from exc


__all__ = [
    "CONFIG_VERSION",
    "MAX_CONFIG_BYTES",
    "ConfigDocument",
    "config_path",
    "read_document",
    "remove_document",
    "values_of",
    "write_document",
]
