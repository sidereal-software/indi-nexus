"""The ``CCD_COMPRESSION`` toggle, driver side, in one session on one property.

``tests/interop/test_blob.py`` runs this against a real ``indiserver``, which is
where the wire is settled but where every frame costs an exposure. This is the
same shape in milliseconds and from the other end: a driver that publishes
``.fits`` or ``.fits.z`` depending on a switch a client keeps flipping, driven
through :class:`~indi_nexus.testing.DeviceHarness` so the ``@on_new`` dispatch,
the handle and the codec are all real.

What it is here to catch is the state a one-directional test cannot see. Each of
``format``, ``size`` and ``data`` is carried on a **single long-lived element**,
so the frame a client receives depends on what the previous frame left behind -
and ``BoundProperty._assign`` derives ``size`` for a plain payload and leaves it
alone for a compressed one, which makes the toggle a branch crossed in both
directions on one object.
"""

from __future__ import annotations

import zlib

import pytest

from indi_nexus.driver import Device, on_new
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    IPerm,
    IPState,
    ISRule,
    ISState,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    to_xml,
)
from indi_nexus.testing import DeviceHarness

#: The 2880-byte block a FITS file is built out of.
BLOCK = 2880


def frame(blocks: int) -> bytes:
    """Return an uncompressed frame of ``blocks`` whole FITS blocks.

    Repetitive enough to deflate to something visibly smaller, and sized by the
    client so that a ``size`` left over from an earlier frame cannot pass for a
    derived one.

    Parameters
    ----------
    blocks : int
        How many 2880-byte blocks the frame occupies.

    Returns
    -------
    payload : bytes
        The frame.
    """
    return (b"SIMPLE  =                    T" + b" " * 50).ljust(BLOCK * blocks, b" ")


