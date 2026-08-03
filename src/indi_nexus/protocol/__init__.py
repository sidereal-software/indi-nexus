"""The INDI protocol layer: typed models, enums, and the XML codec.

This package is the single source of truth for the INDI 1.7 wire format. Every
property is a validated Pydantic model that serializes to *both* canonical INDI
XML (for interoperability with ``indiserver`` and existing C++ drivers/clients)
and to JSON (for modern web clients).
"""

from indi_nexus.protocol.enums import BLOBPolicy, IPerm, IPState, ISRule, ISState
from indi_nexus.protocol.json import from_json, to_json
from indi_nexus.protocol.models import (
    BLOB,
    BLOBVector,
    DefVector,
    DelProperty,
    Element,
    EnableBLOB,
    GetProperties,
    IndiMessage,
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
    slugify,
)
from indi_nexus.protocol.xml import XMLStreamParser, parse_indi, to_xml

__all__ = [
    # enums
    "IPState",
    "IPerm",
    "ISRule",
    "ISState",
    "BLOBPolicy",
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
    # codec
    "to_xml",
    "parse_indi",
    "XMLStreamParser",
    "to_json",
    "from_json",
]
