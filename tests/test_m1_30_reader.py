"""Regression tests for the pinned 30-title offline reader."""
import csv
from datetime import date, timedelta
from io import StringIO
import json
import shutil
from urllib.parse import unquote
import subprocess
from html.parser import HTMLParser
import unittest

from tools.m1_30_reader import render, metrics, largest_daily_rise, largest_daily_fall, weekly_spotlights, cohort_weekly_csv, cohort_daily_csv
from tools.m1_30_retained_candidate import read_candidate


class TagReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.articles = 0
        self.rows = 0
        self.deltas = []
        self.volumes = []
        self.daily_rises = []
        self.daily_falls = []
        self.fall_links = []
        self.rise_links = []
        self.day_rows = []
        self.compare_links = []
        self.article_csv_links = []
        self.spotlights = []
        self.cohort_csv_links = []
        self.cohort_daily_links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a' and dict(attrs).get('class') == 'cohort-daily':
            self.cohort_daily_links.append(dict(attrs))
        if tag == 'a' and dict(attrs).get('class') == 'cohort-csv':
            self.cohort_csv_links.append(dict(attrs))
        if tag == 'a' and dict(attrs).get('class') == 'spotlight':
            self.spotlights.append(dict(attrs))
        if tag == 'article':
            self.articles += 1
            self.deltas.append(float(dict(attrs)['data-delta']))
            self.volumes.append(int(dict(attrs)['data-volume']))
            self.daily_rises.append(int(dict(attrs)['data-daily-rise']))
            self.daily_falls.append(int(dict(attrs)['data-daily-fall']))
        if tag == 'tr':
            self.rows += 1
            if dict(attrs).get('id', '').startswith('day-page-'):
                self.day_rows.append(dict(attrs)['id'])
        if tag == 'a' and dict(attrs).get('class') == 'rise-jump':
            self.rise_links.append(dict(attrs))
        if tag == 'a' and dict(attrs).get('class') == 'fall-jump':
            self.fall_links.append(dict(attrs))
        if tag == 'a' and dict(attrs).get('class') == 'compare-jump':
            self.compare_links.append(dict(attrs))
        if tag == 'a' and dict(attrs).get('class') == 'article-csv':
            self.article_csv_links.append(dict(attrs))


