"""Offline later-day capture controls. Never make Wikimedia requests in tests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import json
import tempfile
import unittest
from tools import m1_identity_followup as m
from tools.m1_identity_panel import canonical_bytes


def utc(day, seconds=43200):
    return datetime.fromisoformat(day+'T00:00:00+00:00')+timedelta(seconds=seconds)


class FollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel, _, cls.provenance, cls.members = m.load_retained()

    def test_real_baseline_has_20_distinct_en_ru_ids(self):
        rows=self.panel['pages']
        self.assertEqual(self.provenance['observation_date_utc'],'2026-11-04')
        self.assertEqual(len({(p['page_ref']['project'],p['page_ref']['page_id']) for p in rows}),20)
        self.assertEqual({p['page_ref']['project'] for p in rows},{'en.wikipedia','ru.wikipedia'})

    def test_date_gate_and_numeric_seed(self):
        for day in ('2026-11-03','2026-11-04'):
            with self.assertRaisesRegex(m.CollectionFailure,'later UTC date'):
                m.eligible_snapshot(self.panel,self.provenance,clock=utc(day))
        self.assertEqual(m.eligible_snapshot(self.panel,self.provenance,clock=utc('2026-11-05')),'2026-11-05')
        with self.assertRaisesRegex(m.CollectionFailure,'midnight'):
            m.eligible_snapshot(self.panel,self.provenance,clock=utc('2026-11-05',86399))
        seed=m.seed_for_same_ids(self.panel,datetime.now(timezone.utc).date().isoformat())
        self.assertEqual(len(seed['pages']),20)
        self.assertTrue(all(set(p)=={'page_ref','topic_id','subject','relation'} for p in seed['pages']))
        missing=deepcopy(self.panel);missing['pages'].pop()
        with self.assertRaisesRegex(m.CollectionFailure,'20 distinct'):
            m.seed_for_same_ids(missing,datetime.now(timezone.utc).date().isoformat())

    def test_same_day_and_existing_destination_do_not_touch_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'candidate'
            with patch.object(m,'collect_to_new_directory',side_effect=AssertionError('provider reached')):
                with self.assertRaisesRegex(m.CollectionFailure,'later UTC date'):
                    m.collect_followup(dest,now=lambda:utc('2026-11-04'))
            self.assertFalse(dest.exists())
            dest.mkdir();(dest/'keep').write_bytes(b'good')
            with self.assertRaisesRegex(m.CollectionFailure,'destination exists'):
                m.collect_followup(dest,now=lambda:utc('2026-11-05'))
            self.assertEqual((dest/'keep').read_bytes(),b'good')

    def test_offline_simulated_pair_builds_immutable_report(self):
        # Simulated dated metadata; not a second real acquisition.
        with tempfile.TemporaryDirectory() as tmp:
            day=datetime.now(timezone.utc).date().isoformat()
            before_day=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()
            before=deepcopy(self.panel);after=deepcopy(before)
            for p in before['pages']:
                p['titles'][-1]['date']=before_day
                p['source']['requested_at']=before_day+'T10:00:00Z'
            for p in after['pages']:
                p['titles'][-1]['date']=day
                p['source']['requested_at']=day+'T12:00:00Z'
            after['panel_id']='m1-followup-'+day.replace('-','')
            after['selection']['selected_at']=day
            keys=('schema_version','panel_id','selection','pages')
            old=canonical_bytes({k:before[k] for k in keys})
            new=canonical_bytes({k:after[k] for k in keys})
            proof={'observation_date_utc':before_day,'capsule':{'sha256':'a'*64}}
            def fake_collect(seed,out,**kwargs):
                self.assertEqual(json.loads(seed.read_bytes())['selected_at'],day)
                out.mkdir();(out/'panel.json').write_bytes(new)
                (out/'collection-report.json').write_bytes(canonical_bytes({
                    'attempts': [{'status': 'retained', 'requested_at': day+'T12:00:00Z'} for _ in range(20)]}))
                return {'intended_count':20,'requests_attempted':20,'retained_count':20,'unavailable_count':0}
            dest=Path(tmp)/'pair'
            with patch.object(m,'load_retained',return_value=(before,{},proof,{'panel.json':old})),\
                 patch.object(m,'collect_to_new_directory',side_effect=fake_collect),\
                 patch.object(m,'verify_bundle',return_value={'manifest_sha256':'b'*64}):
                result=m.collect_followup(dest,now=lambda:utc(day),sleep=lambda _:None)
            self.assertEqual(result['status'],'UNPUBLISHED_SOURCE_REVIEW_REQUIRED')
            self.assertEqual((dest/'baseline-panel.json').read_bytes(),old)
            self.assertEqual((dest/'followup-source/panel.json').read_bytes(),new)
            self.assertTrue((dest/'history/index.html').is_file())
            self.assertEqual(json.loads((dest/'manifest.json').read_bytes()),m._manifest(dest))
            with self.assertRaisesRegex(m.CollectionFailure,'destination exists'):
                m.collect_followup(dest,now=lambda:utc(day))


    def test_unavailable_attempt_crossing_midnight_fails_closed(self):
        # The 20th request is a missing/invalid ID, so it is absent from
        # panel.pages but still has a dated attempt in collection-report.json.
        # Simulate a Nov 3 baseline and a Nov 4 follow-up. Both dates are
        # historically valid to the seed validator even on the Nov 4 test run.
        # Source bytes are *mocked*, not a backdated real Wikimedia observation.
        day='2026-11-04'
        before=deepcopy(self.panel)
        for page in before['pages']:
            page['titles'][-1]['date']='2026-11-03'
            page['source']['requested_at']='2026-11-03T10:00:00Z'
        baseline_bytes=canonical_bytes({key:before[key] for key in ('schema_version','panel_id','selection','pages')})
        provenance={'observation_date_utc':'2026-11-03','capsule':{'sha256':'a'*64}}
        attempts=[{'status':'retained','requested_at':day+'T12:00:00Z'} for _ in range(19)]
        attempts.append({'status':'unavailable','requested_at':'2026-11-05T00:00:01Z'})
        def fake_collect(seed,out,**kwargs):
            out.mkdir()
            (out/'collection-report.json').write_bytes(canonical_bytes({'attempts':attempts}))
            return {'intended_count':20,'requests_attempted':20}
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/'candidate'
            with (patch.object(m,'load_retained',return_value=(before,{},provenance,{'panel.json':baseline_bytes})),
                  patch.object(m,'collect_to_new_directory',side_effect=fake_collect),
                  patch.object(m,'verify_bundle',return_value={'manifest_sha256':'a'*64})):
                with self.assertRaisesRegex(m.CollectionFailure,'attempt retrieval crossed a UTC day boundary'):
                    m.collect_followup(destination,now=lambda:utc(day),sleep=lambda _:None)
            self.assertFalse(destination.exists(), 'cross-day candidate must not be promoted')


if __name__=='__main__':
    unittest.main()
