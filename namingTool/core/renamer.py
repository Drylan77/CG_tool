"""Rename operations (Maya). Every batch is wrapped in a single undo chunk.

All functions accept an explicit ``config`` so they honour the studio settings
(separator, padding, suffix table...).
"""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import maya_utils, naming

log = logging.getLogger(__name__)


@dataclass
class RenameEntry:
    old: str
    new: str
    status: str = "ok"        # "ok" | "skipped" | "error"
    message: str = ""


def _depth_sorted(nodes: List[str]) -> List[str]:
    """Deepest DAG paths first, so renaming children never invalidates a
    parent path we still hold."""
    return sorted(nodes, key=lambda n: n.count("|"), reverse=True)


def _apply(node: str, new_short: str, results: List[RenameEntry],
           config: Dict[str, Any], ensure_unique: bool = True) -> None:
    old = maya_utils.short_name(node)
    if maya_utils.is_protected(node, config):
        results.append(RenameEntry(old, old, "skipped", "noeud protege"))
        return
    if new_short == old:
        results.append(RenameEntry(old, old, "skipped", "inchange"))
        return
    try:
        target = maya_utils.make_unique(new_short) if ensure_unique else new_short
        new = maya_utils.rename_node(node, target)
        results.append(RenameEntry(old, maya_utils.short_name(new), "ok"))
    except Exception as exc:  # noqa: BLE001
        log.exception("rename failed on %s", node)
        results.append(RenameEntry(old, old, "error", str(exc)))


# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #
def rename_and_number(base: str, suffix: str, config: Dict[str, Any],
                      side: str = "", nodes: Optional[List[str]] = None) -> List[RenameEntry]:
    """Rename the selection to ``base01_SUFFIX``, ``base02_SUFFIX`` ... in
    selection order."""
    nodes = nodes if nodes is not None else maya_utils.get_selection()
    if not nodes:
        raise RuntimeError("Aucun objet selectionne.")
    results: List[RenameEntry] = []
    with maya_utils.undo_chunk("namingTool_renameNumber"):
        # keep selection order but rename deepest first to protect paths
        order = {n: i for i, n in enumerate(nodes)}
        for node in _depth_sorted(nodes):
            idx = order[node] + int(config.get("add_index_start", 1))
            new = naming.build_name(base, suffix, config, side=side, increment=idx)
            _apply(node, new, results, config)
    return results


def add_affix(affix: str, where: str, config: Dict[str, Any],
              nodes: Optional[List[str]] = None) -> List[RenameEntry]:
    """Add a prefix or suffix, avoiding duplicates (no ``_GEO_GEO``)."""
    nodes = nodes if nodes is not None else maya_utils.get_selection()
    if not nodes:
        raise RuntimeError("Aucun objet selectionne.")
    sep = config.get("separator", "_")
    affix = affix.strip(sep)
    results: List[RenameEntry] = []
    with maya_utils.undo_chunk("namingTool_affix"):
        for node in _depth_sorted(nodes):
            old = maya_utils.short_name(node)
            tokens = old.split(sep)
            if where == "prefix":
                new = old if tokens and tokens[0] == affix else f"{affix}{sep}{old}"
            else:
                new = old if tokens and tokens[-1] == affix else f"{old}{sep}{affix}"
            _apply(node, new, results, config)
    return results


def search_replace(search: str, replace: str, config: Dict[str, Any],
                   nodes: Optional[List[str]] = None, use_wildcard: bool = False,
                   case_sensitive: bool = True) -> List[RenameEntry]:
    """Search & replace on short names. Supports ``*`` wildcards."""
    nodes = nodes if nodes is not None else maya_utils.get_selection()
    if not nodes:
        raise RuntimeError("Aucun objet cible.")
    flags = 0 if case_sensitive else re.IGNORECASE
    if use_wildcard:
        pattern = re.compile(fnmatch.translate(search), flags)
    else:
        pattern = re.compile(re.escape(search), flags)
    results: List[RenameEntry] = []
    with maya_utils.undo_chunk("namingTool_searchReplace"):
        for node in _depth_sorted(nodes):
            old = maya_utils.short_name(node)
            new = pattern.sub(replace, old)
            if new != old:
                _apply(node, new, results, config)
    return results


