"""
Hata parser engine.

Strategy for evading anti-scraping on eri2.nca.by / au.nca.by:
  * Headless Chromium via Playwright (real TLS/JA3 fingerprint, real JS engine).
  * Per-request randomised delay drawn from the active profile.
  * Rotating User-Agent pool.
  * Batch pacing: after `batch_size` requests, pause `batch_pause_seconds`.
  * Hourly request cap enforced before every request; on cap hit, sleep until the
    rolling window allows more.
  * Exponential backoff on 403/429/5xx, up to `retry_attempts`.
  * Optional upstream proxy (HTTP/SOCKS) with basic auth.
  * Photo downloads throttled in small concurrent batches with a pause between.

A `dry_run` mode generates realistic mock data so the full UI (map, cards,
lightbox, logs, stats) is exercisable without network access to the source.
"""
from .runtime import start_run, status, request_stop, logs, log_file_path

__all__ = ["start_run", "status", "request_stop", "logs", "log_file_path"]
