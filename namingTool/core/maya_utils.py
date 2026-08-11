"""Thin Maya helpers shared by the renamer and the checks.

Everything touching ``maya.cmds`` is centralised here so the rest of the core
(``naming``, ``config``) stays importable and testable outside of Maya.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from . import naming

log = logging.getLogger(__name__)

try:
    import maya.cmds as cmds  # type: ignore
    IN_MAYA = True
except ImportError:  # pragma: no cover - allows import outside Maya
    cmds = None
    IN_MAYA = False


def require_maya() -> None:
    if not IN_MAYA:
        raise RuntimeError("Fonction disponible uniquement dans Maya (maya.cmds absent).")


# --------------------------------------------------------------------------- #
# Selection & listing
# --------------------------------------------------------------------------- #
def get_selection(long_names: bool = True) -> List[str]:
    require_maya()
    return cmds.ls(selection=True, long=long_names) or []


def short_name(node: str) -> str:
    return naming.strip_namespace(node)


def list_nodes(scope: str = "scene", root: Optional[str] = None,
               node_type: Optional[str] = None) -> List[str]:
    """List DAG nodes for a given scope.

    scope: "selection" | "hierarchy" (below ``root`` / selection) | "scene".
    Selection takes priority over ``root`` when scope is "hierarchy".
    """
    require_maya()
    kwargs: Dict[str, Any] = {"long": True, "dag": True}
    if node_type:
        kwargs["type"] = node_type

    if scope == "selection":
        sel = get_selection()
        if not sel:
            return []
        return cmds.ls(sel, **kwargs) or []

    if scope == "hierarchy":
        top = get_selection() or ([root] if root else [])
        if not top:
            return []
        nodes = cmds.listRelatives(top, allDescendents=True, fullPath=True, type="transform") or []
        nodes = list(top) + nodes
        if node_type:
            nodes = cmds.ls(nodes, **kwargs) or []
        return nodes

    # scene
    return cmds.ls(**kwargs) or []


# --------------------------------------------------------------------------- #
# Node introspection
# --------------------------------------------------------------------------- #
def shapes_of(node: str) -> List[str]:
    require_maya()
    return cmds.listRelatives(node, shapes=True, fullPath=True) or []


def real_node_type(node: str) -> str:
    """Return the effective node type key (shape type for a transform)."""
    require_maya()
    ntype = cmds.nodeType(node)
    if ntype != "transform":
        return ntype
    shapes = shapes_of(node)
    if shapes:
        return cmds.nodeType(shapes[0])
    return "group"  # a transform with no shape is an organisational group


def expected_suffix(node: str, config: Dict[str, Any]) -> Optional[str]:
    """Return the convention suffix expected for ``node`` given its real type."""
    mapping = config.get("node_type_suffix", {})
    key = real_node_type(node)
    if key in mapping:
        return mapping[key]
    # a transform with children but no shape -> group
    if cmds.nodeType(node) == "transform" and not shapes_of(node):
        return mapping.get("group", "GRP")
    return None


def has_namespace(node: str) -> bool:
    return ":" in short_name_with_ns(node)


def short_name_with_ns(node: str) -> str:
    return node.split("|")[-1]


def is_protected(node: str, config: Dict[str, Any]) -> bool:
    name = short_name(node)
    return name in set(config.get("protected_nodes", []))


def node_exists(name: str) -> bool:
    require_maya()
    return bool(cmds.objExists(name))


def make_unique(desired: str) -> str:
    require_maya()
    if not cmds.objExists(desired):
        return desired
    i = 1
    while cmds.objExists(f"{desired}{i:02d}"):
        i += 1
    return f"{desired}{i:02d}"


def rename_node(node: str, new_name: str) -> str:
    require_maya()
    return cmds.rename(node, new_name)


# --------------------------------------------------------------------------- #
# Undo
# --------------------------------------------------------------------------- #
@contextmanager
def undo_chunk(name: str = "namingTool"):
    """Group every Maya edit in the block into a single undo step."""
    require_maya()
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)
