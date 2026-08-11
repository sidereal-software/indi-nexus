"""Differential: our client's view against libindi's, for the same server.

Assertions we invent can only be as good as our understanding of the spec. Here the
oracle is libindi itself: two independent clients read one server, and any
disagreement about a value, a state or a permission means one of them is wrong.

Numbers are the interesting part. ``indi_getprop`` prints what libindi parsed from
the wire, so comparing it with what our client parsed from the same bytes is a
direct check on the number codec, sexagesimal formats included.
"""

from __future__ import annotations

import asyncio

from conftest import getprop, wait_until

from indi_nexus.client import IndiClient
from indi_nexus.protocol import BLOBVector, LightVector, NumberVector, SwitchVector, TextVector
from indi_nexus.protocol.xml import parse_number

# One of each kind of driver, chosen for the property shapes they bring: RA/Dec
# sexagesimal, a temperature and exposure, and a weather station's many numbers.
DRIVERS = ["indi_simulator_telescope", "indi_simulator_ccd", "indi_simulator_weather"]


def _ours(vector: object, element: str) -> str | None:
    """Render one element the way ``indi_getprop`` would print it.

    Parameters
    ----------
    vector : Vector
        The parsed vector holding the element.
    element : str
        The element name.

    Returns
    -------
    text : str or None
        The comparable text, or None for kinds not worth comparing as strings.
    """
    if not isinstance(vector, NumberVector | TextVector | SwitchVector | LightVector):
        return None
    if element not in vector:
        return None
    value = vector.get(element)
    return f"{value}" if isinstance(value, float) else str(value)


async def test_our_snapshot_agrees_with_indi_getprop(indi_server):
    """Every value both clients can see matches."""
    server = indi_server(*DRIVERS)

    async with IndiClient("127.0.0.1", server.port) as client:
        await wait_until(lambda: len(client.store.devices()) >= len(DRIVERS), seconds=25)
        await asyncio.sleep(4)
        ours = {name: dict(client[name]) for name in client.store.devices()}

    theirs = getprop(server.port, timeout=8)
    assert theirs, f"indi_getprop returned nothing:\n{server.output()}"

    compared = 0
    mismatches: list[str] = []
    for qualified, their_value in theirs.items():
        parts = qualified.split(".")
        if len(parts) != 3:
            continue
        device, prop, element = parts
        vector = ours.get(device, {}).get(prop)
        if vector is None or isinstance(vector, BLOBVector):
            continue
        our_value = _ours(vector, element)
        if our_value is None:
            continue
        compared += 1
        if isinstance(vector, NumberVector):
            # Both sides print floats; compare numerically so formatting choices
            # (trailing zeros, exponents) are not treated as disagreement.
            # A %m number is printed sexagesimally by libindi, so parse rather than
            # float() it. That makes this a check on our sexagesimal reader too.
            try:
                if abs(float(our_value) - parse_number(their_value)) > 1e-4:
                    mismatches.append(f"{qualified}: ours={our_value} theirs={their_value}")
            except ValueError:
                mismatches.append(
                    f"{qualified}: unparseable ours={our_value!r} theirs={their_value!r}"
                )
        elif our_value != their_value:
            mismatches.append(f"{qualified}: ours={our_value!r} theirs={their_value!r}")

    assert compared > 50, f"only compared {compared} elements, corpus too thin to mean anything"
    assert not mismatches, "our client disagrees with libindi:\n" + "\n".join(mismatches[:25])


async def test_our_states_and_permissions_agree_with_indi_getprop(indi_server):
    """Property state and permission match libindi's reading of the same server.

    These come from attributes rather than element text, so they exercise a
    different part of the parser than the values above.
    """
    server = indi_server("indi_simulator_telescope")

    async with IndiClient("127.0.0.1", server.port) as client:
        await client.wait_for("Telescope Simulator", "CONNECTION", timeout=20)
        await asyncio.sleep(3)
        ours = dict(client["Telescope Simulator"])

    states = getprop(server.port, "Telescope Simulator.*._STATE", timeout=8)
    perms = getprop(server.port, "Telescope Simulator.*._PERM", timeout=8)

    checked = 0
    for qualified, their_state in states.items():
        prop = qualified.split(".")[1]
        vector = ours.get(prop)
        if vector is None:
            continue
        checked += 1
        assert str(vector.state) == their_state, f"{prop} state: {vector.state} vs {their_state}"

    for qualified, their_perm in perms.items():
        prop = qualified.split(".")[1]
        vector = ours.get(prop)
        if vector is None or isinstance(vector, LightVector):
            continue  # lights have no permission in INDI
        assert str(vector.perm) == their_perm, f"{prop} perm: {vector.perm} vs {their_perm}"

    assert checked > 5, f"only checked {checked} properties"
