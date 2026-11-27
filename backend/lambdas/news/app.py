"""News by email: the monthly issue's sender (Bill's picks, 2026-11-23; mock-up claude.ai/artifact/LDJ4ZV7JW5vjSDFwDvDnFn).

WHO PRESSES SEND. Bill does, from the AWS console's Test tab: this function has NO route, so nothing on the internet can
reach it, and the deploy credentials cannot invoke it. Two events, in this order:

    {"issue": "2026-12", "mode": "preview", "to": "you@example.com"}       one copy to one address, "[Preview]" in front
    {"issue": "2026-12", "mode": "send", "confirm": "send 2026-12"}         the confirmed members, once each

WHAT IT PROMISES, each held by backend/tests/test_news_sender.py:
  - only confirmed members (`updates#<email>` rows carrying the consent wording), never a pending sign-up;
  - the do-not-email list (`suppress#<email>`) is read before EVERY send (privacy s2a: "so we never write to it again");
  - every email carries its member's own working unsubscribe link and the RFC 8058 one-click headers; a member without a
    token gets no email, because an email we cannot stop must never go;
  - at most one email a month: the issue's id IS its month, a send is refused outside that month, and a `sent#<issue>#`
    row per member, CLAIMED before the send and keyed by a hash of the address, makes a second run send nothing twice
    (so a run cut short is finished by running it again); the rows expire a week after the month (audit I-3, M-2);
  - only an issue whose file says "approved": true is sent to the list (Bill sets it, in the repo, after the preview);
  - layout A (the letter), the fixed subject "Sky Score news: <Month YYYY>", every link on skyscore.co.uk with the
    campaign tags js/count.mjs allows (totals only, never who), no images, nothing remote, no tracking pixel;
  - the plain-text part carries the same words.
"""
from __future__ import annotations

import calendar
import datetime as dt
import email.policy
import hashlib
import html
import json
import logging
import os
import re
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-2')
MAIL_TABLE = os.environ.get('MAIL_TABLE', 'london-flight-map-mail')
SES_FROM = os.environ.get('SES_FROM', 'Sky Score <noreply@skyscore.co.uk>')
SES_REPLY_TO = 'Sky Score <support@skyscore.co.uk>'
SITE = os.environ.get('CONFIRM_URL_BASE', 'https://skyscore.co.uk').rstrip('/')
ISSUES = Path(__file__).resolve().parent / 'issues'
ISSUE_ID = re.compile(r'^(\d{4})-(0[1-9]|1[0-2])$')
EMAIL = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
TOKEN = re.compile(r'^[A-Za-z0-9_-]{20,64}$')
# A preview's unsubscribe link has the shape of a real one and names nobody (the page says "You are not on the list").
PREVIEW_LINK_ID = 'preview-not-a-real-unsubscribe-token'
# js/count.mjs CAMPAIGN_KEYS: the site counts visits from an issue in total; nothing names who clicked.
CAMPAIGN = (('utm_source', 'news'), ('utm_medium', 'email'))
FOOTER = "You're getting this because you signed up for Sky Score news at skyscore.co.uk. At most one email a month."
FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

_BOTO = Config(connect_timeout=5, read_timeout=10, retries={'max_attempts': 2, 'mode': 'standard'})
# SES is NOT retried (audit M-2, 2026-11-27): a SendEmail that timed out may already have been taken, and a retry would
# send the member a second copy. A failed send gives its claim back instead, so the next run sends it once.
# total_max_attempts, NOT max_attempts: botocore reads `max_attempts: N` as N RETRIES (it stores N + 1 as the total;
# botocore/args.py), so `max_attempts: 1` would still have retried once. One attempt in all is `total_max_attempts: 1`.
_SES_BOTO = Config(connect_timeout=5, read_timeout=10, retries={'total_max_attempts': 1, 'mode': 'standard'})
ddb = boto3.client('dynamodb', region_name=AWS_REGION, config=_BOTO)
ses = boto3.client('sesv2', region_name=AWS_REGION, config=_SES_BOTO)

# The INBOX an address reaches, mirrored from the signup Lambda's mailbox_key() (backend/tests/test_mailbox_key_parity.py
# holds the two equal): `name+tag@` reaches `name@` everywhere, and Gmail ignores dots. The do-not-email list is read by
# the address AND its inbox (audit I-2, 2026-11-27), so `alice+news@gmail.com` hears nothing once `alice@gmail.com` asked.
DOT_BLIND_DOMAINS = {'gmail.com': 'gmail.com', 'googlemail.com': 'gmail.com'}


