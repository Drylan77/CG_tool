"""Naming sanity checks (validator) with a headless API.

Each check returns a :class:`CheckResult`. ``run_all`` aggregates them into a
plain dict so a publish script can gate on it without any UI::

    from namingTool.core import checks
    report = checks.run_all(scope="scene")
    if any(r["status"] == "error" for r in report.values()):
        raise RuntimeError("Naming errors, publish blocked.")
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import maya_utils, naming
from .config import load_config, valid_suffixes

log = logging.getLogger(__name__)

PASS, WARNING, ERROR = "pass", "warning", "error"


@dataclass
class CheckResult:
    name: str
    label: str
    status: str = PASS
    nodes: List[str] = field(default_factory=list)
    message: str = ""
    fixable: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "nodes": self.nodes,
            "message": self.message,
            "fixable": self.fixable,
        }


# --------------------------------------------------------------------------- #
# Individual checks. Each takes (nodes, config) and returns a CheckResult.
# --------------------------------------------------------------------------- #
def check_default_names(nodes, config) -> CheckResult:
    patterns = config.get("default_name_patterns", [])
    rx = re.compile(r"^(?:%s)\d*$" % "|".join(re.escape(p) for p in patterns)) if patterns else None
    bad = [n for n in nodes if rx and rx.match(maya_utils.short_name(n))]
    return CheckResult(
        "default_names", "Noms par defaut Maya",
        ERROR if bad else PASS, bad,
        f"{len(bad)} noeud(s) au nom par defaut." if bad else "Aucun nom par defaut.",
        fixable=True,
    )


def check_duplicate_names(nodes, config) -> CheckResult:
    counts = Counter(maya_utils.short_name(n) for n in nodes)
    dupes = {name for name, c in counts.items() if c > 1}
    bad = [n for n in nodes if maya_utils.short_name(n) in dupes]
    return CheckResult(
        "duplicate_names", "Duplicate short names",
        ERROR if bad else PASS, bad,
        f"{len(dupes)} nom(s) en double." if bad else "Aucun doublon.",
        fixable=True,
    )


def check_suffix_valid(nodes, config) -> CheckResult:
    codes = set(valid_suffixes(config))
    sep = config.get("separator", "_")
    bad = []
    for n in nodes:
        tokens = maya_utils.short_name(n).split(sep)
        if len(tokens) < 2 or tokens[-1] not in codes:
            bad.append(n)
    return CheckResult(
        "suffix_valid", "Suffixe present et valide",
        ERROR if bad else PASS, bad,
        f"{len(bad)} noeud(s) sans suffixe valide." if bad else "Suffixes OK.",
        fixable=True,
    )


def check_suffix_matches_type(nodes, config) -> CheckResult:
    codes = set(valid_suffixes(config))
    sep = config.get("separator", "_")
    bad = []
    for n in nodes:
        expected = maya_utils.expected_suffix(n, config)
        if not expected:
            continue
        current = maya_utils.short_name(n).split(sep)[-1]
        if current in codes and current != expected:
            bad.append(n)
    return CheckResult(
        "suffix_type", "Suffixe coherent avec le type de noeud",
        ERROR if bad else PASS, bad,
        f"{len(bad)} suffixe(s) incoherent(s) avec le type reel." if bad else "Coherence OK.",
        fixable=True,
    )


def check_illegal_and_case(nodes, config) -> CheckResult:
    bad, warn = [], []
    for n in nodes:
        res = naming.validate_name(maya_utils.short_name(n), config)
        if res.errors:
            bad.append(n)
        elif res.warnings:
            warn.append(n)
    status = ERROR if bad else (WARNING if warn else PASS)
    return CheckResult(
        "illegal_case", "Caracteres / casse / convention",
        status, bad or warn,
        f"{len(bad)} nom(s) non conformes." if bad else
        (f"{len(warn)} avertissement(s)." if warn else "Conventions OK."),
        fixable=True,
    )


def check_shape_names(nodes, config) -> CheckResult:
    """A transform's shape must be named <transform>Shape."""
    bad = []
    for n in nodes:
        shapes = maya_utils.shapes_of(n)
        base = maya_utils.short_name(n)
        for shp in shapes:
            if maya_utils.short_name(shp) != base + "Shape":
                bad.append(n)
                break
    return CheckResult(
        "shape_names", "Shapes synchronisees avec le transform",
        ERROR if bad else PASS, bad,
        f"{len(bad)} shape(s) desynchronisee(s)." if bad else "Shapes OK.",
        fixable=True,
    )


