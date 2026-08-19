#!/usr/bin/env python3
r"""One driver process, two devices: a camera and the guide chip beside it.

Some instruments are two INDI devices behind one piece of hardware. A camera
with an integrated guide chip is the classic case: one USB link, one vendor
handle, two sets of properties that clients drive independently. INDI has always
modelled that as one driver announcing several devices, and INDIkit does it by
handing a list to :func:`~indikit.driver.run`::

    run([MainChip(), GuideChip()])

Both devices share one stdio pipe, one outbox and one reader. Their ``@every``
jobs run concurrently, so the guider keeps reporting while the main chip is
mid-exposure, but **inbound dispatch is sequential**: a handler that awaits for a
long time delays the next client write for both devices. That is the trade this
shape makes, and it is the right one here because the two chips genuinely share
one link and have to take turns on it anyway. Two instruments that should never
wait for each other belong in two drivers.

Run it under ``indiserver``::

    indiserver ./examples/guided_camera.py

or over stdio directly, naming both devices::

    indikit run examples.guided_camera:MainChip examples.guided_camera:GuideChip

or in the web panel without ``indiserver``, with one ``--device`` per chip::

    indikit serve \
        --device examples.guided_camera:MainChip \
        --device examples.guided_camera:GuideChip
"""

from __future__ import annotations

import math
import random
import time

from indikit.driver import Device, every, on_new, run
from indikit.protocol import (
    BLOB,
    IPerm,
    IPState,
    Number,
    NumberVector,
)

#: Frame size the main chip reports and delivers, in pixels.
MAIN_SIZE = (64, 48)

#: Frame size of the smaller guide chip, in pixels.
GUIDE_SIZE = (32, 24)


class CameraLink:
    """The one USB link both chips talk over, standing in for a vendor SDK.

    Deliberately **blocking**, like every real instrument library: the drivers
    reach it through :meth:`~indikit.driver.device.Device.off_thread`. It is
    also the reason the two devices live in one process - there is one handle,
    and a second process could not open it.
    """

    def __init__(self) -> None:
        """Create a closed, unclaimed link with a fixed synthetic star field."""
        self.open = False
        self._claims = 0
        self._sky = random.Random(x=11)

    def claim(self) -> None:
        """Open the link for one more chip, or join the chip that opened it.

        A real one would enumerate USB and claim the interface on the first
        call. Blocking, like the rest of this class.
        """
        self._claims += 1
        if not self.open:
            time.sleep(0.01)
            self.open = True

    def release(self) -> None:
        """Give up one chip's claim, closing the link when the last one goes."""
        self._claims = max(0, self._claims - 1)
        if not self._claims:
            self.open = False

    def read_frame(self, chip: int, size: tuple[int, int]) -> bytes:
        """Read one raw 8-bit frame off a chip.

        Parameters
        ----------
        chip : int
            ``0`` for the main sensor, ``1`` for the guide sensor.
        size : tuple
            The frame's ``(width, height)`` in pixels.

        Returns
        -------
        frame : bytes
            ``width * height`` raw 8-bit pixels.

        Raises
        ------
        ConnectionError
            Raised when the link is not open, as a vendor SDK would.
        """
        if not self.open:
            raise ConnectionError("camera link is not open")
        width, height = size
        time.sleep(0.01)  # the blocking read this whole class exists to model
        return bytes((chip * 7 + x * y) % 256 for y in range(height) for x in range(width))

    def guide_star(self) -> tuple[float, float, float]:
        """Return the guide star's current ``(x, y, flux)``, seeing and all.

        Returns
        -------
        reading : tuple
            Centroid in guide-chip pixels and the star's flux in ADU.

        Raises
        ------
        ConnectionError
            Raised when the link is not open.
        """
        if not self.open:
            raise ConnectionError("camera link is not open")
        drift = time.monotonic() / 10
        return (
            16.0 + 2.0 * math.sin(drift) + self._sky.gauss(0, 0.05),
            12.0 + 2.0 * math.cos(drift) + self._sky.gauss(0, 0.05),
            4200.0 + self._sky.gauss(0, 40),
        )


#: The link the two chips share when neither is handed one explicitly, so every
#: launch route - ``__main__``, ``indikit run``, ``serve --device`` - gets the
#: single handle the hardware actually has.
LINK = CameraLink()


