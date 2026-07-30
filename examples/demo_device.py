#!/usr/bin/env python3
"""A reference INDINexus driver.

It exposes one of every INDI vector kind, uses ``@every`` to animate them once a
second, and handles a client write to the switch vector with ``@on_new``. Run it
as a child of ``indiserver``::

    indiserver ./examples/demo_device.py

or just ``python examples/demo_device.py`` and type ``getProperties`` XML at it.
"""

from __future__ import annotations

from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import (
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
        """Define one of each vector kind and announce readiness."""
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

    @every(seconds=1)
    async def animate(self) -> None:
        """Advance the counter and cycle every property through the states.

        Only ticks while the power switch is on, so the demo sits quietly at
        startup until a client flips it.
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
        turned_on = vector.selected() == "on"
        # OneOfMany: setting one member On clears its sibling.
        self["power"].set(**{"on" if turned_on else "off": ISState.ON}, state=IPState.OK)
        if not turned_on:
            # Park the animated properties in a quiet Idle state.
            self["counters"].set(state=IPState.IDLE)
            self["status_text"].set(value="Idle", state=IPState.IDLE)
            self["status_light"].set(value=IPState.IDLE, state=IPState.IDLE)
        self.message(f"Power turned {'on' if turned_on else 'off'}.")


if __name__ == "__main__":
    Demo.run()
