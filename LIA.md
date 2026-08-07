# Legitimate Interests Assessment

**Controller:** CUBITT33 LTD (company number 13651304), trading as Sky Score, registered office 50 Pembroke Road, London W8 6NX
**Assessment date:** 2026-08-05
**Controller changed:** 2026-08-07, from Bilal Khizar as a sole trader
**Next review:** 2027-08-05, or on any change to the signup flow, whichever is sooner

> **Status note.** This assessment records the reasoning behind relying on UK
> GDPR Article 6(1)(f) for the processing described below. It is the controller's
> own assessment, not legal advice.
>
> The controller changed on 2026-08-07 from a sole trader to CUBITT33 LTD. The
> balancing test below is unaffected: it turns on what the processing does to
> the data subject, not on who performs it. What does change is that the ICO
> registration must be in the company's name, and that the company is the party
> a data subject would bring a complaint against.

---

## 1. Scope of this assessment

`privacy.html` §2a states two lawful bases for the API signup flow:

| Processing | Lawful basis | Covered here? |
|---|---|---|
| Issuing and operating an API key at the user's request | Art 6(1)(b), performance of a contract | **No.** No LIA is required for 6(1)(b) |
| Enforcing the one-key-per-email limit | Art 6(1)(f), legitimate interests | **Yes** |
| Retaining the email so that check stays possible, and contacting the holder about abuse or deprecation | Art 6(1)(f) | **Yes** |
| Retaining server logs, including source IP addresses, to investigate suspected abuse | Art 6(1)(f) | **Yes** |

Everything else Sky Score does involves no personal data at all. Browsing and
scoring require no account, favourites are keyed to an opaque device token, and
the analytics provider sets no cookies and stores aggregate counts only.

**Personal data in scope:** email address, optional display name, and source IP
addresses appearing in server logs.

---

## 2. Purpose test: is there a legitimate interest?

**The interest.** Preventing abuse of a free, self-service API tier, and being
able to reach a key holder when something is wrong with their key.

**Why it matters.** The free tier issues API keys automatically on request, with
no payment step and no manual review. Without a per-identity limit, one party can
mint unlimited keys and take an unlimited share of a service funded personally by
a sole developer. The quota exists to keep the free tier available to everyone
who wants it; the one-key-per-email check is what makes the quota mean anything.

**Who benefits.** Sky Score, by keeping running costs predictable and the service
available. Other users of the free tier, who would otherwise be crowded out.
Individual key holders, who can be told if their key is being deprecated or has
been compromised rather than discovering it through failure.

**Is it lawful, ethical, and expected?** Yes. Abuse prevention is named in
Recital 47 as a legitimate interest, and rate limiting on a free developer API
is a near-universal industry practice. A developer requesting an API key expects
the provider to know which key is theirs.

**If we could not do this**, the free tier would have to be withdrawn or placed
behind a payment step, which is a worse outcome for users than the processing.

---

## 3. Necessity test: is the processing necessary?

**Does it actually achieve the purpose?** Yes. The email address is the only
identifier collected at signup, so it is the only thing a one-key-per-email check
can be run against. Retention is necessary for the same reason: a uniqueness
check against a register that has been emptied cannot detect anything.

**Is there a less intrusive way?**

| Alternative considered | Why rejected |
|---|---|
| Drop the per-identity limit, rely on the quota alone | Quotas are per key. Unlimited keys means an unlimited quota, so the control does nothing |
| Store a hash of the email instead of the address | Would support the uniqueness check, but not the ability to contact a holder about abuse or deprecation. Worth revisiting if the contact purpose is ever dropped |
| Identify by IP address instead | More intrusive, not less. IPs are shared, reassigned, and would penalise legitimate users behind the same network |
| Require payment details to obtain a key | Substantially more intrusive, and defeats the point of a free tier |

Hashing is the only alternative that is genuinely less intrusive, and it is
recorded above as a live option rather than dismissed. It is not adopted today
because it removes the ability to notify a key holder, which is itself a
protection for them.

**Data minimisation.** One address per key holder. The display name is optional
and the flow works without it. No profile is built, no enrichment is performed,
and the address is never used for marketing.

---

## 4. Balancing test: do the individual's interests override?

**Relationship.** The individual has approached Sky Score and asked for an API
key. This is not data obtained from a third party or scraped.

**Nature of the data.** An email address, usually a developer or work address,
and optionally a display name. **No special category data** under Article 9, no
criminal offence data, no financial data. Source IPs in server logs are personal
data but low sensitivity.

**Reasonable expectations.** A developer signing up for an API key expects the
provider to retain their address, tie it to their key, and email them about it.
The privacy policy states all of this before the form is submitted. There is
nothing here a reasonable person would find surprising.

**Likely impact.** Minimal. The processing does not produce decisions about the
individual, does not affect their access to any service other than a second free
key, and involves no automated decision-making or profiling under Article 22.

**Could it cause harm?** The realistic harm is disclosure of the address through
a security failure. Mitigations: data held in AWS eu-west-2, encrypted in transit
and at rest, no third-party sharing, and no marketing use. The relevant residual
risk is recorded in section 6 below rather than being written out of this
assessment.

**Vulnerable individuals?** Not a group likely to include children or vulnerable
people; the audience is developers integrating an API.

**Safeguards in place.**

- Purpose limitation: the address is used for key issuance, the uniqueness check, and key-related contact only
- No sale, no sharing for marketing, no third-party analytics on the personal data
- Deletion on request, within 30 days, via `support@skyscore.co.uk`
- Right to object under Article 21 is available and stated in the privacy policy
- Retention tied to key life: kept while the key is active

**Conclusion of the balancing test.** The interests of the individual do not
override the legitimate interest. The processing is limited, expected, low
impact, and the individual initiated it.

---

## 5. Outcome

**Article 6(1)(f) is an appropriate lawful basis** for the one-key-per-email
check, the retention that supports it, key-related contact, and the retention of
server logs for abuse investigation.

The Article 21 right to object is engaged. Because the same address is also
processed under 6(1)(b) to operate the key itself, an objection to the 6(1)(f)
processing in practice means closing the key, and that should be explained to
anyone who objects rather than treated as a refusal.

---

## 6. Issue affecting this assessment — CLOSED 2026-08-07

**Server log retention was unlimited. It is now 30 days, verified against the
AWS API.**

The position on 2026-08-05 was that every CloudWatch log group read
`retentionInDays: None`, meaning never expire, while `privacy.html` §2d claimed
7 days. Both halves have been resolved: retention is set to **30 days** on all
seven live groups, `privacy.html` §2d states 30 days, and a blocking preflight
check asserts the two agree in both directions.

This assessment relies on retention being proportionate to the
abuse-investigation purpose. Indefinite retention was not proportionate; a
defined 30-day period is, so **the balancing test above is no longer
conditional**.

The signup Lambda logged raw email addresses between 2026-06-26 and 2026-07-23.
**That log group was deleted on 2026-08-07**, which removes the data rather than
ageing it out.

**Residual, honestly stated:** Lambda recreates a deleted log group with no
retention policy, so the signup group will reappear at *Never Expire* on the next
signup until retention is reapplied. The preflight check goes red when that
happens, so it cannot pass unnoticed, but it is a manual step rather than an
automatic one.

Remediation runbook: `DRAFT_security_retention_passage.md` §1. Until it is
applied, treat section 4's conclusion as conditional.

---

## Related documents

- `privacy.html` - the public notice this assessment supports
- `SUBPROCESSORS.md` - who else touches the data
- `SECURITY.md` - technical and organisational measures
- `terms.html` - terms of use
