"""The INDIkit async client.

Connect to ``indiserver``, keep a typed cache of its properties, watch for
changes, and send updates::

    from indikit.client import IndiClient
    from indikit.protocol import IPState

    async with IndiClient("localhost", 7624) as client:
        await client.get_properties()
        await client.set_number("CCD", "EXPOSURE", {"secs": 1.5})
        vec = await client.wait_for(
            "CCD", "EXPOSURE", lambda v: v.state == IPState.OK, timeout=30
        )
"""

from indikit.client.client import ClientStats, IndiClient
from indikit.client.store import PropertyEvent, PropertyStore

__all__ = [
    "ClientStats",
    "IndiClient",
    "PropertyStore",
    "PropertyEvent",
]
