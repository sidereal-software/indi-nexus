"""Reverse interop: libindi's own clients driving *our* drivers.

This is the direction nothing else covers. In-repo tests only ever read our XML
with our own parser, so a deviation from the spec stays invisible. Here a real
``indiserver`` launches one of our Python drivers as a child process and libindi's
own tools read and write it, which is exactly what KStars or PHD2 would do.

If this passes, "existing INDI software works with an INDINexus driver unchanged"
is a tested claim rather than an intention.
"""

from __future__ import annotations

import time

from conftest import getprop, setprop

from indi_nexus.protocol.xml import parse_number


def _await_value(port: int, spec: str, expected: str, timeout: float = 20.0) -> str:
    """Poll one property until it reads as expected, returning the last value seen.

    Parameters
    ----------
    port : int
        The server's port.
    spec : str
        A fully qualified ``device.property.element``.
    expected : str
        The value being waited for.
    timeout : float, optional
        How long to keep polling.

    Returns
    -------
    value : str
        The final value read, whether or not it matched.
    """
    deadline = time.monotonic() + timeout
    value = ""
    while time.monotonic() < deadline:
        value = getprop(port, spec).get(spec, "")
        if value == expected:
            return value
        time.sleep(0.25)
    return value


def test_libindi_client_sees_our_driver(indi_server, python_driver):
    """indi_getprop enumerates our driver's properties, labels, states and perms."""
    server = indi_server(python_driver("examples/flat_panel.py"))

    # The driver has to define itself before anything is readable.
    assert _await_value(server.port, "Flat Panel.LIGHT_CONTROL.OFF", "On") == "On"

    props = getprop(server.port, "Flat Panel.*.*")
    assert "Flat Panel.LIGHT_CONTROL.ON" in props
    assert "Flat Panel.LIGHT_BRIGHTNESS.BRIGHTNESS" in props
    assert float(props["Flat Panel.LIGHT_BRIGHTNESS.BRIGHTNESS"]) == 128.0

    # The metadata a UI needs travels too, not just the values.
    attrs = getprop(server.port, "Flat Panel.LIGHT_CONTROL._LABEL")
    assert attrs["Flat Panel.LIGHT_CONTROL._LABEL"] == "Lamp"
    perms = getprop(server.port, "Flat Panel.LIGHT_BRIGHTNESS._PERM")
    assert perms["Flat Panel.LIGHT_BRIGHTNESS._PERM"] == "rw"


def test_libindi_client_can_drive_our_switch(indi_server, python_driver):
    """A switch written by indi_setprop is applied and echoed back."""
    server = indi_server(python_driver("examples/flat_panel.py"))
    assert _await_value(server.port, "Flat Panel.LIGHT_CONTROL.OFF", "On") == "On"

    setprop(server.port, "Flat Panel.LIGHT_CONTROL.ON=On", kind="-s")

    assert _await_value(server.port, "Flat Panel.LIGHT_CONTROL.ON", "On") == "On"
    # OneOfMany means turning one member on turns the other off, and the driver
    # is what has to say so on the wire.
    assert _await_value(server.port, "Flat Panel.LIGHT_CONTROL.OFF", "Off") == "Off"


def test_libindi_client_can_drive_our_number(indi_server, python_driver):
    """A number written by indi_setprop is clamped by the driver and echoed back."""
    server = indi_server(python_driver("examples/flat_panel.py"))
    assert _await_value(server.port, "Flat Panel.LIGHT_CONTROL.OFF", "On") == "On"

    setprop(server.port, "Flat Panel.LIGHT_BRIGHTNESS.BRIGHTNESS=200", kind="-n")
    assert float(_await_value(server.port, "Flat Panel.LIGHT_BRIGHTNESS.BRIGHTNESS", "200")) == 200

    # The advertised max is a promise; a client is free to ignore it, and the
    # driver is what has to hold the line.
    setprop(server.port, "Flat Panel.LIGHT_BRIGHTNESS.BRIGHTNESS=100000", kind="-n")
    value = _await_value(server.port, "Flat Panel.LIGHT_BRIGHTNESS.BRIGHTNESS", "255")
    assert float(value) == 255


def test_our_sexagesimal_output_is_read_back_correctly(indi_server, python_driver):
    """An RA/Dec driver's %m formatting survives a round trip through libindi.

    ``format_number`` mirrors libindi's ``fs_sexa``. "Looks right" and "parses back
    to the same number in libindi" are different claims, and only this tests the
    second one.
    """
    server = indi_server(python_driver("examples/telescope_device.py"))
    device = "Telescope Simulator"
    assert _await_value(server.port, f"{device}.CONNECTION.DISCONNECT", "On") == "On"

    setprop(server.port, f"{device}.CONNECTION.CONNECT=On", kind="-s")
    assert _await_value(server.port, f"{device}.CONNECTION.CONNECT", "On") == "On"

    setprop(server.port, f"{device}.EQUATORIAL_EOD_COORD.RA;DEC=5.5;-10.25", kind="-n")

    # libindi prints a %m number in sexagesimal, so reading it back exercises both
    # halves: their formatting of what we sent, and our parsing of what they print.
    deadline = time.monotonic() + 25
    ra = dec = None
    while time.monotonic() < deadline:
        values = getprop(server.port, f"{device}.EQUATORIAL_EOD_COORD.*")
        ra = parse_number(values[f"{device}.EQUATORIAL_EOD_COORD.RA"])
        dec = parse_number(values[f"{device}.EQUATORIAL_EOD_COORD.DEC"])
        if abs(ra - 5.5) < 0.01 and abs(dec - -10.25) < 0.01:
            break
        time.sleep(0.5)

    assert ra is not None and dec is not None
    assert abs(ra - 5.5) < 0.01, f"RA came back as {ra}"
    assert abs(dec - -10.25) < 0.01, f"Dec came back as {dec}"
