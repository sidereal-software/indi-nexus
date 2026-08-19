"""The access controls in front of the web bridge: an origin allowlist and a token.

``WS /ws`` is the bridge's **entire write surface**: a frame arriving there becomes
an INDI ``new*`` message on the upstream connection, which is how a browser slews a
mount or opens a shutter. Browsers do not apply the same-origin policy to
WebSockets and CORS does not cover them either, so without a check here any page an
operator happens to visit can open ``ws://localhost:8000/ws`` and drive the
instrument - cross-site WebSocket hijacking. The ``Origin`` check is therefore *the*
control on that surface, not defence in depth on top of one.

Two deliberate decisions live in :meth:`WebSecurity.origin_allowed`:

* **A missing ``Origin`` is allowed.** A browser always sends one on a WebSocket
  handshake, so refusing a request without one stops no browser; what it does stop
  is every non-browser peer - a Node consumer of ``@indikit/client``, ``curl``,
  the interop suite, Starlette's own ``TestClient`` - none of which sends the
  header. An attacker outside a browser sets the header to anything it likes, so
  the requirement would cost real users and buy nothing.
* **``X-Forwarded-*`` is not consulted.** A header any client can forge is not an
  authorization input. Behind a reverse proxy that rewrites ``Host``, name the
  browser-facing origin explicitly with ``--allow-origin``.

Everything here is a pure function over header strings, so it is testable without a
FastAPI request and has no import cycle with :mod:`indikit.web.app`.
"""

from __future__ import annotations

import hmac
import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def is_loopback(host: str) -> bool:
    """Report whether a bind address reaches only this machine.

    Used by the CLI to refuse a network-facing bind that has no token on it. An
    empty host is **not** loopback: to a socket API it means "every interface",
    which is the exposure this check exists to catch.

    Parameters
    ----------
    host : str
        A bind address as passed to ``--host``: a hostname or an IP literal.

    Returns
    -------
    loopback : bool
        `True` when the address is ``localhost`` or a loopback IP literal.
    """
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        # A name that is not a literal could resolve anywhere, so treat it as
        # exposed: the wrong answer here is the one that stays quiet.
        return False


@dataclass(frozen=True, slots=True)
class WebSecurity:
    """The bridge's access policy: which origins may connect, and with what token.

    Parameters
    ----------
    token : str or None, optional
        A shared secret required on ``/ws`` and ``/api``; `None` (the default)
        leaves both open, which is what a loopback-bound development server
        wants.
    allowed_origins : frozenset of str, optional
        Browser origins accepted in addition to the request's own origin, e.g.
        ``http://localhost:5173`` for a Vite dev server on another port. The
        single entry ``"*"`` accepts any origin.
    """

    token: str | None = None
    allowed_origins: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def build(cls, token: str | None, allowed_origins: Iterable[str]) -> WebSecurity:
        """Build a policy from loose CLI/environment values.

        An empty token string means "no token", which is what an unset
        environment variable and an unpassed option both arrive as.

        Parameters
        ----------
        token : str or None
            The shared secret, or `None`/``""`` for none.
        allowed_origins : Iterable of str
            Extra origins to accept; blank entries are ignored.

        Returns
        -------
        security : WebSecurity
            The configured policy.
        """
        origins = frozenset(origin.strip() for origin in allowed_origins if origin.strip())
        return cls(token=token or None, allowed_origins=origins)

    @property
    def token_required(self) -> bool:
        """Whether a token must be supplied to reach ``/ws`` and ``/api``."""
        return self.token is not None

    def origin_allowed(self, origin: str | None, host: str | None) -> bool:
        """Report whether a handshake's ``Origin`` may open a connection.

        Parameters
        ----------
        origin : str or None
            The request's ``Origin`` header; `None` when it carried none, which
            is allowed (see the module docstring).
        host : str or None
            The request's ``Host`` header, against which same-origin is judged.

        Returns
        -------
        allowed : bool
            `True` when the connection may proceed.
        """
        if origin is None:
            return True
        if "*" in self.allowed_origins:
            return True
        if origin in self.allowed_origins:
            return True
        if host is None:
            return False
        # netloc, not the whole URL: an origin is scheme + host + port, and Host
        # carries host + port, so this is the only comparable pair. The port is
        # part of it - http://localhost:9999 is a different origin from :8000
        # even though a cookie would not distinguish them.
        return urlsplit(origin).netloc.casefold() == host.casefold()

    def token_ok(self, supplied: str | None) -> bool:
        """Report whether a supplied token matches the configured one.

        Parameters
        ----------
        supplied : str or None
            The token read from the request, or `None` if it carried none.

        Returns
        -------
        ok : bool
            `True` when no token is configured, or when the supplied one matches.
        """
        if self.token is None:
            return True
        if supplied is None:
            return False
        return hmac.compare_digest(supplied, self.token)


__all__ = ["WebSecurity", "is_loopback"]