def check_namespaces(nodes, config) -> CheckResult:
    bad = [n for n in nodes if maya_utils.has_namespace(n)]
    return CheckResult(
        "namespaces", "Absence de namespaces",
        ERROR if bad else PASS, bad,
        f"{len(bad)} noeud(s) avec namespace." if bad else "Aucun namespace.",
        fixable=True,
    )


def check_hierarchy(nodes, config) -> CheckResult:
    """World-level orphan geometry and empty groups."""
    maya_utils.require_maya()
    import maya.cmds as cmds  # type: ignore

    codes_geo = {config.get("suffixes", {}).get("geometry", "GEO")}
    sep = config.get("separator", "_")
    issues = []
    for n in nodes:
        parent = cmds.listRelatives(n, parent=True, fullPath=True)
        short = maya_utils.short_name(n)
        # orphan geo at world level
        if parent is None and short.split(sep)[-1] in codes_geo:
            issues.append(n)
        # empty group (transform, no shape, no children)
        if maya_utils.real_node_type(n) == "group":
            children = cmds.listRelatives(n, children=True) or []
            if not children:
                issues.append(n)
    issues = list(dict.fromkeys(issues))
    return CheckResult(
        "hierarchy", "Hierarchie (orphelins / groupes vides)",
        WARNING if issues else PASS, issues,
        f"{len(issues)} probleme(s) de hierarchie." if issues else "Hierarchie OK.",
        fixable=False,
    )


def check_numbering(nodes, config) -> CheckResult:
    """Detect mixed padding among siblings sharing a base descriptor."""
    sep = config.get("separator", "_")
    groups: Dict[str, List[int]] = defaultdict(list)
    node_by_key: Dict[str, List[str]] = defaultdict(list)
    rx = re.compile(r"^(.*?)(\d+)(_[A-Z]+)?$")
    for n in nodes:
        short = maya_utils.short_name(n)
        m = rx.match(short)
        if m and m.group(2):
            base = m.group(1) + (m.group(3) or "")
            groups[base].append(len(m.group(2)))
            node_by_key[base].append(n)
    bad = []
    for base, pads in groups.items():
        if len(set(pads)) > 1:            # mixed padding within one series
            bad.extend(node_by_key[base])
    return CheckResult(
        "numbering", "Numerotation coherente (padding)",
        WARNING if bad else PASS, bad,
        f"{len(bad)} noeud(s) a padding incoherent." if bad else "Numerotation OK.",
        fixable=True,
    )


def check_transforms_frozen(nodes, config) -> CheckResult:
    """Bonus: GEO transforms should be frozen (T=0, R=0, S=1)."""
    maya_utils.require_maya()
    import maya.cmds as cmds  # type: ignore

    geo = config.get("suffixes", {}).get("geometry", "GEO")
    sep = config.get("separator", "_")
    bad = []
    for n in nodes:
        if maya_utils.short_name(n).split(sep)[-1] != geo:
            continue
        t = cmds.getAttr(n + ".translate")[0]
        r = cmds.getAttr(n + ".rotate")[0]
        s = cmds.getAttr(n + ".scale")[0]
        if any(abs(v) > 1e-4 for v in t + r) or any(abs(v - 1) > 1e-4 for v in s):
            bad.append(n)
    return CheckResult(
        "frozen", "Transforms GEO freezes (bonus)",
        WARNING if bad else PASS, bad,
        f"{len(bad)} transform(s) non freeze(s)." if bad else "Transforms OK.",
        fixable=True,
    )


ALL_CHECKS: List[Callable] = [
    check_default_names,
    check_duplicate_names,
    check_suffix_valid,
    check_suffix_matches_type,
    check_illegal_and_case,
    check_shape_names,
    check_namespaces,
    check_hierarchy,
    check_numbering,
    check_transforms_frozen,
]


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def _gather(scope: str, root: Optional[str], config: Dict[str, Any]) -> List[str]:
    nodes = maya_utils.list_nodes(scope=scope, root=root, node_type="transform")
    protected = set(config.get("protected_nodes", []))
    return [n for n in nodes if maya_utils.short_name(n) not in protected]


