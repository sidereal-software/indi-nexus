"""Hatchling build hook that bundles the built reference panel into the artifact.

The TypeScript panel (``web/apps/panel``) compiles into
``src/indikit/web/static/panel/`` - a gitignored build output that
``[tool.hatch.build.targets.*].artifacts`` then force-includes in the sdist and
wheel. This hook makes a source build self-contained: when that output is missing
it builds it with pnpm, so ``pip install .`` / ``uv build`` ship the UI without a
separate step.

It is deliberately best-effort. If the panel is already built (for example by CI
before packaging) it is used as-is; if it is missing and pnpm is unavailable or the
build fails, packaging continues without the panel and the web bridge falls back to
its debug page at runtime. It never fails the install.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_ROOT = Path(__file__).parent
_PANEL_INDEX = _ROOT / "src" / "indikit" / "web" / "static" / "panel" / "index.html"
_WEB = _ROOT / "web"


class FrontendBuildHook(BuildHookInterface):
    """Build the reference panel (once, if needed) before the package is assembled."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Ensure the built panel exists so ``artifacts`` can bundle it.

        Parameters
        ----------
        version : str
            The build version (unused).
        build_data : dict
            Mutable build metadata from hatchling (unused).
        """
        if _PANEL_INDEX.exists():
            return
        pnpm = shutil.which("pnpm")
        if pnpm is None or not _WEB.is_dir():
            self.app.display_warning(
                "reference panel not built and pnpm unavailable; packaging without "
                "the UI (the web bridge serves its debug page instead). Run "
                "`cd web && pnpm install && pnpm -r build` to include it."
            )
            return
        try:
            self.app.display_info("building the reference panel with pnpm ...")
            subprocess.run([pnpm, "install", "--frozen-lockfile"], cwd=_WEB, check=True)
            subprocess.run([pnpm, "-r", "build"], cwd=_WEB, check=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            self.app.display_warning(
                f"failed to build the reference panel ({exc}); packaging without it."
            )
