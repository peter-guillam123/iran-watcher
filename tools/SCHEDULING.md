# Scheduling — external trigger setup

The collect workflow has three independent paths into a daily run:

1. **GitHub Actions internal cron** (primary). Four firings per
   edition spread over ~75 minutes:
   - Morning: 05:30, 05:50, 06:15, 06:45 UTC
   - Evening: 14:30, 14:50, 15:15, 15:45 UTC

   GitHub explicitly documents `schedule:` events as best-effort.
   They can be delayed by 30+ minutes during high load and
   occasionally skip entirely. On 2026-05-11 both the 05:30 primary
   AND the 05:50 backup silently dropped — the trigger for moving to
   a parallel path.

2. **External cron-job.org → repository_dispatch** (safety net).
   An outside scheduler hits GitHub's REST API and triggers the
   workflow directly. Independent of GH Actions' own scheduler.
   This is what these instructions set up.

3. **Manual fire** (override): `tools/dispatch.sh morning` /
   `tools/dispatch.sh evening` from anywhere with `gh` installed
   and a token in scope.

The `skip-if-fresh` gate inside the workflow means all three paths
play nicely together — whichever fires first generates the brief,
the rest see a fresh file and no-op cleanly.

---

## One-time setup: cron-job.org → repository_dispatch

### Step 1 · Create a GitHub fine-grained personal access token

A fine-grained PAT scoped to just this repo with the minimum
permissions needed for `repository_dispatch`.

1. Go to <https://github.com/settings/personal-access-tokens/new>
2. Token name: `iran-watcher cron dispatch`
3. Expiration: **1 year** (set a calendar reminder to rotate;
   tokens silently fail after expiry)
4. Repository access: **Only select repositories** →
   `peter-guillam123/iran-watcher`
5. Repository permissions:
   - **Contents: Read-only** (required so the API recognises the
     token has repo access)
   - **Metadata: Read-only** (auto-granted)
6. Generate token. Copy it immediately — GitHub only shows it once.

(Classic tokens with `public_repo` scope also work, but
fine-grained is preferred — minimum blast radius if leaked.)

### Step 2 · Create a cron-job.org account and a job

1. Sign up at <https://cron-job.org/en/signup/> with your work
   email. Free tier is enough — we only need two jobs.
2. After verifying, click **Create cronjob**.

#### Morning job

- **Title**: `iran-watcher · morning brief`
- **URL**:
  ```
  https://api.github.com/repos/peter-guillam123/iran-watcher/dispatches
  ```
- **Schedule** (expand "Advanced"):
  - **Time zone**: UTC
  - Run every day at **05:25 UTC** (5 minutes before the GH cron
    primary, so this becomes the *primary* path and GH's internal
    schedule becomes the backup)
- **Advanced → Request method**: `POST`
- **Advanced → Request headers**: add two headers
  - `Accept` = `application/vnd.github+json`
  - `Authorization` = `Bearer ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
    (replace with the PAT from step 1)
  - `X-GitHub-Api-Version` = `2022-11-28`
  - `User-Agent` = `iran-watcher-cron`
- **Advanced → Request body**:
  ```json
  {"event_type": "morning_brief"}
  ```
- **Notifications** (optional but recommended): tick "Notify on
  failure" so you get an email if cron-job.org's request to GitHub
  returns non-2xx.
- **Save**.

#### Evening job

Duplicate the morning job, change:
- **Title**: `iran-watcher · evening brief`
- **Schedule**: every day at **14:25 UTC**
- **Request body**: `{"event_type": "evening_brief"}`

### Step 3 · Verify

After saving each job, click **Test run** in cron-job.org. Then:

1. Check <https://github.com/peter-guillam123/iran-watcher/actions/workflows/collect.yml>
   — a new run should appear within seconds, triggered by
   `repository_dispatch`.
2. The run's "Determine edition" step should resolve to `morning` /
   `evening` correctly based on the event type.
3. If today's brief was already generated, the "Skip if today's
   edition is already fresh" step will exit cleanly — that's the
   correct behaviour, not a failure.

---

## Rotating the token

When the PAT expires (1-year default), the cron-job.org request will
start returning 401 from GitHub. Symptoms:

- No new runs in `collect.yml` Actions tab
- cron-job.org's "Last execution" log shows 401 responses

Fix:
1. Generate a new PAT (Step 1 above).
2. Edit each cron-job.org job → Request headers → update the
   `Authorization` header with the new token.

A calendar reminder for ~11 months out is the cheapest way to
catch this before it bites.

---

## Why not a GitHub App or Cloudflare Worker?

Considered both, both rejected as over-engineered:

- **GitHub App** — installable, fine-grained, no token expiry. But
  requires hosting an HTTP listener somewhere (the App needs a
  callback URL during creation, even if we don't use it for cron).
  Not free.

- **Cloudflare Worker** — free tier supports scheduled triggers
  (cron triggers in Workers KV). Would let us self-host the cron
  with no third-party. But adds a Worker deployment, a wrangler
  config, a KV namespace for the token, and another moving piece.

cron-job.org is the cheapest workable thing. If it itself becomes
unreliable, the GH Actions internal schedule still fires four times
per edition. Two independent failure paths is enough.