def auto_suffix(config: Dict[str, Any],
                nodes: Optional[List[str]] = None) -> List[RenameEntry]:
    """Inspect each node's real type and apply / fix the correct suffix.

    The flagship modeler operation: ``pCube1`` mesh -> ``pCube1_GEO`` (then a
    cleanup pass can camelCase / renumber it). An existing wrong suffix is
    replaced; a correct one is left untouched.
    """
    nodes = nodes if nodes is not None else maya_utils.get_selection()
    if not nodes:
        raise RuntimeError("Aucun objet selectionne.")
    sep = config.get("separator", "_")
    from .config import valid_suffixes
    codes = set(valid_suffixes(config))

    results: List[RenameEntry] = []
    with maya_utils.undo_chunk("namingTool_autoSuffix"):
        for node in _depth_sorted(nodes):
            old = maya_utils.short_name(node)
            expected = maya_utils.expected_suffix(node, config)
            if not expected:
                results.append(RenameEntry(old, old, "skipped", "type inconnu"))
                continue
            tokens = old.split(sep)
            if tokens[-1] in codes:      # replace an existing (maybe wrong) suffix
                tokens[-1] = expected
            else:                         # append a missing suffix
                tokens.append(expected)
            _apply(node, sep.join(tokens), results, config)
    return results


def side_by_bbox(config: Dict[str, Any],
                 nodes: Optional[List[str]] = None) -> List[RenameEntry]:
    """Prefix L_/R_ based on the object's bounding-box centre on X."""
    maya_utils.require_maya()
    import maya.cmds as cmds  # type: ignore

    nodes = nodes if nodes is not None else maya_utils.get_selection()
    if not nodes:
        raise RuntimeError("Aucun objet selectionne.")
    sides = config.get("side_from_bbox", {"positive_x": "L", "negative_x": "R"})
    sep = config.get("separator", "_")
    results: List[RenameEntry] = []
    with maya_utils.undo_chunk("namingTool_side"):
        for node in _depth_sorted(nodes):
            old = maya_utils.short_name(node)
            bbox = cmds.xform(node, q=True, worldSpace=True, boundingBox=True)
            center_x = (bbox[0] + bbox[3]) / 2.0
            if abs(center_x) < 1e-4:
                side = config.get("sides", {}).get("center", "C")
            else:
                side = sides["positive_x"] if center_x > 0 else sides["negative_x"]
            new = old if old.split(sep)[0] == side else f"{side}{sep}{old}"
            _apply(node, new, results, config)
    return results


def cleanup(config: Dict[str, Any], nodes: Optional[List[str]] = None,
            remove_namespaces: bool = True) -> List[RenameEntry]:
    """Strip illegal chars, camelCase the descriptor, drop ``pasted__`` and
    (optionally) namespaces."""
    nodes = nodes if nodes is not None else maya_utils.get_selection()
    if not nodes:
        raise RuntimeError("Aucun objet selectionne.")
    sep = config.get("separator", "_")
    from .config import valid_suffixes
    codes = set(valid_suffixes(config))

    results: List[RenameEntry] = []
    with maya_utils.undo_chunk("namingTool_cleanup"):
        for node in _depth_sorted(nodes):
            old = maya_utils.short_name(node)
            name = old
            if remove_namespaces:
                name = name.split(":")[-1]
            name = name.replace("pasted__", "").replace("pasted_", "")
            tokens = [t for t in name.split(sep) if t != ""]
            suffix = tokens.pop() if tokens and tokens[-1] in codes else ""
            descriptor = naming.to_camel_case(sep.join(tokens))
            new = descriptor + (sep + suffix if suffix else "")
            if new and new != old:
                _apply(node, new, results, config)
            else:
                results.append(RenameEntry(old, old, "skipped", "inchange"))
    return results