def mailbox_key(email: str) -> str:
    local, _, domain = email.rpartition('@')
    local = local.split('+', 1)[0]
    if domain in DOT_BLIND_DOMAINS:
        local = local.replace('.', '')
        domain = DOT_BLIND_DOMAINS[domain]
    return f'{local}@{domain}'


def suppress_keys(email: str) -> list[str]:
    inbox = mailbox_key(email)
    return [email] if inbox == email else [email, inbox]


def sent_key(iid: str, email: str) -> str:
    """The record that this member has this issue, keyed by a one-way hash, never the address (audit I-3, 2026-11-27):
    privacy s2a keeps nothing but the do-not-email entry once someone unsubscribes, and these rows outlived them."""
    return f'{iid}#{hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]}'


def sent_expires(iid: str) -> int:
    """An issue can only go out in its own month (send() refuses any other), so its records are needed until that month
    ends: they expire a week after it (MailTable's TTL on expiresAt), and nothing about a member outlives the month."""
    year, month = (int(p) for p in iid.split('-'))
    last = calendar.monthrange(year, month)[1]
    end = dt.datetime(year, month, last, tzinfo=dt.UTC) + dt.timedelta(days=8)
    return int(end.timestamp())


class Refused(Exception):
    """The event or the issue is not one this function will send; nothing has been sent."""


# ---- the issue --------------------------------------------------------------------------------------------------

def month_name(issue_id: str) -> str:
    year, month = ISSUE_ID.match(issue_id).groups()
    return dt.date(int(year), int(month), 1).strftime('%B %Y')


def load_issue(issue_id: str) -> dict:
    """The issue file, checked: its id is its month, the subject is the fixed form, every link is ours."""
    if not isinstance(issue_id, str) or not ISSUE_ID.match(issue_id):
        raise Refused('issue must be YYYY-MM')
    path = ISSUES / f'{issue_id}.json'
    if not path.is_file():
        raise Refused(f'no issue file {issue_id}.json')
    issue = json.loads(path.read_text(encoding='utf-8'))
    if issue.get('id') != issue_id:
        raise Refused('the file names another issue')
    want = f'Sky Score news: {month_name(issue_id)}'
    if issue.get('subject') != want:
        raise Refused(f'the subject must be "{want}"')
    items = issue.get('items') or []
    if not items:
        raise Refused('an issue with nothing new is not sent: at most monthly means a quiet month sends nothing')
    for item in items:
        for key in ('title', 'body', 'link', 'label'):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise Refused(f'every item needs a {key}')
        parts = urlsplit(item['link'])
        if parts.scheme != 'https' or parts.netloc != 'skyscore.co.uk' or parts.query or parts.fragment:
            raise Refused(f'links go to a skyscore.co.uk page, without a query: {item["link"]}')
    return issue


def tagged(link: str, issue_id: str) -> str:
    return f'{link}?{urlencode(CAMPAIGN + (("utm_campaign", issue_id),))}'


def unsubscribe_url(token: str) -> str:
    return f'{SITE}/v1/signup/unsubscribe?{urlencode({"token": token})}'


