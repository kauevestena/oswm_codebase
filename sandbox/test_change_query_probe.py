"""Client protocol/transaction fixtures; live server parity is a separate test."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

import requests

import change_query_probe as p


def node(identifier=1, lat=1, tags=None):
    return p.primitive(dict(type="node", id=identifier, lat=lat, lon=2, tags=tags or {}))


def xml(actions, watermark=p.T1):
    return f'<osm><meta osm_base="{watermark}"/>{actions}</osm>'.encode()


def n(identifier=1, lat=1, version=1, tags=""):
    return f'<node id="{identifier}" lat="{lat}" lon="2" version="{version}">{tags}</node>'


class DeltaTests(unittest.TestCase):
    def test_scope_departure_is_removed_even_while_visible(self):
        base = {"node:1": node(), "node:2": node(2)}
        body = '<action type="delete"><old>' + n() + '</old><new><node id="1" visible="true" version="2"/></new></action>'
        actions, stats = p.parse_adiff(xml(body), p.T1)
        self.assertEqual(p.apply_adiff(base, actions), {"node:2": node(2)})
        self.assertEqual(stats["left_query_but_visible"], 1)
        self.assertEqual(len(base), 2)  # prepare did not mutate its baseline

    def test_actual_osm_deletion_and_no_visibility_shape(self):
        for new, counter in [('<new><node id="1" visible="false"/></new>', "osm_deleted"), ("", "delete_without_visibility")]:
            actions, stats = p.parse_adiff(xml('<action type="delete"><old>' + n() + '</old>' + new + '</action>'), p.T1)
            self.assertEqual(p.apply_adiff({"node:1": node(), "node:2": node(2)}, actions), {"node:2": node(2)})
            self.assertEqual(stats[counter], 1)

    def test_same_version_indirect_geometry_with_cached_parent(self):
        # A nested parent need not be emitted if membership is unchanged:
        # reconstruct from updated children rather than caching inline geometry.
        base = {"node:1": node(), "way:1": p.primitive(dict(type="way", id=1, nodes=[1])),
                "relation:1": p.primitive(dict(type="relation", id=1, members=[dict(type="way", ref=1, role="outer")])),
                "relation:2": p.primitive(dict(type="relation", id=2, members=[dict(type="relation", ref=1, role="")]))}
        way = '<way id="1" version="4"><nd ref="1" lat="{}" lon="2"/></way>'
        body = '<action type="modify"><old>' + n() + '</old><new>' + n(lat=3, version=2) + '</new></action>'
        body += '<action type="modify"><old>' + way.format(1) + '</old><new>' + way.format(3) + '</new></action>'
        actions, stats = p.parse_adiff(xml(body), p.T1)
        updated = p.apply_adiff(base, actions)
        self.assertEqual(updated["node:1"]["lat"], 3)
        self.assertEqual(updated["relation:2"], base["relation:2"])
        self.assertEqual(stats["same_version_modifies"], 1)
        self.assertEqual(updated["way:1"]["nodes"], [1])

    def test_entrant_can_have_old_osm_version_and_colliding_numeric_id(self):
        base = {"node:1": node()}
        body = '<action type="create"><way id="1" version="9"><nd ref="1"/></way></action>'
        actions, stats = p.parse_adiff(xml(body), p.T1)
        self.assertEqual(set(p.apply_adiff(base, actions)), {"node:1", "way:1"})
        self.assertEqual(stats["create"], 1)

    def test_changed_old_data_and_missing_references_reject_delta(self):
        for body in [
            '<action type="modify"><old>' + n(lat=9) + '</old><new>' + n(lat=3) + '</new></action>',
            '<action type="create"><way id="2"><nd ref="999"/></way></action>',
        ]:
            actions, _ = p.parse_adiff(xml(body), p.T1)
            with self.assertRaises(p.InvalidSource):
                p.apply_adiff({"node:1": node()}, actions)

    def test_errors_partial_response_stale_and_duplicate_actions_are_rejected(self):
        create = '<action type="create">' + n() + '</action>'
        for data in [xml('<remark>timeout</remark>'), xml('', p.T0), b'<osm>',
                     xml(n()), xml(create + create), xml('<action type="info"/>'),
                     xml('<action type="modify"><old>' + n() + '</old></action>')]:
            with self.subTest(data=data), self.assertRaises(Exception):
                p.parse_adiff(data, p.T1)

    def test_naive_edited_object_upserts_do_not_handle_scope_departures(self):
        base = {"node:1": node(), "node:2": node(2)}
        naive = {**base, **{"node:2": node(2, lat=3)}}
        target = {"node:2": node(2, lat=3)}
        self.assertNotEqual(naive, target)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cache = p.SnapshotCache(self.temporary.name)
        self.base = {"node:1": node()}
        self.pointer = self.cache.commit(self.base, p.T0, "query")

    def fail_delta(self):
        raise requests.ReadTimeout("injected")

    def test_timeout_fallback_does_not_advance_checkpoint_until_commit(self):
        target = {"node:1": node(lat=3)}
        fresh, result = p.acquire(self.base, self.pointer, "query", p.T0, p.T1, self.fail_delta, lambda t: target)
        self.assertEqual(result["mode"], "full_fallback")
        self.assertEqual(self.cache.load("query"), (self.base, self.pointer))
        self.cache.commit(fresh, p.T1, "query")
        self.assertEqual(self.cache.load("query")[0], target)

    def test_both_sources_fail_preserves_last_good_cache(self):
        def fail_full(t): raise requests.ReadTimeout("full failed")
        with self.assertRaises(requests.ReadTimeout):
            p.acquire(self.base, self.pointer, "query", p.T0, p.T1, self.fail_delta, fail_full)
        self.assertEqual(self.cache.load("query"), (self.base, self.pointer))

    def test_target_replay_performs_no_requests(self):
        end = self.cache.commit(self.base, p.T1, "query")
        data, result = p.acquire(self.base, end, "query", p.T0, p.T1,
                                 lambda: self.fail("delta called"), lambda t: self.fail("full called"))
        self.assertIs(data, self.base)
        self.assertFalse(result["needs_commit"])

    def test_changed_query_or_wrong_window_bootstraps_without_delta(self):
        for identity, start in [("new-query", p.T0), ("query", "2026-10-30T00:00:00Z")]:
            data, result = p.acquire(self.base, self.pointer, identity, start, p.T1,
                                     lambda: self.fail("delta called"), lambda t: self.base)
            self.assertEqual(result["mode"], "full_fallback")

    def test_checksum_and_configuration_are_enforced(self):
        with self.assertRaises(p.InvalidSource): self.cache.load("other")
        (self.cache.path / self.pointer["file"]).write_bytes(gzip.compress(b'{}'))
        with self.assertRaises(p.InvalidSource): self.cache.load("query")

    def test_local_detection_covers_roads_geometry_tags_add_remove_config(self):
        before = {name: {"way:1": {"g": "old", "a": "tags"}}
                  for name in ["kerbs", "sidewalks", "crossings", "other_footways", "roads_for_completeness"]}
        self.assertFalse(p.local_changes(before, before)["needs_rebuild"])
        self.assertTrue(p.local_changes(before, before, True)["needs_rebuild"])
        for layer in before:
            for change in ["geometry", "tags", "add", "remove"]:
                after = copy.deepcopy(before)
                if change == "geometry": after[layer]["way:1"]["g"] = "new"
                elif change == "tags": after[layer]["way:1"]["a"] = "new"
                elif change == "add": after[layer]["way:2"] = after[layer]["way:1"]
                else: del after[layer]["way:1"]
                self.assertTrue(p.local_changes(before, after)["needs_rebuild"])


if __name__ == "__main__": unittest.main()
