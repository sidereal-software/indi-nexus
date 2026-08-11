#!/usr/bin/env python3
"""A dome-control driver: libindi's classic Dome Simulator, rebuilt on INDINexus.

This is a port of ``dome_simulator.cpp`` (Jasem Mutlaq's C++ Dome Simulator) to
the INDINexus driver SDK. It keeps the standard INDI property names - the
device-level ``CONNECTION`` switch (one ``define_connection()`` call here),
``ABS_DOME_POSITION``, ``REL_DOME_POSITION``, ``DOME_SHUTTER``, ``DOME_PARK``,
``DOME_ABORT_MOTION`` - so any INDI client recognises it, and the same motion
model: the dome rotates toward a target azimuth at a configurable deg/s taking
the shortest way around, and the shutter opens/closes over time at m/s.
Commands only work while connected, and the ~300-line C++ class becomes a
compact typed device: properties are declared in ``setup()``, client writes
arrive as parsed vectors via ``@on_new``, and the whole simulation is one
``@every`` tick that pauses automatically while disconnected.

Run it under ``indiserver``::

    indiserver ./examples/dome_device.py

or in the web panel without ``indiserver``::

    indi-nexus serve --device examples.dome_device:DomeSimulator
"""

from __future__ import annotations

from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import (
    IPState,
    ISRule,
    ISState,
    Number,
    NumberVector,
    Switch,
    SwitchVector,
)

#: Azimuth the dome parks at, in degrees (the C++ simulator's default).
PARK_AZ = 90.0

#: Metres of shutter travel per open/close: half the 1 m width, since both
#: halves move at once (same assumption as the C++ simulator).
SHUTTER_TRAVEL_M = 0.5


def _range360(degrees: float) -> float:
    """Normalise an angle to the [0, 360) range.

    Parameters
    ----------
    degrees : float
        The angle in degrees.

    Returns
    -------
    normalised : float
        The equivalent angle in [0, 360).
    """
    return degrees % 360.0


