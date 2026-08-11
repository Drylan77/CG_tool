"""Unit tests for the Maya-independent naming logic.

Run with:  python -m pytest tests/  (or  python tests/test_naming_convention.py)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cg_renamer.naming_convention import (  # noqa: E402
    NamingConvention,
    sanitize_part,
    is_maya_safe,
)

CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "naming_convention.json")


class TestBuildName(unittest.TestCase):
    def setUp(self):
        self.conv = NamingConvention.from_file(CONFIG)

    def test_full_name(self):
        name = self.conv.build_name({
            "name": "hand",
            "place": "L",
            "surface": "metal",
            "color": "grey",
            "type": "GEO",
        })
        self.assertEqual(name, "hand_L_metal_grey_GEO")

    def test_optional_tokens_skipped(self):
        name = self.conv.build_name({
            "name": "chair",
            "surface": "wood",
            "type": "GEO",
        })
        self.assertEqual(name, "chair_wood_GEO")

    def test_suffix_stays_last(self):
        name = self.conv.build_name({
            "name": "bolt",
            "place": "Top",
            "surface": "metal",
            "type": "GEO",
        })
        self.assertTrue(name.endswith("_GEO"))
        self.assertEqual(name, "bolt_Top_metal_GEO")

    def test_index_before_suffix(self):
        name = self.conv.build_name(
            {"name": "screw", "surface": "metal", "type": "GEO"}, index=3
        )
        self.assertEqual(name, "screw_metal_03_GEO")

    def test_missing_required_raises(self):
        with self.assertRaises(ValueError):
            self.conv.build_name({"name": "x", "type": "GEO"})  # surface missing

    def test_sanitizes_spaces_and_symbols(self):
        name = self.conv.build_name({
            "name": "engine block!",
            "surface": "metal",
            "type": "GEO",
        })
        self.assertEqual(name, "engineblock_metal_GEO")


class TestValidate(unittest.TestCase):
    def setUp(self):
        self.conv = NamingConvention.from_file(CONFIG)

    def test_valid_name(self):
        res = self.conv.validate_name("hand_L_metal_grey_GEO")
        self.assertTrue(res.is_valid, res.errors)

    def test_valid_minimal(self):
        res = self.conv.validate_name("chair_wood_GEO")
        self.assertTrue(res.is_valid, res.errors)

    def test_starts_with_digit(self):
        res = self.conv.validate_name("3hand_metal_GEO")
        self.assertFalse(res.is_valid)

    def test_invalid_chars(self):
        res = self.conv.validate_name("hand-metal GEO")
        self.assertFalse(res.is_valid)

    def test_unknown_surface_value(self):
        res = self.conv.validate_name("hand_L_kryptonite_grey_GEO")
        self.assertFalse(res.is_valid)
        self.assertTrue(any("kryptonite" in e for e in res.errors))

    def test_unknown_type_value(self):
        res = self.conv.validate_name("hand_metal_XYZ")
        self.assertFalse(res.is_valid)

    def test_too_short(self):
        res = self.conv.validate_name("hand")
        self.assertFalse(res.is_valid)

    def test_reserved_name(self):
        res = self.conv.validate_name("persp")
        self.assertFalse(res.is_valid)


class TestParse(unittest.TestCase):
    def setUp(self):
        self.conv = NamingConvention.from_file(CONFIG)

    def test_parse_full(self):
        parsed = self.conv.parse_name("hand_L_metal_grey_GEO")
        self.assertEqual(parsed["name"], "hand")
        self.assertEqual(parsed["type"], "GEO")

    def test_roundtrip(self):
        values = {"name": "door", "place": "R", "surface": "wood",
                  "color": "brown", "type": "GEO"}
        name = self.conv.build_name(values)
        res = self.conv.validate_name(name)
        self.assertTrue(res.is_valid, res.errors)


class TestSuggestFix(unittest.TestCase):
    def setUp(self):
        self.conv = NamingConvention.from_file(CONFIG)

    def _valid(self, name):
        return self.conv.validate_name(name).is_valid

    def test_fix_spaces_and_symbols(self):
        fixed = self.conv.suggest_fix("hand metal!")
        self.assertTrue(self._valid(fixed), fixed)

    def test_fix_missing_required_uses_defaults(self):
        fixed = self.conv.suggest_fix("hand")
        self.assertTrue(self._valid(fixed), fixed)
        # defaults: surface=metal, type=GEO
        self.assertTrue(fixed.endswith("_GEO"))
        self.assertIn("metal", fixed)

    def test_fix_keeps_recognized_tokens(self):
        fixed = self.conv.suggest_fix("hand_L_glass_red")  # missing type only
        self.assertTrue(self._valid(fixed), fixed)
        self.assertIn("glass", fixed)
        self.assertIn("red", fixed)

    def test_fix_leading_digit(self):
        fixed = self.conv.suggest_fix("3hand_metal_GEO")
        self.assertTrue(self._valid(fixed), fixed)

    def test_fix_with_type_override(self):
        fixed = self.conv.suggest_fix("hand_metal_GEO", overrides={"type": "CRV"})
        self.assertTrue(fixed.endswith("_CRV"), fixed)

    def test_already_valid_roundtrips(self):
        fixed = self.conv.suggest_fix("hand_L_metal_grey_GEO")
        self.assertEqual(fixed, "hand_L_metal_grey_GEO")


class TestHelpers(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(sanitize_part("  hello world! "), "helloworld")

    def test_maya_safe(self):
        self.assertTrue(is_maya_safe("hand_metal_GEO"))
        self.assertFalse(is_maya_safe("3hand"))
        self.assertFalse(is_maya_safe("hand-metal"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
