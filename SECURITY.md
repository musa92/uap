# Security policy

## Reporting a vulnerability

Report privately through GitHub's "Report a vulnerability" flow on this
repository. Do not open a public issue for an unpatched vulnerability.

Include the affected component, a reproduction, and the impact you believe it
has on one of the three invariants. Expect an acknowledgement within 5 working
days.

## Scope

In scope:

- Any means of extracting prompt or completion text from a conformant node
  through UAP traffic (breaks I1).
- Any means of causing creative content to influence generation on a conformant
  implementation (breaks I2).
- Any means of obtaining payment for an impression that was not rendered, or of
  causing a conformant exchange to accept a fabricated receipt (breaks I3).
- Signature forgery, canonicalization mismatches, or replay across object types.

Also in scope, and specifically wanted:

- Signal combinations that defeat the k-anonymity floor (§6.5).
- Bundle-fetch patterns that fingerprint a node's audience (§8.2).
- Auction traces that replay correctly while misrepresenting the auction (§8.4).

Out of scope: the reference implementation's in-memory stores, which are
explicitly not durable; denial of service against the demo server; and findings
that require a non-conformant implementation.

## Known weaknesses

Documented rather than hidden. See the "Status" section of the README and §13 of
the specification.

- The pure-Python Ed25519 fallback in `reference/python/uap/crypto.py` is not
  constant-time. It exists so the reference implementation can be vendored
  without a dependency; production deployments should install the
  `cryptography` extra, which is detected and used automatically.
- Trust tier 0 supply is by construction indistinguishable from general invalid
  traffic. This is why it is not CPM-eligible.
- The nonce store in the reference exchange is in-memory and single-process. A
  production exchange needs a durable store with an explicit replay window.