class _Camera(Device):
    """A camera whose ``CCD_COMPRESSION`` switch decides how the next frame goes out.

    Modelled on what libindi's CCD simulator does with the switch, minus the
    exposure: ``INDI_ENABLED`` publishes a compressed payload under a compressed
    format, ``INDI_DISABLED`` publishes the frame as it stands.
    """

    name = "Camera"

    async def setup(self) -> None:
        """Define the connection, the compression switch, the trigger and the image."""
        self.define_connection()
        self.define_switch(
            "CCD_COMPRESSION",
            [
                Switch(name="INDI_ENABLED", label="Enabled"),
                Switch(name="INDI_DISABLED", label="Disabled", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Compression",
            group="Image Settings",
        )
        self.define_switch(
            "CAPTURE",
            [Switch(name="GO", label="Capture")],
            label="Capture",
            group="Main Control",
        )
        self.define_number(
            "FRAME_BLOCKS",
            [Number(name="BLOCKS", label="Blocks", format="%.0f", min=1, max=16, value=4)],
            label="Frame Size",
            group="Image Settings",
        )
        self.define_blob(
            "CCD1",
            [BLOB(name="CCD1", label="Image", format=".fits")],
            perm=IPerm.RO,
            label="Image Data",
            group="Image Info",
        )

    @on_new("CCD_COMPRESSION")
    async def _set_compression(self, vector: SwitchVector) -> None:
        """Record the client's compression choice.

        Parameters
        ----------
        vector : SwitchVector
            The client's write; the exclusive rule clears the other member.
        """
        if not self.require_connected():
            return
        selected = vector.selected()
        assert selected is not None
        self.switch("CCD_COMPRESSION").select(selected, ISState.ON, state=IPState.OK)

    @on_new("CAPTURE")
    async def _capture(self, vector: SwitchVector) -> None:
        """Publish one frame in whichever form compression is currently set to.

        The format is written **before** the payload, which is the order
        ``BoundProperty.set`` requires: it decides whether to derive ``size``
        from the format the element carries at that moment.

        Parameters
        ----------
        vector : SwitchVector
            The client's write; only its arrival matters.
        """
        if not self.require_connected():
            return
        payload = frame(int(self.number("FRAME_BLOCKS").value("BLOCKS")))
        image = self.blob("CCD1")
        element = image.vector.element("CCD1")
        if self.switch("CCD_COMPRESSION").value("INDI_ENABLED") is ISState.ON:
            element.format = ".fits.z"
            element.size = len(payload)  # the uncompressed length, by definition
            image.set(CCD1=zlib.compress(payload), state=IPState.OK)
        else:
            element.format = ".fits"
            image.set(CCD1=payload, state=IPState.OK)
        self.switch("CAPTURE").set(GO=False, state=IPState.OK)

    @on_new("FRAME_BLOCKS")
    async def _set_frame_blocks(self, vector: NumberVector) -> None:
        """Accept a new frame size.

        Parameters
        ----------
        vector : NumberVector
            The client's write, carrying the new block count.
        """
        if not self.require_connected():
            return
        self.number("FRAME_BLOCKS").set(BLOCKS=vector.get("BLOCKS"), state=IPState.OK)


@pytest.fixture
async def camera() -> DeviceHarness:
    """Return a connected camera harness with compression off, as it starts.

    Returns
    -------
    harness : DeviceHarness
        The harness, with ``setup`` run and ``CONNECTION`` established.
    """
    harness = DeviceHarness(_Camera())
    await harness.setup()
    await harness.write("CONNECTION", CONNECT=True)
    harness.clear()
    return harness


async def _capture(harness: DeviceHarness) -> BLOB:
    """Trigger one frame and return the image element the client would receive.

    Parameters
    ----------
    harness : DeviceHarness
        A connected camera harness.

    Returns
    -------
    element : BLOB
        The element off the emitted ``set``, which is a detached copy and so
        survives the next capture mutating the driver's live vector.
    """
    harness.clear()
    await harness.write("CAPTURE", GO=True)
    (published,) = harness.sets("CCD1")
    assert isinstance(published, BLOBVector)
    element = published.element("CCD1")
    assert isinstance(element, BLOB)
    # Serialising is part of publishing: a `.z` element with no size is refused
    # in the codec, so a frame that will not serialise never reached a client.
    to_xml(SetVector(vector=published))
    return element


async def test_compression_off_publishes_the_frame_uncompressed(camera) -> None:
    """With the switch at ``INDI_DISABLED`` the payload and ``size`` are the frame's own."""
    element = await _capture(camera)

    assert element.format == ".fits"
    assert element.data == frame(4)
    assert element.size == len(frame(4))


async def test_compression_on_publishes_deflated_bytes_under_the_uncompressed_size(
    camera,
) -> None:
    """Turning the switch on deflates the payload and keeps ``size`` uncompressed."""
    await camera.write("CCD_COMPRESSION", INDI_ENABLED=True)

    element = await _capture(camera)

    assert element.format == ".fits.z"
    assert element.data == zlib.compress(frame(4))
    assert len(element.data) < len(frame(4)), "the payload was not actually deflated"
    assert element.size == len(frame(4)), "size must be the uncompressed length"


async def test_turning_compression_off_again_returns_the_frame_to_plain_fits(
    camera,
) -> None:
    """The whole toggle on one property: off, on, off, with nothing left behind.

    This is the test that would catch a format or a ``size`` sticking. Both live
    on the same element for the life of the device, so the third frame is
    published by an object that has already been compressed once - and a client
    told ``.fits.z`` for a payload it can read straight, or handed deflate's
    output length under INDI's uncompressed ``size``, has no way to notice.

    The last frame is deliberately a **different size** from the two before it.
    Derivation resuming and derivation having quietly stopped are the same
    number otherwise, so the frame the client asks for last is the only one that
    can tell them apart.
    """
    first = await _capture(camera)
    assert first.format == ".fits"

    await camera.write("CCD_COMPRESSION", INDI_ENABLED=True)
    second = await _capture(camera)
    assert second.format == ".fits.z"
    assert second.size == len(frame(4))

    await camera.write("CCD_COMPRESSION", INDI_DISABLED=True)
    await camera.write("FRAME_BLOCKS", BLOCKS=2)
    third = await _capture(camera)

    assert third.format == ".fits", "the compressed format outlived the compression"
    assert third.data == frame(2), "the client was handed deflated bytes as plain FITS"
    assert third.size == len(frame(2)), "the compressed frame's declared size stuck"
    # The switch really did move; a handler that ignored the second write would
    # otherwise make the assertions above pass for the wrong reason.
    assert camera.latest("CCD_COMPRESSION").get("INDI_DISABLED") is ISState.ON
