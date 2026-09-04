# Quickstart: run your first campaign in five minutes

For advertisers, agencies and DSPs. The API is shaped like the buying
platforms you already use: advertiser, campaign, line item, creative.

Three things differ from a conventional platform and are worth knowing before
you start. There is no audience object, because no cross-session identifier
exists. A creative is structured data, never markup. Reporting is aggregate,
under a published k-anonymity floor, and never per user.

## 1. Install

```bash
pip install uap-protocol
```

## 2. Forecast before you spend

```python
from uap import DemandClient

dsp = DemandClient("https://uax.example.com", advertiser_id="brand.acme.example")

targeting = {"all": [
    {"intent_any": ["travel.accommodation.hotel", "travel.destination.japan"]},
    {"commercial_intent_gte": 0.5},
    {"not": {"intent_any": ["travel.insurance"]}},
]}

fc = dsp.forecast(targeting=targeting,
                  pricing={"model": "cpm", "currency": "USD", "bid_cpm_micros": 40_000_000})
print(fc["matched"]["impressions_per_day"])      # {'low': ..., 'high': ...}
print(fc["estimate"]["clearing_cpm_micros"])     # where it is expected to clear
```

Forecasts are ranges, never points. Breakdowns that would describe fewer users
than the k floor are suppressed and listed under `suppressed`.

## 3. Create the campaign

```python
campaign = dsp.create_campaign(
    name="Q4 Japan autumn travel",
    objective="clicks",                 # reach | clicks | conversions | sponsorship
    budget_micros=5_000_000_000,        # USD 5,000
    currency="USD",
    spend_mandate="ap2:intent:01J9...", # AP2 intent mandate authorising the spend
)
```

A campaign will not run without a spend mandate. The exchange uses it to prove
every cleared batch was authorised.

## 4. Add a line item with a creative

```python
creative = {
    "creative_id": "cr_kyoto_01",
    "format": "sponsored_card",
    "content": {
        "headline": "Kyoto ryokan, free cancellation",
        "body": "Traditional inns from $180 a night, cancel up to 24h before.",
        "brand_name": "Acme Travel",
        "actions": [{"type": "link", "label": "See rooms",
                     "url": "https://acme.example/kyoto?uap_click={CLICK_ID}"}],
    },
    "disclosure": {"label": "Sponsored", "advertiser_name": "Acme Travel"},
}

item = dsp.create_line_item(
    campaign["campaign_id"],
    targeting=targeting,
    pricing={"model": "cpc", "currency": "USD", "bid_cpc_micros": 900_000},
    creative=creative,
    display_name="Acme Travel",
)
print(item["status"])                          # active, or rejected
print(dsp.review_status("cr_kyoto_01"))        # reasons if rejected
```

Review is synchronous in the reference exchange. It resolves every action URL
against your `/.well-known/uap-brand` verified domains, scans the text for
anything shaped like an instruction to a model, and rejects markup. A
rejected creative never reaches an auction.

## 5. Report conversions from your own systems

```python
dsp.report_conversions([{
    "event_id": "order_88213",              # idempotency key
    "click_id": "ck_a91f3b2e",              # from the placement the user clicked
    "event_type": "purchase",
    "occurred_at": "2026-10-03T11:42:10Z",
    "value": {"amount_micros": 180_000_000, "currency": "USD"},
    "source": {"kind": "advertiser_server", "reference": "order_88213"},
}])
```

Only you, or a payment mandate, can report a conversion. A serving node cannot.

## 6. Read the numbers

```python
rep = dsp.report(start="2026-10-01", end="2026-10-31",
                 dimensions=["campaign", "line_item"],
                 metrics=["impressions", "clicks", "spend_micros", "ecpm_micros"])
for row in rep["rows"]:
    print(row["keys"], row["values"])
print(rep["privacy"])   # k floor, cell minimum, epsilon if intent dimensions were used
```

Dimensions are a closed set of at most four. Cells under 50 events are
suppressed. Intent-level breakdowns carry differential-privacy noise, with the
epsilon stated in the response.

## Without a real exchange

```bash
docker compose up        # then point DemandClient at http://localhost:8787
```
