"""``DeviceHarness``: drive a driver in a test without ``indiserver``.

A driver's value is in what it *emits* - the ``def`` it announces, the ``set`` it
publishes from a poll, the ``message`` it logs when hardware refuses a command.
This module gives that a first-class seam::

    async def test_shutter_opens():
        harness = DeviceHarness(MyDome())
        await harness.setup()

        await harness.write("DOME_SHUTTER", SHUTTER_OPEN=True)

        assert harness.latest("DOME_SHUTTER").state is IPState.BUSY
        assert "Shutter" in harness.messages[-1]

No sockets, no subprocess, no XML. Writes go through the device's real dispatch
path - the ``@on_new`` map, the device-name guard, the serialisation lock - so a
handler that works here works under ``indiserver``, and ticks run through the
same per-tick isolation the runtime applies.

For coverage of the wire itself (framing, chunk boundaries, the codec), drive a
:class:`~indi_nexus.driver.runtime.DriverRuntime` over byte streams instead; see
``tests/test_driver.py``.
"""

from __future__ import annotations

import inspect
from typing import Any, cast

from indi_nexus.driver.device import Device
from indi_nexus.driver.property import _coerce_switch
from indi_nexus.driver.scheduling import iter_periodic
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    DefVector,
    DelProperty,
    GetProperties,
    IndiMessage,
    IPState,
    Light,
    LightVector,
    Message,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    Text,
    TextVector,
    Vector,
)


def _client_write(defined: Vector, values: dict[str, Any]) -> Vector:
    """Build the partial vector a client would send to change ``defined``.

    Mirrors what comes off the wire: only the named elements, carrying just a
    name and a value, with none of the ``def``-only metadata.

    Parameters
    ----------
    defined : Vector
        The vector as the device defined it, for its kind and identity.
    values : dict
        The element values the client is asking for, keyed by element name.

    Returns
    -------
    request : Vector
        The vector to hand to the device's dispatch.
    """
    device, name = defined.device, defined.name
    if isinstance(defined, NumberVector):
        elements = [Number(name=key, value=float(val)) for key, val in values.items()]
        return NumberVector(device=device, name=name, elements=elements)
    if isinstance(defined, TextVector):
        texts = [Text(name=key, value=str(val)) for key, val in values.items()]
        return TextVector(device=device, name=name, elements=texts)
    if isinstance(defined, SwitchVector):
        # No rule: a newSwitchVector does not carry one, so a handler must not
        # rely on it, and the harness should not hand it one the wire wouldn't.
        switches = [Switch(name=key, value=_coerce_switch(val)) for key, val in values.items()]
        return SwitchVector(device=device, name=name, elements=switches)
    if isinstance(defined, LightVector):
        lights = [Light(name=key, value=IPState(val)) for key, val in values.items()]
        return LightVector(device=device, name=name, elements=lights)
    blobs = [
        BLOB(name=key, data=bytes(val), size=len(bytes(val))) for key, val in values.items()
    ]
    return BLOBVector(device=device, name=name, elements=blobs)


