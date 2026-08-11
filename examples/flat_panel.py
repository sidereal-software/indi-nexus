#!/usr/bin/env python3
"""A flat-field lamp: the driver built line by line in the "Writing a driver" guide.

A flat panel is a lit screen an observatory points the telescope at to record a
flat field. There are two things to say to one: turn it on or off, and set how
bright it is - which makes it the smallest driver that still has both a switch
and a number, and the reason the guide teaches with it.

Deliberately the simplest example here: no hardware link, no ``@every`` polling,
no failure handling. ``weather_device.py`` is the one to copy for real hardware.

Run it as a child of ``indiserver``::

    indiserver ./examples/flat_panel.py

or see it in the reference panel with no ``indiserver`` at all::

    python -m examples.demo_bridge --device examples.flat_panel:FlatPanel
"""

from __future__ import annotations

from indi_nexus.driver import Device, on_new
from indi_nexus.protocol import (
    IPState,
    ISRule,
    ISState,
    Number,
    NumberVector,
    Switch,
    SwitchVector,
)

MIN_BRIGHTNESS = 0
MAX_BRIGHTNESS = 255


class FlatPanel(Device):
    """A flat-field lamp: on/off, and a brightness dial."""

    name = "Flat Panel"

    async def setup(self) -> None:
        """Define the lamp switch and the brightness dial, then announce readiness."""
        self.define_switch(
            "LIGHT_CONTROL",
            [
                Switch(name="ON", label="On"),
                Switch(name="OFF", label="Off", value=ISState.ON),
            ],
            # Exactly one of these is on, so a client draws it as radio buttons and
            # turning one on turns the other off without the driver saying so.
            rule=ISRule.ONE_OF_MANY,
            label="Lamp",
            group="Main Control",
        )
        self.define_number(
            "LIGHT_BRIGHTNESS",
            [
                Number(
                    name="BRIGHTNESS",
                    label="Brightness",
                    format="%.0f",
                    min=MIN_BRIGHTNESS,
                    max=MAX_BRIGHTNESS,
                    value=128,
                )
            ],
            label="Brightness",
            group="Main Control",
        )
        self.message("Flat panel ready.")

    @on_new("LIGHT_CONTROL")
    async def _switch_lamp(self, vector: SwitchVector) -> None:
        """Turn the lamp on or off in response to a client write.

        Parameters
        ----------
        vector : SwitchVector
            The requested switch state. A client usually sends only the member it
            changed, so this reads the selection rather than a fixed element.
        """
        on = vector.selected() == "ON"
        self["LIGHT_CONTROL"].set(
            {"ON" if on else "OFF": ISState.ON},
            state=IPState.OK,
        )
        self.message(f"Lamp turned {'on' if on else 'off'}.")

    @on_new("LIGHT_BRIGHTNESS")
    async def _set_brightness(self, vector: NumberVector) -> None:
        """Apply a requested brightness, clamped to the range the driver advertised.

        Parameters
        ----------
        vector : NumberVector
            The requested brightness. Reading it with a default keeps the handler
            working when a client sends some other element of the vector.
        """
        wanted = vector.get("BRIGHTNESS", 0.0)
        # A client is free to ask for anything; the advertised min/max is a promise
        # about the hardware, so hold to it rather than passing the value through.
        clamped = max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, wanted))
        self["LIGHT_BRIGHTNESS"].set(BRIGHTNESS=clamped, state=IPState.OK)


if __name__ == "__main__":
    FlatPanel.run()
