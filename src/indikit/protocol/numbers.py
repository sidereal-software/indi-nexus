"""INDI number text: the printf ``format`` and the sexagesimal forms.

The two halves of libindi's ``fs_sexa`` / ``f_scansexa`` pair, as pure functions
over a value and a format string. They are a *protocol* concern rather than an
XML one - the same rendering decides what a browser sees through the JSON codec,
and a driver's ``"on_change"`` policy compares numbers in exactly this
representation, because "changed" means changed as far as a client can tell.
"""

from __future__ import annotations

import math
import re

from indikit.exceptions import ProtocolError


def parse_number(text: str) -> float:
    """Parse a number that may be decimal or sexagesimal.

    Accepts plain decimals as well as ``dd:mm:ss`` (or space-separated)
    sexagesimal forms used for RA/Dec, as libindi's ``f_scansexa`` does.

    Deliberately a superset of libindi on the ``set`` path: libindi reads a
    ``oneNumber`` with ``std::stod`` there and only uses ``f_scansexa`` on the
    ``def`` path, so *it* reads ``"10:30:00"`` in a ``setNumberVector`` as
    ``10.0``. We read sexagesimal in both, which cannot silently truncate a
    coordinate. Do not "fix" this to match: matching would mean reading 10:30
    as 10, which is a data-corruption bug wearing a compatibility badge.

    Strict on purpose, where the XML codec around it is lenient: ``value`` is
    not nullable on the model, so there is no way to say "absent". Raising here
    lets the stream parser drop the whole element rather than publish a reading
    a mount would act on.

    That covers the non-finite values too. ``float`` reads ``"nan"`` and
    ``"inf"`` happily, but neither survives the round trip - JSON cannot write
    them, and an integer ``format`` cannot render them - so they are refused
    here as well as on the model.

    Parameters
    ----------
    text : str
        The raw element text.

    Returns
    -------
    value : float
        The parsed value; ``0.0`` for empty input.

    Raises
    ------
    ProtocolError
        Raised (as a ValueError, which the stream parser drops on) if the text
        is neither a decimal nor a sexagesimal number, or if it names a
        non-finite value.
    """
    s = text.strip()
    if not s:
        return 0.0
    value = _decimal_or_sexagesimal(s)
    if not math.isfinite(value):
        raise ProtocolError(f"non-finite number {s!r}")
    return value


def _decimal_or_sexagesimal(s: str) -> float:
    """Read a non-empty, stripped number in decimal or sexagesimal form.

    Parameters
    ----------
    s : str
        The stripped element text.

    Returns
    -------
    value : float
        The parsed value, finite or not.

    Raises
    ------
    ProtocolError
        Raised (as a ValueError) if the text is neither a decimal nor a
        sexagesimal number.
    """
    try:
        return float(s)
    except ValueError:
        pass
    parts = re.split(r"[:\s]+", s)
    sign = -1.0 if parts[0].lstrip().startswith("-") else 1.0
    try:
        nums = [abs(float(p)) for p in parts if p]
    except ValueError as exc:
        # A component that is not a number at all ("10:xx:00"). float's own
        # ValueError would escape as a bare one, which is what the public
        # docstring promises against.
        raise ProtocolError(f"not a number: {s!r}") from exc
    acc = 0.0
    for i, n in enumerate(nums):
        acc += n / (60**i)
    return sign * acc


def format_number(value: float, fmt: str) -> str:
    """Format a number per an INDI printf-style format.

    Handles ordinary printf conversions as well as the ``%m`` sexagesimal form
    (e.g. ``%9.6m``), field-width padded like libindi's ``fs_sexa``.

    Half-way values round *away from zero*, which is what ``fs_sexa`` does
    (``indicom.c:165`` casts ``a * fracbase + 0.5`` to an integer). Python's
    built-in `round` is half-to-*even*, so it disagrees on exactly the values
    that land on a tick boundary: at ``%10.6m`` it renders ``0.03125`` as
    ``0:01:52`` where libindi says ``0:01:53``. One arcsecond, only on exact
    halves, in the format mounts use for RA and Dec.

    One divergence from ``fs_sexa`` is kept on purpose: libindi passes a
    negative width to ``%*s`` when ``w - f < 3`` (``indicom.c:171``), which
    left-justifies instead. No real driver declares such a format, and matching
    the quirk would only preserve it.

    Parameters
    ----------
    value : float
        The number to format.
    fmt : str
        The INDI ``format`` string from the element definition.

    Returns
    -------
    text : str
        The formatted value.
    """
    m = re.fullmatch(r"%(\d+)\.(\d+)m", fmt.strip())
    if not m:
        # OverflowError belongs with the other two: an integer conversion
        # against a non-finite value raises it (``"%d" % float("inf")``), and
        # this is the last stop before the writer loop. The models refuse a
        # non-finite ``value`` now, but ``format`` is the peer's string and this
        # function is public, so the fallback still has to hold.
        try:
            return (fmt % value).strip()
        except (TypeError, ValueError, OverflowError):
            return repr(value)

    width, frac = int(m.group(1)), int(m.group(2))
    fracbase = {9: 360000, 8: 36000, 6: 3600, 5: 600}.get(frac, 60)
    neg = value < 0
    n = math.floor(abs(value) * fracbase + 0.5)
    d, f = divmod(n, fracbase)
    dd = f"{'-' if neg else ''}{d}"
    field = max(width - frac, 1)
    dd = dd.rjust(field)
    if fracbase == 60:  # dd:mm
        return f"{dd}:{f:02d}"
    if fracbase == 600:  # dd:mm.m
        return f"{dd}:{f // 10:02d}.{f % 10:1d}"
    if fracbase == 3600:  # dd:mm:ss
        return f"{dd}:{f // 60:02d}:{f % 60:02d}"
    if fracbase == 36000:  # dd:mm:ss.s
        return f"{dd}:{f // 600:02d}:{(f % 600) // 10:02d}.{f % 10:1d}"
    # dd:mm:ss.ss
    return f"{dd}:{f // 6000:02d}:{(f % 6000) // 100:02d}.{f % 100:02d}"
