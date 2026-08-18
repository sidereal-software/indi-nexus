# Interop tests

These run against a real `indiserver` and real libindi drivers. Everything else in
the test suite feeds our serializer into our own parser, which is self-consistent by
construction and so cannot catch a deviation from the INDI spec. These put libindi on
the other side of the wire instead.

They are excluded from a normal `pytest` run (`addopts` in `pyproject.toml`) because
they are slow and need libindi installed. CI runs them nightly against several
libindi versions: [`.github/workflows/interop.yml`](../../.github/workflows/interop.yml).

## Running them

```bash
uv run pytest tests/interop -p no:cacheprovider
```

The suite skips itself with a clear message if `indiserver` is not on the PATH.

| Ubuntu / Debian | `sudo apt install indi-bin` |
| Newer libindi | the [indilib PPA](https://launchpad.net/~mutlaqja/+archive/ubuntu/ppa) |
| macOS | no package; use the container below |

Nothing packages libindi for macOS, so on a Mac run them in the container, which carries
libindi, the dev dependencies and a browser already:

```bash
docker compose --profile interop run --rm --build interop
```

That is the `test` target of [`docker/Dockerfile`](../../docker/Dockerfile), on the same
Ubuntu 24.04 and the same libindi 1.9.9 as the nightly job's distro leg. Pass a command
to narrow it, e.g. `... run --rm interop pytest tests/interop/test_smoke.py -q`.
[`docs/docker.md`](../../docs/docker.md) has the rest.

Outside the container the browser test additionally needs Playwright
(`pip install -e ".[interop]"` then `playwright install chromium`); it skips itself when
that is missing.

## What each file is for

| File | What it proves |
|---|---|
| `test_smoke.py` | The stack reaches a real hub at all. Fails first and cheaply. |
| `test_reverse_interop.py` | libindi's own clients can read and drive *our* drivers. |
| `test_corpus.py` | Our parser handles every simulator libindi ships. |
| `test_differential.py` | Our reading of a server matches `indi_getprop`'s. |
| `test_blob.py` | `enableBLOB` negotiation, the three policies, and FITS bytes surviving intact. |
| `test_reconnect.py` | Recovery from a real socket dropping, not a queue sentinel. |
| `test_panel_e2e.py` | A browser drives a real C++ driver through the whole stack. |
| `test_capture_corpus.py` | Records real traffic into a fixture the fast suite replays. |

`drivers/` holds drivers written for these tests rather than for readers - a shape no
example covers, exercised against a real hub. Anything meant to be read as a model driver
belongs in `examples/` instead, which is where `test_reverse_interop.py` gets the rest.

## Refreshing the recorded corpora

Two files of real traffic, both replayed by `tests/test_protocol_corpus.py` in the fast
suite so pull requests get the benefit without libindi:

| Fixture | What it holds |
|---|---|
| `tests/data/interop_corpus.xml` | Breadth: every simulator's definitions, from one `getProperties`. |
| `tests/data/interop_blob_corpus.xml` | Depth: one CCD driven through connect, a 64x64 sub-frame, `enableBLOB` and an exposure - so `set` vectors, driver messages and a real FITS payload libindi base64-encoded. |

Refresh them when libindi gains drivers or changes what it emits:

```bash
INDI_CAPTURE_CORPUS=1 uv run pytest tests/interop/test_capture_corpus.py
```

Review the diff before committing. A capture is only worth having if it parses, and
the test checks that before writing.
