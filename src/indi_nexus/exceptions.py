"""The exception hierarchy every INDINexus failure belongs to.

Two rules shape this module, and both matter more than the class names.

**One root.** Everything the package raises deliberately derives from
:class:`IndiError`, so an application that wants to survive the library rather
than diagnose it can write one ``except IndiError`` and mean it. Before this
existed the same ``RuntimeError`` came out of a retracted property handle and an
unattached device - two unrelated failures a caller had to tell apart by reading
the message text.

**Every type keeps its builtin.** Each class below also inherits from the
builtin that used to be raised at its site, so
``PropertyNotFound`` *is* a :class:`KeyError`, ``WrongPropertyKind`` *is* a
:class:`TypeError`, and so on. That is what makes adopting the hierarchy purely
additive: existing ``except KeyError`` in this repository, in the examples and
in third-party drivers keeps catching exactly what it caught before, and the
familiar idioms (``vector["RA"]`` inside a ``try``/``except KeyError``,
``dict``-style lookups) go on reading naturally. The builtin also comes first in
the MRO for message formatting, so ``str(PropertyNotFound("RA"))`` still renders
the way a :class:`KeyError` does.

Adding a new type here means answering both questions: what it is a kind of
(:class:`IndiError`, always) and what it must stay compatible with.
"""

from __future__ import annotations


class IndiError(Exception):
    """Base class for every error INDINexus raises on purpose.

    Catching this catches the whole library. It is never raised directly.
    """


class ProtocolError(IndiError, ValueError):
    """The INDI wire format was violated by a value or a message.

    Raised for text that is not a number where the DTD requires one, a
    ``#REQUIRED`` attribute that is absent, an unknown element kind, or a value
    (a non-finite float) that neither wire format can carry. Also a
    :class:`ValueError`, which is what the codecs raised before and what the
    stream parser catches to drop a bad element instead of dying on it.
    """


class PropertyNotFound(IndiError, KeyError):
    """A property or an element was looked up by a name nothing answers to.

    Covers both lookups because they are the same mistake at two depths: the
    device has no such property, or the vector has no such element. Also a
    :class:`KeyError`, so mapping-shaped access (``device["COOLER"]``,
    ``vector["RA"]``) keeps failing the way a mapping fails.
    """


class WrongPropertyKind(IndiError, TypeError):
    """A property was reached through an accessor for a different vector kind.

    ``device.number("CONNECTION")`` on a switch vector, or a
    :meth:`~indi_nexus.driver.property.BoundProperty.select` on a vector kind
    with no natural "unselected" value. Also a :class:`TypeError`: the name
    resolved, the operation does not apply to what it resolved to.
    """


class PropertyRetracted(IndiError, RuntimeError):
    """A retracted property's handle was used to publish an update.

    The client has been told the property is gone, so anything published
    through the dead handle contradicts that. Define the property again and use
    the handle that returns. Also a :class:`RuntimeError`.
    """


class DeviceNotServing(IndiError, RuntimeError):
    """A device tried to send while not attached to a runtime.

    ``define_*``, ``message()`` and every other emission need somewhere to send
    to, which a device only has while it is being served. Also a
    :class:`RuntimeError`.
    """


class NotConnectedError(IndiError, ConnectionError):
    """The client has no live connection to ``indiserver``.

    Raised by every :class:`~indi_nexus.client.IndiClient` send rather than
    queueing the message for a connection that may be an hour away, and used to
    fail the waiters still parked on
    :meth:`~indi_nexus.client.IndiClient.wait_for` when the client is closed.
    Also a :class:`ConnectionError` (hence an :class:`OSError`), because that is
    what it is: the peer is not there.
    """


class ConfigError(IndiError, OSError):
    """A device's saved configuration could not be read, written or located.

    Covers every way persistence fails: no resolvable configuration directory,
    a device name that cannot be a filename, a file that is absent, oversized or
    not valid JSON, and any refusal from the filesystem underneath. Also an
    :class:`OSError`, because that is what the filesystem would have raised on
    its own, so an ``except OSError`` already wrapped around a driver goes on
    catching it.

    Its message is written for a client to read: it never quotes a path or an
    operating-system error string, both of which go to the ``indi_nexus``
    logger instead.
    """


class SendQueueFull(IndiError, RuntimeError):
    """The outbox is full: the connection is not draining as fast as we send.

    The bound exists so a wedged writer cannot grow the queue without limit.
    Reaching it means the socket has stopped accepting what this client is
    producing, and for instrument control a command that arrives late is worse
    than one that fails, so this is raised rather than awaited. Also a
    :class:`RuntimeError`.
    """


__all__ = [
    "ConfigError",
    "DeviceNotServing",
    "IndiError",
    "NotConnectedError",
    "PropertyNotFound",
    "PropertyRetracted",
    "ProtocolError",
    "SendQueueFull",
    "WrongPropertyKind",
]
