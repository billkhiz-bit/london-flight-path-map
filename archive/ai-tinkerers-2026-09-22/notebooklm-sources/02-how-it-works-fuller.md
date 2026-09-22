# How the application works, in plain English

Written 2026-09-21 for the AI Tinkerers demo. Every fact here was checked
against the code and the deployment the same day. Read it once slowly; then
the diagrams and the script will make sense on their own.

---

## 1. What it is, in one paragraph

A postcode goes in. A score from 0 to 10 comes out, telling you how liveable
that spot is - built from eight things: aircraft noise, road noise, air
quality, flood risk, house prices, crime, school results and transport. Every
one of those eight comes from an official government dataset, and every
number can be traced back to where it came from. There are two front doors:
a **website with a map** for people, and an **API** for businesses (an API is
just a way for one program to ask another for data - send a postcode, get
numbers back). There is also a small **AI assistant** on the API that can
explain a score in a sentence, and the whole point of the demo is the forty
lines that keep that assistant honest.

---

## 2. What happens when someone searches a postcode on the website

1. You type `SW11 1AA` into the map site.
2. The site asks a free public service (postcodes.io) "where is this
   postcode, and which borough is it in?"
3. The site **already holds every borough's numbers** - they were downloaded
   with the page. So it looks up the borough (Wandsworth), applies the
   scoring formula in your browser, and draws the score. Nothing is invented
   on the spot; it is arithmetic over numbers that were computed weeks ago
   from the government files.
4. For aircraft noise it goes one step finer: a file of ~42,000 postcodes
   where DEFRA actually measured the noise. If your postcode is in it, that
   measurement is used; if not, distance-from-the-flight-path geometry
   stands in.
5. Four small helpers are called to fill the side panel: energy certificates
   (`/epc`), recent sold prices (`/sold-prices`), nearest stations and line
   status (`/transport`), and nearby GPs/pharmacies (`/nhs`). Each one is a
   tiny program on Amazon that fetches from a public source and hands it back.

That is the consumer path. It is deliberately simple, and it never touches
the AI.

---

## 3. What happens when a business calls the API

1. The business sends `postcode=SW11 1AA` with its API key (a password that
   identifies them and counts their usage - the free tier is 10,000 calls a
   month).
2. Amazon's **API Gateway** checks the key and passes the request to the
   **scoring program** (a Lambda - see section 6).
