"""``PropertyStore``: the client's typed cache of INDI properties.

The store is the single source of cached truth for a client. It folds inbound
messages into a ``device -> name -> vector`` cache following standard INDI
semantics (``def`` defines, ``set`` merges values onto the definition, ``del``
removes), and it holds the subscription registry.

It is deliberately free of any socket or ``asyncio`` behaviour: :meth:`apply`
updates the cache and returns a :class:`PropertyEvent`, and :meth:`matching`
returns the callbacks interested in that event. The client performs the actual
(possibly asynchronous) dispatch, so the store stays pure and trivially testable.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from itertools import count
from typing import Literal

from indi_nexus.protocol import (
    BLOB,
    DefVector,
    DelProperty,
    IndiMessage,
    SetVector,
    Vector,
)

EventType = Literal["def", "set", "del"]

#: A subscription callback. May be sync or async; the client awaits coroutines.
Subscriber = Callable[["PropertyEvent"], object]


@dataclass(frozen=True)
class PropertyEvent:
    """A change the store applied to its cache.

    Attributes
    ----------
    type : str
        ``"def"``, ``"set"``, or ``"del"``.
    device : str
        The device the change applies to.
    name : str or None
        The property name, or `None` for a whole-device ``del``.
    vector : Vector or None
        The affected (post-merge) vector, or `None` for a ``del``.
    message : str or None
        The explanation a ``delProperty`` carried, if any. Only a ``del`` sets
        this: a ``def`` or ``set`` keeps its message on the vector, whereas a
        deletion has no vector to keep anything on, and the text is often the
        only account of *why* the property went away.
    timestamp : datetime or None
        When a ``delProperty`` said the retraction happened, if it said. Carried
        for the same reason as ``message``, and `None` for a ``def`` or ``set``,
        whose vector is already stamped.
    """

    type: EventType
    device: str
    name: str | None
    vector: Vector | None
    message: str | None = None
    timestamp: dt.datetime | None = None


def _merge(dst: Vector, src: Vector, *, state_present: bool = True) -> None:
    """Merge a ``set`` vector's values and status onto a cached definition.

    Only values (and vector status) are copied; element metadata such as a
    number's ``min``/``max``/``format`` stays as defined, per INDI ``set``
    semantics.

    Parameters
    ----------
    dst : Vector
        The cached, previously-defined vector to update in place.
    src : Vector
        The incoming ``set`` vector carrying new values.
    state_present : bool, optional
        Whether the wire message carried a ``state``. It is ``#IMPLIED`` on
        every ``set*Vector`` and means "no change if absent", so a stateless
        ``set`` must leave the cached state alone rather than reset it to the
        parsed default - a property latched into ``Alert`` stays there until the
        device says otherwise.
    """
    by_name = {el.name: el for el in dst.elements}
    for new_el in src.elements:
        cur = by_name.get(new_el.name)
        if cur is None:
            continue
        if isinstance(cur, BLOB) and isinstance(new_el, BLOB):
            cur.data = new_el.data
            cur.size = new_el.size
            if new_el.format is not None:
                cur.format = new_el.format
        else:
            cur.value = new_el.value  # type: ignore[union-attr]
    if state_present:
        dst.state = src.state
    if src.timeout is not None:
        dst.timeout = src.timeout
    if src.timestamp is not None:
        dst.timestamp = src.timestamp
    if src.message is not None:
        dst.message = src.message


class PropertyStore:
    """A cache of INDI property vectors plus a subscription registry."""

    def __init__(self) -> None:
        """Create an empty store with no cached properties or subscribers."""
        self._by_device: dict[str, dict[str, Vector]] = {}
        self._subs: dict[int, tuple[Subscriber, str | None, str | None]] = {}
        self._ids = count()

    # -- reads ------------------------------------------------------------- #
    def get(self, device: str, name: str) -> Vector | None:
        """Return a cached vector, or `None` if it is not present.

        Parameters
        ----------
        device : str
            The device name.
        name : str
            The property name.

        Returns
        -------
        vector : Vector or None
            The cached vector, or `None`.
        """
        return self._by_device.get(device, {}).get(name)

    def device(self, name: str) -> Mapping[str, Vector]:
        """Return a read-only mapping of one device's properties.

        Parameters
        ----------
        name : str
            The device name.

        Returns
        -------
        properties : Mapping
            The device's ``property-name -> vector`` mapping (empty if unknown).
        """
        return dict(self._by_device.get(name, {}))

    def devices(self) -> list[str]:
        """Return the names of all known devices."""
        return list(self._by_device)

    def __getitem__(self, device: str) -> Mapping[str, Vector]:
        """Return one device's properties (see :meth:`device`)."""
        return self.device(device)

    def __contains__(self, device: str) -> bool:
        """Return whether any property is cached for ``device``."""
        return device in self._by_device

    def __iter__(self) -> Iterator[str]:
        """Iterate over the known device names."""
        return iter(self._by_device)

    # -- writes ------------------------------------------------------------ #
    def apply(self, msg: IndiMessage) -> PropertyEvent | None:
        """Fold one inbound message into the cache.

        Parameters
        ----------
        msg : IndiMessage
            The parsed inbound message.

        Returns
        -------
        event : PropertyEvent or None
            The change applied, or `None` if the message did not change the cache
            (an unknown ``set``, or a non-property message).
        """
        if isinstance(msg, DefVector):
            vec = msg.vector
            self._by_device.setdefault(vec.device, {})[vec.name] = vec
            return PropertyEvent("def", vec.device, vec.name, vec)
        if isinstance(msg, SetVector):
            cur = self.get(msg.vector.device, msg.vector.name)
            if cur is None:
                return None
            _merge(cur, msg.vector, state_present=msg.state_present)
            return PropertyEvent("set", cur.device, cur.name, cur)
        if isinstance(msg, DelProperty):
            return self._delete(msg)
        return None

    def _delete(self, msg: DelProperty) -> PropertyEvent | None:
        """Remove a property or a whole device from the cache.

        A named deletion removes only that property. The device stays, even when
        it was the last one: "this device is here and currently publishes
        nothing" is an ordinary state - it is what a driver that defines its
        properties on connect looks like while disconnected - and it is not the
        same thing as the device being gone, which is what an unnamed
        ``delProperty`` means. libindi draws the line in the same place
        (``INDI::AbstractBaseClient`` erases the property and leaves the device).

        Parameters
        ----------
        msg : DelProperty
            The deletion message; a `None` ``name`` removes the whole device.

        Returns
        -------
        event : PropertyEvent or None
            The ``del`` event, or `None` if nothing matched.
        """
        props = self._by_device.get(msg.device)
        if props is None:
            return None
        if msg.name is None:
            del self._by_device[msg.device]
            return PropertyEvent("del", msg.device, None, None, msg.message, msg.timestamp)
        if msg.name in props:
            del props[msg.name]
            return PropertyEvent("del", msg.device, msg.name, None, msg.message, msg.timestamp)
        return None

    # -- subscriptions ----------------------------------------------------- #
    def subscribe(
        self, callback: Subscriber, *, device: str | None = None, name: str | None = None
    ) -> Callable[[], None]:
        """Register a callback for matching property events.

        Parameters
        ----------
        callback : Subscriber
            Called with each matching :class:`PropertyEvent`. May be sync or
            async; the client awaits coroutine results.
        device : str, optional
            Restrict to one device; `None` matches every device.
        name : str, optional
            Restrict to one property name; `None` matches every property.

        Returns
        -------
        unsubscribe : Callable
            Call with no arguments to remove the subscription.
        """
        token = next(self._ids)
        self._subs[token] = (callback, device, name)

        def unsubscribe() -> None:
            """Remove this subscription."""
            self._subs.pop(token, None)

        return unsubscribe

    def matching(self, event: PropertyEvent) -> list[Subscriber]:
        """Return the callbacks subscribed to a given event.

        Parameters
        ----------
        event : PropertyEvent
            The event to match against the registry.

        Returns
        -------
        callbacks : list of Subscriber
            The callbacks whose device/name filters match, in registration order.
        """
        out: list[Subscriber] = []
        for callback, device, name in self._subs.values():
            if device is not None and device != event.device:
                continue
            if name is not None and name != event.name:
                continue
            out.append(callback)
        return out
