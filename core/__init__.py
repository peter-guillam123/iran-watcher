"""Core processing helpers used by collect.py.

  - translate: bundle non-English event titles/summaries into a single
    Haiku call and write English versions back onto each event. Cached
    on disk by event id so re-runs are free.
  - threads:   single Opus call that clusters the day's events into
    five themed two-sentence blurbs. Editorial-rules system prompt
    keeps the model from editorializing or collapsing tier-4 claims
    into facts.

Both gracefully no-op if ANTHROPIC_API_KEY isn't set, so collect can
still run in degraded mode."""
