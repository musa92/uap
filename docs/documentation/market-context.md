# Market context

*Last revised 2026-09-02. This document is non-normative. It exists because a
protocol whose defaults contradict the market it serves does not get adopted,
and because every constraint in the specification should be traceable to a
commercial fact rather than to taste.*

---

## 1. The inventory is real and it is premium

OpenAI launched ChatGPT advertising in February 2026 on the Free and Go tiers in
the US. Reported: **$100M ARR inside two months at roughly a $60 CPM**, against
800M+ weekly users, with Adobe, Ford and Target as launch brands and WPP and
Omnicom buying the early inventory. The unit is a **static sponsored link
rendered below the answer**, contextually matched to the conversation.

Three consequences for UAP:

1. **`post_answer` + `sponsored_link` is the format that works.** UAP already
   makes `post_answer` the only REQUIRED-to-implement position. That is now an
   evidence-backed choice rather than a stylistic one.
2. **Price the protocol for $60 CPM, not $0.20.** An LLM turn is closer to paid
   search than to display. Floors, examples and rate cards in this repository
   are denominated accordingly (§ *Money*, below).
3. **The buyers are holding companies.** WPP and Omnicom buy from rate cards,
   demand `sellers.json`-grade supply transparency, and reconcile against
   MRC-accredited measurement. A protocol they cannot audit is a protocol they
   cannot spend against.

## 2. The failure case is instructive

Perplexity shipped **sponsored follow-up questions** in November 2024 with
Indeed and Whole Foods, on a conventional CPM model. Revenue was minimal; they
stopped accepting new advertisers in October 2025 with only launch partners
still testing.

UAP therefore does **not** treat its five formats as equals. The registry ranks
them by observed market outcome:

| Format | Evidence | Status in UAP |
|---|---|---|
| `sponsored_link` at `post_answer` | ChatGPT Ads, Feb 2026, ~$60 CPM | REQUIRED to implement |
| `sponsored_card` at `post_answer` | Same surface, richer creative | RECOMMENDED |
| `product_offer` | Retail media analogue, proven at scale off-LLM | RECOMMENDED with `uap.commerce` |
| `sponsored_action` in tool results | Untested in LLM surfaces; highest integrity risk | OPTIONAL, extra constraints (§7.3) |
| `sponsored_suggestion` (follow-up) | Perplexity 2024-2025, withdrawn | OPTIONAL, **NOT RECOMMENDED** |

Ranking formats by evidence is a service to implementers. Listing them
neutrally would imply the market has not already answered the question.

## 3. Answer integrity is a revenue argument, not an ethics argument

An Ipsos survey found nearly **two-thirds of US adults say ads in AI search
results make them trust the results less**. In retail media — the nearest
structural analogue, where a platform sells placement adjacent to organic
results it also ranks — studies attribute **30–40% of sponsored-product sales to
purchases that would have happened organically**. Retail media is a $130B+
category in 2026, with Amazon at roughly 69% share and $88.6B in US ad revenue.

Read those two numbers together and §7 stops being a compliance section:

- The cannibalization figure is I2 measured in dollars. When commercial ranking
  bleeds into organic ranking, a large fraction of the revenue is not
  incremental — the platform is being paid for demand it already had.
- The trust figure is the decay curve. A surface that bends its answers
  converges on display CPMs. **The integrity boundary is the mechanism that
  defends a $60 CPM from becoming a $6 CPM**, which is why §7 is normative,
  digest-committed in the receipt, and non-waivable by extension.

This is the argument to make to a publisher who asks why they cannot simply
paste the creative into the system prompt.

## 4. Supply-chain transparency is the missing table stakes

The open web settled "who is allowed to sell this inventory" years ago, and not
with cryptography:

- **`ads.txt` / `app-ads.txt`** — the publisher declares who may sell its
  inventory. Baseline requirement for legitimate supply since 2019.
- **`sellers.json`** — every exchange publishes the identity, domain and role
  (`PUBLISHER` / `INTERMEDIARY` / `BOTH`) of every seller it pays.
- **`SupplyChain` object** — carried on the bid request, naming every hop
  between the publisher and the buyer, so buyers can run supply path
  optimization and cut indirect, fee-heavy, fraud-prone routes.

UAP draft-01 has none of this, and it is a larger practical gap than anything in
the signing section. A media buyer's first question is not "is the receipt
Ed25519-signed", it is "who am I paying, and how many hops are between me and
the impression".

The hard part is that UAP's core supply — a self-hosted node — **has no domain
and nothing to lose**, which is exactly the assumption `ads.txt` relies on. UAP
resolves this by substituting the two authorities that do exist:

| Web mechanism | Anchored on | UAP equivalent | Anchored on |
|---|---|---|---|
| `ads.txt` | Publisher domain | `/.well-known/uap-model` | Model steward's domain + `weights_digest` |
| `sellers.json` | Exchange's seller registry | `/.well-known/uap-sellers.json` | Exchange's enrolled-entity registry |
| `SupplyChain` object | Per-hop declaration | `supply_chain` on `AdRequest` | Per-hop declaration, signed at each hop |
| Domain reputation | WHOIS, history | **Trust tier** (§9.3) | Enrolment, attestation, replay history |

Trust tiers are not a replacement for supply-chain transparency. They are the
credit rating that sits *on top of* it, for supply that cannot present a domain.
Both are required.

