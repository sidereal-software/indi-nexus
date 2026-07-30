#!/usr/bin/env python3
"""A telescope-mount driver: libindi's Telescope Simulator, rebuilt on INDINexus.

This ports the operator-facing core of ``telescope_simulator.cpp`` (Jasem
Mutlaq's C++ ScopeSim) to the INDINexus driver SDK, keeping the standard INDI
telescope property names so any INDI client (KStars, ...) recognises it:

- ``EQUATORIAL_EOD_COORD`` with ``ON_COORD_SET`` (Track/Slew/Sync) - the
  standard goto/sync interaction;
- ``TELESCOPE_TRACK_STATE`` / ``TELESCOPE_TRACK_MODE`` - tracking on/off in
  sidereal, solar, or lunar rate, with realistic RA drift when not tracking;
- ``TELESCOPE_SLEW_RATE`` and momentary ``TELESCOPE_MOTION_NS``/``_WE`` paddles;
- ``TELESCOPE_PARK`` (slews to the celestial pole and stops tracking),
  ``TELESCOPE_ABORT_MOTION``, timed guide pulses with ``GUIDE_RATE``, a
  ``GEOGRAPHIC_COORD`` site, and the device-level ``CONNECTION`` switch.

The C++ simulator's alignment subsystem (mount models, pier side, Wallace
corrections, PAC snooping) is a research framework layered on top of the mount
interface and is deliberately out of scope here - this example is the mount.

Run it under ``indiserver``::

    indiserver ./examples/telescope_device.py

or in the web panel without ``indiserver``::

    python -m examples.demo_bridge --device examples.telescope_device:TelescopeSimulator
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

#: On-sky slew speed per TELESCOPE_SLEW_RATE member, in degrees/second.
SLEW_RATES = {
    "SLEW_GUIDE": 0.05,
    "SLEW_CENTERING": 0.5,
    "SLEW_FIND": 5.0,
    "SLEW_MAX": 30.0,
}

#: Tracking rates in arcseconds/second (libindi's TRACKRATE_* constants).
TRACK_RATES = {
    "TRACK_SIDEREAL": 15.041,
    "TRACK_SOLAR": 15.0,
    "TRACK_LUNAR": 14.511,
}

#: The sidereal rate the sky moves at, in arcseconds/second.
SIDEREAL_ARCSEC = TRACK_RATES["TRACK_SIDEREAL"]


def _value(vector: NumberVector, name: str, default: float) -> float:
    """Return the requested value for element ``name``, or ``default``.

    Parameters
    ----------
    vector : NumberVector
        The client's write, which may name only some elements.
    name : str
        The element to look for.
    default : float
        Returned when the write does not include the element.

    Returns
    -------
    value : float
        The requested or fallback value.
    """
    return next((el.value for el in vector.elements if el.name == name), default)


def _selected(vector: SwitchVector) -> str | None:
    """Return the name of the element a client turned On, or `None`.

    Parameters
    ----------
    vector : SwitchVector
        The client's requested switch vector (it may name only one element).

    Returns
    -------
    name : str or None
        The first element whose requested value is On.
    """
    return next((el.name for el in vector.elements if el.value is ISState.ON), None)


class TelescopeSimulator(Device):
    """A simulated GEM-style mount: goto/sync, track, move, guide, park."""

    name = "Telescope Simulator"

    def __init__(self, name: str | None = None) -> None:
        """Initialise the mount pointing at the pole, unparked, not tracking."""
        super().__init__(name)
        self._ra = 0.0  # hours [0, 24)
        self._dec = 90.0  # degrees [-90, 90]
        self._target: tuple[float, float] | None = None  # None = not slewing
        self._track_after_slew = False
        self._parking = False
        self._ns_rate = 0.0  # manual paddle, degrees/second (+N, -S)
        self._we_rate = 0.0  # manual paddle, degrees/second (+W, -E)

    async def setup(self) -> None:
        """Define the standard INDI telescope properties and announce readiness."""
        self.define_switch(
            "CONNECTION",
            [
                Switch(name="CONNECT", label="Connect", value=ISState.OFF),
                Switch(name="DISCONNECT", label="Disconnect", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Connection",
            group="Main Control",
        )
        self.define_number(
            "EQUATORIAL_EOD_COORD",
            [
                Number(name="RA", label="RA (hh:mm:ss)", format="%010.6m", min=0, max=24, value=0),
                Number(
                    name="DEC", label="DEC (dd:mm:ss)", format="%010.6m", min=-90, max=90, value=90
                ),
            ],
            label="Eq. Coordinates",
            group="Main Control",
        )
        self.define_switch(
            "ON_COORD_SET",
            [
                Switch(name="TRACK", label="Track", value=ISState.ON),
                Switch(name="SLEW", label="Slew", value=ISState.OFF),
                Switch(name="SYNC", label="Sync", value=ISState.OFF),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="On Set",
            group="Main Control",
        )
        self.define_switch(
            "TELESCOPE_TRACK_STATE",
            [
                Switch(name="TRACK_ON", label="On", value=ISState.OFF),
                Switch(name="TRACK_OFF", label="Off", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Tracking",
            group="Main Control",
        )
        self.define_switch(
            "TELESCOPE_TRACK_MODE",
            [
                Switch(name="TRACK_SIDEREAL", label="Sidereal", value=ISState.ON),
                Switch(name="TRACK_SOLAR", label="Solar", value=ISState.OFF),
                Switch(name="TRACK_LUNAR", label="Lunar", value=ISState.OFF),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Track Mode",
            group="Main Control",
        )
        self.define_switch(
            "TELESCOPE_PARK",
            [
                Switch(name="PARK", label="Park", value=ISState.OFF),
                Switch(name="UNPARK", label="Unpark", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Parking",
            group="Main Control",
        )
        self.define_switch(
            "TELESCOPE_ABORT_MOTION",
            [Switch(name="ABORT", label="Abort", value=ISState.OFF)],
            rule=ISRule.AT_MOST_ONE,
            label="Abort Motion",
            group="Main Control",
        )
        self.define_switch(
            "TELESCOPE_SLEW_RATE",
            [
                Switch(name="SLEW_GUIDE", label="Guide", value=ISState.OFF),
                Switch(name="SLEW_CENTERING", label="Centering", value=ISState.OFF),
                Switch(name="SLEW_FIND", label="Find", value=ISState.OFF),
                Switch(name="SLEW_MAX", label="Max", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Slew Rate",
            group="Motion",
        )
        self.define_switch(
            "TELESCOPE_MOTION_NS",
            [
                Switch(name="MOTION_NORTH", label="North", value=ISState.OFF),
                Switch(name="MOTION_SOUTH", label="South", value=ISState.OFF),
            ],
            rule=ISRule.AT_MOST_ONE,
            label="Motion N/S",
            group="Motion",
        )
        self.define_switch(
            "TELESCOPE_MOTION_WE",
            [
                Switch(name="MOTION_WEST", label="West", value=ISState.OFF),
                Switch(name="MOTION_EAST", label="East", value=ISState.OFF),
            ],
            rule=ISRule.AT_MOST_ONE,
            label="Motion W/E",
            group="Motion",
        )
        self.define_number(
            "GUIDE_RATE",
            [
                Number(
                    name="GUIDE_RATE_WE", label="W/E Rate", format="%.2f", min=0, max=1, value=0.5
                ),
                Number(
                    name="GUIDE_RATE_NS", label="N/S Rate", format="%.2f", min=0, max=1, value=0.5
                ),
            ],
            label="Guiding Rate",
            group="Motion",
        )
        self.define_number(
            "TELESCOPE_TIMED_GUIDE_NS",
            [
                Number(name="TIMED_GUIDE_N", label="North (ms)", format="%.0f", min=0, max=60000),
                Number(name="TIMED_GUIDE_S", label="South (ms)", format="%.0f", min=0, max=60000),
            ],
            label="Guide N/S",
            group="Motion",
        )
        self.define_number(
            "TELESCOPE_TIMED_GUIDE_WE",
            [
                Number(name="TIMED_GUIDE_W", label="West (ms)", format="%.0f", min=0, max=60000),
                Number(name="TIMED_GUIDE_E", label="East (ms)", format="%.0f", min=0, max=60000),
            ],
            label="Guide W/E",
            group="Motion",
        )
        self.define_number(
            "GEOGRAPHIC_COORD",
            [
                Number(
                    name="LAT", label="Lat (dd:mm:ss)", format="%010.6m", min=-90, max=90, value=32
                ),
                Number(
                    name="LONG", label="Lon (dd:mm:ss)", format="%010.6m", min=0, max=360, value=249
                ),
                Number(
                    name="ELEV",
                    label="Elevation (m)",
                    format="%.0f",
                    min=-200,
                    max=10000,
                    value=2600,
                ),
            ],
            label="Scope Location",
            group="Site",
        )
        self.message("Telescope simulator ready.")

    # -- connection -------------------------------------------------------- #
    @property
    def _connected(self) -> bool:
        """Whether the (simulated) mount link is up."""
        return self["CONNECTION"]["CONNECT"].value is ISState.ON

    def _require_connected(self) -> bool:
        """Return whether commands may run, logging the standard error if not."""
        if self._connected:
            return True
        self.log_error("Telescope is not connected.")
        return False

    @property
    def _parked(self) -> bool:
        """Whether the mount is parked."""
        return self["TELESCOPE_PARK"]["PARK"].value is ISState.ON

    def _require_unparked(self) -> bool:
        """Return whether motion may run, logging the standard error if not."""
        if not self._parked:
            return True
        self.log_error("Please unpark the mount before issuing any motion commands.")
        return False

    @property
    def _tracking(self) -> bool:
        """Whether sidereal-style tracking is currently on."""
        return self["TELESCOPE_TRACK_STATE"]["TRACK_ON"].value is ISState.ON

    @on_new("CONNECTION")
    async def _connection(self, vector: SwitchVector) -> None:
        """Open or close the (simulated) mount link."""
        connect = _selected(vector) == "CONNECT"
        self["CONNECTION"].set(
            **{"CONNECT" if connect else "DISCONNECT": ISState.ON}, state=IPState.OK
        )
        if not connect:
            # Halt all motion so nothing is left Busy behind a dead link.
            self._target = None
            self._parking = False
            self._ns_rate = self._we_rate = 0.0
            self["EQUATORIAL_EOD_COORD"].set(state=IPState.IDLE)
        self.message(f"Telescope simulator is {'online' if connect else 'offline'}.")

    # -- simulation -------------------------------------------------------- #
    @every(seconds=1)
    async def tick(self) -> None:
        """Advance the mount simulation by one second."""
        if not self._connected:
            return
        if self._target is not None:
            self._tick_slew()
            return
        moved = self._tick_manual_motion()
        drifted = self._tick_drift()
        if moved or drifted:
            self._publish(IPState.IDLE if not self._tracking else IPState.OK)

    def _slew_speed(self) -> float:
        """The selected slew rate in degrees/second."""
        rate = self["TELESCOPE_SLEW_RATE"]
        selected = next(
            (el.name for el in rate.vector.elements if el.value is ISState.ON), "SLEW_MAX"
        )
        return SLEW_RATES[selected]

    def _tick_slew(self) -> None:
        """Step both axes toward the slew target, finishing when both arrive."""
        assert self._target is not None
        target_ra, target_dec = self._target
        speed = self._slew_speed()
        ra_step = speed / 15.0  # hours of RA per second
        dec_step = speed

        # RA is circular (24h); take the shortest way around.
        delta = (target_ra - self._ra) % 24.0
        if min(delta, 24.0 - delta) <= ra_step:
            self._ra = target_ra
        else:
            self._ra = (self._ra + (ra_step if delta <= 12.0 else -ra_step)) % 24.0

        # Dec is a plain bounded axis.
        if abs(target_dec - self._dec) <= dec_step:
            self._dec = target_dec
        else:
            self._dec += dec_step if target_dec > self._dec else -dec_step

        if self._ra == target_ra and self._dec == target_dec:
            self._target = None
            if self._parking:
                self._parking = False
                self._set_tracking(False)
                self["TELESCOPE_PARK"].set(PARK=ISState.ON, state=IPState.OK)
                self._publish(IPState.IDLE)
                self.message("Telescope slew is complete. Parked.")
            elif self._track_after_slew:
                self._set_tracking(True)
                self._publish(IPState.OK)
                self.message("Telescope slew is complete. Tracking...")
            else:
                self._publish(IPState.IDLE)
                self.message("Telescope slew is complete.")
        else:
            self._publish(IPState.BUSY)

    def _tick_manual_motion(self) -> bool:
        """Apply the motion paddles for one second; report whether we moved."""
        if self._ns_rate == 0.0 and self._we_rate == 0.0:
            return False
        self._dec = min(90.0, max(-90.0, self._dec + self._ns_rate))
        self._ra = (self._ra + self._we_rate / 15.0) % 24.0
        return True

    def _tick_drift(self) -> bool:
        """Apply one second of sky drift; report whether RA changed.

        With tracking off the sky drifts past the stationary mount at the full
        sidereal rate; solar/lunar tracking leaves the small difference from
        sidereal. Sidereal tracking follows the sky exactly.
        """
        if self._parked:
            return False
        if self._tracking:
            mode = self["TELESCOPE_TRACK_MODE"]
            selected = next(
                (el.name for el in mode.vector.elements if el.value is ISState.ON),
                "TRACK_SIDEREAL",
            )
            arcsec = SIDEREAL_ARCSEC - TRACK_RATES[selected]
        else:
            arcsec = SIDEREAL_ARCSEC
        if arcsec == 0.0:
            return False
        self._ra = (self._ra + arcsec / 15.0 / 3600.0) % 24.0
        return True

    def _publish(self, state: IPState) -> None:
        """Emit the current pointing as a set of EQUATORIAL_EOD_COORD."""
        self["EQUATORIAL_EOD_COORD"].set(RA=self._ra, DEC=self._dec, state=state)

    def _set_tracking(self, on: bool) -> None:
        """Flip the tracking switch (and confirm it) without a log message."""
        self["TELESCOPE_TRACK_STATE"].set(
            **{"TRACK_ON" if on else "TRACK_OFF": ISState.ON}, state=IPState.OK
        )

    def _start_slew(self, ra: float, dec: float, *, track_after: bool) -> None:
        """Begin slewing to ``ra``/``dec`` (hours/degrees).

        Parameters
        ----------
        ra : float
            Target right ascension in hours; wrapped into [0, 24).
        dec : float
            Target declination in degrees; clamped to [-90, 90].
        track_after : bool
            Whether tracking starts when the slew completes.
        """
        self._target = (ra % 24.0, min(90.0, max(-90.0, dec)))
        self._track_after_slew = track_after
        self._publish(IPState.BUSY)

    # -- client writes ------------------------------------------------------ #
    @on_new("EQUATORIAL_EOD_COORD")
    async def _coords(self, vector: NumberVector) -> None:
        """Goto, slew, or sync to the requested coordinates per ON_COORD_SET."""
        if not self._require_connected() or not self._require_unparked():
            return
        ra = _value(vector, "RA", self._ra) % 24.0
        dec = min(90.0, max(-90.0, _value(vector, "DEC", self._dec)))
        action = next(
            (el.name for el in self["ON_COORD_SET"].vector.elements if el.value is ISState.ON),
            "TRACK",
        )
        if action == "SYNC":
            self._ra, self._dec = ra, dec
            self._target = None
            self._publish(IPState.OK)
            self.message("Sync is successful.")
            return
        self._start_slew(ra, dec, track_after=action == "TRACK")
        self.message(f"Slewing to RA: {ra:.4f} Dec: {dec:.4f}")

    @on_new("ON_COORD_SET")
    async def _on_coord_set(self, vector: SwitchVector) -> None:
        """Select what a coordinate write does (track, slew only, or sync)."""
        if not self._require_connected():
            return
        selected = _selected(vector)
        if selected is not None:
            self["ON_COORD_SET"].set(**{selected: ISState.ON}, state=IPState.OK)

    @on_new("TELESCOPE_TRACK_STATE")
    async def _track_state(self, vector: SwitchVector) -> None:
        """Turn tracking on or off."""
        if not self._require_connected() or not self._require_unparked():
            return
        on = _selected(vector) == "TRACK_ON"
        self._set_tracking(on)
        self.message(f"Tracking {'enabled' if on else 'disabled'}.")

    @on_new("TELESCOPE_TRACK_MODE")
    async def _track_mode(self, vector: SwitchVector) -> None:
        """Select the tracking rate (sidereal, solar, or lunar)."""
        if not self._require_connected():
            return
        selected = _selected(vector)
        if selected in TRACK_RATES:
            self["TELESCOPE_TRACK_MODE"].set(**{selected: ISState.ON}, state=IPState.OK)

    @on_new("TELESCOPE_SLEW_RATE")
    async def _slew_rate(self, vector: SwitchVector) -> None:
        """Select the slew/paddle speed."""
        if not self._require_connected():
            return
        selected = _selected(vector)
        if selected in SLEW_RATES:
            self["TELESCOPE_SLEW_RATE"].set(**{selected: ISState.ON}, state=IPState.OK)

    @on_new("TELESCOPE_MOTION_NS")
    async def _motion_ns(self, vector: SwitchVector) -> None:
        """Start or stop the manual North/South paddle."""
        if not self._require_connected() or not self._require_unparked():
            return
        selected = _selected(vector)
        speed = self._slew_speed()
        self._ns_rate = (
            0.0 if selected is None else (speed if selected == "MOTION_NORTH" else -speed)
        )
        prop = self["TELESCOPE_MOTION_NS"]
        if selected is None:
            prop.set(MOTION_NORTH=ISState.OFF, MOTION_SOUTH=ISState.OFF, state=IPState.IDLE)
        else:
            prop.set(**{selected: ISState.ON}, state=IPState.BUSY)

    @on_new("TELESCOPE_MOTION_WE")
    async def _motion_we(self, vector: SwitchVector) -> None:
        """Start or stop the manual West/East paddle."""
        if not self._require_connected() or not self._require_unparked():
            return
        selected = _selected(vector)
        speed = self._slew_speed()
        self._we_rate = (
            0.0 if selected is None else (speed if selected == "MOTION_WEST" else -speed)
        )
        prop = self["TELESCOPE_MOTION_WE"]
        if selected is None:
            prop.set(MOTION_WEST=ISState.OFF, MOTION_EAST=ISState.OFF, state=IPState.IDLE)
        else:
            prop.set(**{selected: ISState.ON}, state=IPState.BUSY)

    @on_new("TELESCOPE_PARK")
    async def _park(self, vector: SwitchVector) -> None:
        """Park (slew to the pole, stop tracking) or unpark."""
        if not self._require_connected():
            return
        if _selected(vector) == "PARK":
            if self._parked:
                self.message("Telescope already parked.")
                return
            self._parking = True
            self._ns_rate = self._we_rate = 0.0
            self["TELESCOPE_PARK"].set(PARK=ISState.ON, state=IPState.BUSY)
            pole = 90.0 if self["GEOGRAPHIC_COORD"]["LAT"].value >= 0 else -90.0
            self._start_slew(self._ra, pole, track_after=False)
            self.message("Parking...")
        else:
            self._parking = False
            self["TELESCOPE_PARK"].set(UNPARK=ISState.ON, state=IPState.OK)
            self.message("Telescope unparked.")

    @on_new("TELESCOPE_ABORT_MOTION")
    async def _abort(self, vector: SwitchVector) -> None:
        """Stop any slew and manual motion; tracking state is left as is."""
        if not self._require_connected():
            return
        self._target = None
        self._parking = False
        self._ns_rate = self._we_rate = 0.0
        self["TELESCOPE_MOTION_NS"].set(
            MOTION_NORTH=ISState.OFF, MOTION_SOUTH=ISState.OFF, state=IPState.IDLE
        )
        self["TELESCOPE_MOTION_WE"].set(
            MOTION_WEST=ISState.OFF, MOTION_EAST=ISState.OFF, state=IPState.IDLE
        )
        self._publish(IPState.IDLE if not self._tracking else IPState.OK)
        self["TELESCOPE_ABORT_MOTION"].set(ABORT=ISState.OFF, state=IPState.OK)
        self.message("Telescope motion aborted.")

    @on_new("GUIDE_RATE")
    async def _guide_rate(self, vector: NumberVector) -> None:
        """Accept new guide rates, clamped to [0, 1] of sidereal."""
        if not self._require_connected():
            return
        rate = self["GUIDE_RATE"]
        updates = {
            el.name: min(1.0, max(0.0, el.value))
            for el in vector.elements
            if el.name in ("GUIDE_RATE_WE", "GUIDE_RATE_NS")
        }
        if updates:
            rate.set(updates, state=IPState.OK)

    def _guide_pulse(self, axis: str, arcsec: float) -> None:
        """Apply one finished guide pulse as a small offset.

        Parameters
        ----------
        axis : str
            `"ra"` or `"dec"`.
        arcsec : float
            The signed on-sky offset in arcseconds.
        """
        if axis == "dec":
            self._dec = min(90.0, max(-90.0, self._dec + arcsec / 3600.0))
        else:
            self._ra = (self._ra + arcsec / 3600.0 / 15.0) % 24.0
        self._publish(IPState.OK if self._tracking else IPState.IDLE)

    @on_new("TELESCOPE_TIMED_GUIDE_NS")
    async def _guide_ns(self, vector: NumberVector) -> None:
        """Apply a timed North/South guide pulse (completes immediately)."""
        if not self._require_connected() or not self._require_unparked():
            return
        rate = self["GUIDE_RATE"]["GUIDE_RATE_NS"].value
        ms = _value(vector, "TIMED_GUIDE_N", 0.0) - _value(vector, "TIMED_GUIDE_S", 0.0)
        self._guide_pulse("dec", rate * SIDEREAL_ARCSEC * ms / 1000.0)
        self["TELESCOPE_TIMED_GUIDE_NS"].set(TIMED_GUIDE_N=0, TIMED_GUIDE_S=0, state=IPState.OK)

    @on_new("TELESCOPE_TIMED_GUIDE_WE")
    async def _guide_we(self, vector: NumberVector) -> None:
        """Apply a timed West/East guide pulse (completes immediately)."""
        if not self._require_connected() or not self._require_unparked():
            return
        rate = self["GUIDE_RATE"]["GUIDE_RATE_WE"].value
        ms = _value(vector, "TIMED_GUIDE_W", 0.0) - _value(vector, "TIMED_GUIDE_E", 0.0)
        self._guide_pulse("ra", rate * SIDEREAL_ARCSEC * ms / 1000.0)
        self["TELESCOPE_TIMED_GUIDE_WE"].set(TIMED_GUIDE_W=0, TIMED_GUIDE_E=0, state=IPState.OK)

    @on_new("GEOGRAPHIC_COORD")
    async def _location(self, vector: NumberVector) -> None:
        """Store the observing site."""
        if not self._require_connected():
            return
        site = self["GEOGRAPHIC_COORD"]
        site.set(
            LAT=min(90.0, max(-90.0, _value(vector, "LAT", site["LAT"].value))),
            LONG=_value(vector, "LONG", site["LONG"].value) % 360.0,
            ELEV=_value(vector, "ELEV", site["ELEV"].value),
            state=IPState.OK,
        )
        self.message("Site location updated.")


if __name__ == "__main__":
    TelescopeSimulator.run()
