"""The INDI ``.z`` transport encoding: inflate a BLOB payload on receipt.

The 1.7 whitepaper defines a BLOB's ``format`` as a chain of suffixes and says a
trailing ``.z`` means the payload is zlib-compressed - ``.fits.z`` is a FITS file
that has been deflated for the wire - and that clients are encouraged to support
it. libindi does exactly that in ``BaseDevicePrivate::setBLOB``: every client
built on it inflates the payload, strips the ``.z`` and hands the application
``.fits``. A consumer written against KStars has never seen a ``.z`` and will not
look for one, so delivering deflated bytes beside a ``size`` describing data we
did not deliver is a correctness bug, not a missing feature.

This lives beside :mod:`indi_nexus.protocol.numbers` rather than inside
:mod:`indi_nexus.protocol.xml` for the same reason that one does: it is not an
XML concern. A BLOB reaches a browser as JSON off the *same* models, and a
browser must no more see a ``.z`` than a Python application does, so the rule
belongs where both codecs can call it. Doing it in :mod:`indi_nexus.client.store`
instead - where libindi happens to put it - would cover the client and leave the
driver's inbound ``newBLOBVector`` and the whole JSON path uncovered.

**Compressing is receive-only in the sense that matters**: nothing here ever
deflates anything. That stays the driver author's decision, as it is in libindi
(an opt-in ``CCD_COMPRESSION`` switch, defaulting to off). A driver may set
``format=".fits.z"`` with deflated bytes and an explicit uncompressed ``size``,
and both codecs serialise that faithfully; what neither will do is guess the
``size`` it cannot know, which is :func:`require_declared_size`.
"""

from __future__ import annotations

import logging
import zlib

from indi_nexus.exceptions import ProtocolError
from indi_nexus.protocol.models import BLOB

logger = logging.getLogger(__name__)

#: The suffix marking a zlib-compressed payload.
#:
#: Matched with a leading dot on purpose. ``format.endswith("z")`` also matches
#: ``.fits.fz``, which is FITS *tile* compression - an astronomy container
#: format, not a transport encoding. No libindi client un-fpacks it, undoing it
#: needs cfitsio, and inflating those bytes as zlib would corrupt every fpacked
#: frame in the field. ``.fz`` is left completely untouched; do not "simplify"
#: this to a bare ``"z"``.
_ZLIB_SUFFIX = ".z"


def zlib_encoded(fmt: str | None) -> bool:
    """Whether a BLOB ``format`` marks its payload as zlib-compressed.

    Parameters
    ----------
    fmt : str or None
        The BLOB's ``format``, a chain of suffixes such as ``.fits.z``.

    Returns
    -------
    encoded : bool
        `True` only for a trailing ``.z``. ``.fz`` is FITS tile compression and
        is not a transport encoding, so it reads as `False`.
    """
    return fmt is not None and fmt.endswith(_ZLIB_SUFFIX)


def require_declared_size(el: BLOB) -> None:
    """Refuse to emit a compressed payload whose uncompressed length is unstated.

    INDI's ``size`` is the decoded **and uncompressed** length, so ``len(data)``
    is the right default only for a payload that is neither encoded nor
    compressed. A ``.z`` format says the bytes are deflated, and the number the
    attribute is defined as could only be learned by inflating them - work the
    driver did not ask for on a path where it already knows the answer. So it
    has to say, and a model that does not is refused rather than described with
    the wrong number.

    Both codecs call this, and that is the point: they serialise the *same*
    models, so a frame one of them will emit and the other will not is drift
    between two descriptions of one contract. Keeping the rule here rather than
    in either codec is what stops it being written twice and diverging once.
    Refusing is loud and contained - the driver runtime's writer reports a
    message it cannot serialise and drops it, rather than taking the driver down.

    ``.fz`` is untouched, as everywhere else in this module: it is a container
    format whose ``size`` the driver states for reasons of its own.

    Parameters
    ----------
    el : BLOB
        The element about to be serialised.

    Raises
    ------
    ProtocolError
        Raised if the element carries a payload and a ``.z`` format but no
        ``size``. Also a ValueError.
    """
    if el.data is not None and el.size is None and zlib_encoded(el.format):
        raise ProtocolError(
            f"BLOB {el.name!r} declares {el.format!r} but no size; a compressed "
            "payload must carry the uncompressed length explicitly"
        )


def _strip_suffix(fmt: str) -> str | None:
    """Remove the trailing ``.z`` from a format chain.

    Only the final suffix goes, which is what libindi's single ``lastIndexOf``
    does: a payload deflated twice is not a shape anything in the ecosystem
    produces, and looping would turn one into an unbounded amount of work driven
    by a peer's string.

    Parameters
    ----------
    fmt : str
        A format chain ending in ``.z``.

    Returns
    -------
    stripped : str or None
        The chain without its ``.z``, or `None` when nothing is left - a bare
        ``".z"`` describes the encoding and never the content, so "absent" is
        the honest answer rather than an empty format on the wire.
    """
    return fmt[: -len(_ZLIB_SUFFIX)] or None


def inflate_blob(el: BLOB) -> None:
    """Inflate a received ``.z`` payload in place, mirroring libindi exactly.

    Three things change together, and an application must never see any of them
    half-applied: the payload becomes the inflated bytes, ``format`` loses its
    ``.z``, and ``size`` becomes the inflated length. Anything else that is
    already what a caller wants - an uncompressed payload, a ``.fz`` frame, a
    ``def`` carrying no bytes at all - is left exactly as it arrived.

    A ``def``-shaped BLOB is untouched even when its ``format`` says ``.z``:
    there is no payload to inflate, and renaming a format on the strength of
    bytes that never arrived would describe a frame nobody sent. The ``set``
    that carries the payload brings the corrected format with it, and a client's
    merge takes the format from the ``set``.

    Parameters
    ----------
    el : BLOB
        The freshly parsed element, mutated in place.

    Raises
    ------
    ProtocolError
        Raised if the payload will not inflate. Also a ValueError, so the XML
        stream parser's documented drop-and-count path applies and a corrupt
        frame costs the message carrying it rather than the connection. The
        compressed bytes are never delivered instead: a caller that asked for a
        ``.fits`` and got deflate would hand it to a FITS reader.
    """
    fmt, data = el.format, el.data
    if data is None or fmt is None or not zlib_encoded(fmt):
        return

    try:
        # RFC 1950, not raw deflate. The whitepaper's footnote cites RFC 1951,
        # but libindi calls zlib's compress2()/uncompress(), which write and
        # expect the 2-byte zlib header and the Adler-32 trailer. Passing
        # wbits=-15 here would refuse every real payload.
        inflated = zlib.decompress(data)
    except zlib.error as exc:
        raise ProtocolError(
            f"BLOB {el.name!r} declares {fmt!r} but its payload will not inflate: {exc}"
        ) from exc

    # `size` is the sender's claim about the uncompressed length, and it is only
    # ever a cross-check: zlib.decompress grows its own buffer, so the number is
    # never an allocation bound, and a sender that miscounts must not cost us the
    # frame we successfully inflated.
    if el.size is not None and el.size != len(inflated):
        logger.warning(
            "BLOB %r declared size %d but inflated to %d bytes",
            el.name,
            el.size,
            len(inflated),
        )

    el.data = inflated
    el.size = len(inflated)
    el.format = _strip_suffix(fmt)
