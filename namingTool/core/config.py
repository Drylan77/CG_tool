"""Configuration loading / saving / merging for the naming tool.

The studio convention lives in ``resources/naming_config.json`` but every value
can be overridden by a user config (deep-merged over the embedded defaults), so
changing e.g. the ``GEO`` suffix reconfigures the whole tool without touching
code (regex, presets, checks all derive from here).
"""

from __future__ import annotations

import copy
import json
import logging
import os
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "resources", "naming_config.json")
)

_cache: Dict[str, Any] = {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``base`` deep-merged with ``override`` (override wins)."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_defaults() -> Dict[str, Any]:
    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_config(user_path: Optional[str] = None, use_cache: bool = True) -> Dict[str, Any]:
    """Load the embedded config, deep-merging an optional user override on top.

    ``user_path`` defaults to the ``NAMINGTOOL_CONFIG`` environment variable so
    a whole team can point at a shared config on the server.
    """
    if use_cache and _cache.get("config") is not None and user_path is None:
        return _cache["config"]

    config = load_defaults()
    path = user_path or os.environ.get("NAMINGTOOL_CONFIG")
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                config = _deep_merge(config, json.load(fh))
            log.info("Loaded user naming config: %s", path)
        except (OSError, ValueError) as exc:
            log.warning("Could not read user config %s: %s", path, exc)

    if user_path is None:
        _cache["config"] = config
    return config


def save_config(config: Dict[str, Any], path: str) -> str:
    """Write ``config`` to ``path`` as pretty JSON. Returns the path."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=4, ensure_ascii=False)
    log.info("Saved naming config: %s", path)
    return path


def clear_cache() -> None:
    _cache.pop("config", None)


# -- convenience accessors -------------------------------------------------- #
def valid_suffixes(config: Dict[str, Any]) -> list:
    """Return the sorted, unique set of accepted suffix codes."""
    codes = set(config.get("suffixes", {}).values())
    return sorted(codes)
