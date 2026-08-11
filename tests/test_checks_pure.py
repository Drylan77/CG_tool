"""Tests for the checks that operate purely on names (no live Maya needed).

These lock the detection logic of the string-only checks. Checks that inspect
real node types / DAG relationships are exercised in Maya.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from namingTool.core import checks, config as config_mod  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.cfg = config_mod.load_config(use_cache=False)


class TestDefaultNames(Base):
    def test_flags_default_names(self):
        nodes = ["|pCube1", "|polySurface23", "|group1", "|L_body_GEO"]
        res = checks.check_default_names(nodes, self.cfg)
        self.assertEqual(res.status, checks.ERROR)
        self.assertEqual(set(res.nodes), {"|pCube1", "|polySurface23", "|group1"})

    def test_clean_scene_passes(self):
        res = checks.check_default_names(["|L_body_GEO", "|chassis_GRP"], self.cfg)
        self.assertEqual(res.status, checks.PASS)


class TestDuplicates(Base):
    def test_detects_cross_branch_duplicates(self):
        nodes = ["|a|ball_GEO", "|b|ball_GEO", "|c|unique_GEO"]
        res = checks.check_duplicate_names(nodes, self.cfg)
        self.assertEqual(res.status, checks.ERROR)
        self.assertEqual(set(res.nodes), {"|a|ball_GEO", "|b|ball_GEO"})


class TestSuffixValid(Base):
    def test_missing_or_bad_suffix(self):
        nodes = ["|body", "|body_XYZ", "|body_GEO"]
        res = checks.check_suffix_valid(nodes, self.cfg)
        self.assertEqual(set(res.nodes), {"|body", "|body_XYZ"})


class TestIllegalCase(Base):
    def test_illegal_and_case(self):
        nodes = ["|Body_GEO", "|good_GEO"]  # Body = bad camelCase
        res = checks.check_illegal_and_case(nodes, self.cfg)
        self.assertIn("|Body_GEO", res.nodes)
        self.assertNotIn("|good_GEO", res.nodes)


class TestNumbering(Base):
    def test_mixed_padding(self):
        nodes = ["|leg1_GEO", "|leg02_GEO", "|leg003_GEO"]
        res = checks.check_numbering(nodes, self.cfg)
        self.assertEqual(res.status, checks.WARNING)
        self.assertEqual(len(res.nodes), 3)

    def test_consistent_padding_ok(self):
        nodes = ["|leg01_GEO", "|leg02_GEO"]
        res = checks.check_numbering(nodes, self.cfg)
        self.assertEqual(res.status, checks.PASS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
