"""High level renaming / checking operations.

Ties the :class:`NamingConvention` to Maya through :mod:`maya_utils`.
"""

from __future__ import annotations

import csv
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
        auto_detect_type: bool = False,
    ) -> List[RenameEntry]:
        """Rename the current Maya selection using ``values``.

        When several objects are selected a numeric index is added
        automatically (if enabled in the convention) to keep names unique.
        When ``auto_detect_type`` is set, the ``type`` token is inferred from
        each node's shape, overriding the value from the form.
        The whole batch is wrapped in a single undo step.
        """
        selection = maya_utils.get_selection(long_names=True)
        if not selection:
            raise RuntimeError("Aucun objet selectionne.")

        results: List[RenameEntry] = []
        count = len(selection)

        with maya_utils.undo_chunk("cgRenamer_rename"):
            for i, node in enumerate(selection):
                old = maya_utils.short_name(node)
                node_values = dict(values)
                if auto_detect_type:
                    detected = maya_utils.detect_type(node)
                    if detected:
                        node_values["type"] = detected
                idx = self._index_for(count, i)
                try:
                    desired = self.convention.build_name(node_values, index=idx)
                    target = maya_utils.make_unique(desired) if ensure_unique else desired
                    new = maya_utils.rename_node(node, target)
                    results.append(RenameEntry(old, maya_utils.short_name(new), "ok"))
                except Exception as exc:  # noqa: BLE001 - report per-node failures
                    results.append(RenameEntry(old, old, "error", str(exc)))
        return results

    def _index_for(self, count: int, i: int):
        """Return the batch index for position ``i`` (or None for a single obj)."""
        idx_opt = self.convention.options.get("add_index", {})
        if count > 1 and idx_opt.get("enabled"):
            return int(idx_opt.get("start", 1)) + i
        return None

    def autofix_selection(self, auto_detect_type: bool = True) -> List[RenameEntry]:
        """Rename every non-compliant selected node to its closest valid name."""
        selection = maya_utils.get_selection(long_names=True)
        if not selection:
            raise RuntimeError("Aucun objet selectionne.")

        results: List[RenameEntry] = []
        with maya_utils.undo_chunk("cgRenamer_autofix"):
            for node in selection:
                old = maya_utils.short_name(node)
                if self.convention.validate_name(old).is_valid:
                    results.append(RenameEntry(old, old, "skipped", "deja conforme"))
                    continue
                overrides = {}
                if auto_detect_type:
                    detected = maya_utils.detect_type(node)
                    if detected:
                        overrides["type"] = detected
                try:
                    desired = self.convention.suggest_fix(old, overrides=overrides)
                    target = maya_utils.make_unique(desired)
                    new = maya_utils.rename_node(node, target)
                    results.append(RenameEntry(old, maya_utils.short_name(new), "ok"))
                except Exception as exc:  # noqa: BLE001
                    results.append(RenameEntry(old, old, "error", str(exc)))
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

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #
    @staticmethod
    def export_report(entries: List[CheckEntry], path: str) -> str:
        """Write a conformity report as CSV. Returns the written path."""
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["name", "status", "errors", "node"])
            for e in entries:
                writer.writerow([
                    e.name,
                    "OK" if e.valid else "INVALID",
                    " | ".join(e.errors),
                    e.node,
                ])
        return path
