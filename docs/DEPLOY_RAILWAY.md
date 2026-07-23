# Deploy Herbie Creative Campaign Pipeline at herbiecreative.com/pipeline

Live URL: **https://herbiecreative.com/pipeline**

The FastAPI app runs on Railway under the `/pipeline` path. Bluehost keeps the main PHP site and reverse-proxies only `/pipeline` to Railway. DNS stays in Squarespace (A record for `@` → Bluehost). Do **not** create a Bluehost `public_html/pipeline` app folder, and do **not** add a Squarespace CNAME for a campaign subdomain.

## 1. Railway

1. Connect GitHub `echrisclarke/herbie-creative` and deploy (Dockerfile).
2. **Variables:**

| Variable | Value |
|---|---|
| `HOSTED` | `1` |
| `ROOT_PATH` | `/pipeline` (also set in the Dockerfile) |
| `DATA_ROOT` | `/data` |
| `CAMPAIGNS_ROOT` | `/data/campaigns` |
| `SECRET_KEY` | long random string |
| `ENCRYPTION_KEY` | long random string |
| `BOOTSTRAP_ADMIN_EMAIL` | your email (first admin) |
| `BOOTSTRAP_ADMIN_PASSWORD` | strong password |
| `OPENAI_API_KEY` | your key for the pre-signup free trial |
| `TRIAL_RUNS_LIMIT` | `3` generate runs before signup |
| `TRIAL_MAX_STILLS_PER_RUN` | `6` |
| `TRIAL_MAX_TOTAL_STILLS` | `18` |
| `TRIAL_FORCE_QUALITY` | `low` |
| `TRIAL_GLOBAL_DAILY_RUNS` | `100` site-wide cap |

Guests can try before signup (3 generate runs, low quality, still caps, no motion). After signup they must add their own OpenAI key.

3. **Volume** at `/data`.
4. Confirm the Railway URL works at `https://YOUR-APP.up.railway.app/pipeline/`.

No custom domain on Railway is required if Bluehost proxies `/pipeline`.

## 2. Bluehost reverse proxy

Edit [`public_html/.htaccess`](../../public_html/.htaccess): uncomment the `mod_proxy` block and set your Railway host:

```apache
<IfModule mod_proxy.c>
  SSLProxyEngine On
  ProxyPreserveHost Off
  ProxyPass        /pipeline https://YOUR-APP.up.railway.app/pipeline
  ProxyPassReverse /pipeline https://YOUR-APP.up.railway.app/pipeline
</IfModule>
```

Upload via Upload Manager. Then open https://herbiecreative.com/pipeline/

If Apache returns 500 or ignores ProxyPass, shared hosting may block `mod_proxy`. Ask Bluehost support to allow reverse proxy for `/pipeline`, or put Cloudflare in front and route `/pipeline*` to the Railway origin.

## 3. Squarespace DNS

Leave `@` pointing at Bluehost (`162.241.226.190`). No new CNAME for this app.

## 4. Invite users

Admin → Settings → Invite user. Each account gets 3 free generate runs on your host key, then must add their own OpenAI key.

## Local vs live

| | Local (`run_app.py`) | Live |
|---|---|---|
| URL | http://127.0.0.1:8000/ | https://herbiecreative.com/pipeline/ |
| `ROOT_PATH` | unset | `/pipeline` |
| Login | Not required | Required |
