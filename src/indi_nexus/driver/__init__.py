"""The INDINexus driver SDK.

Write a driver by subclassing :class:`Device`, defining properties in
:meth:`Device.setup`, polling with :func:`every`, and handling client writes with
:func:`on_new`::

    from indi_nexus.driver import Device, every, on_new
    from indi_nexus.protocol import Number, IPState, IPerm

    class Mount(Device):
        name = "Mount"

        async def setup(self) -> None:
            self.define_number(
                "EQUATORIAL_EOD_COORD",
                [Number(name="RA", format="%9.6m"), Number(name="DEC", format="%9.6m")],
                perm=IPerm.RO,
            )

        @every(seconds=1)
        async def poll(self) -> None:
            ra, dec = await self.read_mount()
            self["EQUATORIAL_EOD_COORD"].set(RA=ra, DEC=dec, state=IPState.OK)

    if __name__ == "__main__":
        Mount.run()
"""

from indi_nexus.driver.device import Device
from indi_nexus.driver.dispatch import on_new
from indi_nexus.driver.property import BoundProperty, EmitPolicy
from indi_nexus.driver.runtime import DriverRuntime, run, serve_stdio
from indi_nexus.driver.scheduling import every

__all__ = [
    "Device",
    "BoundProperty",
    "EmitPolicy",
    "every",
    "on_new",
    "DriverRuntime",
    "run",
    "serve_stdio",
]