class DomeSimulator(Device):
    """A simulated observatory dome: connect, rotate in azimuth, shutter, park."""

    name = "Dome Simulator"

    def __init__(self, name: str | None = None) -> None:
        """Initialise the dome at azimuth 0, shutter closed, not moving."""
        super().__init__(name)
        self._target_az: float | None = None  # None = not rotating
        self._shutter_travel = 0.0  # metres left to move; 0 = shutter at rest
        self._parking = False
        self._unparking = False

    async def setup(self) -> None:
        """Define the standard INDI dome properties and announce readiness."""
        self.define_connection()
        self.define_number(
            "ABS_DOME_POSITION",
            [Number(name="DOME_ABSOLUTE_POSITION", label="Degrees", format="%.2f", min=0, max=360)],
            label="Absolute Position",
            group="Motion",
        )
        self.define_number(
            "REL_DOME_POSITION",
            [
                Number(
                    name="DOME_RELATIVE_POSITION", label="Degrees", format="%.2f", min=-180, max=180
                )
            ],
            label="Relative Position",
            group="Motion",
        )
        self.define_number(
            "SPEEDS",
            [
                Number(name="DOME", label="Dome (deg/s)", format="%.2f", min=0.1, max=10, value=5),
                Number(
                    name="SHUTTER", label="Shutter (m/s)", format="%.2f", min=0.01, max=1, value=0.1
                ),
            ],
            label="Speeds",
            group="Main Control",
        )
        self.define_switch(
            "DOME_SHUTTER",
            [
                Switch(name="SHUTTER_OPEN", label="Open", value=ISState.OFF),
                Switch(name="SHUTTER_CLOSE", label="Close", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Shutter",
            group="Main Control",
        )
        self.define_switch(
            "DOME_PARK",
            [
                Switch(name="PARK", label="Park", value=ISState.OFF),
                Switch(name="UNPARK", label="Unpark", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Parking",
            group="Main Control",
        )
        self.define_switch(
            "DOME_ABORT_MOTION",
            [Switch(name="ABORT", label="Abort", value=ISState.OFF)],
            rule=ISRule.AT_MOST_ONE,
            label="Abort Motion",
            group="Main Control",
        )
        self.message("Dome simulator ready.")

    async def on_disconnect(self) -> None:
        """Halt any motion so nothing is left Busy behind a dead link.

        A real driver would close its serial/network connection here.
        """
        self._target_az = None
        self._shutter_travel = 0.0
        self._parking = self._unparking = False
        self["ABS_DOME_POSITION"].set(state=IPState.IDLE)
        self["DOME_SHUTTER"].set(state=IPState.IDLE)
        self["DOME_PARK"].set(state=IPState.IDLE)

    # -- simulation -------------------------------------------------------- #
    @every(seconds=1, when_connected=True)
    async def tick(self) -> None:
        """Advance the rotation and shutter simulations by one second.

        ``when_connected=True`` pauses the job while disconnected, mirroring
        the C++ ``TimerHit``'s ``if (!isConnected()) return``.
        """
        self._tick_rotation()
        self._tick_shutter()

    def _tick_rotation(self) -> None:
        """Step the dome toward the target azimuth, the shortest way around."""
        if self._target_az is None:
            return
        position = self["ABS_DOME_POSITION"]
        speed: float = self["SPEEDS"]["DOME"].value
        current: float = position["DOME_ABSOLUTE_POSITION"].value

        delta = _range360(self._target_az - current)
        if min(delta, 360.0 - delta) <= speed:  # within one step: arrive
            position.set(DOME_ABSOLUTE_POSITION=self._target_az, state=IPState.OK)
            self._target_az = None
            self.message("Dome reached requested azimuth angle.")
            if self._parking:
                self._parking = False
                self["DOME_PARK"].set(PARK=ISState.ON, state=IPState.OK)
                self.message("Dome parked.")
            return
        step = speed if delta <= 180.0 else -speed
        position.set(DOME_ABSOLUTE_POSITION=_range360(current + step), state=IPState.BUSY)

    def _tick_shutter(self) -> None:
        """Advance the shutter by one second of travel, finishing when done."""
        if self._shutter_travel <= 0:
            return
        self._shutter_travel -= self["SPEEDS"]["SHUTTER"].value
        if self._shutter_travel > 1e-9:  # tolerance: repeated float subtraction
            return
        self._shutter_travel = 0.0
        shutter = self["DOME_SHUTTER"]
        opened = shutter["SHUTTER_OPEN"].value is ISState.ON
        shutter.set(state=IPState.OK)
        self.message(f"Shutter is {'open' if opened else 'closed'}.")
        if self._unparking:
            self._unparking = False
            self["DOME_PARK"].set(UNPARK=ISState.ON, state=IPState.OK)
            self.message("Dome unparked.")

    # -- motion ------------------------------------------------------------ #
    def _slew_to(self, azimuth: float) -> None:
        """Start rotating toward ``azimuth``, arriving at once if it is close.

        Parameters
        ----------
        azimuth : float
            The target azimuth in degrees (any angle; normalised to [0, 360)).
        """
        position = self["ABS_DOME_POSITION"]
        target = _range360(azimuth)
        delta = _range360(target - position["DOME_ABSOLUTE_POSITION"].value)
        if min(delta, 360.0 - delta) <= self["SPEEDS"]["DOME"].value:
            position.set(DOME_ABSOLUTE_POSITION=target, state=IPState.OK)
            return
        self._target_az = target
        position.set(state=IPState.BUSY)

    def _move_shutter(self, open_: bool) -> None:
        """Start opening or closing the shutter.

        Parameters
        ----------
        open_ : bool
            `True` to open the shutter, `False` to close it.
        """
        member = "SHUTTER_OPEN" if open_ else "SHUTTER_CLOSE"
        self["DOME_SHUTTER"].set(**{member: ISState.ON}, state=IPState.BUSY)
        self._shutter_travel = SHUTTER_TRAVEL_M

    # -- client writes ------------------------------------------------------ #
    @on_new("ABS_DOME_POSITION")
    async def _abs_move(self, vector: NumberVector) -> None:
        """Rotate to the requested absolute azimuth."""
        if not self.require_connected():
            return
        current = self["ABS_DOME_POSITION"]["DOME_ABSOLUTE_POSITION"].value
        self._slew_to(vector.get("DOME_ABSOLUTE_POSITION", current))

    @on_new("REL_DOME_POSITION")
    async def _rel_move(self, vector: NumberVector) -> None:
        """Rotate by the requested azimuth offset from the current position."""
        if not self.require_connected():
            return
        offset: float = vector.get("DOME_RELATIVE_POSITION", 0.0)
        current: float = self["ABS_DOME_POSITION"]["DOME_ABSOLUTE_POSITION"].value
        self["REL_DOME_POSITION"].set(DOME_RELATIVE_POSITION=offset, state=IPState.OK)
        self._slew_to(current + offset)

    @on_new("SPEEDS")
    async def _speeds(self, vector: NumberVector) -> None:
        """Accept new dome/shutter speeds, clamped to each member's range."""
        if not self.require_connected():
            return
        speeds = self["SPEEDS"]
        members = {member.name: member for member in speeds.vector.elements}
        updates: dict[str, float] = {}
        for name, value in vector.values().items():
            member = members.get(name)
            if not isinstance(member, Number):
                continue  # ignore unknown members in the request
            value = value if member.min is None else max(value, member.min)
            updates[name] = value if member.max is None else min(value, member.max)
        if updates:
            speeds.set(updates, state=IPState.OK)

    @on_new("DOME_SHUTTER")
    async def _shutter(self, vector: SwitchVector) -> None:
        """Open or close the shutter, whichever member the client selected."""
        if not self.require_connected():
            return
        selected = vector.selected()
        if selected is None:
            return
        self._move_shutter(open_=selected == "SHUTTER_OPEN")

    @on_new("DOME_PARK")
    async def _park(self, vector: SwitchVector) -> None:
        """Park (close the shutter, rotate to the park azimuth) or unpark."""
        if not self.require_connected():
            return
        if vector.selected() == "PARK":
            self._parking, self._unparking = True, False
            self["DOME_PARK"].set(PARK=ISState.ON, state=IPState.BUSY)
            self._move_shutter(open_=False)
            self._slew_to(PARK_AZ)
            if self._target_az is None:  # already at the park azimuth
                self._parking = False
                self["DOME_PARK"].set(PARK=ISState.ON, state=IPState.OK)
                self.message("Dome parked.")
        else:
            self._unparking, self._parking = True, False
            self["DOME_PARK"].set(UNPARK=ISState.ON, state=IPState.BUSY)
            self._move_shutter(open_=True)

    @on_new("DOME_ABORT_MOTION")
    async def _abort(self, vector: SwitchVector) -> None:
        """Stop the rotation; an interrupted shutter is left in an Alert state."""
        if not self.require_connected():
            return
        self._parking = self._unparking = False
        if self._target_az is not None:
            self._target_az = None
            self["ABS_DOME_POSITION"].set(state=IPState.IDLE)
        if self._shutter_travel > 0:
            self._shutter_travel = 0.0
            self["DOME_SHUTTER"].set(state=IPState.ALERT)
            self.log_error("Shutter operation aborted. Status: unknown.")
        self["DOME_ABORT_MOTION"].set(ABORT=ISState.OFF, state=IPState.OK)
        self.message("Motion aborted.")


if __name__ == "__main__":
    DomeSimulator.run()
