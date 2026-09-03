# UAP Payout Handler

**Schema** [`settlement/payout_handler.json`](https://uap.dev/schemas/settlement/payout_handler.json)

A pluggable mechanism for moving money to a party in a RevenueSplit. Handlers are namespaced by reverse-DNS and registered the same way UCP registers payment handlers, so an implementation that already resolves UCP handlers resolves these with the same code.

UAP never carries payment credentials. A handler declares where a payout can go and under what terms; the instrument details live with the handler's own provider.

Registered by this specification: dev.uap.payout.ap2 (AP2 settlement mandate, REQUIRED to implement for the uap.settle profile), dev.uap.payout.ach, com.stripe.connect, com.wise.payout.

## Definitions

### `base`

### `platform_schema`

### `participant_schema`

### `response_schema`

---

*Generated from `source/schemas/settlement/payout_handler.json`. Do not edit; run `make docs`.*
