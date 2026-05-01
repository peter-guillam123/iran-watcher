# Iran watcher

A daily-updated aggregator of primary governmental and multilateral sources on Iran and the Middle East crisis. Pulls from public APIs and RSS feeds (UN OCHA, UK Parliament, US Federal Register, IAEA, UN Security Council, US State Department, UK FCDO, and others) and publishes a per-day brief to a static site.

This is a v1. It does not cover Telegram, X/Twitter, or Iranian state media directly — see the About page on the site for what's in and what isn't.

## Run locally

```sh
uv sync
uv run python collect.py
uv run python render.py
```

Outputs go to `data/YYYY-MM-DD.json` and `docs/YYYY-MM-DD.html`.

## Layout

- `sources/` — one module per data source, each exporting `fetch() -> list[dict]`
- `collect.py` — runs every adapter, applies the keyword filter, de-duplicates, writes today's JSON
- `render.py` — turns today's JSON into an HTML page; updates the index
- `docs/` — what GitHub Pages serves
