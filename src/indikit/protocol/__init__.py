"""The INDI protocol layer: typed models, enums, and the XML codec.

This package is the single source of truth for the INDI 1.7 wire format. Every
property is a validated Pydantic model that serializes to *both* canonical INDI
XML (for interoperability with ``indiserver`` and existing C++ drivers/clients)
and to JSON (for modern web clients).

The number text a codec puts on the wire is its own concern:
:func:`~indikit.protocol.numbers.format_number` and
:func:`~indikit.protocol.numbers.parse_number` implement the INDI printf
``format``, sexagesimal ``%m`` included, and are exported here because RA/Dec
interop turns on them.
"""

from indikit.protocol.compression import zlib_encoded
from indikit.protocol.enums import (
    BLOBPolicy,
    IPerm,
    IPState,
    ISRule,
    ISState,
    coerce_switch,
)
from indikit.protocol.json import from_json, to_json
from indikit.protocol.models import (
    BLOB,
    BLOBVector,
    DefVector,
    DelProperty,
    Element,
    EnableBLOB,
    GetProperties,
    IndiMessage,
    IndiTimestamp,
    Light,
    LightVector,
    Message,
    NewVector,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    Text,
    TextVector,
    Vector,
    as_utc,
    indi_now,
    slugify,
)
from indikit.protocol.numbers import format_number, parse_number
from indikit.protocol.xml import XMLStreamParser, parse_indi, to_xml

__all__ = [
    # enums
    "IPState",
    "IPerm",
    "ISRule",
    "ISState",
    "BLOBPolicy",
    "coerce_switch",
    # elements
    "Number",
    "Text",
    "Switch",
    "Light",
    "BLOB",
    "Element",
    "slugify",
    # vectors
    "NumberVector",
    "TextVector",
    "SwitchVector",
    "LightVector",
    "BLOBVector",
    "Vector",
    # messages / events
    "GetProperties",
    "DelProperty",
    "Message",
    "EnableBLOB",
    "DefVector",
    "SetVector",
    "NewVector",
    "IndiMessage",
    # timestamps
    "IndiTimestamp",
    "as_utc",
    "indi_now",
    # codec
    "to_xml",
    "parse_indi",
    "XMLStreamParser",
    "to_json",
    "from_json",
    # number text
    "format_number",
    "parse_number",
    # BLOB compression
    "zlib_encoded",
]