def render(issue: dict, token: str, preview: bool = False) -> tuple[str, str, str]:
    """(subject, plain text, HTML): layout A, the letter. Every word escaped; no image, nothing remote."""
    e = html.escape
    iid = issue['id']
    subject = ('[Preview] ' if preview else '') + issue['subject']
    stop = unsubscribe_url(token)
    heading = issue.get('heading') or "What's new this month"
    intro = issue.get('intro') or ''

    text = [heading, '']
    if intro:
        text += [intro, '']
    for item in issue['items']:
        text += [item['title'], item['body'], f'{item["label"]}: {tagged(item["link"], iid)}', '']
    text += [FOOTER, f'Unsubscribe in one click: {stop}', '', 'Sky Score - https://skyscore.co.uk', '']

    rows = [
        '<tr><td bgcolor="#dbe4e8" style="background:#dbe4e8;padding:18px 24px;border-radius:18px 18px 0 0">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="font:700 17px/1.3 {FONT};color:#141414">Sky Score</td>'
        f'<td align="right" style="font:400 13px/1.3 {FONT};color:#3a4448">News by email</td></tr></table>'
        f'<div style="margin-top:4px;font:400 14px/1.45 {FONT};color:#3a4448">{e(month_name(iid))}</div></td></tr>',
        f'<tr><td style="padding:22px 24px 0;font:700 22px/1.3 {FONT};color:#141414">{e(heading)}</td></tr>',
    ]
    if intro:
        rows.append(f'<tr><td style="padding:8px 24px 0;font:400 16px/1.55 {FONT};color:#3a4448">{e(intro)}</td></tr>')
    for item in issue['items']:
        rows += [
            '<tr><td style="padding:18px 24px 0"><div style="border-top:1px solid #dedcd6;font-size:0;line-height:0">'
            '&nbsp;</div></td></tr>',
            f'<tr><td style="padding:16px 24px 0;font:700 17px/1.4 {FONT};color:#141414">{e(item["title"])}</td></tr>',
            f'<tr><td style="padding:6px 24px 0;font:400 15.5px/1.55 {FONT};color:#141414">{e(item["body"])}</td></tr>',
            f'<tr><td style="padding:8px 24px 0;font:400 15px/1.5 {FONT}"><a href="{e(tagged(item["link"], iid), quote=True)}" '
            f'style="color:#141414;font-weight:600">{e(item["label"])} &rarr;</a></td></tr>',
        ]
    rows.append('<tr><td style="padding:24px 0 0"></td></tr>')
    page = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">'
        f'<title>{e(subject)}</title></head><body style="margin:0;padding:0;background:#f4f3ef">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f3ef"><tr>'
        '<td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;'
        'background:#ffffff;border:1px solid #dedcd6;border-radius:18px;border-collapse:separate">'
        + ''.join(rows) + '</table>'
        f'<div style="max-width:560px;padding:16px 12px 0;font:400 12.5px/1.5 {FONT};color:#55554f">{e(FOOTER)} '
        f'<a href="{e(stop, quote=True)}" style="color:#55554f">Unsubscribe in one click</a>.<br>'
        'Sky Score - <a href="https://skyscore.co.uk" style="color:#55554f">skyscore.co.uk</a></div>'
        '</td></tr></table></body></html>'
    )
    return subject, '\n'.join(text), page


def message(to: str, subject: str, text: str, page: str, stop: str) -> bytes:
    """The raw MIME: plain text and HTML, Reply-To support@, and RFC 8058's one-click unsubscribe headers (the POST the
    signup Lambda already accepts on /v1/signup/unsubscribe)."""
    msg = MIMEMultipart('alternative')
    msg['From'] = SES_FROM
    msg['To'] = to
    msg['Reply-To'] = SES_REPLY_TO
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=False)
    msg['Message-ID'] = make_msgid(domain='skyscore.co.uk')
    msg['List-Unsubscribe'] = f'<{stop}>'
    msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    msg.attach(MIMEText(page, 'html', 'utf-8'))
    # SMTP policy: CRLF line ends and RFC 5322 folding, which mail apps unfold (a long List-Unsubscribe folds before
    # its "<", never inside the address).
    return msg.as_bytes(policy=email.policy.SMTP)


# ---- the list ---------------------------------------------------------------------------------------------------

def _key(kind: str, value: str) -> dict:
    return {'pk': {'S': f'{kind}#{value}'}}


def members() -> list[dict]:
    """Confirmed members: `updates#` rows that carry a consent. A pending sign-up lives in another table and never here."""
    out, kw = [], {}
    while True:
        page = ddb.scan(TableName=MAIL_TABLE, FilterExpression='begins_with(pk, :p)',
                        ExpressionAttributeValues={':p': {'S': 'updates#'}}, ConsistentRead=True, **kw)
        for item in page.get('Items', []):
            if 'consent' in item and 'email' in item:
                out.append({'email': item['email']['S'], 'token': item.get('unsubToken', {}).get('S', '')})
        if 'LastEvaluatedKey' not in page:
            return sorted(out, key=lambda m: m['email'])
        kw = {'ExclusiveStartKey': page['LastEvaluatedKey']}


def _exists(kind: str, value: str) -> bool:
    return 'Item' in ddb.get_item(TableName=MAIL_TABLE, Key=_key(kind, value), ConsistentRead=True)


def _send(to: str, raw: bytes) -> None:
    ses.send_email(FromEmailAddress=SES_FROM, Destination={'ToAddresses': [to]}, Content={'Raw': {'Data': raw}})


# ---- the two events ---------------------------------------------------------------------------------------------

def preview(issue: dict, to: str) -> dict:
    if not isinstance(to, str) or not EMAIL.match(to):
        raise Refused('a preview needs "to": one email address')
    subject, text, page = render(issue, PREVIEW_LINK_ID, preview=True)
    _send(to, message(to, subject, text, page, unsubscribe_url(PREVIEW_LINK_ID)))
    logger.info('[NEWS_PREVIEW] issue=%s', issue['id'])
    return {'mode': 'preview', 'issue': issue['id'], 'sent': 1}


