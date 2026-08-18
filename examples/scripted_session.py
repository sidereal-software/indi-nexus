#!/usr/bin/env python3
"""A client used as a script rather than a monitor: point a mount, then stop.

``examples/monitor_client.py`` watches; this one *drives*, which is the shape an
observing script or an automated sequence has:

* :meth:`~indi_nexus.client.IndiClient.wait_for` turns "the driver got there"
  into an awaitable, with a timeout, instead of a poll loop. What it hands back
  is a **snapshot** taken at the instant the predicate held - the cached vector
  keeps mutating, so a script that must reason about a value reads the one it
  was given, not the one in the cache a moment later;
* :meth:`~indi_nexus.client.IndiClient.on_connection` reports the link coming
  and going, which is the only warning a long script gets;
* **a send with no connection raises immediately and is never queued.** That is
  deliberate: a slew held while ``indiserver`` was down would arrive minutes
  later, at a mount pointing somewhere else. :class:`NotConnectedError` is how a
  script learns its command did not happen, and it is a ``ConnectionError`` too,
  so existing ``except ConnectionError`` keeps working;
* everything this library raises on purpose is an :class:`IndiError`, so one
  ``except`` at the top of a script survives the whole of it.

Run it against a mount. This speaks INDI over TCP, so it wants a real ``indiserver``
rather than ``serve --device``, which puts its drivers behind the web bridge::

    indiserver ./examples/telescope_device.py               # terminal 1
    python examples/scripted_session.py --ra 5.5 --dec 22.0 # terminal 2

The logic lives in :func:`slew` and :func:`session` (both taking an
already-connected client), so both are importable and unit-testable.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable

from indi_nexus.client import IndiClient
from indi_nexus.exceptions import IndiError, NotConnectedError
from indi_nexus.protocol import IPState, ISState, NumberVector, Vector

#: The mount this script drives by default.
DEFAULT_DEVICE = "Telescope Simulator"

#: The standard INDI pointing property, in hours of RA and degrees of Dec.
COORDINATES = "EQUATORIAL_EOD_COORD"


def watch_link(client: IndiClient, sink: Callable[[str], None] = print) -> Callable[[], None]:
    """Report the upstream link coming up and going down.

    Parameters
    ----------
    client : IndiClient
        The client to watch. Registering before :meth:`IndiClient.start` means
        the first connection is reported too.
    sink : Callable, optional
        Where to send each line (defaults to :func:`print`).

    Returns
    -------
    unsubscribe : Callable
        Call with no arguments to stop watching.
    """

    def on_connection(up: bool) -> None:
        """Announce one connect or disconnect transition."""
        sink("link is up" if up else "link is down")

    return client.on_connection(on_connection)


async def slew(
    client: IndiClient,
    device: str,
    ra: float,
    dec: float,
    *,
    timeout: float = 120.0,  # noqa: ASYNC109 - forwarded to wait_for, which mirrors asyncio
) -> NumberVector:
    """Send the mount to a position and wait until it says it arrived.

    The mount reports ``Busy`` while it moves and ``Ok`` or ``Alert`` when it
    stops, which is the standard INDI contract for a long operation and the only
    thing this function needs to know about mounts.

    Parameters
    ----------
    client : IndiClient
        An already-connected client.
    device : str
        The mount's INDI device name.
    ra : float
        Target right ascension, in hours.
    dec : float
        Target declination, in degrees.
    timeout : float, optional
        Seconds to wait for the slew to finish.

    Returns
    -------
    coordinates : NumberVector
        A snapshot of the pointing at the moment the mount stopped moving.

    Raises
    ------
    TimeoutError
        Raised if the mount is still moving when the timeout elapses. A raise
        here means the slew is unfinished, not abandoned: the mount keeps going,
        and a script that cares should abort it explicitly.
    NotConnectedError
        Raised if the link is down when the command is sent. The command was not
        queued and did not happen.
    """
    await client.set_number(device, COORDINATES, {"RA": ra, "DEC": dec})
    arrived = await client.wait_for(device, COORDINATES, _arrived_at(ra, dec), timeout=timeout)
    if not isinstance(arrived, NumberVector):  # a driver publishing another kind here
        raise ValueError(f"{device}.{COORDINATES} is a {arrived.kind} property, not numbers")
    return arrived


def _arrived_at(ra: float, dec: float, tolerance: float = 1e-3) -> Callable[[Vector], bool]:
    """Build a predicate for "the mount stopped, and it stopped *there*".

    Waiting for "no longer Busy" alone is a race, and a quiet one: the write is
    still in the outbox when
    :meth:`~indi_nexus.client.IndiClient.wait_for` checks the cache, so the
    pre-write vector - ``Ok`` or ``Idle`` from the last operation - satisfies it
    at once and the script sails past a slew that has not started. Naming the
    destination as well as the state makes the wait describe an outcome instead
    of a transition, which is what a script actually wants to know.

    Parameters
    ----------
    ra : float
        The requested right ascension, in hours.
    dec : float
        The requested declination, in degrees.
    tolerance : float, optional
        How close counts as arrived, in each axis' own units.

    Returns
    -------
    predicate : Callable
        Called with a vector; `True` once the mount reports the position.
    """

    def arrived(vector: Vector) -> bool:
        """Return whether the vector reports the requested position, stopped."""
        if vector.state is IPState.BUSY:
            return False
        at_ra, at_dec = vector.get("RA"), vector.get("DEC")
        if not isinstance(at_ra, float) or not isinstance(at_dec, float):
            return False
        return abs(at_ra - ra) <= tolerance and abs(at_dec - dec) <= tolerance

    return arrived


def _connected(vector: Vector) -> bool:
    """Return whether a CONNECTION vector reports the device as connected.

    Parameters
    ----------
    vector : Vector
        The cached vector offered by :meth:`~indi_nexus.client.IndiClient.wait_for`.

    Returns
    -------
    connected : bool
        `True` once the ``CONNECT`` member is On.
    """
    return vector.get("CONNECT") is ISState.ON


async def session(
    client: IndiClient,
    device: str = DEFAULT_DEVICE,
    *,
    ra: float = 5.5,
    dec: float = 22.0,
    timeout: float = 120.0,  # noqa: ASYNC109 - forwarded to wait_for, which mirrors asyncio
) -> NumberVector:
    """Connect a mount, point it, and hand back where it ended up.

    Parameters
    ----------
    client : IndiClient
        An already-connected client.
    device : str, optional
        The mount's INDI device name.
    ra : float, optional
        Target right ascension, in hours.
    dec : float, optional
        Target declination, in degrees.
    timeout : float, optional
        Seconds to wait for each step.

    Returns
    -------
    coordinates : NumberVector
        A snapshot of the pointing when the slew finished.

    Raises
    ------
    TimeoutError
        Raised if the mount does not appear, connect, or arrive in time.
    """
    # The driver may not have announced itself yet - wait for the property
    # rather than assuming the cache is already populated.
    await client.wait_for(device, "CONNECTION", timeout=timeout)
    await client.set_switch(device, "CONNECTION", {"CONNECT": True})
    await client.wait_for(device, "CONNECTION", _connected, timeout=timeout)
    return await slew(client, device, ra, dec, timeout=timeout)


async def _amain(host: str, port: int, device: str, ra: float, dec: float) -> int:
    """Run one scripted session and turn any failure into an exit status.

    Parameters
    ----------
    host : str
        The ``indiserver`` host.
    port : int
        The ``indiserver`` port.
    device : str
        The mount's INDI device name.
    ra : float
        Target right ascension, in hours.
    dec : float
        Target declination, in degrees.

    Returns
    -------
    status : int
        ``0`` if the mount arrived, ``1`` otherwise.
    """
    client = IndiClient(host, port)
    stop_watching = watch_link(client)
    try:
        async with client:
            arrived = await session(client, device, ra=ra, dec=dec)
    except NotConnectedError as exc:
        # Nothing was queued for later, so the command simply did not happen.
        print(f"command not sent: {exc}")
        return 1
    except TimeoutError:
        print(f"{device} did not finish the slew in time; it may still be moving")
        return 1
    except IndiError as exc:
        # One except for everything the library raises on purpose.
        print(f"{type(exc).__name__}: {exc}")
        return 1
    finally:
        stop_watching()
    at_ra, at_dec = arrived.get("RA", 0.0), arrived.get("DEC", 0.0)
    print(f"arrived at RA {at_ra:.4f} Dec {at_dec:.4f}")
    return 0


def main() -> None:
    """Parse command-line arguments and run one scripted session."""
    parser = argparse.ArgumentParser(description="Point an INDI mount, then exit.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7624)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--ra", type=float, default=5.5, help="hours")
    parser.add_argument("--dec", type=float, default=22.0, help="degrees")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_amain(args.host, args.port, args.device, args.ra, args.dec)))


if __name__ == "__main__":
    main()
