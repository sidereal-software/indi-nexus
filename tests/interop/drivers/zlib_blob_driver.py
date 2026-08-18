#!/usr/bin/env python3
"""A driver that publishes a genuinely zlib-compressed BLOB, as ``.fits.z``.

The INDI 1.7 convention is that a ``format`` ending in ``.z`` means the payload
was deflated for the wire, and a client is expected to inflate it and hand the
application the file the rest of the format names. libindi's own CCD simulator
never produces one - with ``CCD_COMPRESSION`` on it routes FITS through fpack and
sends ``.fits.fz``, and its native path sends ``.bin`` uncompressed - so this
driver is how the ``.z`` path gets exercised across a real ``indiserver`` rather
than only against payloads a test compressed for itself.

It lives here rather than in ``examples/`` because it is a fixture for
``tests/interop/test_blob.py`` and teaches nothing about writing a driver.

Compressing is deliberately not automated anywhere in this package: it is the
driver author's decision, as it is in libindi. What the driver owes in return is
the ``size``, which INDI defines as the *uncompressed* length - the one number a
codec looking at deflated bytes cannot work out. ``BoundProperty.set`` derives it
from the payload for an ordinary frame and leaves it alone for a ``.z`` element
precisely so this driver can state it once, here, and have publishing keep it.
"""

from __future__ import annotations

import zlib

from indi_nexus.driver import Device, on_new
from indi_nexus.protocol import BLOB, IPerm, IPState, Switch, SwitchVector

#: The uncompressed payload: a FITS primary header, padded to whole 2880-byte
#: blocks the way a real file is, which also makes it compress convincingly.
FRAME = (b"SIMPLE  =                    T" + b" " * 50).ljust(2880 * 4, b" ")


class Deflater(Device):
    """A camera-shaped device whose one frame is deflated on the wire."""

    name = "Deflater"

    async def setup(self) -> None:
        """Define the connection switch, the trigger, and the image property."""
        self.define_connection()
        self.define_switch(
            "CAPTURE",
            [Switch(name="GO", label="Capture")],
            label="Capture",
            group="Main Control",
        )
        self.define_blob(
            "IMAGE",
            [BLOB(name="IMAGE", label="Image", format=".fits")],
            perm=IPerm.RO,
            label="Image Data",
            group="Image Info",
        )

    @on_new("CAPTURE")
    async def _capture(self, vector: SwitchVector) -> None:
        """Publish one compressed frame when a client asks for it.

        A client has to send ``enableBLOB`` before ``indiserver`` will forward a
        payload at all, so the frame is published on request rather than on
        connect - otherwise the only image would be the one thrown away before
        the client subscribed.

        Parameters
        ----------
        vector : SwitchVector
            The client's write; only its arrival matters.
        """
        if not self.require_connected():
            return
        prop = self.blob("IMAGE")
        element = prop.vector.element("IMAGE")
        element.format = ".fits.z"
        element.size = len(FRAME)  # the uncompressed length, by definition
        prop.set(IMAGE=zlib.compress(FRAME), state=IPState.OK)
        self["CAPTURE"].set(GO=False, state=IPState.OK)


if __name__ == "__main__":
    Deflater.run()
