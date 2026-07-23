# Deploy Herbie Creative on Railway

This app is FastAPI + the built React UI. It does **not** run on Bluehost shared PHP hosting. Railway runs the same system; Bluehost only needs a DNS CNAME for your subdomain.

## 1. Push this repo

Commit and push `main` (Dockerfile + `railway.toml` included) to GitHub:
`echrisclarke/herbie-creative`.

## 2. Railway service

1. Open [Railway](https://railway.app) → your `herbie-creative` project.
2. Connect the GitHub repo if it is not already connected.
3. Open the service → **Settings**:
   - **Builder:** Dockerfile (from `railway.toml`)
   - Root directory: repo root (where `Dockerfile` lives)
4. **Variables** (Settings → Variables):

| Variable | Value |
|---|---|
| `HOSTED` | `1` |
| `DATA_ROOT` | `/data` |
| `CAMPAIGNS_ROOT` | `/data/campaigns` |
| `SECRET_KEY` | long random string (session cookies) |
| `ENCRYPTION_KEY` | long random string (encrypts user API keys) |
| `BOOTSTRAP_ADMIN_EMAIL` | your email (first admin only) |
| `BOOTSTRAP_ADMIN_PASSWORD` | strong password (change after first login) |

Do **not** set `OPENAI_API_KEY` / `XAI_API_KEY` on the server for shared use. Each user pastes their own keys in Settings after login.

5. **Volume:** add a volume mounted at `/data` so campaigns and `app.db` survive redeploys.
6. Redeploy. Build should use the Dockerfile (not Railpack guessing).
7. Open the Railway URL → sign in with the bootstrap admin → Settings → add your OpenAI key.

## 3. Custom domain (Bluehost DNS)

1. In Railway → service → **Settings → Networking → Custom Domain** → add `campaign.herbiecreative.com` (or the name you want).
2. Railway shows a CNAME target (for example `xxx.up.railway.app`).
3. In Bluehost → Domains → Zone Editor for `herbiecreative.com`:
   - Type: **CNAME**
   - Host: `campaign`
   - Points to: the Railway hostname
4. Wait for DNS, then confirm HTTPS works on `https://campaign.herbiecreative.com`.

## 4. Invite other users

While signed in as the admin, open **Settings → Invite user**. They get their own campaigns and API keys.

## 5. Optional hub link

On `herbiecreative.com` (Bluehost `public_html`), add a link to `https://campaign.herbiecreative.com`. No Python upload to Bluehost.

## Local vs hosted

| | Local (`run_app.py`) | Railway (`HOSTED=1`) |
|---|---|---|
| Login | Not required | Required |
| API keys | `.env` or `private/api_keys.json` | Per-user encrypted in SQLite |
| Campaigns | `campaigns/` | `/data/campaigns/<user_id>/` |
| Reveal folder / Local CLI | Available | Hidden |
