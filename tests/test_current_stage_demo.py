"""The first-screen M1 demo must be traceable to the accepted archived dataset."""
import json
from pathlib import Path
import re
from statistics import median
import unittest

ROOT = Path(__file__).resolve().parents[1]

class CurrentStageDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        cls.curated = (ROOT / "site/m1-curated-20261023.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "site/styles.css").read_text(encoding="utf-8")
        cls.dataset = json.loads((ROOT / "site/m1-curated-20261023.json").read_text(encoding="utf-8"))
        cls.story = cls.html.split("<!-- M1_DEMO_START", 1)[1].split("<!-- M1_DEMO_END -->", 1)[0]

    def test_observed_examples_recompute_from_all_35_source_days(self):
        self.assertEqual(self.dataset["coverage"]["measured"], 20)
        self.assertEqual(self.dataset["coverage"]["daily_observations"], 700)
        self.assertEqual(self.dataset["observation_window_utc"],
                         {"start":"2026-09-19","end":"2026-10-23","days":35})
        self.assertEqual(self.dataset["retrieved_at_utc"], "2026-10-26T01:36:18Z")
        for project, page_id in (("en.wikipedia",3921), ("ru.wikipedia",10646)):
            item = next(s for s in self.dataset["series"]
                        if (s["project"],s["observed_page_id"]) == (project,page_id))
            m = re.search(r'<article class="prototype-panel[^>]+data-example="' +
                          re.escape(f"{project}:{page_id}") + r'".*?</article>', self.story, re.S)
            self.assertIsNotNone(m)
            block=m.group(0)
            weeks=[sum(item["daily_views"][i:i+7]) for i in range(0,35,7)]
            published=[int(v) for v in re.findall(r'data-proto-week="[1-5]" data-proto-views="(\d+)"', block)]
            self.assertEqual(published,weeks)
            base=median(weeks[:4])
            self.assertGreater(base,0)
            self.assertIn(f"{weeks[-1]:,}", block)
            self.assertIn(f"{base:,.0f}", block)
            self.assertIn(f"{100*(weeks[-1]/base-1):+.1f}%", block)
        basketball = next(s for s in self.dataset["series"] if s["project"]=="en.wikipedia" and s["observed_page_id"]==3921)
        self.assertEqual(basketball["daily_views"][-1],24881)
        self.assertIn("24,881 requests",self.story)

    def test_deep_links_target_real_atlas_content(self):
        links=re.findall(r'href="m1-curated-20261023\.html#([^"]+)"', self.story)
        self.assertEqual(len(links),6)
        for ident in links:
            self.assertIn('id="'+ident+'"',self.curated)
        self.assertIn('href="m1-curated-20261023.json"',self.story)
        self.assertIn('aria-labelledby="prototype-title"',self.story)
        self.assertIn("ARCHIVED, NOT LIVE",self.story)
        self.assertIn("not proven stable page-ID histories",self.story)

    def test_mobile_keyboard_and_original_m0_are_kept(self):
        self.assertIn(".prototype-journey a:focus-visible",self.css)
        self.assertIn("@media(max-width:850px)",self.css)
        self.assertIn("@media(max-width:480px)",self.css)
        self.assertIn('aria-label="Basketball English Wikipedia: five exact weekly totals"',self.story)
        self.assertIn("EARLIER SAMPLE / CHESS · EN",self.html)
        self.assertIn("19,804",self.html)
        self.assertNotIn("live popularity",self.story.lower())
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        self.assertIn("## Try the guided current-stage demo",readme)
        self.assertIn("not a live feed",readme)

if __name__ == "__main__":
    unittest.main()
