"""Central naming logic: build / parse / validate a node name from config.

A single regex is derived from the configuration and used everywhere (renamer
and validator alike) so the parsing logic is never duplicated. This module is
Maya-independent and unit-testable with plain CPython.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Maya identifier: letters, digits, underscore; must not start with a digit.
_ILLEGAL_CHARS_RE = re.compile(r"[^A-Za-z0-9_]")


@dataclass
class NameParts:
    side: str = ""
    descriptor: str = ""
    increment: str = ""
    lod: str = ""
    suffix: str = ""

    def is_empty(self) -> bool:
        return not (self.descriptor or self.suffix)


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    message: str


@dataclass
class ValidationResult:
    name: str
    is_valid: bool
    issues: List[Issue] = field(default_factory=list)
    parts: Optional[NameParts] = None

    @property
    def errors(self) -> List[str]:
        return [i.message for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[str]:
        return [i.message for i in self.issues if i.severity == "warning"]


# --------------------------------------------------------------------------- #
# Regex construction (derived from config)
# --------------------------------------------------------------------------- #
def _side_pattern(config: Dict[str, Any]) -> str:
    sides = sorted(set(config.get("sides", {}).values()), key=len, reverse=True)
    if not sides:
        return ""
    return "(?:(" + "|".join(re.escape(s) for s in sides) + ")_)?"


def _suffix_pattern(config: Dict[str, Any]) -> str:
    from .config import valid_suffixes

    codes = valid_suffixes(config)
    return "(" + "|".join(re.escape(c) for c in codes) + ")"


def _increment_pattern(config: Dict[str, Any]) -> str:
    pad = int(config.get("padding", 2))
    return r"(\d{%d,%d})?" % (pad, pad + 1)


def _lod_pattern(config: Dict[str, Any]) -> str:
    lod = config.get("lod_token", {})
    if not lod.get("enabled"):
        return ""
    # pattern "lod{n}" -> lod\d+
    token = re.escape(lod.get("pattern", "lod{n}")).replace(r"\{n\}", r"\d+")
    return r"(?:_(%s))?" % token


def build_regex(config: Dict[str, Any]) -> re.Pattern:
    """Assemble the single authoritative name regex from the config."""
    sep = re.escape(config.get("separator", "_"))
    side = _side_pattern(config)
    descriptor = r"([a-z][a-zA-Z0-9]*?)"
    lod = _lod_pattern(config)
    increment = _increment_pattern(config)
    suffix = _suffix_pattern(config)
    pattern = f"^{side}{descriptor}{lod}{increment}{sep}{suffix}$"
    return re.compile(pattern)


# --------------------------------------------------------------------------- #
# Parse / build
# --------------------------------------------------------------------------- #
def parse_name(name: str, config: Dict[str, Any]) -> Optional[NameParts]:
    """Parse a fully compliant name into its parts, or ``None`` if invalid."""
    match = build_regex(config).match(name or "")
    if not match:
        return None
    side, descriptor, lod, increment, suffix = _unpack(match, config)
    return NameParts(
        side=side or "",
        descriptor=descriptor or "",
        increment=increment or "",
        lod=lod or "",
        suffix=suffix or "",
    )


def _unpack(match: re.Match, config: Dict[str, Any]) -> Tuple:
    """Return (side, descriptor, lod, increment, suffix) from a match, coping
    with the lod group being absent when disabled."""
    groups = list(match.groups())
    has_side = bool(config.get("sides"))
    has_lod = bool(config.get("lod_token", {}).get("enabled"))

    side = groups.pop(0) if has_side else None
    descriptor = groups.pop(0)
    lod = groups.pop(0) if has_lod else None
    increment = groups.pop(0)
    suffix = groups.pop(0)
    return side, descriptor, lod, increment, suffix


def build_name(
    descriptor: str,
    suffix: str,
    config: Dict[str, Any],
    side: str = "",
    increment: Optional[int] = None,
    lod: Optional[int] = None,
) -> str:
    """Build a compliant name from its parts (sanitising the descriptor)."""
    sep = config.get("separator", "_")
    parts: List[str] = []

    descriptor = to_camel_case(descriptor)
    if not descriptor:
        raise ValueError("Descriptor requis (camelCase).")
    if not suffix:
        raise ValueError("Suffixe requis.")

    if side:
        parts.append(side)

    core = descriptor
    if lod is not None and config.get("lod_token", {}).get("enabled"):
        pattern = config["lod_token"].get("pattern", "lod{n}")
        core += sep + pattern.replace("{n}", str(lod))
    if increment is not None:
        pad = int(config.get("padding", 2))
        core += str(increment).zfill(pad)
    parts.append(core)

    parts.append(suffix)
    return sep.join(parts)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def is_valid(name: str, config: Dict[str, Any]) -> bool:
    return build_regex(config).match(name or "") is not None


def validate_name(name: str, config: Dict[str, Any]) -> ValidationResult:
    """Validate a name and return granular, human-readable issues."""
    issues: List[Issue] = []
    sep = config.get("separator", "_")

    if not name:
        return ValidationResult(name, False, [Issue("error", "Nom vide.")])

    # Forbidden words are a warning regardless of structural validity.
    lowered = name.lower()
    forbidden = [
        Issue("warning", f"Mot interdit '{word}' dans le nom.")
        for word in config.get("forbidden_words", [])
        if word.lower() in lowered
    ]

    # Fast path: structurally compliant.
    parts = parse_name(name, config)
    if parts is not None:
        return ValidationResult(name, True, forbidden, parts)

    # Otherwise diagnose precisely.
    issues.extend(forbidden)
    illegal = sorted(set(_ILLEGAL_CHARS_RE.findall(name)))
    if illegal:
        shown = ", ".join(repr(c) for c in illegal)
        issues.append(Issue("error", f"Caracteres illegaux: {shown}."))
    if name[0].isdigit():
        issues.append(Issue("error", "Ne peut pas commencer par un chiffre."))
    if "__" in name:
        issues.append(Issue("error", "Double underscore interdit."))
    if name.endswith(sep):
        issues.append(Issue("error", "Underscore final interdit."))

    tokens = [t for t in name.split(sep) if t != ""]
    from .config import valid_suffixes

    codes = valid_suffixes(config)
    if len(tokens) < 2:
        issues.append(Issue("error", "Suffixe manquant (ex: _GEO)."))
    else:
        suffix = tokens[-1]
        if suffix not in codes:
            issues.append(
                Issue("error", f"Suffixe '{suffix}' invalide. Attendu: {', '.join(codes)}.")
            )

    # descriptor casing (first non-side token)
    sides = set(config.get("sides", {}).values())
    body_tokens = tokens[:-1] if len(tokens) >= 2 else tokens
    if body_tokens and body_tokens[0] in sides:
        body_tokens = body_tokens[1:]
    if body_tokens:
        descriptor = body_tokens[0]
        if descriptor and not re.match(r"^[a-z][a-zA-Z0-9]*$", descriptor):
            issues.append(
                Issue("error", f"Descriptor '{descriptor}' doit etre en camelCase (minuscule initiale).")
            )

    if not any(i.severity == "error" for i in issues):
        # Structurally odd but no specific rule caught it.
        issues.append(Issue("error", "Nom non conforme a la convention."))

    return ValidationResult(name, False, issues, parts)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def to_camel_case(value: str) -> str:
    """Convert an arbitrary string to a Maya-safe camelCase token.

    Spaces / dashes / illegal chars become word boundaries; the first word is
    lower-cased, following words are capitalised. Leading digits are stripped.
    """
    if not value:
        return ""
    words = re.split(r"[^A-Za-z0-9]+", value.strip())
    words = [w for w in words if w]
    if not words:
        return ""
    out = words[0][:1].lower() + words[0][1:]
    for w in words[1:]:
        out += w[:1].upper() + w[1:]
    out = out.lstrip("0123456789")
    return out


def strip_illegal(value: str) -> str:
    return _ILLEGAL_CHARS_RE.sub("", value)


def strip_namespace(name: str) -> str:
    """Return the leaf name without namespace(s) and without DAG path."""
    return name.split("|")[-1].split(":")[-1]


def has_illegal_chars(name: str) -> bool:
    return bool(_ILLEGAL_CHARS_RE.search(strip_namespace(name)))
