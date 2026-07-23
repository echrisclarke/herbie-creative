# Deploy Herbie Creative on Railway

This app is FastAPI + the built React UI. It does **not** run on Bluehost shared PHP hosting. Railway runs the same system. DNS for `herbiecreative.com` is managed in **Squarespace**.

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
| `OPENAI_API_KEY` | **your** key for the 3-run free trial only |
| `XAI_API_KEY` | optional; trial motion while free runs remain |
| `TRIAL_RUNS_LIMIT` | `3` (default) |

After 3 generate runs without their own key, users must paste an OpenAI key in Settings. Your host key is never shown in the UI.

5. **Volume:** add a volume mounted at `/data` so campaigns and `app.db` survive redeploys.
6. Redeploy. Build should use the Dockerfile (not Railpack guessing).
7. Open the Railway URL → sign in with the bootstrap admin.

## 3. Custom domain DNS (Squarespace, not Bluehost folders)

Do **not** create a Bluehost `public_html` subdomain folder for this app. The portfolio stays on Bluehost; the campaign app stays on Railway.

1. Railway → Custom Domain → add `campaign.herbiecreative.com` (copy the CNAME target).
2. Squarespace → Domains → DNS → **Custom records** → **Add record**:
   - Type: **CNAME**
   - Name: `campaign`
   - Data: the Railway hostname (for example `something.up.railway.app`)
3. Save and wait for DNS. HTTPS is handled by Railway.

## 4. Invite other users

While signed in as the admin, open **Settings → Invite user**. They get their own campaigns and API keys (plus the 3 free trial runs).

## 5. Optional hub link

On `herbiecreative.com` (Bluehost `public_html`), add a link to `https://campaign.herbiecreative.com`. No Python upload to Bluehost.

## Local vs hosted

| | Local (`run_app.py`) | Railway (`HOSTED=1`) |
|---|---|---|
| Login | Not required | Required |
| API keys | `.env` or `private/api_keys.json` | Per-user encrypted; 3 trial runs on host key |
| Campaigns | `campaigns/` | `/data/campaigns/<user_id>/` |
| Reveal folder / Local CLI | Available | Hidden |
