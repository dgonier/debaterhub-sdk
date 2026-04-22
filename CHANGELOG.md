# Changelog

All notable changes to `debaterhub-sdk` are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

## [0.3.2] — 2026-04-22

### Added
- `DebateConfig.prep_config` — optional dict forwarded to the
  server-side prep pipeline (`debate-prep` Modal service). Accepts
  `values_per_side`, `beliefs_per_value`, `research_per_belief`,
  `arguments_per_leaf`, `max_depth`. Useful for smoke tests / demos
  that want a ~5min tree instead of the ~15min full-breadth default.
- `ManagedDebateSession.on_stall` callback — optional async hook invoked
  when no server event has arrived for `stall_after_seconds` (default
  120s). Signature: `async (elapsed_since_connect, silence_duration,
  last_phase_message) -> None`. The SDK does NOT disconnect on stall;
  the callback decides what to do. Useful for tests, user
  notifications, and alternate fallback paths. Re-arms on next event.
- `ManagedDebateSession` diagnostic properties: `last_phase_message`,
  `seconds_since_last_event`, `seconds_since_connect`, `event_count`.
- `[EVENT]` / `[LOG]` split in verbose-logging output. When
  `DEBATERHUB_VERBOSE=1`, every inbound server event emits a single
  clean `[EVENT]` line with elapsed time + type + short summary (e.g.
  `[+  45.3s] debate_initializing — [beliefs] Generating NEG beliefs`).
  Framework chatter (raw frame dumps, parse errors, handler
  exceptions) is tagged `[LOG]` at DEBUG. Users can `grep EVENT` for
  a phase-by-phase timeline or `grep LOG` for deep-dive.
- E2E smoke test `tests/e2e/test_ipda_handoff_smoke.py` — milestone-
  based IPDA handoff test that asserts each phase arrives within a
  budget (initializing in 20s, first progress in 60s, belief_tree in
  720s, debate_ready in 900s) and prints the full event log on any
  miss. Gated by `LIVEKIT_*` env vars.

## [0.3.1] — 2026-04-22

### Added
- `TopicSearchClient` — basic semantic search over a prepped topic's
  belief tree. Calls `POST /api/debate/topics/{id}/search` on the
  debaterhub backend; returns ranked `SearchHit` objects
  (`node_id`, `kind`, `score`, `preview`). Results are scoped to the
  topic passed in — no cross-topic leakage. Bring your own
  `base_url` + `auth_token`.
- Opt-in verbose logging controlled by env vars:
  - `DEBATERHUB_LOG_LEVEL` — one of `DEBUG | INFO | WARNING | ERROR`.
  - `DEBATERHUB_VERBOSE` — shorthand; any truthy value (`1`, `true`,
    `yes`, `on`) maps to `DEBUG`.
  Setting either one attaches a stream handler to the `debaterhub`
  logger on package import. Default remains silent so hosts with their
  own logging config are unaffected.
- `ManagedDebateSession._on_data_received` now emits a DEBUG-level
  trace for every incoming event (type + trimmed payload) and every
  outgoing `_send`, plus INFO-level lifecycle lines for
  `debate_initializing`, `debate_ready`, and `error`. These together
  give users enough signal to diagnose a stuck session (e.g. hangs at
  `debate_initializing` because a `debate_ready` never arrives).

### Fixed
- Parse-failure path logs the full (trimmed) raw payload at ERROR
  instead of a WARN with only the first 200 bytes — catches schema
  mismatches between SDK + backend that previously went unnoticed.

## [0.3.0] — 2026-04-20

### Added
- `CounterPrepClient` — async client for the v1 counter-argument
  generator on Modal. Given an existing argument (claim/warrant/impact/
  side) and its topic, generates 2-3 typed counters via SSE.
- `CounterEvent`, `CounterPrepStart`, `CounterPrepError`, `CounterType`
  exposed from the package root.
- Counter types: `TAKEOUT`, `LINK_TURN`, `IMPACT_TURN`, `DELINK`.

### Notes
- Generator runs are analytical only (no web research), so they finish
  in ~10-30 seconds. Each counter is persisted server-side to both
  Neo4j (`:Counter` node + typed edge to `:Argument`) and Weaviate
  (`Counter` collection) keyed by the same deterministic UUID.
- Orthogonal to `TopicPrepClient` and `DebateClient`; existing 0.2.x
  surface is unchanged.

## [0.2.0] — 2026-04-19

### Added
- `TopicPrepClient` — async client for the v1 topic belief-prep service
  on Modal. Starts a tree-shaped prep run and streams per-node events
  over SSE until the run emits `done` or `error`.
- `TopicPrepEvent`, `TopicPrepStart`, `TopicPrepError` dataclasses and
  exception types exposed from the package root.
- SDK now supports HTTP-based streaming (in addition to the existing
  LiveKit data-channel-based `DebateEventHandler` flow). The two paths
  are independent — use `TopicPrepClient` for topic creation and
  `DebateClient` for live debate sessions.

### Notes
- All existing APIs (`DebateClient`, `ManagedDebateSession`, etc.)
  continue to work exactly as in 0.1.x. Additive release only.
- Targets the Modal `v1/*` endpoints; schema_version `"1.0"` is
  recognised. Older Modal endpoints (unversioned `/start`, `/events`,
  `/status`, `/health`) remain in service for legacy callers.

## [0.1.0] — 2026-03-09

### Added
- Initial public release of the Python SDK for human-vs-AI IPDA debates
  via LiveKit. `DebateClient`, event handlers, flow schema, format
  specs.