class _Chip(Device):
    """What the two chips have in common: the shared link and its lifecycle.

    Parameters
    ----------
    link : CameraLink, optional
        The link to talk over; defaults to the module-level shared one.
    name : str, optional
        Instance-level device name override.
    """

    def __init__(self, link: CameraLink | None = None, name: str | None = None) -> None:
        """Bind the chip to a link without opening it."""
        super().__init__(name)
        self.link = link if link is not None else LINK

    async def on_connect(self) -> None:
        """Claim the shared link, opening it if this chip is the first."""
        await self.off_thread(self.link.claim)

    async def on_disconnect(self) -> None:
        """Give up this chip's claim on the link.

        The link is shared, so closing it is the *last* chip's job: a guider
        disconnecting must not blind a camera mid-exposure.
        """
        self.link.release()


class MainChip(_Chip):
    """The imaging sensor: an exposure that counts down and delivers a frame."""

    name = "Camera"

    def __init__(self, link: CameraLink | None = None, name: str | None = None) -> None:
        """Initialise with no exposure running."""
        super().__init__(link, name)
        self._remaining = 0.0

    async def setup(self) -> None:
        """Define the connection, the exposure control, and the image BLOB."""
        self.define_connection()
        self.define_number(
            "CCD_EXPOSURE",
            [
                Number(
                    name="CCD_EXPOSURE_VALUE",
                    label="Duration (s)",
                    format="%5.2f",
                    min=0,
                    max=600,
                    value=1,
                )
            ],
            label="Expose",
            group="Main Control",
        )
        self.define_blob(
            "CCD1",
            [BLOB(name="CCD1", label="Image", format=".raw")],
            perm=IPerm.RO,
            label="Image Data",
            group="Image Info",
        )

    async def on_disconnect(self) -> None:
        """Drop any running exposure, then release the link."""
        if self._remaining:
            self._remaining = 0.0
            self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=0, state=IPState.IDLE)
        await super().on_disconnect()

    @every(seconds=1, when_connected=True)
    async def _countdown(self) -> None:
        """Advance a running exposure by one second, reading it out at zero."""
        if not self._remaining:
            return
        self._remaining = max(0.0, self._remaining - 1.0)
        if self._remaining:
            self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=self._remaining, state=IPState.BUSY)
            return
        frame = await self.off_thread(self.link.read_frame, 0, MAIN_SIZE)
        self["CCD1"].set(CCD1=frame, state=IPState.OK)
        self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=0, state=IPState.OK)
        self.message("Exposure complete.")

    @on_new("CCD_EXPOSURE")
    async def _expose(self, vector: NumberVector) -> None:
        """Start an exposure of the requested duration."""
        if not self.require_connected():
            return
        duration = max(0.0, vector.get("CCD_EXPOSURE_VALUE", 1.0))
        self._remaining = duration
        self["CCD_EXPOSURE"].set(CCD_EXPOSURE_VALUE=duration, state=IPState.BUSY)
        self.message(f"Starting {duration:.2f} s exposure.")


class GuideChip(_Chip):
    """The guide sensor: a star centroid published once a second."""

    name = "Camera Guider"

    async def setup(self) -> None:
        """Define the connection and the read-only guide-star readout."""
        self.define_connection()
        self.define_number(
            "GUIDE_STAR",
            [
                Number(name="X", label="X (px)", format="%5.2f", value=0),
                Number(name="Y", label="Y (px)", format="%5.2f", value=0),
                Number(name="FLUX", label="Flux (ADU)", format="%.0f", value=0),
            ],
            perm=IPerm.RO,
            label="Guide Star",
            group="Main Control",
        )
        self.define_blob(
            "CCD2",
            [BLOB(name="CCD2", label="Guide Frame", format=".raw")],
            perm=IPerm.RO,
            label="Guide Data",
            group="Image Info",
        )

    async def on_disconnect(self) -> None:
        """Stop claiming a live centroid, then release the link."""
        self["GUIDE_STAR"].set(state=IPState.IDLE)
        await super().on_disconnect()

    @every(seconds=1, when_connected=True)
    async def _guide(self) -> None:
        """Read the guide chip and publish the star it found.

        This keeps running through the main chip's whole exposure: periodic jobs
        are one task per job, each taking only its own device's guard.
        """
        x, y, flux = await self.off_thread(self.link.guide_star)
        self["GUIDE_STAR"].set(X=x, Y=y, FLUX=flux, state=IPState.OK)
        frame = await self.off_thread(self.link.read_frame, 1, GUIDE_SIZE)
        self["CCD2"].set(CCD2=frame, state=IPState.OK)


if __name__ == "__main__":
    run([MainChip(), GuideChip()])
