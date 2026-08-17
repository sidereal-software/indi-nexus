"""Tests for the bridge's access policy as pure functions over header strings.

``WS /ws`` is the whole write surface, and the ``Origin`` check is the only thing
guarding it against a page on another origin, so the decisions below are pinned
here rather than only through the app.
"""

from __future__ import annotations

from indi_nexus.web.security import WebSecurity, is_loopback


def test_a_missing_origin_is_allowed():
    """A handshake with no Origin connects, deliberately and permanently.

    A browser always sends one, so refusing a request without it stops nothing;
    what it would stop is every non-browser peer - a Node client, curl, the
    interop suite, Starlette's TestClient - none of which sends the header.
    """
    assert WebSecurity().origin_allowed(None, "localhost:8000") is True


def test_the_same_origin_is_allowed_and_a_foreign_one_is_not():
    """Origin's netloc is compared against the request's Host."""
    security = WebSecurity()
    assert security.origin_allowed("http://localhost:8000", "localhost:8000") is True
    assert security.origin_allowed("https://LOCALHOST:8000", "localhost:8000") is True
    assert security.origin_allowed("http://evil.example", "localhost:8000") is False


def test_a_port_mismatch_is_a_different_origin():
    """The port is part of the origin, whatever a cookie would have thought."""
    assert WebSecurity().origin_allowed("http://localhost:9999", "localhost:8000") is False


def test_a_configured_origin_is_allowed():
    """A named origin connects; an unnamed one still does not."""
    security = WebSecurity.build(None, ["http://localhost:5173"])
    assert security.origin_allowed("http://localhost:5173", "localhost:8000") is True
    assert security.origin_allowed("http://localhost:5174", "localhost:8000") is False


def test_a_wildcard_allows_any_origin():
    """``*`` turns the check off, for someone who has decided that is right."""
    security = WebSecurity.build(None, ["*"])
    assert security.origin_allowed("http://anything.example", "localhost:8000") is True


def test_no_host_and_a_foreign_origin_is_refused():
    """With nothing to compare against, an origin cannot be same-origin."""
    assert WebSecurity().origin_allowed("http://evil.example", None) is False


def test_no_token_configured_accepts_anything():
    """Loopback development runs without a token, so an absent one is fine."""
    security = WebSecurity()
    assert security.token_required is False
    assert security.token_ok(None) is True
    assert security.token_ok("anything") is True


def test_a_configured_token_must_match():
    """A configured token is required and compared in constant time."""
    security = WebSecurity.build("s3cret", [])
    assert security.token_required is True
    assert security.token_ok("s3cret") is True
    assert security.token_ok("wrong") is False
    assert security.token_ok(None) is False


def test_build_treats_an_empty_token_as_none():
    """An unset environment variable arrives as ``""`` and means "no token"."""
    assert WebSecurity.build("", [" ", ""]).token is None
    assert WebSecurity.build("", []).allowed_origins == frozenset()


def test_is_loopback_recognises_only_this_machine():
    """Only an address that cannot leave the host counts as loopback.

    ``""`` and ``0.0.0.0`` mean every interface, which is the exposure the CLI's
    refusal exists to catch, so neither may pass.
    """
    assert is_loopback("localhost") is True
    assert is_loopback("127.0.0.1") is True
    assert is_loopback("127.1.2.3") is True
    assert is_loopback("::1") is True
    assert is_loopback("[::1]") is True
    assert is_loopback("") is False
    assert is_loopback("0.0.0.0") is False
    assert is_loopback("192.168.1.10") is False
    assert is_loopback("observatory.local") is False
