# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the
project is pre-1.0, new features bump the **minor** version and fixes bump the **patch**
version. Versions are cut with Commitizen (`uvx --from commitizen cz bump`), which updates
this file and tags `vX.Y.Z`.

## [0.1.0] — 2026-07-20

Baseline: multi-tenant fork of `intervals-mcp-server`. Per-user OAuth credentials with
AES-256-GCM-encrypted Intervals.icu API keys (Better Auth), streamable-HTTP transport with
CORS, and the full activity / event / wellness / power-curve / gear / custom-item toolset.

[0.1.0]: https://git.farh.net/farhoodlabs/intervalsicu-mcp/releases/tag/v0.1.0

## v0.3.0 (2026-07-20)

### Feat

- **readiness**: add get_training_readiness synthesizer
- **writes**: add update_wellness_bulk and update_sport_settings
- **workouts**: add workout library read tools (get_workouts, get_workout)
- **activities**: add search + best-efforts + interval-stats tools
- **athlete**: add profile, sport-settings, and summary read tools

### Fix

- **athlete**: drop athlete-tag filter, harden write guardrail, guard empty echo
- **wellness**: reject unrecognized bulk fields instead of silently dropping
- **readiness**: calendar-anchored windows, disjoint RHR baseline, SWC floor

## v0.2.1 (2026-07-20)

### Fix

- **release**: sync uv.lock into the bump commit and tag

## v0.2.0 (2026-07-20)

### Feat

- **wellness**: add update_wellness write tool, computed Form (TSB), date-label fix

### Fix

- **wellness**: harden Form/TSB and date rendering from code review
- reset version to 0.1.0 baseline; let cz bump own versioning

## v0.1.0 (2026-07-20)

### Feat

- **db**: Alembic migration for users table (async env, DATABASE_URL)
- **multi-tenant**: resolve per-caller credentials in every tool
- **multi-tenant**: data layer, encryption, and per-request credential resolver
