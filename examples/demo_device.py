#!/usr/bin/env python3
"""A reference INDIkit driver.

It exposes the standard ``CONNECTION`` switch plus a number, a text, a light and a
switch vector, uses ``@every`` to animate them once a second while connected, and
handles a client write to the switch vector with ``@on_new``. There is no BLOB
here; ``ccd_device.py`` is the example that publishes one. Run it as a child of
``indiserver``::

    indiserver ./examples/demo_device.py

or just ``python examples/demo_device.py`` and type ``getProperties`` XML at it.
"""

from __future__ import annotations

from indikit.driver import Device, every, on_new
from indikit.protocol import (
    IPerm,
    IPState,
    ISRule,
    ISState,
    Light,
    Number,
    Switch,
    SwitchVector,
    Text,
)

_STATES = [IPState.IDLE, IPState.OK, IPState.BUSY, IPState.ALERT]


class Demo(Device):
    """A device that cycles through states and counts up once per second."""

    name = "Demo"

    def __init__(self, name: str | None = None) -> None:
        """Initialise the device with a zeroed animation counter."""
        super().__init__(name)
        self._tick = 0

    async def setup(self) -> None:
        """Define the connection switch, one of each vector kind, and announce readiness."""
        # Every device gets this, including a simulated one. It is the property
        # clients look for first, and it is what gates the animation below.
        self.define_connection()
        self.define_number(
            "counters",
            [
                Number(name="count", label="Count", format="%.0f"),
                Number(name="ra", label="RA", format="%9.6m", min=0, max=24),
            ],
            label="Counters",
            group="Main",
            perm=IPerm.RO,
            state=IPState.OK,
        )
        self.define_text(
            "status_text",
            [Text(name="value", label="State", value="Idle")],
            label="Status Text",
            group="Main",
            perm=IPerm.RO,
        )
        self.define_light(
            "status_light",
            [Light(name="value", label="State", value=IPState.IDLE)],
            label="Status Light",
            group="Main",
        )
        self.define_switch(
            "power",
            [
                Switch(name="on", label="On", value=ISState.OFF),
                Switch(name="off", label="Off", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Power",
            group="Control",
        )
        self.message("Demo device ready.")

    async def on_disconnect(self) -> None:
        """Park the animated properties when the client goes away.

        The ``@every`` job stops on its own because it is declared
        ``when_connected=True``, but whatever it published last would otherwise
        sit there looking live. A real driver closes its hardware link here.
        """
        self._quiesce()
        self["power"].set(off=ISState.ON, state=IPState.IDLE)

    @every(seconds=1, when_connected=True)
    async def animate(self) -> None:
        """Advance the counter and cycle every property through the states.

        ``when_connected=True`` pauses this while the client is disconnected, so
        the two gates differ: connection decides whether the driver is running at
        all, and the power switch decides whether this particular job does
        anything.
        """
        if self["power"]["on"].value is not ISState.ON:
            return
        self._tick += 1
        state = _STATES[self._tick % len(_STATES)]
        self["counters"].set(count=self._tick, ra=(self._tick % 24), state=state)
        self["status_text"].set(value=str(state), state=state)
        self["status_light"].set(value=state, state=state)

    @on_new("power")
    async def _power(self, vector: SwitchVector) -> None:
        """Apply the client's requested power state and confirm it.

        A OneOfMany write names the newly selected member - typically *only* that
        member (`{"on": On}` or `{"off": On}`), though a client may also send the
        full pair - so ``selected()`` asks "which element is On in the request",
        never assuming a particular element is present.
        """
        if not self.require_connected():
            return
        turned_on = vector.selected() == "on"
        # OneOfMany: setting one member On clears its sibling.
        self["power"].set(**{"on" if turned_on else "off": ISState.ON}, state=IPState.OK)
        if not turned_on:
            self._quiesce()
        self.message(f"Power turned {'on' if turned_on else 'off'}.")

    def _quiesce(self) -> None:
        """Park the animated properties in a quiet Idle state."""
        self["counters"].set(state=IPState.IDLE)
        self["status_text"].set(value="Idle", state=IPState.IDLE)
        self["status_light"].set(value=IPState.IDLE, state=IPState.IDLE)


if __name__ == "__main__":
    Demo.run()
