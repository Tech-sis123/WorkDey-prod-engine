# WorkDey Smart Match & Apply — engine

Flask backend for profile-based search, scheduled alerts, and AI apply packs.

Extract this folder, add API keys, run. The engine harvests job-like posts from X, LinkedIn, and Instagram via Apify, matches them to each seeker’s profile, emails a short Brevo note, and drafts reply / cover letter / CV.

## What you add

Copy `.env.example` to `.env` and set:

| Key | What it does |
|---|---|
| `SECRET_KEY` | Flask sessions. Any long random string. |
| `APIFY_API_TOKEN` | Powers all four scrapers. |
| `BREVO_API_KEY` | Transactional mail. Also set `BREVO_SENDER_EMAIL` to a verified sender. |
| `XAI_API_KEY` | Optional. Grok drafts. Without it, grounded templates still work. |
| `APP_BASE_URL` | Public URL of this app (used in email deep links). |
| `KEEPALIVE_URL` | Optional. Pinger GETs this so a free host does not sleep. |

That is enough. First-party WorkDey jobs always match even with no Apify token.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python run.py
```

Listens on `0.0.0.0:8080`. Production (one worker so the scheduler is not duplicated):

```bash
gunicorn -w 1 -k gthread --threads 8 -b 0.0.0.0:8080 wsgi:app
```

## Scrapers (Apify)

| Source | Actor | Kill switch |
|---|---|---|
| X | `apidojo/twitter-scraper-lite` | `SOURCE_X_ENABLED` / Engine → Kill x |
| LinkedIn jobs | `curious_coder/linkedin-jobs-scraper` | `SOURCE_LINKEDIN_JOBS_ENABLED` |
| LinkedIn posts | `supreme_coder/linkedin-post` | `SOURCE_LINKEDIN_POSTS_ENABLED` |
| Instagram | `apify/instagram-scraper` | `SOURCE_INSTAGRAM_ENABLED` |

Harvest is **global**, not per user. A query planner unions every Watch-on profile’s target roles with a Nigerian hiring seed list, then the matcher scores new opportunities against each due user. That keeps Apify spend flat as users grow.

## Scheduler + pinger

Not one cron per user. Each Watch row has `next_run_at`. Every 30s a worker claims due rows, matches against opportunities ingested since `last_run_at`, writes Match cards, sends at most 3 short emails a day, then sets `next_run_at = now + cadence`, skipping quiet hours (default 21:00–07:00 WAT).

The pinger ticks every 20s:

- heartbeats for matcher, ingest, each source
- restarts a stalled scheduler
- optional `KEEPALIVE_URL`
- `GET /health` and `GET /ping` for UptimeRobot

Point any external monitor at `/ping`.

## Email (Brevo)

Every mail is sent **from WorkDey** (`BREVO_SENDER_NAME=WorkDey`). Copy always starts `Hey there, {name}.` and always ends `WorkDey for you!!!`

| When | What they get | Buttons |
|---|---|---|
| Sign up | Confirmation that all future notifications come from WorkDey | Open your inbox · Complete your profile |
| New match | Role, one-line why, source | **Open the post** (original X / LinkedIn / Instagram / WorkDey URL) · **Open your inbox** |
| Digest | N matches waiting | Same two buttons |

Inbox link `/i/<token>` signs them in and opens the web app. Scraped matches are already there. From a match they prompt Grok for a reply, cover letter, or CV tailored to the role.

Deep links: `/m/<token>` opens that match; `/i/<token>` opens the inbox.

If `BREVO_API_KEY` is missing, the same payload is stored in Outbox so you can still QA copy.

`POST https://api.brevo.com/v3/smtp/email`. Sender name is hard-coded to WorkDey. Verify `BREVO_SENDER_EMAIL` in the Brevo dashboard.

## AI drafts

From Match detail: Reply, Cover letter, CV revamp. LinkedIn-classified matches lead with cover + CV. X/Instagram lead with a short reply. The model may only use the profile, uploaded CV, and the post. It will refuse scams and non-jobs. Rate-limited per user per day.

## API sketch

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/signup` `/login` `/demo` `/logout` | Session cookie |
| GET | `/api/state` | Profile + watch + unread |
| POST | `/api/profile` | Skills, roles, locations |
| POST | `/api/profile/cv` | multipart PDF/DOCX |
| POST | `/api/watch` | cadence 3 / 5 / 24, quiet hours, sources |
| POST | `/api/watch/run` | match this user now |
| GET | `/api/matches` `/api/matches/:id` | inbox + detail |
| POST | `/api/matches/:id/generate` | `{kind: reply\|cover\|cv, note}` |
| GET | `/api/matches/:id/pdf/:kind` | download |
| POST | `/api/ops/ingest` | `{source?}` harvest |
| POST | `/api/ops/kill` | `{source, killed}` |
| GET | `/health` `/ping` | liveness |

## Demo

`DEMO_MODE=1` seeds a seeker (`blessing@workdey.app` / `WorkDey2026!`) plus Lagos-first jobs so the inbox is never empty while you wait on Apify.
