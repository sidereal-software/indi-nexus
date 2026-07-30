#!/usr/bin/env python3
"""A reference INDINexus client - watch an ``indiserver`` and print every update.

Connects to ``indiserver``, subscribes to all property events, and prints a
compact line as each one arrives. Run it against a live server::

    python examples/monitor_client.py --host localhost --port 7624

The logic lives in :func:`monitor` (which takes an already-connected client) and
the pure :func:`format_event`, so both are importable and unit-testable.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable

from indi_nexus.client import IndiClient, PropertyEvent


def format_event(event: PropertyEvent) -> str:
    """Render a property event as one compact line.

    Parameters
    ----------
    event : PropertyEvent
        The event to format.

    Returns
    -------
    line : str
        A ``[type] device.name (state)`` summary.
    """
    state = event.vector.state.value if event.vector is not None else "-"
    return f"[{event.type:>3}] {event.device}.{event.name} ({state})"


async def monitor(
    client: IndiClient,
    *,
    limit: int | None = None,
    sink: Callable[[str], None] = print,
) -> None:
    """Print property events from a connected client until a limit is reached.

    Parameters
    ----------
    client : IndiClient
        An already-connected client.
    limit : int, optional
        Stop after this many events; `None` runs until cancelled.
    sink : Callable, optional
        Where to send each formatted line (defaults to :func:`print`).
    """
    done = asyncio.Event()
    seen = 0

    def on_event(event: PropertyEvent) -> None:
        """Format one event to the sink and stop once the limit is hit."""
        nonlocal seen
        sink(format_event(event))
        seen += 1
        if limit is not None and seen >= limit:
            done.set()

    client.subscribe(on_event)
    await client.get_properties()
    if limit is None:
        await asyncio.Event().wait()  # run forever
    else:
        await done.wait()


async def _amain(host: str, port: int) -> None:
    """Connect to ``indiserver`` and monitor it until interrupted.

    Parameters
    ----------
    host : str
        The ``indiserver`` host.
    port : int
        The ``indiserver`` port.
    """
    async with IndiClient(host, port) as client:
        await monitor(client)


def main() -> None:
    """Parse command-line arguments and run the monitor."""
    parser = argparse.ArgumentParser(description="Monitor an indiserver.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7624)
    args = parser.parse_args()
    asyncio.run(_amain(args.host, args.port))


if __name__ == "__main__":
    main()
