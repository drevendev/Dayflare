"""Browser evidence for deterministic, shareable observed-count ordering.

No lifecycle labels, live measurements, or unvalidated cross-edition equivalence.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'Dayflare-M0-portable-historical-UNPUBLISHED.html').read_text(encoding='utf-8')


def cards(page):
    return page.locator('#cards .card h3').all_text_contents()




def assert_status_coverage(page):
    """The live discovery summary matches visible verified M0 cards, not Wikipedia."""
    rows = page.evaluate("""() => [...document.querySelectorAll('#cards .card')].map(card => ({
        edition: card.querySelector('.tag').textContent.startsWith('EN') ? 'EN' : 'RU',
        delta: Number(card.querySelector('.small').textContent.split(' vs. baseline')[0]
                      .replace('−', '-').replace(/,/g, ''))
    }))""")
    summary = page.locator('#status').inner_text()
    assert f"EN {sum(r['edition'] == 'EN' for r in rows)}, RU {sum(r['edition'] == 'RU' for r in rows)}" in summary, summary
    assert (f"increase {sum(r['delta'] > 0 for r in rows)}, "
            f"decrease {sum(r['delta'] < 0 for r in rows)}, "
            f"unchanged {sum(r['delta'] == 0 for r in rows)}") in summary, summary
    assert ('No matches in this six-series sample' if not rows
            else f'{len(rows)} of 6 measured series') in summary, summary


with sync_playwright() as playwright:
    browser = launch_chromium(playwright)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width':width,'height':850},reduced_motion='reduce')
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.set_content(HTML,wait_until='load')
        page.wait_for_function("document.querySelectorAll('#cards .card').length===6")
        rows=page.evaluate("""() => [...document.querySelectorAll('#cards .card')].map(el => ({
            name:el.querySelector('h3').textContent,
            delta:el.querySelector('.small').textContent,
        }))""")
        assert page.locator('#order').input_value()=='magnitude'
        assert_status_coverage(page)
        # Read the exact observed metric from app-rendered cards; compare order
        # without depending on one source's changing editorial subject names.
        magnitudes=[abs(float(r['delta'].split(' vs.')[0].replace('−','-').replace('+','').replace(',',''))) for r in rows]
        assert magnitudes==sorted(magnitudes,reverse=True), (width,magnitudes)
        page.locator('#order').select_option('decrease')
        decrease=page.evaluate("""() => [...document.querySelectorAll('#cards .card .small')]
            .filter(el=>el.textContent.includes(' vs. baseline'))
            .map(el=>Number(el.textContent.split(' vs. baseline')[0].replace('−','-').replace(/,/g,'')))""")
        assert decrease==sorted(decrease), (width,decrease)
        url=page.url
        assert parse_qs(urlsplit(url).query)['o']==['decrease'],url
        page.locator('#edition').select_option('ru.wikipedia.org')
        assert page.locator('#cards .card').count()==3
        assert_status_coverage(page)
        selected_ru=cards(page)
        page.set_content(HTML,wait_until='load')
        page.wait_for_function("document.querySelectorAll('#cards .card').length===3")
        assert page.locator('#order').input_value()=='decrease'
        assert cards(page)==selected_ru
        assert_status_coverage(page)
        page.locator('#order').select_option('source')
        assert 'o=source' in page.url
        # Reset must be reachable even with matching cards on screen.
        assert page.locator('#clear').is_visible()
        page.locator('#clear').click()
        assert page.locator('#cards .card').count()==6
        assert_status_coverage(page)
        page.locator('#query').fill('nothing-in-six-series')
        assert page.locator('#cards .card').count()==0
        assert_status_coverage(page)
        page.locator('#query').fill('')
        assert_status_coverage(page)
        assert page.locator('#order').input_value()=='source', 'Clear filters must not unexpectedly change selected order'
        page.locator('#order').select_option('magnitude')
        assert 'o=' not in page.url, 'Default ordering should have a canonical shorter link'
        # A duplicate or unsupported order never substitutes a different order.
        for bad in ('o=source&o=decrease','o=unsupported'):
            # Use History API, not network navigation, for controlled DOM.
            page.evaluate("(bad)=>{const u=new URL(location.href);u.search='?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&'+bad;history.replaceState({},'',u.toString())}",bad)
            page.evaluate("window.dispatchEvent(new PopStateEvent('popstate'))")
            assert page.locator('#retry').is_visible(), (width,bad)
            assert page.locator('#cards .card').count()==0,(width,bad)
            assert page.locator('#detail').is_hidden(),(width,bad)
            assert page.locator('#order').is_disabled(),(width,bad)
            page.locator('#retry').click()
            assert page.locator('#order').is_enabled()
            assert page.locator('#cards .card').count()==6
            assert_status_coverage(page)
        assert not errors,(width,errors)
        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth'), width
        print(f'PASS {width}px: numeric ordering, edition filter, versioned restoration, fail-closed and recovery')
        page.close()
    browser.close()
