"""News by email opens and closes as ONE change (Bill, 2026-11-22; it replaced the area updates list's flag test).

Open means four things at once, and this holds them together so none can go live alone:
  - the front page draws the strip (home/index.html `#news`, not `hidden`),
  - backend/template.yaml's UpdatesList default is 'on' (the Lambda accepts source 'updates'),
  - SignupVerify's default is 'on' (the list exists only behind a confirmation email),
  - privacy.html s2a carries the "News by email" paragraph (id="news"), the wording Bill approved that day.
And the words a visitor sees are the words the Lambda stores as their consent, word for word: the strip's heading and
promise, js/news-signup.mjs's PROMISE and app.py's NEWS_PROMISE. News only since news-v2 (Bill, 2026-11-22): no
postcode box on the page, no postcode in the privacy paragraph, none sent by the module, and the page says what one
click on the link does.
(The template's defaults only matter to a new stack: SAM keeps a live stack's values, so a deploy passes
UpdatesList explicitly, docs/lessons/public-surfaces.md; the defaults record the intended state.)
"""

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding='utf-8')


def template_default(name):
    t = read('backend', 'template.yaml').replace('\r\n', '\n')
    m = re.search(rf"\n  {name}:\n(?:    .*\n)+", t)
    assert m, name
    return re.search(r"Default: '(\w+)'", m.group(0)).group(1)


def strip_tag():
    m = re.search(r'<section class="news-strip" id="news"[^>]*>', read('home', 'index.html'))
    assert m, 'the front page has the news strip'
    return m.group(0)


def strip_open():
    return ' hidden' not in strip_tag()


def module_const(name):
    return re.search(rf"export const {name} = '([^']+)';", read('js', 'news-signup.mjs')).group(1)


def lambda_const(name):
    return re.search(rf"^{name} = '([^']+)'", read('backend', 'lambdas', 'signup', 'app.py'), re.M).group(1)


def text_of(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', fragment))).strip()


def test_the_strip_the_lambda_and_the_privacy_text_open_together():
    open_ = strip_open()
    privacy = read('privacy.html')
    assert (template_default('UpdatesList') == 'on') == open_
    assert ('<p id="news">' in privacy and 'News by email (optional' in privacy) == open_, \
        'the privacy paragraph ships in the same change as the strip'
    if open_:
        assert template_default('SignupVerify') == 'on', 'the list exists only behind a confirmation email'


def test_the_strip_says_what_the_lambda_records():
    assert module_const('PROMISE') == lambda_const('NEWS_PROMISE')
    page = read('home', 'index.html')
    heading = text_of(re.search(r'<h2 id="news-h">(.*?)</h2>', page, re.S).group(1))
    promise = text_of(re.search(r'<div class="news-words"><h2 id="news-h">.*?</h2><p>(.*?)</p>', page, re.S).group(1))
    assert f'{heading}. {promise}' == module_const('PROMISE'), (heading, promise)


def test_news_only_on_the_page_in_the_module_and_in_the_privacy_paragraph():
    # news-v2 (Bill, 2026-11-22): each of these, alone, would offer or describe a postcode the others no longer take.
    page = read('home', 'index.html')
    strip = re.search(r'<section class="news-strip".*?</section>', page, re.S).group(0)
    assert 'type="checkbox"' not in strip and 'postcode' not in strip.lower(), 'the strip offers news only'
    module = read('js', 'news-signup.mjs')
    assert 'postcode:' not in module and "source: 'updates' }" in module, 'the module sends the address and nothing else'
    news = re.search(r'<p id="news">(.*?)</p>', read('privacy.html'), re.S).group(1)
    assert 'postcode' not in news.lower(), 'the privacy paragraph names no postcode'
    assert 'Opening the link in that email confirms it.' in text_of(news), 'it says what one click does'
    assert lambda_const('NEWS_CONSENT_VERSION').startswith('news-v2'), 'new words, new version'


def test_the_privacy_link_reaches_the_paragraph():
    assert 'href="/privacy#news"' in read('home', 'index.html')
    assert '<p id="news">' in read('privacy.html')


def test_the_button_ships_disabled_until_the_module_binds_it():
    # Code review 2026-11-22: without the module, a press posted the address to the site itself (the form has no action).
    page = read('home', 'index.html')
    assert '<button type="submit" disabled>Sign me up</button>' in page
    assert 'button.disabled = false;' in read('js', 'news-signup.mjs')


def test_the_do_not_email_list_has_a_way_back_and_its_runbook_reads_what_the_lambda_reads():
    # Bill's pick A, 2026-11-24. The code review found that since audit I-1 a listed address gets no confirmation for ANY
    # sign-up, while the form answers it as any other, and nothing said how to come off the list. The privacy paragraph
    # now says how, /changes dates it, and OPERATIONS s3.10's steps name the table and the key the Lambda reads.
    news = re.search(r'<p id="news">(.*?)</p>', read('privacy.html'), re.S).group(1)
    way = re.search(r'<span id="news-way-back">(.*?)</span>', news, re.S)
    assert way, 'the news paragraph says how to come off the do-not-email list'
    words = text_of(way.group(1))
    for part in ('an API key', 'the score-update list', 'support@skyscore.co.uk from that address', 'take the address off'):
        assert part in words, part
    assert 'href="/privacy#news-way-back"' in read('changes.html'), 'the change is dated on /changes'
    app = read('backend', 'lambdas', 'signup', 'app.py')
    table = re.search(r"^MAIL_TABLE = os\.environ\.get\('MAIL_TABLE', '([^']+)'\)", app, re.M).group(1)
    assert "Key=_mail_key('suppress', email)" in app, 'the Lambda reads suppress#<email>'
    assert "email = (body.get('email') or '').strip().lower()" in app, 'the key is the address in lower case'
    ops = read('OPERATIONS.md')
    step = ops[ops.index('**The way back off the do-not-email list'):ops.index('**Gates, all met 2026-11-22:**')]
    assert f'--table-name {table} ' in step and 'suppress#$E' in step, 'the runbook names the table and key the Lambda reads'
    assert 'attribute_exists(pk)' in step, 'the delete removes only an entry that is there'
