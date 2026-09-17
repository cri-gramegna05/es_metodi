# Scout

Nightly pipeline that looks for small Italian premium **men's footwear** brands that could
be acquisition targets for Venexis: it collects brand-level data from shopping sources,
merges duplicates, applies deterministic rules, and (next steps) scores them with a local
LLM, enriches the best ones with Claude and publishes to Google Sheets + Telegram.

## Status

| Module | State |
| --- | --- |
| `collectors/` (html, shopify, farfetch, yoox, giglio) | done |
| `dedupe/` (name normalization + cross-source merge) | done |
| `rules/` (deterministic filter + prescore) | done |
| CLI (`run`, `show`, `stats`, `sources`, `init-db`) | done |
| `classify/` (Ollama) | not implemented yet |
| `enrich/` (Claude) | not implemented yet |
| `publish/` (Sheets + Telegram) | not implemented yet |

`config.yaml` already carries the settings for the three pending modules, so enabling them
later is a config change, not a rewrite.

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
cp config.example.yaml config.yaml   # then edit
.venv/bin/scout init-db
```

`scout` is also available as `python -m scout.cli`.

## Try it without touching a real site

The repo ships a fixture shop (`tests/fixtures/site`) with a listing page and a Shopify
`products.json`. Serve it and run the pipeline against it:

```bash
./scripts/serve_fixtures.sh &            # http://127.0.0.1:8765
scout run --config config.demo.yaml
scout show "Edhèn Milano" --config config.demo.yaml
scout stats --config config.demo.yaml
```

## Commands

```bash
scout run                      # all enabled sources
scout run --source giglio      # one source, even if disabled in config
scout run --dry-run            # parse and score, write nothing
scout run --json               # machine-readable summary
scout show "Edhèn Milano"      # observations, rules verdict, history
scout stats                    # database and last-run counters
scout sources                  # configured sources and their state
```

## Sources

Two collector types cover most shops; a new source is usually a config block, not code.

- `html` — listing pages. Products are read from schema.org JSON-LD when present,
  otherwise from the CSS selectors given in config. `farfetch`, `yoox` and `giglio` are
  presets of this type with selectors already filled in (`scout/collectors/sites.py`).
- `shopify` — `/<collection>/products.json`. Gives brand (`vendor`), price and
  `compare_at_price` (i.e. the discount) without HTML parsing. Many small Italian
  boutiques run Shopify, so one entry per domain is enough.

**Farfetch and YOOX are disabled by default.** Their robots.txt and bot protection gate
listing pages; Scout skips any URL robots.txt disallows for our user-agent, so enabling
them may simply yield nothing. Check their robots.txt yourself before flipping `enabled`.

Crawling manners, enforced in `scout/http.py`: robots.txt honoured per host (including
`Crawl-delay`), one honest user-agent with a contact, per-host rate limit, exponential
backoff with jitter on retries, and every page cached on disk so a re-run does not hit the
site again within `cache_ttl_hours`.

## Rules

Hard filters (`scout/rules/filters.py`) drop the bulk before any LLM is involved:
blacklisted groups, brands every source agrees are foreign, women-only, prices outside
250–700 € (±20 %), assortments too large or too small, sneaker-first brands. What survives
gets a deterministic prescore 0–100 from the positive signals: price in band, chronic
discount ≥ 40 %, few items, Italian, men's.

Unknown values (a marketplace rarely states a brand's country) are kept, not dropped — the
classification stage decides.

## Storage

SQLite (`data/scout.db`), one row per brand keyed on its normalized slug; each run appends
observations and a rules verdict. Re-running never duplicates a brand: `Edhèn Milano`,
`EDHÈN MILANO` and `Edhen Milano S.r.l.` all resolve to `edhen-milano`, and near-misses are
merged with a fuzzy match above the configured threshold.

## Tests

```bash
.venv/bin/python -m pytest -q
```

Unit tests cover normalization/merging and every rule; integration tests run the collectors
and the whole pipeline against the saved fixtures, with no network.

## Nightly run (launchd)

```bash
cp deploy/com.venexis.scout.plist ~/Library/LaunchAgents/
# edit the paths inside, then:
launchctl load ~/Library/LaunchAgents/com.venexis.scout.plist
launchctl start com.venexis.scout
```

Logs land in `data/scout.log` (structured) plus the stdout/stderr files named in the plist.

## Still to wire (next steps)

- **Ollama** — `brew install ollama && ollama serve && ollama pull gemma3:4b`; model and
  host are already in `config.yaml` under `classify`.
- **Google service account** — create it in Google Cloud, enable the Sheets API, download
  the JSON key to `credentials/service_account.json`, share the sheet with the service
  account e-mail; `sheets` section in `config.yaml`.
- **Telegram bot** — talk to @BotFather, take the token, get your chat id from
  `https://api.telegram.org/bot<TOKEN>/getUpdates`; set `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` in the environment (`config.yaml` reads `${VAR}`).
