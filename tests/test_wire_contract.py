"""A golden snapshot of the JSON contract the browser is written against.

``web/packages/client/src/types.ts`` is a hand-authored mirror of the Pydantic
models (locked decision 3: INDI 1.7 is frozen, so there is no codegen). Nothing
mechanical keeps the two halves together, and the failure mode is silent - the
Python side gains a field, the browser never learns of it, and the first sign is
a control that renders blank.

This test does not fix that. What it does is make a change to the wire models
**impossible to land without touching a committed file whose whole reason for
existing is the mirror**, so the diff that changes the schema and the diff that
should change ``types.ts`` are in front of the same reviewer at the same time.
It is a speed bump with a name on it, and claiming more for it would be worse
than not having it.

Regenerate after an intentional model change with::

    INDI_NEXUS_UPDATE_GOLDEN=1 uv run pytest tests/test_wire_contract.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import TypeAdapter

from indi_nexus.protocol import IndiMessage, Vector
from indi_nexus.web import BRIDGE_PROTOCOL_VERSION, BridgeFrame

_GOLDEN = Path(__file__).parent / "data" / "wire_schema.json"

#: The file a reviewer has to look at when this test fails.
_MIRROR = "web/packages/client/src/types.ts"


def _schema() -> dict[str, object]:
    """Build the current JSON schema of everything a browser sees.

    Returns
    -------
    schema : dict
        The INDI message union, the property vector union and the bridge's own
        control frames, each under its own key.
    """
    return {
        "IndiMessage": TypeAdapter(IndiMessage).json_schema(),
        "Vector": TypeAdapter(Vector).json_schema(),
        "BridgeFrame": TypeAdapter(BridgeFrame).json_schema(),
    }


def test_the_browser_wire_schema_has_not_drifted():
    """The committed schema still describes the models a browser is sent."""
    current = _schema()
    if os.environ.get("INDI_NEXUS_UPDATE_GOLDEN"):
        _GOLDEN.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")

    committed = json.loads(_GOLDEN.read_text())
    assert current == committed, (
        f"the browser JSON contract changed. If that was intended, update {_MIRROR} to match "
        f"and regenerate this file with INDI_NEXUS_UPDATE_GOLDEN=1 uv run pytest {__file__}"
    )


def test_the_hello_frame_carries_no_server_default():
    """``HelloFrame.server`` must stay defaultless, or this check rots.

    A model default lands in ``model_json_schema()``. Pinning
    ``indi_nexus.__version__`` on the model would therefore make the golden file
    fail on every release, and the fix a releaser reaches for is to regenerate
    it without reading it - which is exactly the reflex this test exists to
    prevent. The bridge supplies the version at construction instead.
    """
    schema = _schema()["BridgeFrame"]
    assert isinstance(schema, dict)
    hello = schema["$defs"]["HelloFrame"]["properties"]  # type: ignore[index]
    assert "default" not in hello["server"]
    # The protocol version is the opposite case: it *is* a default, so a bump
    # shows up in the golden diff, which is the diff a reviewer should read.
    assert hello["protocol"]["default"] == BRIDGE_PROTOCOL_VERSION
