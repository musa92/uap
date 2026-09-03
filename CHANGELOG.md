# Changelog

Protocol versions are dates. Reference implementation versions follow the
protocol version they implement. Both are listed here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Buy side: `Campaign`, `LineItem`, `Forecast`, `ConversionEvent` and `Report`
  schemas, a demand-service OpenAPI definition covering campaign and line-item
  management, creative review, forecasting, conversions and aggregate
  reporting, and reference-exchange implementations of each.
- Compiled predicate form (`predicate.compile_predicate`, `predicate.prepare`),
  evaluated once per bundle load rather than per turn. Meets the Appendix A
  bound of 1 ms for 10³ line items; 0.66 ms measured.
- Performance budget tests enforcing the specification's numeric claims.
- Property-based tests over the canonicalizer and predicate evaluator,
  including compiled/interpreted equivalence.
- Generated schema reference under `docs/reference/`, checked in CI.
- Documentation site (`mkdocs.yml`) and Pages publishing so every schema `$id`
  resolves.
- Release workflow, Dependabot, CodeQL.
- Domain-split spelling dictionaries, case-sensitive checking, flagged words,
  and a terminology checker for names a spellchecker cannot catch.

### Fixed

- Appendix A cited a latency figure the implementation did not meet. The
  implementation now meets it and the appendix cites the measurement.

## [2026-09-02] — draft-01

Initial public draft. Specification, 22 schemas with an OpenAPI 3.1 binding,
stdlib-only Python reference implementation, 16 conformance vectors of which
10 are negative, two runnable demos.
