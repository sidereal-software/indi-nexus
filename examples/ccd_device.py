#!/usr/bin/env python3
"""A camera driver: libindi's CCD Simulator, rebuilt on INDIkit.

This is a behavioral port of ``ccd_simulator.cpp`` (Jasem Mutlaq / Gerry
Rozema's C++ CCD Simulator) to the INDIkit driver SDK. It keeps the standard
INDI CCD property names - ``CCD_EXPOSURE``, ``CCD_ABORT_EXPOSURE``,
``CCD_FRAME_TYPE``, ``CCD_BINNING``, ``CCD_TEMPERATURE``, ``CCD_COOLER``,
``CCD_GAIN``, ``CCD_OFFSET``, ``CCD_INFO``, and the ``CCD1`` image BLOB - so
any INDI client recognises it, and the same behaviors: an exposure counts down
in ``CCD_EXPOSURE_VALUE`` and completes with a rendered 16-bit FITS star field,
and the TEC cooler pulls toward a set point at half a degree per second and
drifts back to ambient exponentially when switched off.

Deliberately not ported: the parts that lean on external programs or on
``indiserver``-level plumbing - the GSC star catalog and xplanet planet
rendering, video streaming, the guide head, and mount/focuser snooping. The
star field here is synthetic (a deterministic random field per driver
instance), rendered off the event loop, so the driver stays dependency-free
and fast.

This is the driver half of a BLOB. For the client half - and for the
``enable_blob`` call without which ``indiserver`` silently forwards no image at
all - see ``examples/blob_receiver.py``.

Run it under ``indiserver``::

    indiserver ./examples/ccd_device.py

or in the web panel without ``indiserver``::

    indikit serve --device examples.ccd_device:CCDSimulator
"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
import random
import struct
from array import array

from indikit.driver import Device, every, on_new
from indikit.protocol import (
    BLOB,
    IPerm,
    IPState,
    ISRule,
    ISState,
    Number,
    NumberVector,
    Switch,
    SwitchVector,
)

#: Ambient temperature the sensor rests at with the cooler off (C++ constant).
AMBIENT_C = 25.0

#: Coldest achievable sensor temperature: 40 C below ambient (C++ constant).
MIN_TEC_C = -15.0

#: Degrees the TEC moves per one-second tick while actively cooling.
COOLING_STEP_C = 0.5

#: Stars rendered into the synthetic field (brightest to faintest).
STAR_COUNT = 60


def _fits_card(keyword: str, value: str) -> bytes:
    """Return one 80-byte FITS header card.

    Parameters
    ----------
    keyword : str
        The FITS keyword (8 characters or fewer).
    value : str
        The already-formatted value field, e.g. ``"                   16"``.

    Returns
    -------
    card : bytes
        The keyword, ``= ``, and value, space-padded to exactly 80 bytes.
    """
    return f"{keyword:<8}= {value}".ljust(80).encode("ascii")


def _to_fits(pixels: array, width: int, height: int, headers: dict[str, str]) -> bytes:
    """Encode a 16-bit image as a minimal single-HDU FITS file.

    FITS stores 16-bit data as big-endian *signed* integers with
    ``BZERO = 32768``, so each unsigned pixel is shifted down before packing.

    Parameters
    ----------
    pixels : array
        Unsigned 16-bit pixel values (``array("H")``), row-major, ``width *
        height`` long.
    width : int
        Image width in pixels (``NAXIS1``).
    height : int
        Image height in pixels (``NAXIS2``).
    headers : dict
        Extra header cards as pre-formatted ``keyword -> value field`` pairs.

    Returns
    -------
    fits : bytes
        The complete FITS file: 2880-byte-aligned header and data units.
    """
    cards = [
        _fits_card("SIMPLE", f"{'T':>20}"),
        _fits_card("BITPIX", f"{16:>20}"),
        _fits_card("NAXIS", f"{2:>20}"),
        _fits_card("NAXIS1", f"{width:>20}"),
        _fits_card("NAXIS2", f"{height:>20}"),
        _fits_card("BZERO", f"{32768:>20}"),
        _fits_card("BSCALE", f"{1:>20}"),
    ]
    cards.extend(_fits_card(key, value) for key, value in headers.items())
    cards.append(b"END".ljust(80))
    header = b"".join(cards)
    header += b" " * (-len(header) % 2880)

    signed = array("h", (value - 32768 for value in pixels))
    data = struct.pack(f">{len(signed)}h", *signed)
    data += b"\0" * (-len(data) % 2880)
    return header + data


class CCDSimulator(Device):
    """A simulated camera: exposures, a synthetic star field, and a TEC cooler."""

    name = "CCD Simulator"

    def __init__(self, name: str | None = None) -> None:
        """Initialise with no exposure running and the sensor at ambient."""
        super().__init__(name)
        self._exposure_left = 0.0  # wall seconds until the exposure completes
        self._exposure_request = 0.0  # the client's requested duration
        self._exposing = False
        self._rendering = False  # a frame is being generated off-loop
        self._temperature_target: float | None = None  # None = TEC holding
        # One star field per driver instance: consecutive exposures show the
        # same sky, as a camera on a tracking mount would.
        self._sky = random.Random(x=4)

    async def setup(self) -> None:
        """Define the standard INDI CCD properties and announce readiness."""
        self.define_connection()
        self.define_number(
            "CCD_INFO",
            [
                Number(name="CCD_MAX_X", label="Max Width", format="%.0f", value=640),
                Number(name="CCD_MAX_Y", label="Max Height", format="%.0f", value=480),
                Number(name="CCD_PIXEL_SIZE", label="Pixel size (um)", format="%.2f", value=5.2),
                Number(name="CCD_PIXEL_SIZE_X", label="Pixel X (um)", format="%.2f", value=5.2),
                Number(name="CCD_PIXEL_SIZE_Y", label="Pixel Y (um)", format="%.2f", value=5.2),
                Number(name="CCD_BITSPERPIXEL", label="Bits per pixel", format="%.0f", value=16),
            ],
            perm=IPerm.RO,
            label="CCD Information",
            group="Image Info",
        )
        self.define_number(
            "CCD_EXPOSURE",
            [
                Number(
                    name="CCD_EXPOSURE_VALUE",
                    label="Duration (s)",
                    format="%5.2f",
                    min=0,
                    max=3600,
                    value=1,
                )
            ],
            label="Expose",
            group="Main Control",
        )
        self.define_switch(
            "CCD_ABORT_EXPOSURE",
            [Switch(name="ABORT", label="Abort", value=ISState.OFF)],
            rule=ISRule.AT_MOST_ONE,
            label="Abort Exposure",
            group="Main Control",
        )
        self.define_switch(
            "CCD_FRAME_TYPE",
            [
                Switch(name="FRAME_LIGHT", label="Light", value=ISState.ON),
                Switch(name="FRAME_BIAS", label="Bias", value=ISState.OFF),
                Switch(name="FRAME_DARK", label="Dark", value=ISState.OFF),
                Switch(name="FRAME_FLAT", label="Flat", value=ISState.OFF),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Frame Type",
            group="Image Settings",
        )
        self.define_number(
            "CCD_BINNING",
            [
                Number(name="HOR_BIN", label="X", format="%.0f", min=1, max=4, step=1, value=1),
                Number(name="VER_BIN", label="Y", format="%.0f", min=1, max=4, step=1, value=1),
            ],
            label="Binning",
            group="Image Settings",
        )
        self.define_number(
            "CCD_TEMPERATURE",
            [
                Number(
                    name="CCD_TEMPERATURE_VALUE",
                    label="Temperature (C)",
                    format="%5.2f",
                    min=MIN_TEC_C,
                    max=AMBIENT_C,
                    value=AMBIENT_C,
                )
            ],
            label="Temperature",
            group="Main Control",
        )
        self.define_switch(
            "CCD_COOLER",
            [
                Switch(name="COOLER_ON", label="On", value=ISState.OFF),
                Switch(name="COOLER_OFF", label="Off", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Cooler",
            group="Main Control",
        )
        self.define_number(
            "CCD_GAIN",
            [Number(name="GAIN", label="Gain", format="%.0f", min=0, max=300, step=10, value=90)],
            label="Gain",
            group="Image Settings",
        )
        self.define_number(
            "CCD_OFFSET",
            [Number(name="OFFSET", label="Offset", format="%.0f", min=0, max=6000, value=100)],
            label="Offset",
            group="Image Settings",
        )
        self.define_number(
            "SIMULATOR_SETTINGS",
            [
                Number(
                    name="SIM_NOISE", label="Noise (ADU)", format="%.0f", min=0, max=6000, value=10
                ),
                Number(
                    name="SIM_SKYGLOW",
                    label="Sky glow (ADU/s)",
                    format="%.0f",
                    min=0,
                    max=6000,
                    value=100,
                ),
                Number(
                    name="SIM_TIME_FACTOR",
                    label="Time factor (x)",
                    format="%.2f",
                    min=0.01,
                    max=100,
                    value=1,
                ),
            ],
            label="Settings",
            group="Simulator",
        )
        self.define_blob(
            "CCD1",
            [BLOB(name="CCD1", label="Image", format=".fits")],
            perm=IPerm.RO,
            label="Image Data",
            group="Image Info",
        )
        self.message("CCD simulator ready.")

    async def on_disconnect(self) -> None:
        """Drop any running exposure so nothing is left Busy behind a dead link."""
        if self._exposing:
            self._exposing = False
            self._exposure_left = 0.0
            self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=0, state=IPState.IDLE)
        self._temperature_target = None
        self["CCD_TEMPERATURE"].set(state=IPState.IDLE)
        # State only, as for the temperature above. COOLER_ON/COOLER_OFF describe
        # the TEC itself, which this hook does not switch off, so writing
        # COOLER_OFF here would claim an action nobody performed. Idle says what
        # is actually true: nothing is driving the temperature any more.
        self["CCD_COOLER"].set(state=IPState.IDLE)

    # -- simulation -------------------------------------------------------- #
    @every(seconds=1, when_connected=True)
    async def tick(self) -> None:
        """Advance the exposure countdown and the TEC by one second."""
        await self._tick_exposure()
        self._tick_temperature()

    async def _tick_exposure(self) -> None:
        """Count the running exposure down, rendering the frame when it ends."""
        if not self._exposing or self._rendering:
            return
        self._exposure_left -= 1.0
        if self._exposure_left > 0:
            self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=self._exposure_left, state=IPState.BUSY)
            return
        # Render off the event loop: a Python-rendered frame takes real CPU
        # time and must not stall other drivers sharing the loop.
        self._rendering = True
        try:
            fits = await asyncio.to_thread(self._render_frame)
        finally:
            self._rendering = False
        if not self._exposing:  # aborted or disconnected while rendering
            return
        self._exposing = False
        self["CCD1"].set(CCD1=fits, state=IPState.OK)
        self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=0, state=IPState.OK)
        self.message("Exposure complete.")

    def _tick_temperature(self) -> None:
        """Move the sensor temperature one second toward the TEC target.

        Cooling pulls at a constant half degree per tick; warming relaxes
        exponentially toward ambient (20% of the remaining gap, clamped), the
        same shape as the C++ simulator's ``TimerHit``.
        """
        target = self._temperature_target
        if target is None:
            return
        temperature = self["CCD_TEMPERATURE"]
        current: float = temperature["CCD_TEMPERATURE_VALUE"].value
        if target < current:
            current = max(target, current - COOLING_STEP_C)
        else:
            step = min(0.5, max(0.02, (AMBIENT_C - current) * 0.2))
            current = min(target, current + step)
        if abs(current - target) < 1e-9:
            self._temperature_target = None
            temperature.set(CCD_TEMPERATURE_VALUE=current, state=IPState.OK)
            self.message(f"Temperature reached {current:+.1f} C.")
            if current >= AMBIENT_C - 0.1:  # at ambient: the cooler is idle
                self["CCD_COOLER"].set(COOLER_OFF=ISState.ON, state=IPState.IDLE)
            return
        temperature.set(CCD_TEMPERATURE_VALUE=current, state=IPState.BUSY)

    # -- frame rendering ---------------------------------------------------- #
    def _render_frame(self) -> bytes:
        """Render the current frame type as a FITS file (runs in a thread).

        Returns
        -------
        fits : bytes
            A complete 16-bit FITS image at the binned resolution.
        """
        info = self["CCD_INFO"]
        binning = self["CCD_BINNING"]
        xbin = max(1, int(binning["HOR_BIN"].value))
        ybin = max(1, int(binning["VER_BIN"].value))
        width = int(info["CCD_MAX_X"].value) // xbin
        height = int(info["CCD_MAX_Y"].value) // ybin

        frame_type = self["CCD_FRAME_TYPE"].vector.selected() or "FRAME_LIGHT"
        bias = float(self["CCD_OFFSET"]["OFFSET"].value)
        noise = float(self["SIMULATOR_SETTINGS"]["SIM_NOISE"].value)
        skyglow = float(self["SIMULATOR_SETTINGS"]["SIM_SKYGLOW"].value)
        gain = float(self["CCD_GAIN"]["GAIN"].value)
        duration = self._exposure_request

        # Per-frame-type background level, in ADU (bias/dark stay dark, a
        # light frame accumulates sky glow, a flat sits near half scale).
        background = bias
        if frame_type == "FRAME_LIGHT":
            background += skyglow * duration
        elif frame_type == "FRAME_FLAT":
            background += 32000.0
        rng = random.Random(x=self._sky.random())  # per-frame shot noise
        base = (
            min(65535, max(0, round(background + rng.gauss(0, noise) if noise else background)))
            for _ in range(width * height)
        )
        pixels = array("H", base)

        if frame_type == "FRAME_LIGHT":
            self._draw_stars(pixels, width, height, xbin, ybin, duration, gain)
        observed = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S")
        return _to_fits(
            pixels,
            width,
            height,
            {
                "EXPTIME": f"{duration:>20.3f}",
                "INSTRUME": f"'{self.name:<18}'",
                "GAIN": f"{gain:>20.1f}",
                "OFFSET": f"{bias:>20.1f}",
                "XBINNING": f"{xbin:>20}",
                "YBINNING": f"{ybin:>20}",
                "DATE-OBS": f"'{observed:<19}'",
            },
        )

    def _draw_stars(
        self,
        pixels: array,
        width: int,
        height: int,
        xbin: int,
        ybin: int,
        duration: float,
        gain: float,
    ) -> None:
        """Draw the instance's fixed star field into a light frame.

        Each star is a small Gaussian; brightness scales with exposure time and
        with gain the same way as the C++ simulator (``1 + sqrt(gain)``).

        Parameters
        ----------
        pixels : array
            The frame being rendered, mutated in place.
        width : int
            Frame width in (binned) pixels.
        height : int
            Frame height in (binned) pixels.
        xbin : int
            Horizontal binning factor (bins collect more light per pixel).
        ybin : int
            Vertical binning factor.
        duration : float
            The exposure duration in seconds.
        gain : float
            The camera gain setting.
        """
        stars = random.Random(x=7)  # the fixed sky, independent of shot noise
        boost = (1.0 + math.sqrt(gain)) * max(duration, 0.01) * xbin * ybin
        sigma = 1.6 / ((xbin + ybin) / 2)
        for index in range(STAR_COUNT):
            x = stars.uniform(0, width * xbin) / xbin
            y = stars.uniform(0, height * ybin) / ybin
            # Magnitudes 4..11: a handful of bright stars, many faint ones.
            magnitude = 4 + 7 * (index / STAR_COUNT) ** 0.5
            flux = boost * 400.0 * 10 ** (-0.4 * (magnitude - 4))
            radius = max(2, int(sigma * 4))
            for py in range(max(0, int(y) - radius), min(height, int(y) + radius + 1)):
                for px in range(max(0, int(x) - radius), min(width, int(x) + radius + 1)):
                    fall = math.exp(-((px - x) ** 2 + (py - y) ** 2) / (2 * sigma**2))
                    if fall < 1e-3:
                        continue
                    at = py * width + px
                    pixels[at] = min(65535, pixels[at] + int(flux * fall))

    # -- client writes ------------------------------------------------------ #
    @on_new("CCD_EXPOSURE")
    async def _expose(self, vector: NumberVector) -> None:
        """Start an exposure of the requested duration."""
        if not self.require_connected():
            return
        duration: float = max(0.0, vector.get("CCD_EXPOSURE_VALUE", 1.0))
        factor: float = self["SIMULATOR_SETTINGS"]["SIM_TIME_FACTOR"].value
        self._exposure_request = duration
        self._exposure_left = duration * factor
        self._exposing = True
        self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=duration, state=IPState.BUSY)
        self.message(f"Starting {duration:.2f} s exposure.")

    @on_new("CCD_ABORT_EXPOSURE")
    async def _abort(self, vector: SwitchVector) -> None:
        """Abort the running exposure, leaving no image behind."""
        if not self.require_connected():
            return
        if self._exposing:
            self._exposing = False
            self._exposure_left = 0.0
            self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=0, state=IPState.IDLE)
            self.message("Exposure aborted.")
        self["CCD_ABORT_EXPOSURE"].set(ABORT=ISState.OFF, state=IPState.OK)

    @on_new("CCD_FRAME_TYPE")
    async def _frame_type(self, vector: SwitchVector) -> None:
        """Select the frame type for subsequent exposures."""
        if not self.require_connected():
            return
        selected = vector.selected()
        if selected is not None:
            self["CCD_FRAME_TYPE"].set(**{selected: ISState.ON}, state=IPState.OK)

    @on_new("CCD_BINNING")
    async def _binning(self, vector: NumberVector) -> None:
        """Set the binning factors, clamped to whole values in [1, 4]."""
        if not self.require_connected():
            return
        binning = self["CCD_BINNING"]
        updates = {
            name: min(4, max(1, round(value)))
            for name, value in vector.values().items()
            if name in ("HOR_BIN", "VER_BIN") and isinstance(value, int | float)
        }
        if updates:
            binning.set(updates, state=IPState.OK)

    @on_new("CCD_TEMPERATURE")
    async def _temperature(self, vector: NumberVector) -> None:
        """Drive the TEC toward the requested set point."""
        if not self.require_connected():
            return
        current: float = self["CCD_TEMPERATURE"]["CCD_TEMPERATURE_VALUE"].value
        requested: float = vector.get("CCD_TEMPERATURE_VALUE", current)
        target = min(AMBIENT_C, max(MIN_TEC_C, requested))
        if abs(target - current) < 0.1:
            self["CCD_TEMPERATURE"].set(CCD_TEMPERATURE_VALUE=target, state=IPState.OK)
            return
        self._temperature_target = target
        cooling = target < current
        self["CCD_COOLER"].set(
            COOLER_ON=ISState.ON if cooling else ISState.OFF,
            COOLER_OFF=ISState.OFF if cooling else ISState.ON,
            state=IPState.BUSY if cooling else IPState.IDLE,
        )
        self["CCD_TEMPERATURE"].set(state=IPState.BUSY)
        self.message(f"Cooling to {target:+.1f} C." if cooling else "Warming up.")

    @on_new("CCD_COOLER")
    async def _cooler(self, vector: SwitchVector) -> None:
        """Turn the cooler on (hold) or off (drift back up to ambient)."""
        if not self.require_connected():
            return
        if vector.selected() == "COOLER_OFF":
            self["CCD_COOLER"].set(COOLER_OFF=ISState.ON, state=IPState.IDLE)
            if self["CCD_TEMPERATURE"]["CCD_TEMPERATURE_VALUE"].value < AMBIENT_C - 0.1:
                self._temperature_target = AMBIENT_C
                self["CCD_TEMPERATURE"].set(state=IPState.BUSY)
                self.message("Cooler off; warming to ambient.")
        else:
            self["CCD_COOLER"].set(COOLER_ON=ISState.ON, state=IPState.BUSY)

    @on_new("CCD_GAIN")
    async def _gain(self, vector: NumberVector) -> None:
        """Accept a new gain value."""
        if not self.require_connected():
            return
        gain = self["CCD_GAIN"]
        gain.set(GAIN=min(300, max(0, vector.get("GAIN", gain["GAIN"].value))), state=IPState.OK)

    @on_new("CCD_OFFSET")
    async def _offset(self, vector: NumberVector) -> None:
        """Accept a new offset (bias level)."""
        if not self.require_connected():
            return
        offset = self["CCD_OFFSET"]
        offset.set(
            OFFSET=min(6000, max(0, vector.get("OFFSET", offset["OFFSET"].value))),
            state=IPState.OK,
        )

    @on_new("SIMULATOR_SETTINGS")
    async def _settings(self, vector: NumberVector) -> None:
        """Accept new simulator settings (noise, sky glow, time factor)."""
        if not self.require_connected():
            return
        settings = self["SIMULATOR_SETTINGS"]
        known = {member.name for member in settings.vector.elements}
        updates = {name: value for name, value in vector.values().items() if name in known}
        if updates:
            settings.set(updates, state=IPState.OK)


if __name__ == "__main__":
    CCDSimulator.run()
