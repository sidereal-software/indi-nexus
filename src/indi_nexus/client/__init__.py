"""The INDINexus async client.

Connect to ``indiserver``, keep a typed cache of its properties, watch for
changes, and send updates::

    from indi_nexus.client import IndiClient
    from indi_nexus.protocol import IPState

    async with IndiClient("localhost", 7624) as client:
        await client.get_properties()
        await client.set_number("CCD", "EXPOSURE", {"secs": 1.5})
        vec = await client.wait_for(
            "CCD", "EXPOSURE", lambda v: v.state == IPState.OK, timeout=30
        )
"""

from indi_nexus.client.client import ClientStats, IndiClient
from indi_nexus.client.store import PropertyEvent, PropertyStore

__all__ = [
    "ClientStats",
    "IndiClient",
    "PropertyStore",
    "PropertyEvent",
]