def run_all(scope: str = "scene", root: Optional[str] = None,
            config: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """Run every check and return ``{check_name: {status, nodes, ...}}``."""
    config = config or load_config()
    nodes = _gather(scope, root, config)
    report: Dict[str, Dict[str, Any]] = {}
    for func in ALL_CHECKS:
        try:
            res = func(nodes, config)
        except Exception as exc:  # noqa: BLE001 - one broken check must not kill the run
            log.exception("check %s failed", func.__name__)
            res = CheckResult(func.__name__, func.__name__, ERROR, [], f"Check erreur: {exc}")
        report[res.name] = {**res.as_dict(), "label": res.label}
    return report


def summarize(report: Dict[str, Dict[str, Any]]) -> str:
    total = len(report)
    p = sum(1 for r in report.values() if r["status"] == PASS)
    w = sum(1 for r in report.values() if r["status"] == WARNING)
    e = sum(1 for r in report.values() if r["status"] == ERROR)
    return f"{total} checks - {p} pass, {w} warnings, {e} errors"


# --------------------------------------------------------------------------- #
# Fixes
# --------------------------------------------------------------------------- #
def _fix_shape_names(nodes, config):
    import maya.cmds as cmds  # type: ignore
    fixed = 0
    for n in nodes:
        base = maya_utils.short_name(n)
        for shp in maya_utils.shapes_of(n):
            want = base + "Shape"
            if maya_utils.short_name(shp) != want:
                cmds.rename(shp, maya_utils.make_unique(want))
                fixed += 1
    return fixed


def _fix_make_unique(nodes, config):
    fixed = 0
    for n in sorted(nodes, key=lambda x: x.count("|"), reverse=True):
        short = maya_utils.short_name(n)
        unique = maya_utils.make_unique(short)
        if unique != short:
            maya_utils.rename_node(n, unique)
            fixed += 1
    return fixed


def _fix_renumber(nodes, config):
    """Re-apply consistent padding to numbered siblings."""
    import maya.cmds as cmds  # type: ignore
    pad = int(config.get("padding", 2))
    rx = re.compile(r"^(.*?)(\d+)(_[A-Z]+)?$")
    fixed = 0
    for n in sorted(nodes, key=lambda x: x.count("|"), reverse=True):
        short = maya_utils.short_name(n)
        m = rx.match(short)
        if not m:
            continue
        new = f"{m.group(1)}{int(m.group(2)):0{pad}d}{m.group(3) or ''}"
        if new != short:
            maya_utils.rename_node(n, maya_utils.make_unique(new))
            fixed += 1
    return fixed


def _fix_freeze(nodes, config):
    import maya.cmds as cmds  # type: ignore
    fixed = 0
    for n in nodes:
        try:
            cmds.makeIdentity(n, apply=True, translate=True, rotate=True, scale=True, normal=0)
            fixed += 1
        except Exception:  # noqa: BLE001
            pass
    return fixed


def fix_check(check_name: str, nodes: List[str],
              config: Optional[Dict[str, Any]] = None) -> int:
    """Apply the auto-fix for ``check_name`` to ``nodes``. Returns count fixed.

    The whole fix is a single undo step.
    """
    config = config or load_config()
    from . import renamer

    with maya_utils.undo_chunk(f"namingTool_fix_{check_name}"):
        if check_name in ("suffix_valid", "suffix_type", "default_names"):
            entries = renamer.auto_suffix(config, nodes=nodes)
            if check_name == "default_names":
                renamer.cleanup(config, nodes=nodes)
            return sum(1 for e in entries if e.status == "ok")
        if check_name == "illegal_case":
            entries = renamer.cleanup(config, nodes=nodes)
            return sum(1 for e in entries if e.status == "ok")
        if check_name == "namespaces":
            entries = renamer.cleanup(config, nodes=nodes, remove_namespaces=True)
            return sum(1 for e in entries if e.status == "ok")
        if check_name == "shape_names":
            return _fix_shape_names(nodes, config)
        if check_name == "duplicate_names":
            return _fix_make_unique(nodes, config)
        if check_name == "numbering":
            return _fix_renumber(nodes, config)
        if check_name == "frozen":
            return _fix_freeze(nodes, config)
    return 0
