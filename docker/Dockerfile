# syntax=docker/dockerfile:1

# INDINexus in a container: libindi's indiserver and the Python web bridge together,
# so `docker compose up` gives a working INDI stack - the panel on :8000, the hub on
# :7624 - with nothing installed on the host.
#
# Stages:
#   base     Ubuntu 24.04, libindi from the distro, Python 3.12 in /opt/venv
#   web      Node + pnpm; builds the TypeScript panel into the Python package
#   wheel    builds the indi-nexus wheel with that panel bundled
#   test     the repository, the dev and interop extras and a browser, for running
#            `pytest tests/interop` against real libindi
#   runtime  the wheel on top of base, non-root - the default target, so it is last
#
# Ubuntu 24.04 rather than a python: image on purpose. It is what the nightly interop
# workflow's "distro" leg runs (ubuntu-latest, `apt install indi-bin`), so the test
# target reproduces that job rather than approximating it; it carries libindi 1.9.9,
# which is what every current Debian and Ubuntu ships; its Python 3.12 meets the
# package's floor; and Playwright supports it as a first-class target on both amd64
# and arm64.


FROM ubuntu:24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH

# indi-bin is indiserver, libindi's own client tools (indi_getprop, indi_setprop,
# indi_eval) and the ~146 bundled drivers including every simulator. Those simulators
# are what let this image run something out of the box and what the interop corpus
# reads, so nothing here has to be built from source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        indi-bin \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv


FROM node:22-slim AS web

# corepack picks up the pnpm version pinned in web/package.json's packageManager field,
# so the image and CI build the panel with the same pnpm.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /src/web
# Only web/ is copied, so a change anywhere else in the repository leaves this stage
# cached. The panel's Vite config emits to ../../../src/indi_nexus/web/static/panel,
# which lands at /src/src/indi_nexus/web/static/panel.
COPY web/ ./
RUN --mount=type=cache,target=/pnpm-store \
    corepack enable \
    && pnpm config set store-dir /pnpm-store \
    && pnpm install --frozen-lockfile \
    && pnpm -r build


FROM base AS wheel

WORKDIR /src
COPY pyproject.toml hatch_build.py README.md LICENSE ./
COPY src ./src
COPY --from=web /src/src/indi_nexus/web/static/panel ./src/indi_nexus/web/static/panel
# --no-deps because this builds the distribution rather than installing it. The panel
# is already in place, so hatch_build.py finds it and never reaches for pnpm.
RUN pip wheel --no-deps --wheel-dir /dist .


FROM base AS test

# Chromium refuses to run as root without --no-sandbox, and test_panel_e2e.py calls
# p.chromium.launch() exactly as it does in CI, so the suite runs as a normal user.
# That means the browsers cannot live in root's cache: put them somewhere readable.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /repo
COPY pyproject.toml hatch_build.py README.md LICENSE ./
COPY src ./src
# One layer, and before the tests are copied: editing tests/ or examples/ then leaves
# the browser download cached, which is the loop this image exists for. Chromium is
# installed rather than made opt-in because the browser test is the single hardest
# test in this suite to run on a developer machine - it needs libindi, a built panel
# and a browser at once - and an image that silently skips it reintroduces the
# problem the image was added to solve.
RUN pip install -e ".[dev,interop]" \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && chmod -R a+rX /ms-playwright

# The browser test loads the panel from the source tree, because the install above is
# editable and the bundled copy in the wheel is not involved.
COPY --from=web /src/src/indi_nexus/web/static/panel ./src/indi_nexus/web/static/panel
COPY examples ./examples
COPY tests ./tests

RUN useradd --system --create-home --home-dir /home/indi --shell /bin/bash indi \
    && chown -R indi:indi /repo
USER indi

CMD ["pytest", "tests/interop", "-q", "--durations=10"]


FROM base AS runtime

ARG VERSION=dev
LABEL org.opencontainers.image.title="INDINexus" \
      org.opencontainers.image.description="indiserver, the INDINexus web bridge and the reference panel in one image." \
      org.opencontainers.image.url="https://indi-nexus.sidereal.software/" \
      org.opencontainers.image.documentation="https://indi-nexus.sidereal.software/docker/" \
      org.opencontainers.image.source="https://github.com/sidereal-software/indi-nexus" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

COPY --from=wheel /dist /tmp/dist
RUN pip install /tmp/dist/*.whl && rm -rf /tmp/dist

# The example drivers ship with the source rather than the wheel, so copy them in:
# INDI_DRIVERS can then name one without anything being mounted.
COPY examples /opt/indi-nexus/examples
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/indi-nexus-entrypoint

# A system user rather than uid 1000, which ubuntu:24.04 already gives to its own
# `ubuntu` account. libindi drivers save their configuration under $HOME, so it has to
# exist and be writable.
RUN useradd --system --create-home --home-dir /home/indi --shell /usr/sbin/nologin indi \
    && mkdir -p /drivers \
    && chown indi:indi /drivers
USER indi
WORKDIR /home/indi

# libindi's own telescope simulator, so an image with nothing mounted still shows a
# device with a Connect button, coordinates and a slew. A C++ driver nobody here wrote
# is the better default: it makes the out-of-the-box view a demonstration of interop
# rather than of our own serializer talking to our own parser. Point INDI_DRIVERS at
# /opt/indi-nexus/examples/flat_panel.py to see an INDINexus driver instead.
ENV INDI_DRIVERS=indi_simulator_telescope

EXPOSE 8000 7624

# Healthy means both halves are up: the bridge answers, and it has a live connection
# to the hub in this container. A bridge answering `connected: false` is serving an
# empty panel, which is not what this image promises.
HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=3 \
    CMD ["python3", "-c", "import json, os, urllib.request; url = 'http://127.0.0.1:' + os.environ.get('WEB_PORT', '8000') + '/health'; raise SystemExit(0 if json.load(urllib.request.urlopen(url, timeout=3))['connected'] else 1)"]

ENTRYPOINT ["/usr/local/bin/indi-nexus-entrypoint"]