class DeviceHarness:
    """A device plus every message it has emitted, driven like a client would.

    Parameters
    ----------
    device : Device
        The device under test. It is bound to this harness on construction, so
        ``define_*`` and ``set`` work immediately.
    """

    def __init__(self, device: Device) -> None:
        """Attach to ``device`` and start recording what it emits."""
        self._device = device
        self._emitted: list[IndiMessage] = []
        device._bind(self._emitted.append)

    # -- driving ----------------------------------------------------------- #
    @property
    def device(self) -> Device:
        """The device under test."""
        return self._device

    async def setup(self) -> None:
        """Send a ``getProperties``, running the device's :meth:`Device.setup`.

        The same trigger ``indiserver`` provides at startup. Calling it again
        re-announces the already-defined properties, as a late-joining client
        would see.
        """
        await self._device._dispatch_get_properties(GetProperties(device=self._device.device))

    async def write(self, name: str, values: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """Send a client write to property ``name``, as a real client would.

        Only the named elements are sent - a partial write, which is what INDI
        clients actually do - and switch values accept `bool` or the wire
        strings as well as :class:`~indi_nexus.protocol.ISState`.

        Parameters
        ----------
        name : str
            The property to write to. It must already be defined.
        values : dict, optional
            Element values keyed by name, for names that are not valid Python
            identifiers.
        **kwargs : object
            Element values by name (the common case).

        Raises
        ------
        KeyError
            Raised if no property with that name has been defined.
        """
        merged = {**(values or {}), **kwargs}
        defined = self._device[name].vector
        await self._device._dispatch_new(_client_write(defined, merged))

    async def tick(self, job: str) -> None:
        """Run one iteration of an ``@every`` job, by method name.

        Runs the job body directly - the schedule is the runtime's business, and
        a test should not have to wait out an interval to see one tick.

        Parameters
        ----------
        job : str
            The name of the ``@every``-decorated method.

        Raises
        ------
        KeyError
            Raised if the device has no ``@every`` job by that name.
        """
        jobs = {method.__name__: method for _, method in iter_periodic(self._device)}
        if job not in jobs:
            raise KeyError(f"{self._device.device} has no @every job named {job!r}")
        async with self._device._guard():
            result = jobs[job]()
            if inspect.isawaitable(result):
                await result

    # -- reading back ------------------------------------------------------- #
    @property
    def emitted(self) -> list[IndiMessage]:
        """Every message the device has emitted, in order."""
        return self._emitted

    @property
    def messages(self) -> list[str]:
        """The text of every ``message`` the device has sent."""
        return [msg.message for msg in self._emitted if isinstance(msg, Message)]

    def defs(self, name: str | None = None) -> list[Vector]:
        """Return the vectors the device has defined.

        Parameters
        ----------
        name : str, optional
            Restrict to one property name; all of them when omitted.

        Returns
        -------
        vectors : list of Vector
            The defined vectors, in emission order.
        """
        return self._vectors(DefVector, name)

    def sets(self, name: str | None = None) -> list[Vector]:
        """Return the value updates the device has published.

        Parameters
        ----------
        name : str, optional
            Restrict to one property name; all of them when omitted.

        Returns
        -------
        vectors : list of Vector
            The published vectors, in emission order.
        """
        return self._vectors(SetVector, name)

    def deletes(self) -> list[DelProperty]:
        """Return every ``delProperty`` the device has sent.

        Returns
        -------
        deletions : list of DelProperty
            The deletions, in emission order.
        """
        return [msg for msg in self._emitted if isinstance(msg, DelProperty)]

    def latest(self, name: str) -> Vector:
        """Return what a client would currently hold for one property.

        The last ``def`` or ``set`` recorded for it, falling back to the
        device's live vector when nothing has been emitted - after
        :meth:`clear`, say, or for a property whose ``"on_change"`` policy has
        had nothing to report. The two agree, because every change a client
        would care about is exactly what gets published.

        Parameters
        ----------
        name : str
            The property name.

        Returns
        -------
        vector : Vector
            The latest state of that property.

        Raises
        ------
        KeyError
            Raised if no property with that name has been defined.
        """
        for msg in reversed(self._emitted):
            if isinstance(msg, DefVector | SetVector) and msg.vector.name == name:
                return msg.vector
        return cast("Vector", self._device[name].vector)

    def clear(self) -> None:
        """Drop the recorded messages, keeping the device as it is.

        Useful between the arrange and act halves of a test, so assertions run
        against what one action produced rather than the whole history.
        """
        self._emitted.clear()

    def _vectors(self, kind: type[DefVector] | type[SetVector], name: str | None) -> list[Vector]:
        """Return the vectors carried by messages of one event kind.

        Parameters
        ----------
        kind : type
            `DefVector` or `SetVector`.
        name : str or None
            Restrict to one property name; all of them when `None`.

        Returns
        -------
        vectors : list of Vector
            The matching vectors, in emission order.
        """
        return [
            msg.vector
            for msg in self._emitted
            if isinstance(msg, kind) and (name is None or msg.vector.name == name)
        ]


__all__ = ["DeviceHarness"]