3. The scoring program looks the postcode up in a table of **2.7 million UK
   postcodes** (the ONS's own list, loaded into a database), which gives it
   the location and the borough.
4. It fetches that postcode's DEFRA noise sample from a second table, if
   there is one.
5. It applies the same scoring formula the website uses, and returns the
   score, the eight components, the weights used, and **a list of the
   sources** - because the business's own auditors will ask.

The website and the API must give the same answer for the same place. There
is an automated check that compares them for every borough and a sample of
postcodes, because on two occasions they disagreed while every input matched.

---

## 4. Where the eight numbers come from

Each input is built by a script that downloads the official file, computes
the figure per borough (or per postcode), and writes it into the data. Each
script also has a `--check` mode that re-derives the figure from the source
and fails if the published number has drifted. That is what "traceable" means
in practice.

| Input | Source | How it is measured |
|---|---|---|
| Aircraft noise | DEFRA noise maps (2021) + airport geometry | measured decibels where DEFRA mapped; distance from flight paths elsewhere |
| Road noise | DEFRA road-noise maps | share of a borough's addresses above the WHO guideline |
| Air quality | DEFRA background maps | worse of NO2 / fine particles, against WHO guidelines |
| Flood risk | Environment Agency | share of addresses at medium-or-high risk |
| House prices | HM Land Registry price index | borough median, and 12-month change adjusted for inflation |
| Crime | ONS recorded crime | offences per 1,000 people |
| Schools | Department for Education "Progress 8" | how much pupils progress vs expectation |
| Transport | Department for Transport station register | share of addresses within 800 m of a station |

All of it is Open Government Licence - free to use with attribution.

---

## 5. The AI assistant, and the forty lines (the demo)

The assistant is one address on the API: `/v1/chat`. Send a question and a
postcode; get back a sentence and a flag called `grounded`.

1. The assistant program fetches the score for that postcode by calling the
   scoring program **directly** (not over the web - so the data it gets is
   exactly what the API would return).
2. It hands that data, plus the question, to the AI model - **Amazon Nova 2
   Lite** - with instructions that say: explain these numbers; use nothing
   else; never invent a figure.
3. The model writes a sentence.
4. Then forty lines of ordinary Python run `verify_answer`:
   - pull every number out of the data the model was given (the "haystack");
   - pull every number out of the model's sentence;
   - every number in the sentence must be in the haystack.
5. If they all are, the sentence ships with `grounded: true`. If even one is
   missing, the sentence is **thrown away**, replaced with "I can't answer
   that from the data I have", and the offending numbers are written to the
   log.

Why throw it away rather than add a warning? Because a warning next to a
made-up number still ships the number, and people read the number. It also
means a *correct* answer can be discarded - "50 out of 100" is right, but 50
and 100 aren't in the data - and that trade is taken on purpose.

The check had three holes over five weeks, each one found by writing a test
that failed first and then fixing the code. The third was found rehearsing
this very demo. That is the second lesson: a check that has never gone red
has not been tested.

---

## 6. The Amazon pieces, in plain words

Everything runs on AWS in London (`eu-west-2`), except the AI model. Nothing
is a server that sits switched on; every piece wakes when asked and you pay
for what runs.

| Service | Plain meaning | What it does here |
|---|---|---|
| **S3** | a file cabinet in the cloud | holds the website's files (the page, the map data, the 100 area pages) |
| **CloudFront** | a worldwide network of copies | serves those files fast from a location near the visitor; also caches the score badge image |
| **API Gateway** | the front desk for the API | checks API keys, counts usage against the free tier, rate-limits every route, hands requests to the right program |
| **Lambda** (x8) | a small program that only runs when called | the scoring engine, the assistant, key sign-up, favourites, and the four helpers (EPC, sold prices, transport, NHS). Written in Python. |
| **DynamoDB** (5 tables) | a very fast lookup table | the 2.7M-row postcode index, the DEFRA noise samples per postcode, favourites, sign-ups, pending sign-ups |
| **Bedrock** | Amazon's door to AI models | the one AI call: Nova 2 Lite, in `us-east-1` (Virginia) because that is where the model lives - the only piece outside London, and the privacy page says so |
| **CloudWatch** | the logbook | every program's log lines, kept 30 days; where the `CHAT_UNGROUNDED` catches live |
| **IAM** | who is allowed to do what | one deploy user with one written-down policy; the coding agent deploys nothing without an explicit instruction from me, and on 16 Sep its own safety layer refused a production deploy and I ran the script myself |
| **SAM / CloudFormation** | the blueprint | one file (`template.yaml`) describes all of the above; a deploy means "make reality match the file" |
| **SES** | outgoing email | built for verified sign-ups; switched off until the sending address is verified |

Not Amazon: the domain's DNS is Cloudflare; postcodes.io is the fallback
postcode lookup; analytics is GoatCounter (no cookies).

---

## 7. What was removed in May, and why

The project began at the Amazon Nova hackathon in March 2026 as an
"AI-powered" build. By May the consumer site had **five AI features**: a chat
panel (with a "multi-agent" router behind it that sent complex questions to
the bigger Nova Pro model and simple ones to Nova Lite), an automatic AI
summary on every postcode, photo analysis of property listings, document
analysis of EPCs and surveys, and a generated "AI report".

On 7 May 2026 all five were removed from the site in one commit, and their
five back-end programs were deleted from the blueprint the same day. The
commit gives two reasons, in this order:

1. **The primary reason: variance.** The product's selling point to a
   business is a score their audit team can reproduce. An AI summary on top
   of a deterministic score adds an answer that varies and is sometimes
   wrong - and "not fully accurate" is structural to a language model, not
   something you tune away.
2. **The secondary reason: credits.** Five Bedrock-calling features cost
   roughly **$80-115 a month at modest traffic**, the heavier Nova Pro calls
   most of all, and the hackathon credits were finite.

What came back, in August, is one narrow thing: the assistant in section 5.
It calls the cheapest model, is capped at 400 tokens (about three sentences),
costs about **25p per 1,000 questions**, and cannot say a number it was not
handed. That is what "less AI, better product" means concretely.

---

## 8. How it was built, and the 57 checks

Most of the code was written by a coding agent, **Claude Code**, over six
months. I direct it, read what it writes, and own the decisions - what to
score, what to throw away, what counts as grounded.

What makes that safe is not the agent. It is **57 automated checks** that run
before any change is saved into the project (45 must pass; 12 only warn).
They lint the code, run the unit tests, drive the website in a real browser,
scan it for accessibility, and - the unusual part - **re-derive published
numbers from their government source** and fail if one has drifted. Each new
check is proven able to fail before it is trusted, because twelve checks in
this project's history were green for months while checking nothing.

The agent also keeps about eighty memory notes between sessions. The useful
ones do not record facts ("the tests pass"); they record checks ("audit a
check by asking what it would miss"). One of them is in this folder.

---

## 9. The one-sentence versions

- **What it is:** a postcode goes in, a traceable 0-10 liveability score
  comes out, as a website and as an API.
- **What the AI does:** explains numbers it was handed - and only those.
- **What keeps it honest:** forty lines that throw away any answer containing
  a number that isn't in the data.
- **What runs it:** a handful of Amazon services that sleep until called.
- **What was cut:** five AI features, in May, because variance costs more
  than dullness on a product about someone's home - and they burned credits.
- **What built it:** a coding agent, behind 57 checks that were each proven
  able to fail.
