#!/usr/bin/env python3
"""A focuser: the driver built line by line in the "Writing a driver" guide.

A focuser moves a telescope's drawtube in and out until a star comes to a point.
There are three things to say to one: send it to a position, nudge it a step, and
tell it to stop. That makes it the smallest driver that still has a number, a
switch, a job that takes time, and something that has to happen when the client
goes away - which is why the guide teaches with it.

The property names are libindi's own, so KStars and any other standard INDI client
recognises this as a focuser without being told: ``ABS_FOCUS_POSITION`` carries the
target, ``FOCUS_MOTION`` nudges, ``FOCUS_ABORT_MOTION`` stops.

The motor is simulated. ``@every`` walks the position toward its target a few steps
per tick, the way a real one arrives over a second or two rather than at once - and
that delay is what makes ``ABORT`` and the disconnect handler mean anything. There
is no hardware behind it: a real driver opens its serial link in ``on_connect`` and
closes it in ``on_disconnect``.

Run it as a child of ``indiserver``::

    indiserver ./examples/focuser_device.py

or, to try it without installing ``indiserver`` first::

    indikit serve --device examples.focuser_device:Focuser
"""

from __future__ import annotations

from indikit.driver import Device, every, on_new
from indikit.protocol import (
    IPState,
    ISRule,
    ISState,
    Number,
    NumberVector,
    Switch,
    SwitchVector,
)

MIN_POSITION = 0
MAX_POSITION = 50000
NUDGE_STEPS = 500
STEPS_PER_TICK = 250


class Focuser(Device):
    """A focuser: drive to an absolute position, nudge a step, or stop."""

    name = "Focuser"

    def __init__(self, name: str | None = None) -> None:
        """Start the drawtube at rest, with nowhere to be.

        Parameters
        ----------
        name : str or None, optional
            Device name to publish under. Defaults to the class's own ``name``.
        """
        super().__init__(name)
        self._target: float | None = None  # None = at rest, nothing to travel to

    async def setup(self) -> None:
        """Define the connection switch, the position, the nudge and the stop."""
        self.define_connection()
        self.define_number(
            "ABS_FOCUS_POSITION",
            [
                Number(
                    name="FOCUS_ABSOLUTE_POSITION",
                    label="Position",
                    format="%.0f",
                    min=MIN_POSITION,
                    max=MAX_POSITION,
                    value=MAX_POSITION / 2,
                )
            ],
            label="Absolute position",
            group="Main Control",
        )
        self.define_switch(
            "FOCUS_MOTION",
            [
                Switch(name="FOCUS_INWARD", label="In"),
                Switch(name="FOCUS_OUTWARD", label="Out", value=ISState.ON),
            ],
            # Exactly one direction is the current one, so a client draws these as
            # radio buttons and picking one clears the other without the driver
            # saying so.
            rule=ISRule.ONE_OF_MANY,
            label="Nudge",
            group="Main Control",
        )
        self.define_switch(
            "FOCUS_ABORT_MOTION",
            [Switch(name="ABORT", label="Stop")],
            # Nothing is ever "currently aborting", so this rule lets the button
            # spring back rather than latch on the way a ONE_OF_MANY member would.
            rule=ISRule.AT_MOST_ONE,
            label="Abort",
            group="Main Control",
        )
        self.message("Focuser ready.")

    async def on_disconnect(self) -> None:
        """Halt the motor as the link goes down.

        Not housekeeping: a drawtube still travelling when the client walked away
        keeps going until it reaches a hard stop. A real driver would close its
        serial or network link here too, once the motor is at rest.
        """
        self._halt("Motion stopped: the client disconnected.")

    @on_new("ABS_FOCUS_POSITION")
    async def _goto(self, vector: NumberVector) -> None:
        """Take a requested position as the new target and start travelling.

        Parameters
        ----------
        vector : NumberVector
            The requested position. Reading it with a default keeps the handler
            working when a client sends some other element of the vector.
        """
        if not self.require_connected():
            return
        wanted = vector.get("FOCUS_ABSOLUTE_POSITION", 0.0)
        # A client is free to ask for anything; the advertised min/max is a promise
        # about the hardware, so hold to it rather than passing the value through.
        self._target = max(MIN_POSITION, min(MAX_POSITION, wanted))
        # Busy rather than Ok: the drawtube has not arrived, and a client drawing
        # this vector as settled would be telling the operator something false.
        self["ABS_FOCUS_POSITION"].set(state=IPState.BUSY)

    @on_new("FOCUS_MOTION")
    async def _nudge(self, vector: SwitchVector) -> None:
        """Set off toward a fixed step in the selected direction.

        Parameters
        ----------
        vector : SwitchVector
            The requested direction. A client usually sends only the member it
            changed, so this reads the selection rather than a fixed element.
        """
        if not self.require_connected():
            return
        inward = vector.selected() == "FOCUS_INWARD"
        self["FOCUS_MOTION"].set(
            {"FOCUS_INWARD" if inward else "FOCUS_OUTWARD": ISState.ON},
            state=IPState.OK,
        )
        here = self["ABS_FOCUS_POSITION"].value("FOCUS_ABSOLUTE_POSITION")
        step = -NUDGE_STEPS if inward else NUDGE_STEPS
        self._target = max(MIN_POSITION, min(MAX_POSITION, here + step))
        self["ABS_FOCUS_POSITION"].set(state=IPState.BUSY)

    @on_new("FOCUS_ABORT_MOTION")
    async def _abort(self, vector: SwitchVector) -> None:
        """Stop the drawtube where it stands.

        Parameters
        ----------
        vector : SwitchVector
            The abort request. Its contents do not matter: that the button was
            pressed at all is the whole message.
        """
        if not self.require_connected():
            return
        self._halt("Motion aborted.")

    @every(seconds=0.2, when_connected=True)
    async def _step(self) -> None:
        """Walk the drawtube one tick's travel toward its target.

        ``when_connected=True`` stops this on its own while disconnected, so the
        handler never has to ask whether anyone is listening.
        """
        if self._target is None:
            return
        here = self["ABS_FOCUS_POSITION"].value("FOCUS_ABSOLUTE_POSITION")
        remaining = self._target - here
        if abs(remaining) <= STEPS_PER_TICK:
            # Close enough to land exactly rather than overshoot and come back.
            arrived = self._target
            self._target = None
            self["ABS_FOCUS_POSITION"].set(
                FOCUS_ABSOLUTE_POSITION=arrived,
                state=IPState.OK,
            )
            return
        onward = here + (STEPS_PER_TICK if remaining > 0 else -STEPS_PER_TICK)
        self["ABS_FOCUS_POSITION"].set(
            FOCUS_ABSOLUTE_POSITION=onward,
            state=IPState.BUSY,
        )

    def _halt(self, why: str) -> None:
        """Drop the target and settle the position vector where the tube stands.

        Parameters
        ----------
        why : str
            Message sent to clients explaining the stop. Only sent when the tube
            was actually travelling, so an abort pressed at rest stays quiet.
        """
        was_moving = self._target is not None
        self._target = None
        self["ABS_FOCUS_POSITION"].set(state=IPState.IDLE)
        self["FOCUS_ABORT_MOTION"].set({"ABORT": ISState.OFF}, state=IPState.IDLE)
        if was_moving:
            self.message(why)


if __name__ == "__main__":
    Focuser.run()
