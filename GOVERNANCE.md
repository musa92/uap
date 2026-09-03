# Governance

## Decisions

Changes proceed by public pull request. Anyone may open one. A change lands
when the maintainers listed in [MAINTAINERS.md](MAINTAINERS.md) reach consensus
on the PR; where they do not, it does not land, because a protocol defaults to
not changing.

## What cannot change by consensus

Sections §6 (context confinement), §7 (answer integrity) and §9 (earned
payment) of the specification are the invariants. An extension may strengthen
them and may not weaken them. A change to their normative text requires two
independent interoperating implementations demonstrating it, regardless of
maintainer agreement. This is stated so that "can we add a mode where the
prompt is sent?" has a documented answer.

## Versioning

Protocol versions are dates, `YYYY-MM-DD`. A newer version MUST remain backward
compatible for twelve months or introduce a distinct capability name. There are
no semantic version numbers on the protocol; the reference implementation
carries one that tracks the protocol version it implements.

## Leaving draft

A capability leaves draft after a public PR, a thirty-day comment window, and
two independent interoperating implementations.

## Registries

Formats, positions, auction mechanisms, and payout handlers are open registries
keyed by reverse-DNS name. `dev.uap.*` is reserved for this specification.
Anyone may register a name under a domain they control by pull request.

## Becoming a maintainer

Sustained contribution in an area of the repository, followed by nomination by
an existing maintainer and no objection within fourteen days.
