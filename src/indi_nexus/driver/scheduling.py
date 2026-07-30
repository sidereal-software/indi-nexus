"""The ``@every`` decorator: declarative periodic jobs for a driver.

This is the modern replacement for pyINDI's ``@device.repeat(millis)``. The
legacy decorator stored callbacks in *class-level* dictionaries
(``device._registrants``), so every instance shared - and could clobber - the
same schedule; it also re-implemented interval timing by hand with chained
``call_later`` closures.

Here the decorator only **tags** a method with a small :class:`PeriodicSpec`.
Discovery and execution are per-instance: the runtime scans the concrete device
object for tagged methods (:func:`iter_periodic`) and supervises one asyncio task
per method. No shared mutable state, so two device instances never interfere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, TypeVar

_SPEC_ATTR = "__indi_periodic__"

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class PeriodicSpec:
    """The schedule attached to an ``@every``-tagged method.

    Attributes
    ----------
    interval : float
        Seconds between runs.
    start_immediately : bool
        Whether to run once at startup before the first interval elapses.
    when_connected : bool
        Whether ticks are skipped while the device is not connected.
    name : str or None
        Optional label for the job (currently informational).
    """

    interval: float
    start_immediately: bool = False
    when_connected: bool = False
    name: str | None = None


def every(
    *,
    seconds: float = 0.0,
    minutes: float = 0.0,
    hours: float = 0.0,
    start_immediately: bool = False,
    when_connected: bool = False,
    name: str | None = None,
) -> Callable[[F], F]:
    """Tag a device method to run on a fixed interval.

    The interval is the sum of ``seconds`` + ``minutes`` + ``hours``. The method
    may be sync or async. This only records a :class:`PeriodicSpec` on the
    function; :class:`~indi_nexus.driver.runtime.DriverRuntime` discovers and runs
    it once the device is served.

    Parameters
    ----------
    seconds : float, optional
        Seconds component of the interval.
    minutes : float, optional
        Minutes component of the interval.
    hours : float, optional
        Hours component of the interval. The three components are summed and
        must total a positive duration.
    start_immediately : bool, optional
        If `True`, run once right away and then every interval thereafter;
        otherwise the first run is one interval in.
    when_connected : bool, optional
        If `True`, ticks are skipped while ``device.connected`` is false - the
        usual behavior for polling jobs that talk to real hardware.
    name : str, optional
        Optional label for the job.

    Returns
    -------
    decorator : Callable
        A decorator that tags and returns the method unchanged.

    Raises
    ------
    ValueError
        Raised if the combined interval is not positive.

    Examples
    --------
    >>> class Mount(Device):
    ...     @every(seconds=1)
    ...     async def poll(self) -> None:
    ...         ra, dec = await self.read_mount()
    ...         self["EQUATORIAL_EOD_COORD"].set(RA=ra, DEC=dec)
    """
    interval = seconds + minutes * 60.0 + hours * 3600.0
    if interval <= 0.0:
        raise ValueError("every(...) requires a positive interval")

    spec = PeriodicSpec(
        interval=interval,
        start_immediately=start_immediately,
        when_connected=when_connected,
        name=name,
    )

    def decorator(func: F) -> F:
        """Tag ``func`` with the schedule and return it unchanged."""
        setattr(func, _SPEC_ATTR, spec)
        return func

    return decorator


def iter_periodic(obj: object) -> Iterator[tuple[PeriodicSpec, Callable[[], Any]]]:
    """Yield the schedule and bound method for each ``@every`` job on ``obj``.

    Walks the full MRO so tagged methods on base classes are found, while an
    override in a subclass shadows the base entry (whether or not the override is
    itself tagged) - standard method-resolution semantics.

    Parameters
    ----------
    obj : object
        The instance to scan (typically a `~indi_nexus.driver.device.Device`).

    Yields
    ------
    spec : PeriodicSpec
        The schedule for a tagged job.
    method : Callable
        The bound method to run for that job.
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
