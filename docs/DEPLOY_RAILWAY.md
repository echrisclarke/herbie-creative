# Deploy Campaign Pipeline at pipeline.herbiecreative.com

Live URL: **https://pipeline.herbiecreative.com/**

The FastAPI app runs on Railway. DNS for the subdomain is a Squarespace CNAME to Railway. The main site (`herbiecreative.com` → Bluehost) stays unchanged. Bluehost reverse proxy is **not** used (shared hosting blocks `ProxyPass`).

## 1. Railway app settings

1. Connect GitHub `echrisclarke/herbie-creative` and deploy (Dockerfile).
2. **Variables:**

| Variable | Value |
|---|---|
| `HOSTED` | `1` |
| `ROOT_PATH` | leave empty / unset (app at domain root) |
| `DATA_ROOT` | `/data` |
| `CAMPAIGNS_ROOT` | `/data/campaigns` |
| `SECRET_KEY` | long random string |
| `ENCRYPTION_KEY` | long random string |
| `BOOTSTRAP_ADMIN_EMAIL` | your email (first admin) |
| `BOOTSTRAP_ADMIN_PASSWORD` | strong password |
| `OPENAI_API_KEY` | your key for the post-signup free trial |
| `TRIAL_RUNS_LIMIT` | `3` |
| `TRIAL_MAX_STILLS_PER_RUN` | `6` |
| `TRIAL_MAX_TOTAL_STILLS` | `18` |
| `TRIAL_FORCE_QUALITY` | `low` |
| `TRIAL_GLOBAL_DAILY_RUNS` | `100` |

Visitors can browse the library without an account. Signup is required to run the pipeline so creatives save under `campaigns/<user_id>/`. New accounts get 3 host-key generate runs (low quality, still caps), then add their own OpenAI key.

3. **Volume** at `/data`.
4. Confirm the default Railway URL works at the **root**:  
   `https://YOUR-APP.up.railway.app/`  
   (not `/pipeline/` once `ROOT_PATH` is empty).

## 2. Railway custom domain

1. Railway → your service → **Settings → Networking → Custom Domain**.
2. Add: `pipeline.herbiecreative.com`
3. Copy the **CNAME** target Railway shows (and the **TXT** verify record if shown).

## 3. Squarespace DNS

DNS for `herbiecreative.com` is in Squarespace. Leave `@` → Bluehost alone.

1. Squarespace → **Domains** → `herbiecreative.com` → **DNS Settings**.
2. Add **CNAME**:
   - Host: `pipeline`
   - Data / points to: the value Railway gave you (often `….up.railway.app`)
3. If Railway shows a **TXT** for verification, add that too.
4. Wait for DNS (often a few minutes; can take longer).

## 4. Confirm

Open **https://pipeline.herbiecreative.com/**  
You should see Campaign Pipeline (landing / free trial / login).

## 5. Optional hub link

On the main PHP site, link to `https://pipeline.herbiecreative.com/` (no Bluehost upload required for the app itself).

## Local vs live

| | Local (`run_app.py`) | Live |
|---|---|---|
| URL | http://127.0.0.1:8000/ | https://pipeline.herbiecreative.com/ |
| `ROOT_PATH` | unset | unset / empty |
| Login | Not required | Sign up to run; 3 host-key trial runs, then own keys |
