# Changelog

All notable changes to `debaterhub-sdk` are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

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
