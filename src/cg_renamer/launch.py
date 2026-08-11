"""Entry point to open the CG Asset Renamer from Maya.

Usage from the Maya Script Editor (Python tab) or a shelf button:

    import cg_renamer.launch as launch
    launch.main()
"""

from __future__ import annotations

import os


def _default_config() -> str:
    from .naming_convention import DEFAULT_CONFIG_PATH
    override = os.environ.get("CG_RENAMER_CONFIG")
    return override if override and os.path.isfile(override) else DEFAULT_CONFIG_PATH


def main(config_path: str | None = None):
    from . import renamer_ui
    return renamer_ui.show(config_path or _default_config())


if __name__ == "__main__":
    main()
