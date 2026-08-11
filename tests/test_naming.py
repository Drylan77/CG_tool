"""Unit tests for the Maya-independent naming core (parse / build / validate).

Run:  python -m unittest discover tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from namingTool.core import config as config_mod  # noqa: E402
from namingTool.core import naming  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.cfg = config_mod.load_config(use_cache=False)


class TestParse(Base):
    def test_valid_names(self):
        cases = {
            "L_doorHandle_GEO": ("L", "doorHandle", "", "GEO"),
            "wheelFront01_GEO": ("", "wheelFront", "01", "GEO"),
            "C_body_GEO": ("C", "body", "", "GEO"),
            "chassis_GRP": ("", "chassis", "", "GRP"),
            "tableLeg03_GEO": ("", "tableLeg", "03", "GEO"),
        }
        for name, (side, desc, inc, suf) in cases.items():
            p = naming.parse_name(name, self.cfg)
            self.assertIsNotNone(p, name)
            self.assertEqual((p.side, p.descriptor, p.increment, p.suffix),
                             (side, desc, inc, suf), name)

    def test_invalid_names_parse_none(self):
        for name in ["pCube1", "Door Handle_geo", "1stFloor_GEO",
                     "handle_GEO1", "porte_poignee_geo"]:
            self.assertIsNone(naming.parse_name(name, self.cfg), name)


class TestValidate(Base):
    def test_illegal_char(self):
        r = naming.validate_name("Door Handle_geo", self.cfg)
        self.assertFalse(r.is_valid)
        self.assertTrue(any("illega" in e.lower() for e in r.errors))

    def test_leading_digit(self):
        r = naming.validate_name("1stFloor_GEO", self.cfg)
        self.assertFalse(r.is_valid)
        self.assertTrue(any("chiffre" in e for e in r.errors))

    def test_bad_suffix(self):
        r = naming.validate_name("handle_GEO1", self.cfg)
        self.assertFalse(r.is_valid)
        self.assertTrue(any("uffixe" in e for e in r.errors))

    def test_camel_case_error(self):
        r = naming.validate_name("DoorHandle_GEO", self.cfg)
        self.assertFalse(r.is_valid)
        self.assertTrue(any("camelCase" in e for e in r.errors))

    def test_forbidden_word_warning(self):
        r = naming.validate_name("finalChair_GEO", self.cfg)
        self.assertTrue(any("interdit" in w for w in r.warnings))

    def test_valid_passes(self):
        self.assertTrue(naming.validate_name("L_doorHandle_GEO", self.cfg).is_valid)


class TestBuild(Base):
    def test_build_basic(self):
        self.assertEqual(naming.build_name("body", "GEO", self.cfg, side="C"), "C_body_GEO")

    def test_build_increment_padding(self):
        self.assertEqual(naming.build_name("tableLeg", "GEO", self.cfg, increment=3), "tableLeg03_GEO")

    def test_build_sanitizes(self):
        self.assertEqual(naming.build_name("chair leg", "GEO", self.cfg), "chairLeg_GEO")

    def test_build_requires_descriptor(self):
        with self.assertRaises(ValueError):
            naming.build_name("", "GEO", self.cfg)

    def test_roundtrip(self):
        name = naming.build_name("wheelFront", "GEO", self.cfg, side="L", increment=2)
        p = naming.parse_name(name, self.cfg)
        self.assertEqual(p.side, "L")
        self.assertEqual(p.descriptor, "wheelFront")
        self.assertEqual(p.increment, "02")
        self.assertEqual(p.suffix, "GEO")


class TestHelpers(Base):
    def test_to_camel_case(self):
        self.assertEqual(naming.to_camel_case("Door-Handle front"), "doorHandleFront")
        self.assertEqual(naming.to_camel_case("1stFloor"), "stFloor")
        self.assertEqual(naming.to_camel_case("porte gauche"), "porteGauche")

    def test_strip_namespace(self):
        self.assertEqual(naming.strip_namespace("ns:grp|ns:ball_GEO"), "ball_GEO")


class TestConfigReconfig(Base):
    def test_change_suffix_reconfigures_regex(self):
        cfg = config_mod.load_config(use_cache=False)
        cfg["suffixes"]["geometry"] = "MSH"
        # old suffix no longer valid, new one is
        self.assertIsNone(naming.parse_name("body_GEO", cfg))
        self.assertIsNotNone(naming.parse_name("body_MSH", cfg))


class TestLodToken(Base):
    def test_lod_enabled(self):
        cfg = config_mod.load_config(use_cache=False)
        cfg["lod_token"]["enabled"] = True
        p = naming.parse_name("body_lod0_GEO", cfg)
        self.assertIsNotNone(p)
        self.assertEqual(p.descriptor, "body")
        self.assertEqual(p.lod, "lod0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
