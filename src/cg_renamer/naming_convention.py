"""Core naming convention logic for the CG asset renaming tool.

This module is intentionally **independent from Maya** so that it can be unit
tested outside of a Maya session and reused in other DCCs / pipeline scripts.

It knows how to:
    * load a naming convention from a JSON config file,
    * build a compliant name from a set of token values,
    * parse an existing name back into its tokens,
    * validate a name against the convention and report precise errors.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


DEFAULT_CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "naming_convention.json")
)

# Maya identifiers: letters, digits, underscore; must not start with a digit.
_MAYA_SAFE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INVALID_CHARS_RE = re.compile(r"[^A-Za-z0-9_]")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Token:
    """A single element of the naming convention (e.g. name, surface, type)."""

    key: str
    label: str
    type: str = "text"           # "text" | "choice" | "int"
    required: bool = False
    default: str = ""
    values: List[Dict[str, str]] = field(default_factory=list)
    hint: str = ""
    position: str = "body"       # "body" | "prefix" | "suffix"
    case: str = ""               # informational: camelCase, lower, upper...

    @property
    def allowed_values(self) -> List[str]:
        """Return the list of accepted raw values for a choice token."""
        return [v["value"] for v in self.values]

    def is_valid_value(self, value: str) -> bool:
        if self.type == "choice":
            if value == "" and not self.required:
                return True
            return value in self.allowed_values
        if self.required and value == "":
            return False
        return True


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    message: str


@dataclass
class ValidationResult:
    original: str
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    parsed: Optional[Dict[str, str]] = None

    @property
    def errors(self) -> List[str]:
        return [i.message for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[str]:
        return [i.message for i in self.issues if i.severity == "warning"]


# --------------------------------------------------------------------------- #
# Convention
# --------------------------------------------------------------------------- #
class NamingConvention:
    """Loads a convention from JSON and provides build / parse / validate."""

    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("convention_name", "Naming Convention")
        self.version = config.get("version", "0.0.0")
        self.separator = config.get("separator", "_")
        self.rules = config.get("rules", {})
        self.options = config.get("options", {})
        self.tokens: List[Token] = [Token(**self._clean_token(t)) for t in config.get("tokens", [])]

    # -- construction -------------------------------------------------------- #
    @staticmethod
    def _clean_token(raw: dict) -> dict:
        allowed = {f for f in Token.__dataclass_fields__}  # noqa: SLF001
        return {k: v for k, v in raw.items() if k in allowed}

    @classmethod
    def from_file(cls, path: str = DEFAULT_CONFIG_PATH) -> "NamingConvention":
        with open(path, "r", encoding="utf-8") as fh:
            return cls(json.load(fh))

    def get_token(self, key: str) -> Optional[Token]:
        for tok in self.tokens:
            if tok.key == key:
                return tok
        return None

    # -- ordering ------------------------------------------------------------ #
    def _ordered_tokens(self) -> List[Token]:
        """Return tokens ordered prefix -> body -> suffix (stable otherwise)."""
        order = {"prefix": 0, "body": 1, "suffix": 2}
        return sorted(self.tokens, key=lambda t: order.get(t.position, 1))

    # -- build --------------------------------------------------------------- #
    def build_name(self, values: Dict[str, str], index: Optional[int] = None) -> str:
        """Build a compliant name from token values.

        ``values`` maps token keys to raw values. Empty optional tokens are
        skipped. ``index`` optionally injects a numeric batch counter.

        A missing key is treated as an empty value (defaults belong to the UI
        initialisation, not to name construction) so that a genuinely missing
        required token raises instead of being silently filled.
        """
        parts: List[str] = []
        for tok in self._ordered_tokens():
            raw = str(values.get(tok.key, "") or "").strip()
            if tok.type != "int":
                raw = sanitize_part(raw)
            if raw == "":
                if tok.required:
                    raise ValueError(f"Token requis manquant: '{tok.label}' ({tok.key})")
                continue

            # Inject the batch index just before the suffix token.
            if (
                index is not None
                and tok.position == "suffix"
                and self.options.get("add_index", {}).get("enabled")
            ):
                idx_opt = self.options["add_index"]
                pad = int(idx_opt.get("padding", 2))
                parts.append(str(index).zfill(pad))

            parts.append(raw)

        name = self.separator.join(p for p in parts if p)
        return name

    # -- parse --------------------------------------------------------------- #
    def _analyze(self, name: str) -> Tuple[Dict[str, str], List[str]]:
        """Vocabulary-aware parse.

        Because every *choice* token has a controlled, disjoint vocabulary, we
        can identify each slot by the value it carries instead of relying on a
        fixed position. This makes optional tokens (``place``, ``color``) safe
        to omit. Returns ``(parsed, unrecognized_parts)``.
        """
        parsed: Dict[str, str] = {}
        ordered = self._ordered_tokens()
        suffix_toks = [t for t in ordered if t.position == "suffix"]
        middle_toks = [t for t in ordered if t.position != "suffix"]
        text_toks = [t for t in middle_toks if t.type != "choice"]

        work = [p for p in name.split(self.separator) if p != ""]

        # 1. suffix tokens are anchored to the end
        for tok in reversed(suffix_toks):
            parsed[tok.key] = work.pop() if work else ""

        # 2. an optional numeric batch index sits just before the suffix
        if (
            self.options.get("add_index", {}).get("enabled")
            and work
            and work[-1].isdigit()
        ):
            work.pop()

        # 3. choice tokens matched by vocabulary, from the right
        for tok in reversed(middle_toks):
            if tok.type != "choice":
                continue
            if work and work[-1] in tok.allowed_values:
                parsed[tok.key] = work.pop()
            else:
                parsed[tok.key] = ""

        # 4. leftover leading parts feed the free-text token(s); the primary
        #    text token (name) takes exactly one part, extras are unrecognized
        for tok in text_toks:
            parsed[tok.key] = work.pop(0) if work else ""

        return parsed, work  # anything still in ``work`` is unrecognized

    def parse_name(self, name: str) -> Dict[str, str]:
        """Best-effort parse of a name back into its tokens."""
        parsed, _ = self._analyze(name)
        return parsed

    # -- auto-fix ------------------------------------------------------------ #
    def suggest_fix(self, name: str, overrides: Optional[Dict[str, str]] = None) -> str:
        """Return the closest compliant name for a (possibly invalid) name.

        Recognised tokens are kept, unrecognised leading parts are folded back
        into ``name``, missing required tokens fall back to their default, and
        everything is sanitised. ``overrides`` (e.g. an auto-detected type)
        takes precedence over the parsed values.
        """
        parsed, unrecognized = self._analyze(name)
        values = dict(parsed)

        # Any choice value that is not in its vocabulary is not a real token
        # value: reclaim it (e.g. a missing type suffix pushes the color into
        # the type slot).
        reclaimed: List[str] = list(unrecognized)
        for tok in self.tokens:
            if tok.type == "choice":
                val = values.get(tok.key, "")
                if val and not tok.is_valid_value(val):
                    reclaimed.append(val)
                    values[tok.key] = ""

        # A reclaimed value that matches an empty choice token's vocabulary is
        # re-homed there rather than dumped into the name.
        leftover: List[str] = []
        for val in reclaimed:
            for tok in self.tokens:
                if (
                    tok.type == "choice"
                    and not values.get(tok.key)
                    and val
                    and val in tok.allowed_values
                ):
                    values[tok.key] = val
                    break
            else:
                leftover.append(val)
        reclaimed = leftover

        # Rebuild a clean name token from the parsed name + reclaimed bits.
        text_key = next((t.key for t in self.tokens if t.type != "choice"), None)
        if text_key is not None:
            chunks = [values[text_key]] if values.get(text_key) else []
            chunks.extend(reclaimed)
            merged = sanitize_part("".join(c.capitalize() if i else c
                                            for i, c in enumerate(chunks)))
            merged = merged.lstrip("0123456789")  # cannot start with a digit
            values[text_key] = merged

        if overrides:
            values.update({k: v for k, v in overrides.items() if v})

        # Fill any still-missing required token with its default.
        for tok in self.tokens:
            if tok.required and not values.get(tok.key):
                values[tok.key] = tok.default

        # A required text token with no material to work from gets a safe stub.
        for tok in self.tokens:
            if tok.required and tok.type != "choice" and not values.get(tok.key):
                values[tok.key] = "asset"

        return self.build_name(values)

    # -- validate ------------------------------------------------------------ #
    def validate_name(self, name: str) -> ValidationResult:
        issues: List[ValidationIssue] = []

        if not name:
            issues.append(ValidationIssue("error", "Nom vide."))
            return ValidationResult(name, False, issues)

        # 1. Maya-safe characters
        if self.rules.get("allow_only_alphanumeric", True):
            bad = sorted(set(_INVALID_CHARS_RE.findall(name.replace(self.separator, ""))))
            if bad:
                issues.append(
                    ValidationIssue("error", f"Caracteres non autorises: {', '.join(bad)}")
                )
        if self.rules.get("cannot_start_with_digit", True) and name[:1].isdigit():
            issues.append(ValidationIssue("error", "Le nom ne peut pas commencer par un chiffre."))
        if not _MAYA_SAFE_RE.match(name):
            issues.append(
                ValidationIssue("error", "Nom non valide pour Maya (caracteres ou 1er char).")
            )

        max_len = int(self.rules.get("max_length", 0) or 0)
        if max_len and len(name) > max_len:
            issues.append(
                ValidationIssue("error", f"Nom trop long ({len(name)} > {max_len}).")
            )

        if name in self.rules.get("reserved_maya_names", []):
            issues.append(ValidationIssue("error", f"'{name}' est un nom reserve Maya."))

        # 2. Token structure (vocabulary-aware)
        parsed, unrecognized = self._analyze(name)

        for tok in self.tokens:
            val = parsed.get(tok.key, "")
            if tok.required and val == "":
                issues.append(ValidationIssue("error", f"Element requis manquant: {tok.label}."))
            elif tok.type == "choice" and val and not tok.is_valid_value(val):
                allowed = ", ".join(v for v in tok.allowed_values if v)
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Valeur '{val}' invalide pour {tok.label}. Attendu: {allowed}.",
                    )
                )

        if unrecognized:
            issues.append(
                ValidationIssue(
                    "error",
                    f"Valeur(s) non reconnue(s): {', '.join(unrecognized)}.",
                )
            )

        is_valid = not any(i.severity == "error" for i in issues)
        return ValidationResult(name, is_valid, issues, parsed)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def sanitize_part(value: str) -> str:
    """Make a single token part Maya-safe (no separators, no invalid chars)."""
    value = value.strip()
    # spaces / dashes -> nothing (keep camelCase intent), then strip invalid
    value = re.sub(r"[\s\-]+", "", value)
    value = _INVALID_CHARS_RE.sub("", value)
    return value


def is_maya_safe(name: str) -> bool:
    return bool(_MAYA_SAFE_RE.match(name))
