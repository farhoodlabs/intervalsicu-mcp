# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the
project is pre-1.0, new features bump the **minor** version and fixes bump the **patch**
version. Versions are cut with Commitizen (`uvx --from commitizen cz bump`), which updates
this file and tags `vX.Y.Z`.

## [0.2.0] — unreleased

### Added
- Nutrition & wellness intelligence tooling (in progress on this branch): training-readiness
  signal (HRV/RHR/sleep/subjective synthesis), pre-activity fueling planner (carbs/fluid/
  sodium), energy-availability / underfueling screen, and a wellness/nutrition write path
  (`PUT /athlete/{id}/wellness/{date}`).
- Computed **Form (TSB = CTL − ATL)** surfaced in wellness output.

### Fixed
- Wellness output mislabeled the record `id` as the date.

## [0.1.0] — 2026-07-20

Baseline: multi-tenant fork of `intervals-mcp-server`. Per-user OAuth credentials with
AES-256-GCM-encrypted Intervals.icu API keys (Better Auth), streamable-HTTP transport with
CORS, and the full activity / event / wellness / power-curve / gear / custom-item toolset.

[0.2.0]: https://git.farh.net/farhoodlabs/intervalsicu-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://git.farh.net/farhoodlabs/intervalsicu-mcp/releases/tag/v0.1.0
