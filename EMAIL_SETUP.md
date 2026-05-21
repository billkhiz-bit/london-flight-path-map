# Email setup for skyscore.co.uk

How to get `bilalkhizar@skyscore.co.uk` (and any other addresses on the domain)
working, with reasonable deliverability for B2B outreach.

> **STATUS (2026-05-21): DONE via Cloudflare Email Routing + Gmail "Send mail as".** Three addresses live and tested: `support@`, `info@`, `bilalkhizar@skyscore.co.uk`, all forwarding to `billkhiz@gmail.com` (catch-all left disabled). Outbound via `smtp.gmail.com:587` + a Google app password, "Treat as an alias" **checked**. This is the free route — good for inbound + replying to users. **Not yet on a DKIM-signing provider**, so before any *cold* B2B outreach (the `OUTREACH_LOG.md` targets) from `bilalkhizar@`, revisit the Migadu (€19/yr) section below for proper deliverability. The provider comparison is kept below for that decision.

## Provider comparison

| Provider | Cost | Send + receive? | Best for | Domains covered |
|---|---|---|---|---|
| **Cloudflare Email Routing** | Free | Receive only — replies come from the gmail you forward to | Just want to receive `bilalkhizar@skyscore.co.uk` and forward to your gmail | Per domain |
| **Migadu** | €19/year | Yes | Cost-conscious solo with multiple domains (Cubitt33, Cubitt International, Sky Score all on one plan) | Unlimited |
| **Fastmail** | £3.50/mo (~£42/yr) | Yes | Best UX + privacy (Australian, no US data laws) | 1 domain on basic plan, more on higher tiers |
| **Google Workspace** | £4.60/mo annual (~£55/yr) | Yes | Familiar Gmail UI + Google Drive integration if needed | 1 user / multiple aliases per user |
| **iCloud+ custom domain** | £0.99/mo (~£12/yr) base | Yes (in Apple Mail / iCloud web) | Apple ecosystem only | Up to 5 domains |

## My recommendation

**Migadu** — €19/year unlimited mailboxes on unlimited domains. With three
companies (Cubitt33, Cubitt International, Sky Score) you'd get
business email for all three for the price of one month of Google
Workspace. Swiss-hosted. Reasonable web UI; full SMTP/IMAP for
desktop/mobile clients.

If you prefer a familiar Gmail experience and the £55/year doesn't
sting: **Google Workspace Business Starter**.

If you only need to *receive* (not send) on the custom domain — for
example, you'll list `bilalkhizar@skyscore.co.uk` in outreach but reply from
gmail — **Cloudflare Email Routing is free** and takes 5 minutes.

---

## Setup: Cloudflare Email Routing (free, receive-only)

For when you just need a forwarding alias.

1. Cloudflare dashboard → `skyscore.co.uk` → **Email** → **Email Routing**
2. Click **Get started** → confirm the auto-added MX records (Cloudflare adds 3 MX records + a TXT record automatically)
3. **Routes** → **Create address**:
   - Custom address: `bilalkhizar@skyscore.co.uk`
   - Action: Send to `billkhiz@gmail.com`
4. Verify your gmail address (Cloudflare sends a confirmation)
5. Optional: catch-all → forward `*@skyscore.co.uk` to gmail (helps you not miss anything sent to a typo address)

After setup: any email to `bilalkhizar@skyscore.co.uk` lands in your gmail. **Replies
will be from `billkhiz@gmail.com`** unless you configure Gmail's "Send mail
as" feature with another provider's SMTP credentials.

---

## Setup: Migadu (€19/year, send + receive)

1. Sign up at https://www.migadu.com → Choose "Mini" plan (€19/yr)
2. Add domain `skyscore.co.uk` in Migadu admin
3. Migadu shows you DNS records to add — typically:
   - **MX**: 10 → `aspmx1.migadu.com`
   - **MX**: 20 → `aspmx2.migadu.com`
   - **TXT** (SPF): `v=spf1 include:spf.migadu.com -all`
   - **TXT** (DKIM, key1): `key1._domainkey CNAME key1.your-domain._domainkey.migadu.com`
   - **TXT** (DKIM, key2 + key3): same pattern
   - **TXT** (DMARC): `_dmarc TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@skyscore.co.uk"`
4. Add each record in Cloudflare DNS (proxy: **DNS only / grey cloud**)
5. Create your mailbox: `bilalkhizar@skyscore.co.uk`
6. Set IMAP/SMTP creds in your mail client (Apple Mail / Outlook / Thunderbird) or use Migadu's webmail
7. Send a test email from a different account to verify deliverability

Repeat steps 2-6 for `cubitt33.com` and `cubitt-international.com` if you want them
on the same Migadu plan.

---

## Setup: Google Workspace (£4.60/mo annual)

1. Sign up at https://workspace.google.com → Business Starter plan
2. Verify domain ownership (TXT record in Cloudflare DNS)
3. Set MX records in Cloudflare DNS:
   - **MX** 1 → `smtp.google.com`
   - (Modern Google setup uses a single MX; older guides show 5 MX records — both work)
4. Set up SPF/DKIM:
   - **TXT** (SPF): `v=spf1 include:_spf.google.com ~all`
   - **TXT** (DKIM): generate inside Google Admin → DKIM authentication → publish the long key as `google._domainkey TXT ...`
5. **TXT** (DMARC): `_dmarc TXT "v=DMARC1; p=quarantine; rua=mailto:postmaster@skyscore.co.uk"`
6. Create user `bilalkhizar@skyscore.co.uk`
7. Use Gmail interface or Google Workspace mobile app

---

## Deliverability — non-optional records

Whichever provider you pick, **add all three** of these to Cloudflare DNS or
your B2B emails will hit spam:

| Record | Purpose | Failing → consequence |
|---|---|---|
| **SPF** (TXT on apex) | Tells receivers which IPs are allowed to send mail for skyscore.co.uk | Hits spam at Gmail/Outlook/Yahoo |
| **DKIM** (TXT on `<selector>._domainkey`) | Cryptographic signature on outgoing mail | Soft-fails authentication; spam-flag risk |
| **DMARC** (TXT on `_dmarc`) | Policy telling receivers what to do with SPF/DKIM failures | Without it, spoofed mail "from" you can be delivered |

The provider gives you the exact values to publish — just paste them into
Cloudflare DNS as TXT records, **proxy off (grey cloud)**.

---

## After setup — verify deliverability

Send a test email to **`check-auth@verifier.port25.com`**. It auto-replies
with a full SPF / DKIM / DMARC report. You want all three to show "pass".

Or use https://www.mail-tester.com/ — send a mail to the address they show
and they grade your deliverability out of 10. Aim for ≥ 9/10 before you
send any B2B outreach.

---

## What to do today

1. **Pick a provider** based on the table above (most likely Migadu for
   value or Google Workspace for familiarity)
2. **Sign up + add `skyscore.co.uk` as a domain**
3. **Add the records they specify in Cloudflare DNS** (proxy off on all of them)
4. **Create the mailbox** `bilalkhizar@skyscore.co.uk`
5. **Test deliverability** via mail-tester.com
6. **Use it for the outreach drafts** in `OUTREACH_LOG.md` — HACAN,
   Tier 1 / Tier 2 cold emails, etc. all benefit from being "from"
   the custom domain rather than gmail.com