STOP_WITH_MS_LEFT = 5000  # the function's 28 s: stop before the next send could be cut off between its claim and SES


def send(issue: dict, confirm: str, today: dt.date | None = None, pause: float = 0.1, ms_left=None) -> dict:
    """`ms_left` is the Lambda context's get_remaining_time_in_millis: with under STOP_WITH_MS_LEFT left the run stops,
    says so, and the next run carries on. Each member's copy is CLAIMED (a conditional sent# write) before SES is asked,
    so nothing is ever sent twice; a run cut off between the claim and the send would leave that member without the
    month's issue, the safer side for a list of people who asked for at most one email a month (audit M-2, 2026-11-27)."""
    iid = issue['id']
    if confirm != f'send {iid}':
        raise Refused(f'to send to the list, "confirm" must be exactly "send {iid}"')
    if issue.get('approved') is not True:
        raise Refused('the issue file is not approved: preview it, then set "approved": true in the repo')
    today = today or dt.datetime.now(dt.UTC).date()
    if today.strftime('%Y-%m') != iid:
        raise Refused(f'issue {iid} can only go out in its own month (today is {today:%Y-%m}): at most one a month')
    counts = {'sent': 0, 'already': 0, 'do_not_email': 0, 'no_token': 0, 'failed': 0, 'stopped_early': False}
    for m in members():
        email = m['email']
        if ms_left is not None and ms_left() < STOP_WITH_MS_LEFT:
            counts['stopped_early'] = True
            logger.warning('[NEWS_STOPPED_EARLY] issue=%s: run the same event again to carry on', iid)
            break
        claimed = None
        try:
            # The do-not-email list before EVERY send, by the address and by its inbox (audit I-2, 2026-11-27).
            if any(_exists('suppress', k) for k in suppress_keys(email)):
                counts['do_not_email'] += 1
                continue
            if not TOKEN.match(m['token']):
                counts['no_token'] += 1
                logger.error('[NEWS_NO_TOKEN] issue=%s', iid)
                continue
            # CLAIM the member's copy BEFORE sending (audit M-2, 2026-11-27): a conditional write, so two runs at once,
            # or a run after a write that failed, can never send twice. Until then the record was written after SES
            # took the email, unconditionally, so a failed write meant a second copy on the re-run.
            key = sent_key(iid, email)
            try:
                ddb.put_item(TableName=MAIL_TABLE, Item={**_key('sent', key), 'expiresAt': {'N': str(sent_expires(iid))}},
                             ConditionExpression='attribute_not_exists(pk)')
            except ClientError as err:
                if err.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
                    counts['already'] += 1
                    continue
                raise
            claimed = key
            subject, text, page = render(issue, m['token'])
            _send(email, message(email, subject, text, page, unsubscribe_url(m['token'])))
            claimed = None
            counts['sent'] += 1
            if pause:
                time.sleep(pause)  # well under SES's send rate
        except (ClientError, BotoCoreError) as err:
            code = getattr(err, 'response', {}).get('Error', {}).get('Code', type(err).__name__)
            logger.error('[NEWS_SEND_FAILED] issue=%s code=%s', iid, code)
            counts['failed'] += 1
            if claimed:
                # The send failed, so the claim is given back and the next run sends this member once.
                try:
                    ddb.delete_item(TableName=MAIL_TABLE, Key=_key('sent', claimed))
                except (ClientError, BotoCoreError) as undo:
                    undo_code = getattr(undo, 'response', {}).get('Error', {}).get('Code', type(undo).__name__)
                    logger.error('[NEWS_CLAIM_NOT_GIVEN_BACK] issue=%s code=%s', iid, undo_code)
    logger.info('[NEWS_SENT] issue=%s %s', iid, json.dumps(counts, sort_keys=True))
    return {'mode': 'send', 'issue': iid, **counts}


def handler(event, context):
    """The console's Test event. Returns what happened in words and counts; never an address."""
    try:
        event = event if isinstance(event, dict) else {}
        issue = load_issue(event.get('issue'))
        mode = event.get('mode')
        if mode == 'preview':
            return preview(issue, event.get('to'))
        if mode == 'send':
            return send(issue, event.get('confirm'), ms_left=getattr(context, 'get_remaining_time_in_millis', None))
        raise Refused('mode must be "preview" or "send"')
    except Refused as why:
        logger.warning('[NEWS_REFUSED] %s', why)
        return {'refused': str(why), 'sent': 0}
