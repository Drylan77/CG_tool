"""High level renaming / checking operations.

Ties the :class:`NamingConvention` to Maya through :mod:`maya_utils`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .naming_convention import NamingConvention, ValidationResult
from . import maya_utils


@dataclass
class RenameEntry:
    old_name: str
    new_name: str
    status: str          # "ok" | "skipped" | "error"
    message: str = ""


@dataclass
class CheckEntry:
    node: str
    name: str
    valid: bool
    errors: List[str]
    warnings: List[str]


class Renamer:
    def __init__(self, convention: NamingConvention):
        self.convention = convention

    # ------------------------------------------------------------------ #
    # Renaming
    # ------------------------------------------------------------------ #
    def build_preview(self, values: Dict[str, str], count: int = 1) -> List[str]:
        """Build the name(s) that would be applied, without touching Maya."""
        names: List[str] = []
        use_index = count > 1 and self.convention.options.get("add_index", {}).get("enabled")
        start = int(self.convention.options.get("add_index", {}).get("start", 1)) if use_index else 1
        for i in range(count):
            idx = (start + i) if use_index else None
            names.append(self.convention.build_name(values, index=idx))
        return names

    def rename_selection(
        self,
        values: Dict[str, str],
        ensure_unique: bool = True,
    ) -> List[RenameEntry]:
        """Rename the current Maya selection using ``values``.

        When several objects are selected a numeric index is added
        automatically (if enabled in the convention) to keep names unique.
        """
        selection = maya_utils.get_selection(long_names=True)
        if not selection:
            raise RuntimeError("Aucun objet selectionne.")

        results: List[RenameEntry] = []
        count = len(selection)
        names = self.build_preview(values, count=count)

        # Rename from the leaf up is safer with long names; iterate as-is,
        # resolving each node freshly since paths change as we rename.
        for node, desired in zip(selection, names):
            old = maya_utils.short_name(node)
            try:
                target = maya_utils.make_unique(desired) if ensure_unique else desired
                new = maya_utils.rename_node(node, target)
                results.append(RenameEntry(old, maya_utils.short_name(new), "ok"))
            except Exception as exc:  # noqa: BLE001 - report per-node failures
                results.append(RenameEntry(old, desired, "error", str(exc)))
        return results

    # ------------------------------------------------------------------ #
    # Checking
    # ------------------------------------------------------------------ #
    def check_names(self, nodes: List[str]) -> List[CheckEntry]:
        entries: List[CheckEntry] = []
        for node in nodes:
            name = maya_utils.short_name(node)
            res: ValidationResult = self.convention.validate_name(name)
            entries.append(
                CheckEntry(node, name, res.is_valid, res.errors, res.warnings)
            )
        return entries

    def check_selection(self) -> List[CheckEntry]:
        selection = maya_utils.get_selection(long_names=True)
        if not selection:
            raise RuntimeError("Aucun objet selectionne.")
        return self.check_names(selection)

    def check_scene(self, node_type: str = "transform") -> List[CheckEntry]:
        nodes = maya_utils.scene_nodes(dag_only=True, node_type=node_type)
        # skip Maya default cameras / reserved nodes
        reserved = set(self.convention.rules.get("reserved_maya_names", []))
        nodes = [n for n in nodes if maya_utils.short_name(n) not in reserved]
        return self.check_names(nodes)
