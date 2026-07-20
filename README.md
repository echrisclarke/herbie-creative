# Herbie Creative

Local proof-of-concept for **creative automation of social ad campaigns**: turn a campaign brief and product assets into multi-ratio stills, then optionally stamp brand-safe message, CTA, and logo on finals.

Built for the FDE Take-Home Lite exercise (creative automation for scalable social campaigns). Stack: **FastAPI + React**, local folders as mock storage, **OpenAI** for GenAI image/copy, **Pillow** for deterministic text/logo overlays, optional **xAI/Grok** for motion.

**Run it three ways:** UI pipeline, **Local CLI** from Intake, or CLI in your own terminal. See [Three ways to run](#three-ways-to-run).

## How-to video and example outputs

Walkthrough video plus sample stills, localized finals, and a motion clip:

**[Clarke How To and Examples (Google Photos)](https://photos.app.goo.gl/yTQzG8yhnPbUhHjB9)**

https://photos.app.goo.gl/yTQzG8yhnPbUhHjB9

---

## Quick start (any computer)

These steps put the app on your **Desktop** and start it. **Git is not required.** The open terminal **is** the local server, so leave it running while you use the app. Stop with `Ctrl+C` (or close the window).

**Ways to start**

| Path | Notes |
|---|---|
| **One-line paste** (below) | Puts the app on your Desktop and starts it. |
| **Download ZIP** + `run_app.py` | Same start without pasting a script. |
| **Git clone** + `run_app.py` | Same start if you already use Git. |
| **Optional npm rebuild** | For editing the React source. `frontend/dist` is already in the repo. |
| **`Open App.bat` / `Open App.sh`** | Mostly for me. On other computers Windows SmartScreen (and the Mac equivalents) often block them. |

The paste below runs a one-line bootstrap: it checks for **Python 3.12+** and installs it when missing (winget on Windows, Homebrew on macOS, apt on Debian/Ubuntu), then downloads the app and starts it. First run also installs Python packages, then opens **http://127.0.0.1:8000**.

### 1. Open a terminal

| OS | How |
|---|---|
| **Windows** | Press `Win`, type **PowerShell** or **Terminal**, open it. |
| **macOS** | `Cmd+Space`, type **Terminal**, open it. |
| **Linux** | Open **Terminal** from the app menu. |

### 2. Paste and run

One line downloads a small bootstrap script, checks/installs Python 3.12+ if needed, puts the app on your Desktop, and starts it. Leave the window open. You may see a permission prompt for the Python install.

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/echrisclarke/herbie-creative/main/scripts/quick-start.ps1 | iex
```

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/echrisclarke/herbie-creative/main/scripts/quick-start.sh | bash
```

That creates `Desktop/herbie-creative`, then starts the app (venv, packages, server, browser).

If auto-install cannot run (no winget / Homebrew / apt), or winget fails with a **Microsoft Store / msstore** error (common on public or locked-down PCs), the Windows Quick start falls back to a **per-user** install from python.org. If that is blocked too, install Python 3.12+ from https://www.python.org/downloads/ yourself: choose **Install for current user**, check **Add python.exe to PATH**, open a **new** terminal, and paste again.

**Browser alternative (no terminal download):** open https://github.com/echrisclarke/herbie-creative → **Code** → **Download ZIP** → extract to your Desktop → rename to `herbie-creative` if needed → open a terminal in that folder → run `py -3 run_app.py` (Windows) or `python3 run_app.py` (Mac/Linux). Same auto-install behavior when Python is missing.

**Or clone with Git** (if you already use Git):

**Windows (PowerShell):**

```powershell
cd ~/Desktop   # or your preferred folder
git clone https://github.com/echrisclarke/herbie-creative.git
cd herbie-creative
py -3 run_app.py
```

**macOS / Linux:**

```bash
cd ~/Desktop   # or your preferred folder
git clone https://github.com/echrisclarke/herbie-creative.git
cd herbie-creative
python3 run_app.py
```

That starts the app the same way as Quick start (venv, packages, server, browser). Leave the window open. After clone or ZIP, start with `run_app.py`.

Enter your **OpenAI API key** when the app asks (Settings also works). First-time setup is: Herbie Creative start screen → keys (if needed) → pipeline. No Node.js required: `frontend/dist` is included. Optional React rebuild: [Optional: rebuild UI from source](#optional-rebuild-ui-from-source).

If a previous install failed halfway, delete `backend/.venv` (or `backend\.venv` on Windows) and run `py -3 run_app.py` / `python3 run_app.py` again from inside `herbie-creative`.

**Grok / motion:** optional `XAI_API_KEY` in Settings.

### Open App.bat / Open App.sh (mostly for me)

I left `Open App.bat`, `Close App.bat`, `Open App.sh`, and `Close App.sh` in the repo because they’re handy for me. I know they don’t travel well. On other computers, Windows SmartScreen and Mac security warnings often stop a downloaded `.bat` or `.sh` from just running.

**Windows:** double-click `Open App.bat` (stop with `Close App.bat` or close the window). If Windows shows *Windows protected your PC*, click **More info** → **Run anyway**, or unblock first: right-click the ZIP or `.bat` → **Properties** → **Unblock** → **OK**, or in the project folder run:

```powershell
Get-ChildItem -File | Unblock-File
```

**macOS / Linux:**

```bash
chmod +x "Open App.sh" "Close App.sh"
./Open\ App.sh
```

Stop with `./Close\ App.sh`. These can auto-install Python via winget / Homebrew / apt when missing.

### Keys

| Key | Required? | Where |
|---|---|---|
| `OPENAI_API_KEY` | Yes (generation) | In-app setup / Settings, or `.env` |
| `XAI_API_KEY` | Optional (Grok motion) | Settings or `.env` |
| `GOOGLE_FONTS_API_KEY` | Optional (font search) | Settings or `.env` |

Copy `.env.example` → `.env` if you prefer files over the UI. **Use your own keys.** Do not commit secrets. Keys saved in the UI go to `private/api_keys.json` (gitignored).

---

## Three ways to run

After the app is on your machine and you have an **OpenAI API key**, pick one path.

| Path | What it is | Best for |
|---|---|---|
| **A. UI pipeline** | Full local app in the browser | Interactive Review → Generate → Finalize → Results |
| **B. Local CLI from the UI** | Intake button opens a terminal and runs the CLI | Same Jordan hero zoom smoke, without walking the UI |
| **C. Local CLI yourself** | You run the CLI in a terminal | Scripting, demos, or reviewers who prefer CLI only |

All three use the same pipeline and write under `campaigns/`.

### A. UI pipeline

1. Start the app with `py -3 run_app.py` / `python3 run_app.py` (or the one-line Quick start). The `.bat` / `.sh` launchers are mostly for me.
2. Open **http://127.0.0.1:8000** and enter your OpenAI key.
3. On **Intake**, open **Sample briefs** and click **Run this sample** on **Jordan hero zoom** (listed first), or paste/upload your own brief.
4. **Review** → **Approve & Generate creatives** → **Finalize** (message/logo optional; captions default to bottom-center, except **16:9 → top-right**) → **Results**.

Pipeline steps: **Intake → Review → Generate → Finalize → Results**.

- **Intake:** paste, upload JSON/YAML/text/PDF, or load a sample. Optional logo / product / style / likeness / background uploads.
- **Review:** products (optional per-product message / CTA / scene), ratios (`1:1` / `9:16` / `16:9`), framing, locales, assets. Optional **Motion notes** for later (no motion is generated on this step).
- **Generate:** no-text heroes (`creative.png`). Progress continues if you leave the page. Stills only.
- **Finalize:** Composer / AI / Hybrid text, or no campaign text. Default caption band is bottom-center for `1:1` / `9:16`, and **top-right for `16:9`**. Writes `final.*.png`.
- **Results / Library:** stills and optional motion. On Results, pick specific stills to animate (nothing is selected by default). Motion notes from the brief carry into an editable prompt there. Motion is not generated during Review/Generate.

### B. Local CLI from the UI

1. Start the app and enter an OpenAI key (same as A).
2. On **Intake**, click **Run local CLI**.
3. A system terminal opens and runs the Jordan hero zoom smoke (full exercise coverage: 2 products; `1:1` / `9:16` / `16:9`; quality=low; framing=zoomed; finals with message + CTA + legal in **en-US / es-ES / zh-CN**; `report.json` + compliance). Each tile is written as soon as it finishes under `campaigns/<id>/outputs/` so **Library / Gallery** in the UI can refresh while the run continues.

You can leave the browser open; the CLI run is independent and prints progress in that terminal.

### C. Local CLI yourself

From the project root (`herbie-creative` / this repo), use the backend venv Python. If `backend/.venv` does not exist yet, start the app once with Quick start (that creates the venv), then run these commands.

**Windows (PowerShell):**

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.cli smoke
```

**macOS / Linux:**

```bash
cd backend
./.venv/bin/python -m app.cli smoke
```

If the venv is already activated:

```bash
cd backend
python -m app.cli smoke
```

`smoke` is the fixed local CLI path (Jordan hero zoom). Alias `assignment` still works.

Defaults favor a complete exercise demo at practical speed: **quality=low**, **framing=zoomed**, **both products × three ratios**, finals with **message + CTA + legal** in **en-US / es-ES / zh-CN**, plus `report.json` and compliance flags. Each ratio is generated, written, and finalized before the next, so you can open the campaign folder or the UI Library / Gallery and watch tiles appear. Smoke writes a fresh campaign id (`jordan-hero-zoom-cli-…`) so runs show up as their own campaign. Pass `--image-quality medium` (or `high`) if you want richer gens.

Same brief with explicit flags (fuller / slower run):

```bash
cd backend
python -m app.cli run ../sample-briefs/jordan-hero-zoom.json --outputs 1:1,9:16,16:9 --framing both --image-quality medium
```

Other briefs:

```bash
python -m app.cli run ../sample-briefs/jordan-frozen-moments-candid.json
python -m app.cli run ../sample-briefs/cardobot.json
```

**Keys for CLI:** set `OPENAI_API_KEY` in `.env` at the project root, or in the environment, before running. Optional `XAI_API_KEY` for motion.

Optional quality / folder slug:

```bash
python -m app.cli smoke --image-quality medium
python -m app.cli smoke --campaign-id my-smoke-run
```

---

## Sample briefs (UI presets)

You do **not** need to write a brief or upload files to test the pipeline. JSON briefs live under `sample-briefs/`; images under `sample-assets/`. Loading a sample in the UI stages assets into a new `campaigns/<id>/` folder.

| Sample (Intake title) | Why use it |
|---|---|
| **Jordan hero zoom** | First sample. Same brief as **Local CLI** / `python -m app.cli smoke` (**Frozen Moments AJ4** + **Shattered Backboard AJ1**, each with its own message / CTA / scene; `1:1` / `9:16` / `16:9`, en/es/zh finals with legal). |
| **Jordan Frozen Moments (candid)** | Lifestyle person demo with AJ4 product refs. |
| **Jordan Shattered Backboard (candid)** | Lifestyle person wearing AJ1 Shattered Backboard (2025). |
| **Jordan Clara studio candid** | Studio candid with likeness + AJ4 product refs. |
| **Card-o-Bot (deck + app)** | Two creative tracks (printed deck + app-on-device). |
| Card-o-Bot apartment deck / hologram deal | Extra Card-o-Bot scenes. |
| Spitfire Deathmask II (US) | Optional skate campaign (two products). |

**Suggested first try:** **Run local CLI**, or **Jordan hero zoom** in the UI. For a richer UI demo after that, try Jordan Frozen Moments (candid) or Card-o-Bot.

### What gets staged

When you run a sample in the UI, the app copies referenced logos and product images into:

```text
campaigns/<new-id>/uploads/logo/
campaigns/<new-id>/uploads/product/
```

…and writes `campaign.json` from the sample brief. From there the flow matches any hand-built Intake campaign.

---

## Example input and output

**Input (excerpt from `sample-briefs/jordan-hero-zoom.json`):**

- Brand / campaign / market / audience / message / CTA  
- Legal disclaimer stating this is an unofficial software-evaluation sample (not a real Jordan / Nike ad)  
- Two products with **their own** message, CTA, and scene direction (Frozen Moments AJ4 vs Shattered Backboard AJ1; shoe refs under `sample-assets/jordan-frozen-moments/` and `sample-assets/jordan-shattered-backboard/`)  
- Outputs: `1:1`, `9:16`, `16:9`  
- Logo path staged from sample assets

**Output layout:**

```text
campaigns/<campaign-id>/
  campaign.json
  outputs/
    us/
      frozen-moments-hero/
        1x1/creative.png
        1x1/creative.tight.png
        1x1/final.en-us.png
        9x16/...
        16x9/...
      frozen-moments-pair/
        1x1/...
  report.json
  report.md
```

- `creative.png` = GenAI still without campaign copy  
- `final.*.png` = same still + Pillow (or AI) message / CTA / logo when Finalize applies text

---

## Design decisions

- **Local folders as storage.** `campaigns/` is the mock object store (Azure/S3/Dropbox-shaped layout without cloud SDKs). Easy to swap later.
- **Two-phase creatives.** GenAI produces clean heroes first; Finalize applies exact brand text with Pillow so copy stays character-accurate and editable.
- **Per-product copy and scenes.** Campaign message/CTA/direction are defaults. Each product can override them (and attach its own style/background refs) so a multi-product run does not stamp one shoe's line or set onto another.
- **Products ≠ product photos.** Products come from the brief. Extra images are references for fidelity, not extra ads.
- **Selectable ratios and framing.** Chained AI reframes across 1:1 / 9:16 / 16:9 (not crop-only).
- **OpenAI primary.** Image + brief parse + localization. Optional xAI motion. Firefly sketched behind the same provider idea when credentials exist.
- **Shipped UI build.** `frontend/dist` is committed on purpose. Normally you would not commit build output, but this path skips Node install and `npm run build` so reviewers can open the app sooner. Rebuild from source is still documented if you want it.

---

## Assumptions and limitations

- Requires a valid **OpenAI** key for real generation.  
- First launch needs network access to install Python (if missing) and Python packages.  
- On Windows, Python auto-install uses **winget** and may show a permission prompt. On Mac/Linux it uses Homebrew or apt when available.  
- Runtime outputs under `campaigns/` are gitignored (regenerate via samples).  
- Brand/legal checks are basic (logo presence, colors, forbidden words), not a full DAM/compliance suite.  
- Adobe Firefly is documented as planned, not wired as the default path.  
- `Open App.bat` / `Open App.sh` are mostly for me. SmartScreen and Mac security warnings often stop them on someone else’s machine.

---

## How this meets the exercise

Separate checklist against the FDE Take-Home Lite requirements.

### Required

| Requirement | How this repo meets it |
|---|---|
| Accept a campaign brief (JSON, YAML, or reasonable format) with **product(s) (≥2)**, **target region/market**, **target audience**, **campaign message** | Intake accepts paste or upload (JSON / YAML / text / PDF). Primary sample `jordan-hero-zoom.json` has **two products**, market, audience, message, and a legal disclaimer. Each product can also carry its own **message / CTA / creative_direction** (and style/background refs) when stories differ; empty fields fall back to campaign defaults. Other samples (`cardobot.json`, `spitfire-deathmask-us.json`, etc.) also include market/audience/message; Card-o-Bot and Spitfire ship **two products**. Free-text briefs are parsed into the same schema. |
| Accept input assets (local / mock storage) and **reuse when available** | Role uploads (logo, product refs, style, likeness, background) stage into `campaigns/<id>/uploads/`. Sample assets live in `sample-assets/`. Modes: **use-provided** reuses photos; paths are remapped on parse/Review. |
| When assets are missing, **generate with a GenAI image model** | **generate-concept** (and background product-seed generation when no photos were uploaded) calls OpenAI image generation / edit APIs. |
| Produce creatives for **at least three aspect ratios** (e.g. 1:1, 9:16, 16:9) | Review defaults and samples set `outputs: ["1:1","9:16","16:9"]`. CLI `smoke` forces those three. Pipeline writes one folder per ratio under each product. |
| **Display campaign message** on final posts (English at least; localization a plus) | Finalize (and CLI smoke) stamps **per-product** message + CTA when set, else campaign defaults, plus legal. Locales: **en-US / es-ES / zh-CN** on smoke. |
| **Run locally** (CLI or simple local app) | **A** UI via Quick start / `run_app.py`. **B** Intake **Run local CLI**. **C** `backend` then `python -m app.cli smoke` (see Three ways to run). |
| **Save outputs** organized by product and aspect ratio | `campaigns/<id>/outputs/<market>/<product-slug>/<ratio>/`. |
| **README**: how to run, example I/O, design decisions, assumptions/limitations | This file. |

### Nice to have (bonus)

| Nice to have | Support in this POC |
|---|---|
| Brand compliance checks (logo, brand colors) | Finalize / report path can require logo and use brand color notes; compliance helpers flag gaps. |
| Simple legal / prohibited-word checks | `brand_notes.forbidden_words` and compliance scanning on copy. |
| Logging or reporting of results | `report.json` + `report.md` per campaign; Library gallery for browsing. |

### Deliverables

| Deliverable | Status |
|---|---|
| Working POC pipeline | This repository |
| Comprehensive README | This file |
| Public GitHub repo | Published from this project root |
| 2–3 minute demo video | How-to video and example outputs: [Clarke How To and Examples](https://photos.app.goo.gl/yTQzG8yhnPbUhHjB9). Suggested local path to regenerate: **Run local CLI** (Jordan hero zoom) or Intake sample → Review → Generate → Finalize → Results. |

---

## Optional: rebuild UI from source

Only needed if you change the React app:

```bash
cd frontend
npm install
npm run build
```

## Optional: backend sync

```bash
cd backend
python -m uv sync
# or: pip install -e .
```

## Optional: local CLI (shortcut)

Same as **C. Local CLI yourself** above:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.cli smoke
```

```bash
cd backend
./.venv/bin/python -m app.cli smoke
```

---

## Project layout

```text
creative-automation/
  run_app.py                     # normal start (bootstrap + uvicorn)
  Open App.bat / Open App.sh     # mostly for me (often blocked elsewhere)
  Close App.bat / Close App.sh   # stop server
  frontend/dist                  # shipped UI (no npm needed to open)

  backend/app                    # FastAPI, pipeline, providers
  sample-briefs/                 # demo JSON briefs
  sample-assets/                 # demo logos / product refs
  campaigns/                     # local runtime storage (gitignored)
```

## License / keys note for reviewers

Use **your own** API keys. Don’t ask me for keys, and don’t commit `.env` or `private/`.