## 5. Profile L has a production precedent

Chrome's **Protected Audience API** (formerly FLEDGE) runs on-device ad auctions
and is available to 99% of Chrome users. Buyers ship bidding logic and interest
groups to the device; the seller scores bids on-device; reporting is
event-level today and moves to Private Aggregation. Google additionally
operates **Bidding and Auction services** that run this same auction inside
TEEs when it must be server-side.

UAP Profile L is the same architecture applied to a conversation turn:

| Protected Audience | UAP Profile L |
|---|---|
| Interest group joined on advertiser site | Line item in a signed `CampaignBundle` |
| `generateBid()` shipped to device | `pricing` + `targeting` predicate in the bundle |
| `scoreAd()` run by seller on-device | Local auction on the serving node (§8.4) |
| Trusted bidding signals server | Bundle sync endpoint (§8.2) |
| Private Aggregation / ARA | Aggregate, k-floored, DP-noised reporting (§6.6) |
| B&A services in a TEE | Trust tier 2 attestation (§9.4) |

This matters for adoption. "Protected Audience for LLM turns" is a positioning
every DSP engineer already understands, and it means trust tier 2 has a
reference architecture rather than a research project. Where UAP diverges it
should do so deliberately: UAP's targeting predicate is **declarative and
closed** (Appendix A) where `generateBid()` is arbitrary JavaScript, because a
serving node must be able to bound evaluation cost and prove the auction
replayed correctly.

## 6. Measurement must speak MRC

Buyers reconcile against accredited measurement or they do not pay. The
vocabulary is fixed:

- **Viewable impression** — display: ≥50% of pixels in view for ≥1 continuous
  second; video: ≥50% for ≥2 continuous seconds; large formats (≥242,000 px):
  ≥30% for ≥1 second.
- **GIVT** — general invalid traffic; list-based filtration of data-center
  traffic, known bots, crawlers, non-browser user agents.
- **SIVT** — sophisticated invalid traffic; requires advanced analytics and
  multi-point corroboration.
- **MRC accreditation** — an independent audit of a vendor's methodology before
  its counts are trusted.

UAP's `viewability` object is currently free-form, which means no buyer can map
it onto a rate card. It MUST be redefined against these thresholds, including an
honest LLM-native answer for surfaces that have no pixels at all — a CLI, an
API response, a voice channel. The `measurement_agent` role exists so that an
MRC-accredited third party can verify receipts; that role should say so.

UAP's trust tiers map cleanly onto the IVT frame: tier 0 supply is
indistinguishable from GIVT by construction (an anonymous binary in a loop),
which is precisely why §9.3 forbids selling it on CPM.

## 7. What this changes in the specification

| # | Change | Driver |
|---|---|---|
| 1 | Re-denominate all floors, examples and rate cards for a $10–$80 CPM market | ChatGPT Ads at ~$60 CPM |
| 2 | Add `/.well-known/uap-sellers.json` and a signed per-hop `supply_chain` on `AdRequest` | `sellers.json` + SupplyChain object are buyer table stakes |
| 3 | Redefine `viewability` against MRC thresholds; add GIVT/SIVT vocabulary | Buyers reconcile against accredited measurement |
| 4 | Rank formats by market evidence; mark `sponsored_suggestion` NOT RECOMMENDED | Perplexity 2024-2025 |
| 5 | Add a Protected Audience mapping appendix alongside the OpenRTB one | Positions Profile L in a known lineage |
| 6 | Reframe §7's rationale in revenue terms | Ipsos trust data + retail media cannibalization |

## Sources

- [AI Ads in 2026: ChatGPT, Gemini, Claude & Perplexity](https://www.paperstack.com.au/blog/ai-ads/)
- [Advertising on AI Platforms: The Complete 2026 Landscape](https://www.stackmatix.com/blog/advertising-on-ai-platforms-2026-landscape)
- [ChatGPT Ads vs Perplexity Ads: 2026 AI Search Advertising Comparison](https://adventuremedia.ai/blog/chatgpt-ads-vs-perplexity-ads-2026-ai-search-advertising-comparison)
- [Protected Audience API overview — Privacy Sandbox](https://privacysandbox.google.com/private-advertising/protected-audience)
- [Bidding and Auction services API](https://github.com/privacysandbox/protected-auction-services-docs/blob/main/bidding_auction_services_api.md)
- [sellers.json — IAB Tech Lab](https://iabtechlab.com/sellers-json/)
- [Understanding Supply Chain Transparency: Ads.txt, Sellers.json, and SupplyChain — Index Exchange](https://www.indexexchange.com/en-au/index-explains/understanding-supply-chain-transparency-aus/)
- [FAQ on Amazon advertising: retail media dominance — eMarketer](https://www.emarketer.com/content/faq-on-amazon-advertising--retail-media-dominance--prime-video-scale--agentic-ad-tools)
- [Retail Media Networks: The $150 Billion Opportunity in 2026](https://www.crispidea.com/retail-media-networks-2026/)
- [IAB/MRC Invalid Traffic Detection and Filtration Guidelines Addendum](https://www.iab.com/guidelines/mrc-invalid-traffic-ivt-detection-and-filtration-guidelines-addendum/)
- [MRC: The Standard Behind Ad Measurement](https://optickssecurity.com/fraud-types/mrc)
