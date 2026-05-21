# Changelog

All notable changes to the Legichain Python SDK.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the package adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-05-20

First public release on PyPI.

### Added
- `Legichain` and `AsyncLegichain` clients (httpx-backed).
- `screen_person`, `screen_company`, `screen_crypto` endpoints with
  full Pydantic-typed responses (`HitFlags`, `ScreeningSummary`,
  `ScreeningResponse`) — banks can branch on
  `response.summary.recommendation` in a single line.
- `screen_batch` (synchronous) and `screen_batch_async` (queued + webhook).
- PDF report helpers: `report_wallet`, `report_person`, `report_company`.
- Admin / account endpoints: `credits`, `usage`, `status`.
- Idempotency-Key passthrough on every mutating call (`idem=…`).
- `LegichainError` carries the full RFC 7807 Problem Details payload —
  `status_code`, `code`, `title`, `detail`, `errors[]`.
- `webhooks.verify_signature()` helper for HMAC-SHA256 delivery checks
  (Stripe-style `t=<unix>,v1=<hex>` header, 5-min replay tolerance).
- `Idempotent-Replay: true` header surfaced on the response for cache hits.

### Requirements
- Python 3.10 — 3.13
- `httpx >= 0.27`, `pydantic >= 2.0`
