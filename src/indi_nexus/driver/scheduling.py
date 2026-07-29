"""The ``@every`` decorator: declarative periodic jobs for a driver.

This is the modern replacement for pyINDI's ``@device.repeat(millis)``. The
legacy decorator stored callbacks in *class-level* dictionaries
(``device._registrants``), so every instance shared - and could clobber - the
same schedule; it also re-implemented interval timing by hand with chained
``call_later`` closures.

Here the decorator only **tags** a method with a small :class:`PeriodicSpec`.
Discovery and execution are per-instance: the runtime scans the concrete device
object for tagged methods (:func:`iter_periodic`) and supervises one async task
per method inside a structured task group. No shared mutable state, so two
device instances never interfere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, TypeVar

_SPEC_ATTR = "__indi_periodic__"

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class PeriodicSpec:
    """How often a tagged method should run, in seconds."""

    interval: float
    start_immediately: bool = False
    name: str | None = None


def every(
    *,
    seconds: float = 0.0,
    minutes: float = 0.0,
    hours: float = 0.0,
    start_immediately: bool = False,
    name: str | None = None,
) -> Callable[[F], F]:
    """Run the decorated (async or sync) device method on a fixed interval.

    The interval is the sum of ``seconds`` + ``minutes`` + ``hours`` and must be
    positive. With ``start_immediately=True`` the method runs once right away and
    then every interval thereafter; otherwise the first run is one interval in.

    Example::

        class Mount(Device):
            @every(seconds=1)
            async def poll(self) -> None:
                ra, dec = await self.read_mount()
                self["EQUATORIAL_EOD_COORD"].set(RA=ra, DEC=dec)
    """
    interval = seconds + minutes * 60.0 + hours * 3600.0
    if interval <= 0.0:
        raise ValueError("every(...) requires a positive interval")

    spec = PeriodicSpec(interval=interval, start_immediately=start_immediately, name=name)

    def decorator(func: F) -> F:
        setattr(func, _SPEC_ATTR, spec)
        return func

    return decorator


def iter_periodic(obj: object) -> Iterator[tuple[PeriodicSpec, Callable[[], Any]]]:
    """Yield ``(spec, bound_method)`` for every ``@every``-tagged method on ``obj``.

    Walks the full MRO so tagged methods on base classes are found, while an
    override in a subclass shadows the base entry (whether or not the override is
    itself tagged) - standard method-resolution semantics.
    """
    seen: set[str] = set()
    for klass in type(obj).__mro__:
        for attr, value in vars(klass).items():
            if attr in seen:
                continue
            seen.add(attr)
            spec = getattr(value, _SPEC_ATTR, None)
            if isinstance(spec, PeriodicSpec):
                yield spec, getattr(obj, attr)
