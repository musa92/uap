# Schema reference

Every wire object in the protocol, generated from `source/schemas/`. The schemas are normative; this page is a rendering of them.

## Protocol metadata

- [**UAP Capability**](capability.md) — Schema for UAP capabilities and extensions.
- [**UAP Service**](service.md) — A transport-bound endpoint group exposing one or more capabilities.
- [**UAP Metadata**](uap.md) — Protocol metadata for discovery manifests and responses.

## Supply side

- [**AdRequest**](ad_request.md) — The request body a serving node sends to an exchange to fill one or more placements on a generated turn.
- [**ContextSignal**](context_signal.md) — The only conversation-derived data permitted to leave a serving node.
- [**ImpressionReceipt**](impression_receipt.md) — The billable artefact, emitted and signed by the surface.
- [**Placement**](placement.md) — An advertising slot on a generated turn, described by the surface rather than by pixels.
- [**UAP Sellers Declaration**](sellers.md) — Served at `GET /.well-known/uap-sellers.json` by every exchange and supply agent that pays anyone.

## Demand side

- [**BidResponse**](bid_response.md) — A demand agent's reply to an AdRequest.
- [**Campaign**](campaign.md) — A buyer's top-level unit of spend: an objective, a budget, a flight, and the line items that execute it.
- [**ConversionEvent**](conversion.md) — A server-to-server report that a click led to an outcome.
- [**Creative**](creative.md) — The advertisement as structured data.
- [**Forecast**](forecast.md) — Available inventory and expected delivery for a proposed line item, before any budget is committed.
- [**LineItem**](line_item.md) — The unit of demand that an auction ranks.
- [**Report**](report.md) — Aggregate delivery and performance for a buyer, under the privacy floors of SPEC.md §6.6: every cell describes at least 50 events and at least the k-anonymity floor of users, with differential-privacy noise on intent-level breakdowns.

## Settlement

- [**Account**](account.md) — The commercial relationship between a participant and an exchange.
- [**Invoice**](invoice.md) — What an advertiser owes for a settlement period, itemised, with every adjustment shown.
- [**Payout**](payout.md) — What a serving node, supply agent or model steward is owed for a period, and the state of its disbursement.
- [**UAP Payout Handler**](payout_handler.md) — A pluggable mechanism for moving money to a party in a RevenueSplit.

## Common types

- [**Brand Manifest**](brand.md) — Served at `GET /.well-known/uap-brand` by every advertiser.
- [**CPM (micros)**](cpm.md) — Price of one thousand impressions, in micros of the stated currency.
- [**Currency**](currency.md) — ISO 4217 alphabetic currency code.
- [**Deal**](deal.md) — A pre-negotiated arrangement between a buyer and this supply, identified by `deal_id` and priced outside the open auction.
- [**Digest**](digest.md) — A content digest formatted as `<algorithm>:<lowercase-hex>`.
- [**Integrity Assertion**](integrity_assertion.md) — Operator attestations that the answer-integrity boundary held for this turn.
- [**Micros**](micros.md) — A monetary amount as an integer count of micros of the stated currency, where one unit equals 1000000 micros.
- [**Regulatory Signals**](regs.md) — Consent and regulatory state applying to this request.
- [**Reverse Domain Name**](reverse_domain_name.md) — Reverse-DNS identifier used as a registry key for capabilities, services, formats, auction mechanisms, and payout handlers.
- [**Detached Object Signature**](signature.md) — A detached signature over a UAP object.
- [**SupplyChain**](supply_chain.md) — The complete set of entities that participated in selling this placement, in the order they were involved.
- [**Viewability**](viewability.md) — The surface's measurement of whether a human could have seen the placement.