class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = read_candidate()[1]

    def test_static_counts_provenance_and_determinism(self):
        raw = render(self.candidate)
        self.assertEqual(raw, render(self.candidate))
        text = raw.decode('utf-8')
        parsed = TagReader()
        parsed.feed(text)
        self.assertEqual(parsed.articles, 30)
        self.assertEqual(parsed.rows, 30 * (35 + 5 + 2))
        expected = sorted(self.candidate['series'],
                          key=lambda row: (-abs(metrics(row)[1]), row['project'], row['page_id']))
        self.assertEqual(parsed.deltas, [metrics(row)[1] for row in expected])
        self.assertEqual(parsed.volumes, [metrics(row)[0] for row in expected])
        self.assertEqual(parsed.daily_rises, [largest_daily_rise(row['daily'])[0] for row in expected])
        self.assertEqual(parsed.daily_falls, [largest_daily_fall(row['daily'])[0] for row in expected])
        self.assertEqual(len(parsed.day_rows), 30 * 35)
        self.assertEqual(len(set(parsed.day_rows)), 30 * 35)
        self.assertTrue(any(delta > 0 for delta in parsed.deltas))
        self.assertTrue(any(delta < 0 for delta in parsed.deltas))
        self.assertIn('<label for="sort">Order by requests or measured change', text)
        self.assertIn('value="volume">Most requests in last complete UTC week', text)
        self.assertIn('Largest signed increase first', text)
        self.assertIn('Largest signed decrease first', text)
        self.assertIn('<option value="daily-rise">Largest one-day request rise</option>', text)
        self.assertIn('<option value="daily-fall">Largest one-day request fall</option>', text)
        self.assertIn('34 adjacent UTC-day pairs', text)
        self.assertIn('Retrieved 2026-11-17T08:30:55Z', text)
        self.assertIn('OFFLINE · UNPUBLISHED', text)
        self.assertIn('Original raw HTTP response bodies', text)
        self.assertIn(self.candidate['dataset_id'], text)
        self.assertIn('History, values &amp; evidence', text)
        self.assertIn('dataset:data.dataset,method:data.method', text)

    def test_native_cohort_daily_csv_exact_and_fail_closed(self):
        """All 1,050 source-pinned observations can be exported with JS off."""
        rendered = render(self.candidate).decode('utf-8')
        parsed = TagReader()
        parsed.feed(rendered)
        self.assertEqual(len(parsed.cohort_daily_links), 1)
        link = parsed.cohort_daily_links[0]
        self.assertEqual(link['download'], 'dayflare-30-all-daily.csv')
        self.assertIn('Download all 1,050 exact daily requests (CSV)', rendered)
        self.assertLess(rendered.index('id="spotlights"'),
                        rendered.index('class="cohort-daily"'))
        self.assertLess(rendered.index('class="cohort-daily"'), rendered.index('</header>'))
        href = link['href']
        self.assertEqual(href, cohort_daily_csv(
            self.candidate['series'],
            self.candidate['dataset_id'], self.candidate['method_version']))
        self.assertEqual(href, cohort_daily_csv(
            list(reversed(self.candidate['series'])),
            self.candidate['dataset_id'], self.candidate['method_version']))
        self.assertTrue(href.startswith('data:text/csv;charset=utf-8,'))
        raw = unquote(href.split(',', 1)[1])
        self.assertEqual(raw.count('\r\n'), 1051)
        records = list(csv.DictReader(StringIO(raw)))
        self.assertEqual(len(records), 1050)
        expected_rows = sorted(self.candidate['series'], key=lambda row: (
            -abs(metrics(row)[1]), row['project'], row['page_id']))
        expected = [
            (point, row) for row in expected_rows for point in row['daily']
        ]
        for record, (point, row) in zip(records, expected):
            self.assertEqual(record['utc_date'], point['date'])
            self.assertEqual(record['project_page_id'],
                             f"{row['project']}:{row['page_id']}")
            self.assertEqual(record['requests'], str(point['views']))
            self.assertEqual(record['dataset_id'], self.candidate['dataset_id'])
            self.assertEqual(record['method_version'], self.candidate['method_version'])
            self.assertEqual(record['recorded_api_endpoint'], row['source']['endpoint'])
            self.assertEqual(record['reported_response_sha256'],
                             row['source']['body_sha256'])
        self.assertEqual(len({r['project_page_id'] for r in records}), 30)
        for kind in ('missing-day', 'duplicate-id', 'inexact', 'different-window', 'source'):
            invalid = json.loads(json.dumps(self.candidate['series']))
            if kind == 'missing-day':
                invalid[0]['daily'].pop()
            elif kind == 'duplicate-id':
                invalid[0]['project'] = invalid[1]['project']
                invalid[0]['page_id'] = invalid[1]['page_id']
            elif kind == 'inexact':
                invalid[0]['daily'][0]['views'] = 2**53
            elif kind == 'different-window':
                invalid[0]['daily'][0]['date'] = '2026-10-12'
            else:
                invalid[0]['source']['body_sha256'] = 'unverified'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                cohort_daily_csv(invalid, self.candidate['dataset_id'],
                                 self.candidate['method_version'])

    def test_static_cohort_weekly_csv_exact_values_without_javascript(self):
        """Source-pinned 30-title weekly overview is independently usable as CSV."""
        rendered = render(self.candidate).decode('utf-8')
        parsed = TagReader()
        parsed.feed(rendered)
        self.assertEqual(len(parsed.cohort_csv_links), 1)
        link = parsed.cohort_csv_links[0]
        self.assertEqual(link['download'], 'dayflare-30-weekly-summary.csv')
        self.assertIn('Download all 30 exact weekly comparisons (CSV)', rendered)
        self.assertLess(rendered.index('id="spotlights"'), rendered.index('class="cohort-csv"'))
        self.assertLess(rendered.index('class="cohort-csv"'), rendered.index('</header>'))
        href = link['href']
        self.assertTrue(href.startswith('data:text/csv;charset=utf-8,'))
        raw = unquote(href.split(',', 1)[1])
        self.assertTrue(raw.endswith('\r\n') and raw.count('\r\n') == 31)
        records = list(csv.DictReader(StringIO(raw)))
        self.assertEqual(len(records), 30)
        self.assertEqual(cohort_weekly_csv(self.candidate['series'],
                                           self.candidate['dataset_id'],
                                           self.candidate['method_version']), href)
        self.assertEqual(href, cohort_weekly_csv(
            list(reversed(self.candidate['series'])),
            self.candidate['dataset_id'], self.candidate['method_version']))

        def half_text(twice):
            return ('-' if twice < 0 else '') + str(abs(twice) // 2) + (
                '.5' if abs(twice) % 2 else '')

        expected = []
        for row in self.candidate['series']:
            weeks = [sum(day['views'] for day in row['daily'][i:i + 7])
                     for i in (0, 7, 14, 21, 28)]
            ranked = sorted(weeks[:4])
            middle_twice = ranked[1] + ranked[2]
            change_twice = 2 * weeks[-1] - middle_twice
            expected.append((-abs(change_twice), row['project'], row['page_id'], row,
                             weeks, middle_twice, change_twice))
        expected.sort(key=lambda item: item[:3])
        for record, (_, project, page_id, row, weeks, baseline, change) in zip(records, expected):
            self.assertEqual(record['project_page_id'], f'{project}:{page_id}')
            self.assertEqual(record['article_title'], row['title'])
            self.assertEqual(record['observed_start_utc'], row['daily'][0]['date'])
            self.assertEqual(record['observed_end_utc'], row['daily'][-1]['date'])
            self.assertEqual([record[f'week_{i}_requests'] for i in range(1, 6)],
                             list(map(str, weeks)))
            self.assertEqual(record['prior_four_week_median_requests'], half_text(baseline))
            self.assertEqual(record['final_week_minus_median_requests'], half_text(change))
            self.assertEqual(record['dataset_id'], self.candidate['dataset_id'])
            self.assertEqual(record['method_version'], self.candidate['method_version'])
            self.assertEqual(record['recorded_api_endpoint'], row['source']['endpoint'])
            self.assertEqual(record['reported_response_sha256'], row['source']['body_sha256'])
        self.assertEqual(len(set(record['project_page_id'] for record in records)), 30)
        self.assertIn('Works without JavaScript', rendered)

    def test_cohort_csv_half_medians_and_fail_closed_untrusted_labels(self):
        rows = json.loads(json.dumps(self.candidate['series']))
        # Four weekly totals 1, 2, 3, 4 => exact median 2.5, last 8 => +5.5.
        for day in rows[0]['daily']:
            day['views'] = 0
        for i, value in zip((0, 7, 14, 21, 28), (1, 2, 3, 4, 8)):
            rows[0]['daily'][i]['views'] = value
        rows[0]['title'] = '=HYPERLINK("https://example.invalid","x")'
        content = unquote(cohort_weekly_csv(
            rows, self.candidate['dataset_id'], self.candidate['method_version']
        ).split(',', 1)[1])
        records = list(csv.DictReader(StringIO(content)))
        match = next(r for r in records
                     if r['project_page_id'] ==
                     f"{rows[0]['project']}:{rows[0]['page_id']}")
        self.assertEqual(match['prior_four_week_median_requests'], '2.5')
        self.assertEqual(match['final_week_minus_median_requests'], '5.5')
        self.assertEqual(match['article_title'], "'" + rows[0]['title'])
        rows[0]['daily'][28]['views'] = 1
        content = unquote(cohort_weekly_csv(
            rows, self.candidate['dataset_id'], self.candidate['method_version']
        ).split(',', 1)[1])
        match = next(r for r in csv.DictReader(StringIO(content))
                     if r['project_page_id'] ==
                     f"{rows[0]['project']}:{rows[0]['page_id']}")
        self.assertEqual(match['final_week_minus_median_requests'], '-1.5')

        for kind in ('bool', 'negative', 'unsafe', 'short', 'duplicate', 'bad-date',
                     'incomparable', 'source', 'checksum'):
            invalid = json.loads(json.dumps(self.candidate['series']))
            if kind == 'bool':
                invalid[0]['daily'][0]['views'] = True
            elif kind == 'negative':
                invalid[0]['daily'][0]['views'] = -1
            elif kind == 'unsafe':
                invalid[0]['daily'][0]['views'] = 2**53
            elif kind == 'short':
                invalid[0]['daily'].pop()
            elif kind == 'duplicate':
                invalid[1]['page_id'] = invalid[0]['page_id']
                invalid[1]['project'] = invalid[0]['project']
            elif kind == 'bad-date':
                invalid[0]['daily'][0]['date'] = '2026-10-1'
            elif kind == 'incomparable':
                invalid[0]['daily'] = [
                    dict(p, date=(date.fromisoformat(p['date']) + timedelta(days=1)).isoformat())
                    for p in invalid[0]['daily']]
            elif kind == 'source':
                invalid[0]['source']['endpoint'] = 'https://example.invalid/not-wikimedia'
            elif kind == 'checksum':
                invalid[0]['source']['body_sha256'] = 'not-a-sha'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                cohort_weekly_csv(invalid, self.candidate['dataset_id'],
                                  self.candidate['method_version'])
        with self.assertRaises(ValueError):
            cohort_weekly_csv(self.candidate['series'], '../unsafe', 'method')
        with self.assertRaises(ValueError):
            cohort_weekly_csv(self.candidate['series'][:29], 'ok', 'method')

    def test_first_screen_spotlights_match_exact_signed_weekly_differences(self):
        html = render(self.candidate).decode('utf-8')
        parsed = TagReader()
        parsed.feed(html)
        self.assertIn('<nav id="spotlights" class="spotlights"', html)
        self.assertEqual(len(parsed.spotlights), 2)
        self.assertLess(html.index('class="status"'), html.index('id="spotlights"'))
        self.assertIn('selected 30 only', html)
        self.assertNotIn('data-page-id=', html.split('<nav id="spotlights"', 1)[1].split('</nav>', 1)[0])
        for direction, positive in (('positive', True), ('negative', False)):
            members = [r for r in self.candidate['series']
                       if (metrics(r)[1] > 0 if positive else metrics(r)[1] < 0)]
            winner = min(members, key=lambda r: (
                -metrics(r)[1] if positive else metrics(r)[1],
                r['project'], r['page_id']))
            entry = next(item for item in parsed.spotlights
                         if item['data-direction'] == direction)
            anchor = f"#page-{winner['project'].split('.')[0]}-{winner['page_id']}"
            self.assertEqual(entry['href'], anchor)
            self.assertIn(f'<article id="{anchor[1:]}" class="tile"', html)
            latest, change, baseline = metrics(winner)
            signed = f'{change:+,.1f}' if change % 1 else f'{change:+,.0f}'
            reference = f'{baseline:,.1f}' if baseline % 1 else f'{baseline:,.0f}'
            self.assertIn(f'{signed} requests</strong>', html)
            self.assertIn(f'{latest:,} requests during {winner["daily"][28]["date"]}–'
                          f'{winner["daily"][34]["date"]} UTC; prior four-week median '
                          f'{reference}.', html)
        self.assertEqual(weekly_spotlights(self.candidate['series']),
                         weekly_spotlights(list(reversed(self.candidate['series']))))
        self.assertIn('@media(max-width:620px){.spotlights{grid-template-columns:1fr}}', html)

    def test_spotlights_do_not_invent_change_when_all_histories_are_flat(self):
        clone = json.loads(json.dumps(self.candidate))
        for row in clone['series']:
            for day in row['daily']:
                day['views'] = 20
        html = render(clone).decode('utf-8')
        parsed = TagReader()
        parsed.feed(html)
        self.assertEqual(parsed.spotlights, [])
        self.assertEqual(html.count('class="spotlight spotlight--empty"'), 2)
        self.assertIn('none measured among these 30 selected histories', html)
        self.assertIn('35 observed days', html)

    def test_largest_daily_rise_exact_dates_ties_and_invalid_windows(self):
        """Adapt already-reviewed 20-title daily-rise semantics to retained 30-title rows."""
        daily = json.loads(json.dumps(self.candidate['series'][0]['daily']))
        for point in daily:
            point['views'] = 20
        self.assertEqual(largest_daily_rise(daily), (0, None))
        daily[2]['views'] = 40
        daily[9]['views'] = 40
        self.assertEqual(largest_daily_rise(daily), (20, 2))  # earliest tie
        daily[30]['views'] = 2**53 - 1
        self.assertEqual(largest_daily_rise(daily), ((2**53 - 1) - 20, 30))
        descending = json.loads(json.dumps(daily))
        for i, point in enumerate(descending):
            point['views'] = 40 - i
        self.assertEqual(largest_daily_rise(descending), (0, None))
        for kind in ('short', 'bool', 'negative', 'unsafe', 'duplicate', 'bad-date'):
            corrupted = json.loads(json.dumps(daily))
            if kind == 'short':
                corrupted.pop()
            elif kind == 'bool':
                corrupted[0]['views'] = True
            elif kind == 'negative':
                corrupted[1]['views'] = -1
            elif kind == 'unsafe':
                corrupted[0]['views'] = 2**53
            elif kind == 'duplicate':
                corrupted[3]['date'] = corrupted[2]['date']
            elif kind == 'bad-date':
                corrupted[3]['date'] = '2026-11-3'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                largest_daily_rise(corrupted)

    def test_largest_daily_fall_exact_dates_ties_and_invalid_windows(self):
        daily = json.loads(json.dumps(self.candidate['series'][0]['daily']))
        for point in daily:
            point['views'] = 20
        self.assertEqual(largest_daily_fall(daily), (0, None))
        daily[3]['views'] = 4
        daily[9]['views'] = 4
        self.assertEqual(largest_daily_fall(daily), (16, 3))  # earliest tie
        daily[0]['views'] = 2**53 - 1
        self.assertEqual(largest_daily_fall(daily), ((2**53 - 1) - 20, 1))
        rising = json.loads(json.dumps(daily))
        for i, point in enumerate(rising):
            point['views'] = i
        self.assertEqual(largest_daily_fall(rising), (0, None))
        for kind in ('short', 'bool', 'negative', 'unsafe', 'duplicate', 'bad-date'):
            corrupted = json.loads(json.dumps(daily))
            if kind == 'short':
                corrupted.pop()
            elif kind == 'bool':
                corrupted[0]['views'] = True
            elif kind == 'negative':
                corrupted[1]['views'] = -1
            elif kind == 'unsafe':
                corrupted[0]['views'] = 2**53
            elif kind == 'duplicate':
                corrupted[3]['date'] = corrupted[2]['date']
            elif kind == 'bad-date':
                corrupted[3]['date'] = '2026-11-3'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                largest_daily_fall(corrupted)

    def test_daily_fall_cards_and_exact_day_anchors_from_real_retained_values(self):
        html = render(self.candidate).decode('utf-8')
        parsed = TagReader()
        parsed.feed(html)
        expected = sorted(self.candidate['series'],
                          key=lambda row: (-abs(metrics(row)[1]), row['project'], row['page_id']))
        self.assertEqual(len(parsed.daily_falls), 30)
        self.assertEqual(html.count('class="daily-fall"'), 30)
        self.assertEqual(len(parsed.fall_links),
                         sum(largest_daily_fall(r['daily'])[0] > 0 for r in expected))
        for row in expected:
            fall, index = largest_daily_fall(row['daily'])
            anchor = f"page-{row['project'].split('.')[0]}-{row['page_id']}"
            if index is not None:
                current, prior = row['daily'][index], row['daily'][index - 1]
                target = f"day-{anchor}-{current['date']}"
                self.assertIn(target, parsed.day_rows)
                self.assertIn(f'<time datetime="{current["date"]}">', html)
                self.assertIn(f'({prior["views"]:,} → {current["views"]:,} from the preceding day)', html)
                self.assertTrue(any(link.get('href') == f'#{target}'
                                    for link in parsed.fall_links))
            else:
                self.assertIn('No one-day request fall across 34 consecutive UTC-day comparisons', html)
        self.assertIn("document.querySelectorAll('.rise-jump,.fall-jump')", html)
        self.assertIn("['magnitude','volume','daily-rise','daily-fall','increase','decrease']", html)

    def test_static_no_fall_is_not_a_misleading_zero_day(self):
        clone = json.loads(json.dumps(self.candidate))
        selected = clone['series'][0]
        selected['daily'] = [{**day, 'views': i}
                             for i, day in enumerate(selected['daily'])]
        html = render(clone).decode('utf-8')
        anchor = f"page-{selected['project'].split('.')[0]}-{selected['page_id']}"
        self.assertIn('No one-day request fall across 34 consecutive UTC-day comparisons', html)
        self.assertIn(f'<article id="{anchor}" class="tile"', html)
        self.assertIn('data-daily-fall="0"', html)
        self.assertEqual(largest_daily_fall(selected['daily']), (0, None))
        self.assertIn(f'id="day-{anchor}-{selected["daily"][0]["date"]}"', html)

    def test_daily_rise_cards_and_exact_day_anchors_from_real_retained_values(self):
        html = render(self.candidate).decode('utf-8')
        parsed = TagReader()
        parsed.feed(html)
        expected = sorted(self.candidate['series'],
                          key=lambda row: (-abs(metrics(row)[1]), row['project'], row['page_id']))
        self.assertEqual(len(parsed.daily_rises), 30)
        self.assertEqual(html.count('class="daily-rise"'), 30)
        self.assertEqual(len(parsed.rise_links),
                         sum(largest_daily_rise(r['daily'])[0] > 0 for r in expected))
        for row in expected:
            rise, index = largest_daily_rise(row['daily'])
            anchor = f"page-{row['project'].split('.')[0]}-{row['page_id']}"
            if index is not None:
                current, prior = row['daily'][index], row['daily'][index - 1]
                target = f"day-{anchor}-{current['date']}"
                self.assertIn(target, parsed.day_rows)
                self.assertIn(f'<time datetime="{current["date"]}">', html)
                self.assertIn(f'({prior["views"]:,} → {current["views"]:,} from the preceding day)', html)
                self.assertTrue(any(link.get('href') == f'#{target}'
                                    for link in parsed.rise_links))
            else:
                self.assertIn('No positive one-day rise across 34 consecutive UTC-day comparisons', html)
        self.assertIn("link.closest('.tile').querySelector('details')", html)
        self.assertIn("['magnitude','volume','daily-rise','daily-fall','increase','decrease']", html)

    def test_static_no_positive_rise_state_is_not_a_misleading_zero_day(self):
        """A complete synthetic declining row must not invent a rise or source link."""
        clone = json.loads(json.dumps(self.candidate))
        selected = clone['series'][0]
        selected['daily'] = [{**day, 'views': 40 - i}
                             for i, day in enumerate(selected['daily'])]
        html = render(clone).decode('utf-8')
        anchor = f"page-{selected['project'].split('.')[0]}-{selected['page_id']}"
        self.assertIn('No positive one-day rise across 34 consecutive UTC-day comparisons', html)
        self.assertIn(f'<article id="{anchor}" class="tile"', html)
        self.assertIn('data-daily-rise="0"', html)
        self.assertEqual(largest_daily_rise(selected['daily']), (0, None))
        self.assertIn(f'id="day-{anchor}-{selected["daily"][0]["date"]}"', html)

    def test_each_card_links_to_existing_stable_identity_comparison(self):
        text = render(self.candidate).decode('utf-8')
        parsed = TagReader()
        parsed.feed(text)
        expected_ids = {f"{row['project']}:{row['page_id']}" for row in self.candidate['series']}
        self.assertEqual(len(parsed.compare_links), 30)
        self.assertEqual({item['data-compare-id'] for item in parsed.compare_links}, expected_ids)
        self.assertTrue(all(item['href'] == '#compare' and
                            item['aria-label'].startswith('Compare ') for item in parsed.compare_links))
        self.assertIn('.controls,#compare,.card-actions{display:none!important}', text)
        self.assertIn("right.focus({preventScroll:true})", text)
        self.assertIn("if(right.value===id)right.value=''", text)

    def test_static_per_article_csv_downloads_are_exact_and_no_js(self):
        """Every history has a native, self-contained CSV link in its static detail."""
        raw = render(self.candidate).decode('utf-8')
        parser = TagReader()
        parser.feed(raw)
        self.assertEqual(len(parser.article_csv_links), 30)
        series = {f"{row['project']}:{row['page_id']}": row
                  for row in self.candidate['series']}
        observed_files = set()
        for attrs in parser.article_csv_links:
            href = attrs['href']
            self.assertTrue(href.startswith('data:text/csv;charset=utf-8,'), href[:100])
            # Decoding the actual href verifies escaping and CRLF—not a parallel formatter.
            csv_text = unquote(href.split(',', 1)[1])
            self.assertEqual(csv_text.count(chr(13) + chr(10)), 36)
            records = list(csv.reader(StringIO(csv_text, newline='')))
            self.assertEqual(len(records), 36)
            self.assertEqual(records[0], [
                'utc_date', 'project_page_id', 'requests', 'dataset_id', 'method_version'])
            key = records[1][1]
            self.assertIn(key, series)
            row = series[key]
            self.assertEqual(attrs['download'],
                             f"dayflare-{row['project'].split('.')[0]}-{row['page_id']}-35day.csv")
            observed_files.add(attrs['download'])
            self.assertEqual(records[1:], [
                [point['date'], key, str(point['views']),
                 self.candidate['dataset_id'], self.candidate['method_version']]
                for point in row['daily']])
        self.assertEqual(len(observed_files), 30)
        self.assertIn('class="article-csv"', raw)
        # no-JS CSS must hide interactive controls, not static per-history exports.
        self.assertIn('.controls,#compare,.card-actions{display:none!important}', raw)
        self.assertNotIn('.article-csv{display:none', raw)

    def test_static_article_csv_rejects_noninteger_or_unsafe_values(self):
        for invalid in (True, -1, 2**53, '3', 3.5):
            clone = json.loads(json.dumps(self.candidate))
            clone['series'][0]['daily'][0]['views'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, TypeError)):
                render(clone)
        clone = json.loads(json.dumps(self.candidate))
        clone['dataset_id'] = '=HYPERLINK("bad")'
        with self.assertRaises(ValueError):
            render(clone)

    def test_final_week_volume_sort_runs_generated_javascript(self):
        """Volume sorting must differ from signed change and preserve ties/inputs."""
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for generated sorting JavaScript')
        html = render(self.candidate).decode('utf-8')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        sort_fn = ('function sortTiles()' + script.split('function sortTiles()', 1)[1]
                   .split(chr(10) + ' search.addEventListener', 1)[0])
        setup = r"""
const tiles=[
  {dataset:{delta:'100',volume:'4',dailyRise:'3',dailyFall:'50'}},
  {dataset:{delta:'-20',volume:'25',dailyRise:'30',dailyFall:'15'}},
  {dataset:{delta:'0',volume:'25',dailyRise:'30',dailyFall:'15'}},
  {dataset:{delta:'5',volume:'10',dailyRise:'15',dailyFall:'80'}}
];
const original=JSON.stringify(tiles.map(t=>t.dataset));
const sort={value:'magnitude'};
const parent={children:[],replaceChildren(...items){this.children=items;}};
const $=id=>{if(id!=='cards')throw Error('Unexpected selector');return parent;};
function check(mode,expected){
  sort.value=mode;sortTiles();
  const actual=parent.children.map(t=>tiles.indexOf(t));
  if(JSON.stringify(actual)!==JSON.stringify(expected))
    throw Error('Incorrect '+mode+' order: '+actual);
  if(JSON.stringify(tiles.map(t=>t.dataset))!==original)
    throw Error('Sorting mutated source observations');
}
check('magnitude',[0,1,3,2]);
check('increase',[0,3,2,1]);
check('decrease',[1,2,3,0]);
check('volume',[1,2,3,0]); // equal-volume ties retain original card order
check('daily-rise',[1,2,3,0]); // earliest original card on daily-rise ties
check('daily-fall',[3,0,1,2]); // independent daily-drop values, stable equal ties
"""
        result = subprocess.run(
            ['node', '-'], input=sort_fn + chr(10) + setup,
            text=True, capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_visible_filtered_csv_exact_source_values_and_fail_closed(self):
        """Exercise the actual emitted exporter over ordered, filtered stable IDs."""
        html = render(self.candidate).decode('utf-8')
        self.assertEqual(html.count('data-page-id='), 30)
        self.assertIn('id="download-visible" download="dayflare-30-visible.csv" hidden', html)
        self.assertIn('utc_date,project_page_id,requests,dataset_id,method_version', html)
        self.assertIn('Number.isSafeInteger(value)', html)
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for generated CSV export test')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        exporter = ('function updateVisibleCsv()' +
                    script.split('function updateVisibleCsv()', 1)[1]
                    .split('\nfunction filter()', 1)[0])
        setup = r"""
const data={dataset:'retained-id',method:'v0-test',dates:['2026-11-13','2026-11-14']};
const rows=Object.create(null);
rows['en.wikipedia:10']={values:[10,20]};
rows['ru.wikipedia:20']={values:[0,7]};
const en={dataset:{pageId:'en.wikipedia:10'},hidden:false};
const ru={dataset:{pageId:'ru.wikipedia:20'},hidden:false};
const cards={children:[en,ru]};
const $=id=>{if(id!=='cards')throw Error('Unexpected element');return cards};
const visibleCsv={href:'',hidden:true};
function lines(){
  if(visibleCsv.hidden || !visibleCsv.href.startsWith('data:text/csv;charset=utf-8,'))
    throw Error('CSV not available');
  return decodeURIComponent(visibleCsv.href.split(',',2)[1]).trimEnd().split('\r\n');
}
updateVisibleCsv();
const header='utc_date,project_page_id,requests,dataset_id,method_version';
const before=lines();
if(JSON.stringify(before)!==JSON.stringify([
  header,
  '2026-11-13,en.wikipedia:10,10,retained-id,v0-test',
  '2026-11-14,en.wikipedia:10,20,retained-id,v0-test',
  '2026-11-13,ru.wikipedia:20,0,retained-id,v0-test',
  '2026-11-14,ru.wikipedia:20,7,retained-id,v0-test']))throw Error('Exact CSV mismatch');
cards.children.reverse();updateVisibleCsv();
if(lines()[1]!=='2026-11-13,ru.wikipedia:20,0,retained-id,v0-test')throw Error('DOM sort not preserved');
ru.hidden=true;updateVisibleCsv();
if(lines().length!==3 || lines()[1].split(',')[1]!=='en.wikipedia:10')throw Error('Edition/filter was ignored');
en.hidden=true;updateVisibleCsv();
if(!visibleCsv.hidden || visibleCsv.href!=='')throw Error('Empty export not disabled');
en.hidden=false;rows['en.wikipedia:10'].values[0]=NaN;updateVisibleCsv();
if(!visibleCsv.hidden || visibleCsv.href!=='')throw Error('Invalid number exported');
rows['en.wikipedia:10'].values[0]=10;en.dataset.pageId='constructor';updateVisibleCsv();
if(!visibleCsv.hidden || visibleCsv.href!=='')throw Error('Inherited unknown key exported');
"""
        result = subprocess.run(['node', '-'], input=exporter + '\n' + setup,
                                text=True, capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_numeric_change_exactly_median_of_four_weeks(self):
        row = self.candidate['series'][0]
        values = [item['views'] for item in row['daily']]
        latest, delta, baseline = metrics(row)
        self.assertEqual(latest, sum(values[-7:]))
        self.assertEqual(delta, latest - baseline)
        self.assertGreaterEqual(baseline, 0)

    def test_half_integer_median_is_exact_in_rendered_cards(self):
        clone = json.loads(json.dumps(self.candidate))
        row = clone['series'][0]
        for week, total in enumerate((100, 100, 101, 101, 200)):
            for day in range(7):
                row['daily'][week * 7 + day]['views'] = total if day == 0 else 0
        marker = f'id="page-{row["project"].split(".")[0]}-{row["page_id"]}"'

        def card():
            return render(clone).decode('utf-8').split(marker, 1)[1].split('</article>', 1)[0]

        self.assertEqual(metrics(row)[1], 99.5)
        self.assertIn('>+99.5</strong>', card())
        row['daily'][28]['views'] = 100
        self.assertEqual(metrics(row)[1], -0.5)
        self.assertIn('>-0.5</strong>', card())
        row['daily'][28]['views'] = 101
        self.assertEqual(metrics(row)[1], 0.5)
        self.assertIn('>+0.5</strong>', card())

    def test_share_link_id_validation_rejects_inherited_properties(self):
        html = render(self.candidate).decode('utf-8')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        own_key = script.split('const hasHistory=', 1)[1].split(';', 1)[0]
        predicate = script.split('let valid=', 1)[1].split(';if(valid)', 1)[0]
        cleaner = script.split('const cleaned=', 1)[1].split(';', 1)[0]
        self.assertIn('Object.prototype.hasOwnProperty.call(rows,id)', own_key)
        self.assertIn("hasHistory(params.get('left'))", predicate)
        self.assertIn("hasHistory(params.get('right'))", predicate)
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for JavaScript URL validation')
        js = ("const rows={'en.wikipedia:1':{},'ru.wikipedia:2':{}};"
              "const data={dataset:'d',method:'m'};"
              "const hasHistory=" + own_key + ";"
              "const cleaned=" + cleaner + ";"
              "function check(s){const params=new URLSearchParams(s);"
              "let valid=" + predicate + ";return !!valid;}"
              "const url=(left,right,dataset='d')=>new URLSearchParams({"
              "dataset,method:'m',left,right}).toString();"
              "if(!check(url('en.wikipedia:1','ru.wikipedia:2')))process.exit(10);"
              "for(const id of ['toString','constructor','__proto__','unknown'])"
              "if(check(url(id,'ru.wikipedia:2')))process.exit(11);"
              "if(check(url('en.wikipedia:1','ru.wikipedia:2','old')))process.exit(12);"
              "if(check(url('en.wikipedia:1','en.wikipedia:1')))process.exit(13);"
              "const rich=(q='',ed='',order='magnitude')=>new URLSearchParams({"
              "dataset:'d',method:'m',left:'en.wikipedia:1',right:'ru.wikipedia:2',q,ed,order}).toString();"
              "if(!check(rich('Chess','RU','decrease')))process.exit(14);"
              "if(!check(rich('Chess','RU','volume')))process.exit(21);"
              "if(!check(rich('Chess','RU','daily-rise')))process.exit(22);"
              "for(const q of ['a\\nb','a\\u007fb','x'.repeat(81)])"
              "if(check(rich(q)))process.exit(15);"
              "if(check(rich('','BAD')))process.exit(16);"
              "if(check(rich('','RU','bad')))process.exit(17);"
              "if(check(rich()+'&unexpected=1'))process.exit(18);"
              "if(check(url('en.wikipedia:1','ru.wikipedia:2')+'&q=x'))process.exit(19);"
              "if(check('other=1'))process.exit(20);")
        result = subprocess.run(['node', '-'], input=js, text=True,
                                capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_russian_yo_search_matches_without_rewriting_titles_or_queries(self):
        """Use the actual generated filter JS, not a separate invented matcher."""
        html = render(self.candidate).decode('utf-8')
        self.assertIn('aria-describedby="search-hint"', html)
        self.assertIn('Russian е and ё spellings match for search', html)
        self.assertIn('s.normalize(\'NFC\')', html)
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for generated discovery JavaScript')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        cleaned = 'const cleaned=' + script.split('const cleaned=', 1)[1].split(';', 1)[0] + ';'
        matcher = 'const matchKey=' + script.split('const matchKey=', 1)[1].split(';', 1)[0] + ';'
        filter_fn = ('function filter()' + script.split('function filter()', 1)[1]
                     .split('\nfunction sortTiles()', 1)[0])
        setup = r"""
const search={value:''},edition={value:''},status={textContent:''};
const noResults={hidden:true};
const $=id=>id==='no-results'?noResults:null;
const tiles=[
  {dataset:{text:'RU Чёрная дыра',edition:'RU'},hidden:false},
  {dataset:{text:'EN Black hole',edition:'EN'},hidden:false}
];
const original=tiles[0].dataset.text;
function check(input,ed,expected) {
  search.value=input;edition.value=ed;filter();
  const count=tiles.filter(t=>!t.hidden).length;
  if(count!==expected || status.textContent!==expected+' of 2 histories' ||
     noResults.hidden!==(expected!==0) || search.value!==input ||
     tiles[0].dataset.text!==original)
    throw Error('Incorrect search/identity behavior for '+JSON.stringify([input,ed]));
}
check('черная дыра','RU',1);
check('ЧЁРНАЯ ДЫРА','',1);
check('че\u0308рная дыра','RU',1);
check('чёрная дыра','RU',1);
check('черная дыра','EN',0);
check('черная дырка','RU',0);
check('Black hole','EN',1);
"""
        result = subprocess.run(
            ['node', '-'], input=cleaned + '\n' + matcher + '\n' +
            filter_fn + '\nfunction updateVisibleCsv(){}\n' + setup, text=True, capture_output=True,
            timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plain_text_evidence_summary_uses_exact_weekly_counts_and_source_refs(self):
        """Run the emitted summary formatter in Node with half-integer median controls."""
        html = render(self.candidate).decode('utf-8')
        self.assertIn('id="share-summary" rows="11" readonly hidden', html)
        self.assertIn('id="copy-summary" type="button" hidden', html)
        self.assertIn('Share the evidence as text', html)
        self.assertIn("summary.hidden=true;summary.value='';copySummary.hidden=true", html)
        self.assertIn("Number.isSafeInteger(v)&&v>=0", html)
        self.assertIn('"source_url":', html)
        self.assertIn('"body_sha256":', html)
        self.assertIn("summary.value=['DAYFLARE", html)
        if not shutil.which('node'):
            self.skipTest('Node unavailable for generated evidence formatter')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        actual = ('const evidence=' + script.split('const evidence=', 1)[1]
                  .split('summary.value=', 1)[0])
        setup = r"""
const data={dates:Array.from({length:35},(_,i)=>new Date(Date.UTC(2026,9,11+i)).toISOString().slice(0,10))};
const entry={title:'Measured topic',edition:'EN',source_url:'https://wikimedia.org/api',
             body_sha256:'a'.repeat(64)};
const up=evidence('A','en.wikipedia:12',entry,[100,100,101,101,200]);
const down=evidence('B','en.wikipedia:12',entry,[100,100,101,101,100]);
if(!up.includes('W1 2026-10-11–2026-10-17 UTC: 100 requests') ||
   !up.includes('W5 2026-11-08–2026-11-14 UTC: 200 requests') ||
   !up.includes('Median W1–W4: 100.5; W5 minus median: +99.5 requests') ||
   !down.includes('W5 minus median: -0.5 requests') ||
   !up.includes('en.wikipedia:12') ||
   !up.includes('https://wikimedia.org/api') ||
   !up.includes('Recorded raw response SHA-256: '+'a'.repeat(64)))
  throw Error('Evidence text is not sourced from exact dated weekly metrics');
"""
        result = subprocess.run(['node', '-'], input=actual + chr(10) + setup,
                                text=True, capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pair_csv_export_requires_complete_equivalent_utc_dates(self):
        html = render(self.candidate).decode('utf-8')
        self.assertIn('id="download-csv" download="dayflare-30-pair.csv" hidden', html)
        self.assertIn('utc_date,left_page_id,left_requests,right_page_id,right_requests,dataset_id,method_version', html)
        self.assertIn('data:text/csv;charset=utf-8,', html)
        self.assertIn("const peak=Math.max(1,...ta,...tb)", html)
        self.assertIn('One shared zero-based scale', html)
        self.assertIn('className=\'pair-chart\'', html)
        self.assertIn('className=\'pair-daily\'', html)
        self.assertIn('Inspect all 35 exact UTC days (A and B)', html)
        self.assertIn('Exact daily requests for the same 35-day window', html)
        self.assertIn("csvLink.hidden=true;csvLink.href=''", html)
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['daily'][18]['date'] = '2026-10-11'
        with self.assertRaisesRegex(ValueError, 'incomparable observation window'):
            render(clone)

    def test_week_date_ranges_are_inclusive_and_observed(self):
        html = render(self.candidate).decode('utf-8')
        dates = [point['date'] for point in self.candidate['series'][0]['daily']]
        self.assertEqual(len(dates), 35)
        self.assertEqual(html.count('class="week-date"'), 150)
        for week in range(5):
            exact = dates[week * 7] + '–' + dates[week * 7 + 6] + ' UTC'
            self.assertEqual(html.count(f'<span class="week-date">{exact}</span>'), 30)
        self.assertIn("dates.textContent=data.dates[i*7]+'–'+data.dates[i*7+6]+' UTC'", html)
        self.assertIn('W1–W5 map to inclusive UTC date ranges', html)

    def test_no_js_fallback_hides_inoperative_actions(self):
        """Static histories remain usable without inert interactive controls."""
        html = render(self.candidate).decode('utf-8')
        self.assertIn('<noscript><style>.controls,#compare,.card-actions{display:none!important}</style>', html)
        head, body = html.split('</head>', 1)
        self.assertIn('<noscript><style>.controls,#compare,.card-actions{display:none!important}</style>', head)
        self.assertIn('<noscript><p class="warning" role="note">', body)
        self.assertIn('JavaScript is disabled.', html)
        self.assertIn('Search, filters and comparison require JavaScript.', html)
        self.assertIn('All 30 selected articles and their exact 35-day histories', html)
        self.assertEqual(html.count('<article '), 30)
        self.assertEqual(html.count('<table><caption>Daily requests'), 30)

    def test_reject_incomplete_window_and_unsafe_source_link(self):
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['daily'].pop()
        with self.assertRaises(ValueError):
            render(clone)
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][0]['source']['endpoint'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError):
            render(clone)

    def test_reject_duplicate_page_identity_and_inconsistent_dates(self):
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['project'] = clone['series'][0]['project']
        clone['series'][1]['page_id'] = clone['series'][0]['page_id']
        with self.assertRaises(ValueError):
            render(clone)
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['daily'][0]['date'] = '1900-01-01'
        with self.assertRaises(ValueError):
            render(clone)


    def test_incompatible_share_link_warning_clears_after_repair(self):
        """Exercise the generated inline JS: invalid link -> valid comparison."""
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for comparison interaction test')
        html = render(self.candidate).decode('utf-8')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        setup = r"""
class Element {
  constructor(id='') {
    this.id=id; this.hidden=true; this.value=''; this.textContent='';
    this.dataset={}; this.children=[]; this.handlers={};this.style={};this.attributes={};
  }
  addEventListener(type,fn){this.handlers[type]=fn;}
  setAttribute(name,value){this.attributes[name]=String(value);}
  replaceChildren(...children){this.children=children;}
  append(...children){this.children.push(...children);}
  select(){} focus(){}
}
const elements=Object.create(null);
const el=id=>elements[id]||(elements[id]=new Element(id));
const rows=Object.create(null);
rows['en.wikipedia:1']={title:'A',edition:'EN',values:Array(35).fill(2)};
rows['ru.wikipedia:2']={title:'B',edition:'RU',values:Array(35).fill(3)};
el('dataset').textContent=JSON.stringify({
  dataset:'current',method:'v0',rows,
  dates:Array.from({length:35},(_,i)=>new Date(Date.UTC(2026,9,11+i)).toISOString().slice(0,10)),
  start:'2026-10-11',end:'2026-11-14'
});
const document={
  getElementById:el,querySelectorAll:()=>[],
  createElement:tag=>new Element(tag),
  createElementNS:(ns,tag)=>new Element(tag)
};
const location={
  search:'?dataset=outdated&method=v0&left=en.wikipedia%3A1&right=ru.wikipedia%3A2',
  href:'file:///local/dayflare.html?dataset=outdated#compare'
};
const navigator={clipboard:{writeText:async()=>{}}};
"""
        check = r"""
if(el('invalid-link').hidden!==false) throw Error('Old link warning missing');
if(!el('compare-message').textContent.includes('Incompatible')) {
  throw Error('Old link error missing');
}
el('left').value='en.wikipedia:1';
el('right').value='ru.wikipedia:2';
el('right').handlers.change();
if(el('comparison').children.length!==2 || el('comparison').children[1].id!=='table') {
  throw Error('Exact comparison table missing');
}
const chart=el('comparison').children[0];
const weeks=chart.children[2].children;
if(chart.className!=='pair-chart' || weeks.length!==5 || weeks.some(w=>w.children[0].children.length!==2)) {
  throw Error('Five pairs of chart bars missing');
}
const tableRows=el('comparison').children[1].children[2].children;
if(tableRows.length!==5) throw Error('Weekly date-range rows absent');
const dates=JSON.parse(el('dataset').textContent).dates;
const daily=chart.children[3];
if(!daily||daily.id!=='details'||daily.className!=='pair-daily'||daily.children[0].textContent!=='Inspect all 35 exact UTC days (A and B)'){
  throw Error('Exact daily comparison disclosure missing');
}
const dailyTable=daily.children[1],dailyRows=dailyTable.children[2].children;
if(dailyTable.id!=='table'||dailyRows.length!==35||dailyTable.children[1].children[0].children.length!==3){
  throw Error('35-day three-column comparison table missing');
}
for(const i of [0,17,34]){
  const cells=dailyRows[i].children;
  if(cells.length!==3||cells[0].textContent!==dates[i]||cells[1].textContent!=='2'||cells[2].textContent!=='3'){
    throw Error('Exact daily comparison values mismatch at '+i);
  }
}
for(let i=0;i<5;i++){
  const label=tableRows[i].children[0];
  const expected=dates[7*i]+'–'+dates[7*i+6]+' UTC';
  if(label.textContent!=='W'+(i+1)||label.children[0].textContent!==expected)
    throw Error('Incorrect inclusive UTC week '+i);
}
const heights=weeks.flatMap(w=>w.children[0].children.map(b=>parseFloat(b.style.height)));
if(heights.length!==10 || heights.some(h=>!Number.isFinite(h)||h<0||h>112) || Math.abs(Math.max(...heights)-112)>0.00001) {
  throw Error('Pair bars do not use shared nonnegative scale');
}
if(!el('share-field').value.includes('dataset=current')) {
  throw Error('Recovered link still uses wrong dataset');
}
if(el('invalid-link').hidden!==true) {
  throw Error('Stale error is shown after recovery');
}
if(el('download-csv').hidden || !el('download-csv').href.startsWith('data:text/csv;charset=utf-8,')) {
  throw Error('Valid pair CSV not available');
}
const exported=decodeURIComponent(el('download-csv').href.split(',',2)[1]);
if(exported.trimEnd().split(/\r\n/).length!==36) {
  throw Error('Pair CSV must have a header and 35 exact UTC daily rows');
}
el('search').value='  Chess\t\n  ';
el('search').handlers.input();
el('edition').value='RU';el('edition').handlers.change();
el('sort').value='decrease';el('sort').handlers.change();
const shared=new URL(el('share-field').value);
if(shared.searchParams.get('q')!=='Chess'||shared.searchParams.get('ed')!=='RU'||shared.searchParams.get('order')!=='decrease'||!el('search').value.startsWith('  Chess'))throw Error('Discovery filters dropped from comparison share or edited the live input');
el('search').value='Black ';
el('search').handlers.input();
if(el('search').value!=='Black ')throw Error('Typing removed word separator');
el('search').value+='hole';
el('search').handlers.input();
if(el('search').value!=='Black hole'||new URL(el('share-field').value).searchParams.get('q')!=='Black hole')throw Error('Multiword title/share mismatch');
el('search').value='че\u0308рная дыра';
el('search').handlers.input();
if(new URL(el('share-field').value).searchParams.get('q')!==el('search').value)throw Error('Unicode source search was normalized in shared q');
el('right').value='en.wikipedia:1';
el('right').handlers.change();
if(el('download-csv').hidden!==true || el('download-csv').href!=='') {
  throw Error('Pair CSV available after invalid same-article comparison');
}
"""
        result = subprocess.run(
            ['node', '-'], input=setup + '\n' + script + '\n' + check,
            text=True, capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        restored_setup = setup.replace(
            "search:'?dataset=outdated&method=v0&left=en.wikipedia%3A1&right=ru.wikipedia%3A2'",
            "search:'?dataset=current&method=v0&left=en.wikipedia%3A1&right=ru.wikipedia%3A2&q=Chess&ed=RU&order=decrease'")
        restored_check = r"""
if(el('invalid-link').hidden!==true || el('search').value!=='Chess' ||
   el('edition').value!=='RU' || el('sort').value!=='decrease')
  throw Error('Rich share link did not restore exact discovery controls');
if(el('comparison').children.length!==2 || el('download-csv').hidden)
  throw Error('Rich share link did not restore the comparison');
if(!el('share-field').value.includes('q=Chess&ed=RU&order=decrease'))
  throw Error('Restored share URL lost filter state');
"""
        restored = subprocess.run(
            ['node', '-'], input=restored_setup + '\n' + script + '\n' + restored_check,
            text=True, capture_output=True, timeout=8, check=False)
        self.assertEqual(restored.returncode, 0, restored.stderr)



if __name__ == '__main__':
    unittest.main()
