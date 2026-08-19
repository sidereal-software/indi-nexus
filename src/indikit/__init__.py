"""INDIkit: a modern, typed Python framework for INDI instrument control."""

from indikit.exceptions import (
    ConfigError,
    DeviceNotServing,
    IndiError,
    NotConnectedError,
    PropertyNotFound,
    PropertyRetracted,
    ProtocolError,
    SendQueueFull,
    WrongPropertyKind,
)

__version__ = "0.2.0"

__all__ = [
    "ConfigError",
    "DeviceNotServing",
    "IndiError",
    "NotConnectedError",
    "PropertyNotFound",
    "PropertyRetracted",
    "ProtocolError",
    "SendQueueFull",
    "WrongPropertyKind",
    "__version__",
]
