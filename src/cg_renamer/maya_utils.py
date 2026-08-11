"""Maya-specific helpers used by the renaming tool.

Everything that touches ``maya.cmds`` lives here, so the rest of the package
stays importable and testable outside of Maya.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

try:
    import maya.cmds as cmds  # type: ignore
    IN_MAYA = True
except ImportError:  # pragma: no cover - allows import outside Maya
    cmds = None
    IN_MAYA = False


# Maya shape node type  ->  convention "type" token value.
SHAPE_TYPE_MAP = {
    "mesh": "GEO",
    "nurbsSurface": "GEO",
    "subdiv": "GEO",
    "nurbsCurve": "CRV",
    "bezierCurve": "CRV",
    "locator": "LOC",
    "joint": "JNT",
    "camera": "CAM",
    "pointLight": "LGT",
    "directionalLight": "LGT",
    "spotLight": "LGT",
    "areaLight": "LGT",
    "aiAreaLight": "LGT",
    "aiSkyDomeLight": "LGT",
    "nParticle": "FX",
    "particle": "FX",
    "fluidShape": "FX",
    "nCloth": "FX",
}


def _require_maya() -> None:
    if not IN_MAYA:
        raise RuntimeError("Cette fonction doit etre executee dans Maya (maya.cmds indisponible).")


def get_selection(long_names: bool = True) -> List[str]:
    """Return the current selection (transform nodes)."""
    _require_maya()
    sel = cmds.ls(selection=True, long=long_names) or []
    return sel


def short_name(node: str) -> str:
    """Return the short (leaf) name of a DAG path."""
    return node.split("|")[-1].split(":")[-1]


def rename_node(node: str, new_name: str) -> str:
    """Rename a single node, returning the resulting name.

    Maya guarantees uniqueness by appending a numeric suffix when needed;
    the actual resulting name is returned so the caller can report it.
    """
    _require_maya()
    return cmds.rename(node, new_name)


def name_exists(name: str) -> bool:
    _require_maya()
    return bool(cmds.objExists(name))


def scene_nodes(dag_only: bool = True, node_type: str = "transform") -> List[str]:
    """Return nodes in the scene for a full-scene name check."""
    _require_maya()
    kwargs = {"long": True}
    if dag_only:
        kwargs["dag"] = True
    if node_type:
        kwargs["type"] = node_type
    return cmds.ls(**kwargs) or []


def make_unique(desired: str) -> str:
    """Return a scene-unique variant of ``desired`` (append _01, _02 ...)."""
    _require_maya()
    if not cmds.objExists(desired):
        return desired
    i = 1
    while cmds.objExists(f"{desired}_{i:02d}"):
        i += 1
    return f"{desired}_{i:02d}"


def detect_type(node: str) -> Optional[str]:
    """Infer the convention ``type`` value from a node's shape.

    A transform with no shape is treated as a group (``GRP``). Returns ``None``
    when the type cannot be determined so the caller can keep the user's choice.
    """
    _require_maya()
    node_type = cmds.nodeType(node)
    if node_type in SHAPE_TYPE_MAP:
        return SHAPE_TYPE_MAP[node_type]

    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    if not shapes:
        # a transform with children but no shape is a group
        children = cmds.listRelatives(node, children=True) or []
        return "GRP" if children else None

    shape_type = cmds.nodeType(shapes[0])
    return SHAPE_TYPE_MAP.get(shape_type)


@contextmanager
def undo_chunk(name: str = "cgRenamer"):
    """Group every Maya edit inside the block into a single undo step."""
    _require_maya()
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)
