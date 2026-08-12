# Email authentication for skyscore.co.uk — DKIM, DMARC, SPF

**Status as measured 2026-08-12** (via public DNS, not from Cloudflare):

| Record | Present | Value |
|---|---|---|
| SPF | ✅ | `v=spf1 include:_spf.mx.cloudflare.net ~all` |
| DKIM | ❌ | no selector published (checked `google`, `s1`, `s2`, `k1`, `mail`, `zoho`, `fm1`, `selector1`, `selector2`) |
| DMARC | ❌ | `_dmarc.skyscore.co.uk` does not exist |
| MX | ✅ | `route1/2/3.mx.cloudflare.net` — **Cloudflare Email Routing** |

---

## Corrected 2026-08-12: sending WORKS. It is not ALIGNED.

An earlier draft of this file said there was "no way to send as
@skyscore.co.uk". **That was wrong**, and Bill corrected it: mail already goes
out as `support@skyscore.co.uk` through Gmail's **"Send mail as"**, with
Cloudflare Email Routing handling the inbound side. It has been working.

The accurate problem is narrower and easy to miss precisely because sending
works:

- **Cloudflare Email Routing is receive-only** — that part stands. It forwards
  `support@` to the Gmail inbox and signs nothing outbound.
- **Gmail sends the message and DKIM-signs it as `gmail.com`**, because that is
  the authenticated account. The `From:` header says `support@skyscore.co.uk`.
- Those two domains differ, so **DKIM does not ALIGN with the From: domain**.
  The signature is valid; it just vouches for the wrong domain.

Today nothing enforces that, because no DMARC record exists — which is exactly
why the setup appears fine. The consequences are:

1. **Cold email is already being penalised.** Gmail and Yahoo have required
   aligned SPF+DKIM+DMARC from bulk senders since Feb 2024; unaligned mail from
   an unknown domain is spam-foldered on arrival, not bounced. You would see no
   error.
2. **Publishing DMARC at `p=none` is safe** and changes nothing about delivery.
3. **Moving to `p=quarantine` or `p=reject` would break your own outbound mail**
   unless real DKIM is in place first. This is the trap: the enforcement step
   looks like the finish line and is the thing that bins your own sends.

So "add a DKIM record" still cannot be done in isolation — Gmail will not issue
a DKIM key for a domain it does not host. A sending decision is still needed;
it is an alignment upgrade rather than a from-scratch build.

### Why this matters more than it used to

Since February 2024, Gmail and Yahoo require bulk senders to publish SPF, DKIM
**and** DMARC, with DKIM aligned to the From: domain. Microsoft followed in 2025.
Cold email from an unauthenticated domain is now spam-foldered or rejected at the
gateway — not delivered-but-ignored. This is why the five drafts sitting unsent
since 21 May would not have landed even if they had been sent.

---

## Step 1 — DMARC, do this now (no provider needed)

DMARC is a policy record on the domain itself. Publishing it at `p=none` starts
the reporting feed **without affecting delivery**, so it is safe to add before
any sending decision and it tells you who is already sending as your domain.

**Cloudflare → skyscore.co.uk → DNS → Records → Add record**

```
Type:  TXT
Name:  _dmarc
TTL:   Auto
Content:
v=DMARC1; p=none; rua=mailto:support@skyscore.co.uk; fo=1; adkim=r; aspf=r
```

- `p=none` — monitor only. **Do not start at `quarantine` or `reject`**: with no
  DKIM in place that would bin your own mail.
- `rua=` — where aggregate reports go. `support@skyscore.co.uk` already routes to
  your inbox via Cloudflare, so this works today.
- `adkim=r` / `aspf=r` — relaxed alignment, correct while you are still deciding
  the sending path.

**Move to `p=quarantine` only after** the reports show your legitimate mail
passing for two weeks, and then to `p=reject`.

---

## Step 2 — choose how you will send. This is the real decision.

| Option | Cost | DKIM for skyscore.co.uk? | Notes |
|---|---|---|---|
| **Gmail "Send mail as"** — *what is in place today* | £0 | ❌ **No** | Sends fine and always has. DKIM-signs as `gmail.com`, so it does **not align** with `From: @skyscore.co.uk`. Invisible until DMARC is enforced, at which point it fails. |
| **Google Workspace** | ~£5/user/month | ✅ Yes | Generates a `google._domainkey` record in the admin console. Cheapest option that actually aligns, and you already live in Gmail. |
| **Transactional ESP** (Resend, Postmark, AWS SES) | £0–£15/month | ✅ Yes | Better deliverability reporting and a sending API. SES is already in your AWS account and in-region, but its sandbox needs a production-access request. Overkill for hand-written outreach. |

**Recommendation: Google Workspace.** The outreach is a handful of personal
emails, not a campaign. Workspace gives DKIM alignment, keeps you in the Gmail
interface you already use, and takes about ten minutes. Because
`support@skyscore.co.uk` already exists as a Gmail send-as identity, this is an
upgrade of a working setup rather than a migration — the address, the signature
and the habit all stay.

---

## Step 3 — DKIM, once a provider exists

The provider generates the key; you publish what it gives you. For Google
Workspace:

1. Admin console → **Apps → Google Workspace → Gmail → Authenticate email**
2. Select `skyscore.co.uk`, key length **2048**, prefix `google`
3. It shows a TXT record — publish it in Cloudflare exactly as given:

```
Type:  TXT
Name:  google._domainkey
TTL:   Auto
Content:  v=DKIM1; k=rsa; p=<the long key Google shows you>
```

4. Wait for propagation, then click **Start authentication** in the console.

**Then update SPF** so it authorises Google as well as Cloudflare routing —
one record, not two, because a domain may publish only one SPF record:

```
v=spf1 include:_spf.google.com include:_spf.mx.cloudflare.net ~all
```

---

## Step 4 — verify before sending anything

Do not trust the console's own tick. Check from outside:

```bash
nslookup -type=TXT _dmarc.skyscore.co.uk
nslookup -type=TXT google._domainkey.skyscore.co.uk
nslookup -type=TXT skyscore.co.uk
```

Then send one message to a Gmail address you control, open **Show original**,
and confirm all three read **PASS**:

```
SPF:   PASS   with domain skyscore.co.uk
DKIM:  PASS   with domain skyscore.co.uk     <- the domain matters, not just PASS
DMARC: PASS
```

**DKIM passing for `gmail.com` is not the same as passing for
`skyscore.co.uk`.** That distinction is the whole point of alignment, and it is
the specific way the free option fails while appearing to work.

---

## Why this file exists rather than the change itself

Applying these needs Cloudflare dashboard access, which is not available to this
repo's tooling — the same constraint recorded for the AWS console work in
`DRAFT_security_retention_passage.md` §1. Everything above is measured from
public DNS or taken from the provider's own documentation, so it can be executed
without re-deriving anything.

**Sequence matters:** Step 1 is safe today and starts the reporting clock. Steps
2–4 gate cold outreach. Warm follow-ups from your personal Gmail need none of
this — they are already authenticated as `gmail.com`, which is what they claim
to be.
