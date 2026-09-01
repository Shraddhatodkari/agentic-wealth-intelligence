# Deployment guide: GitHub → local → cloud (no Docker anywhere)

Step by step, small to complete. Do these in order — each step should
work before you move to the next.

This project has **no Docker or Kubernetes dependency at all** — not
locally, not in CI, not in cloud deployment. Everything runs as plain
Python processes, both on your machine and on the hosting provider.

## 1. Verify everything works locally

```bash
cd agentic-wealth-intelligence
pip install -r requirements.txt
pytest tests/ -v            # 110 tests should pass, zero external services needed
python run_demo.py                  # single-filing pipeline
python run_yoy_comparison.py        # year-over-year comparison
python run_evaluation.py            # evaluation harness
uvicorn src.api.main:app --reload --port 8000   # API at localhost:8000/docs
```

Don't skip this. If something fails on your machine before you push, it
will fail in CI too — better to catch it now.

### Running everything at once locally (optional)

`Procfile` declares the app's process types (`web`, `worker`, `dashboard`).
[Honcho](https://github.com/nickstenning/honcho) runs them all from one
terminal, plain Python, no containers:

```bash
pip install honcho   # already in requirements.txt
PORT=8000 honcho start -f Procfile
# or: make dev
```

## 2. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit: multi-agent 10-K analysis pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/agentic-wealth-intelligence.git
git push -u origin main
```

Then in the repo's Actions tab, confirm the `Tests` workflow runs and
goes green. This is the moment the CI badge in your README becomes true
instead of aspirational.

## 3. Fix the README placeholder

Find and replace `YOUR_USERNAME` in `README.md` (badge URL and clone
command) with your actual GitHub username, commit, push.

## 4. (Optional) Get a real Gemini API key and run live once

```bash
export LLM_MODE=live
export GEMINI_API_KEY=your-key-here
python run_demo.py
```

Or run a fully local model with no cloud key at all:

```bash
# Install Ollama from https://ollama.com (native installer, no Docker)
export LLM_MODE=ollama
python run_demo.py
```

Take a screenshot of real (non-mock) output for your portfolio/LinkedIn.
Don't commit any API key — `.env` is already gitignored.

## 5. Deploy the API somewhere reachable (optional, but a strong signal)

You don't need Docker for this — Render and Railway both **auto-detect a
Python app from `requirements.txt` and `Procfile`** and build it natively
(via buildpacks/Nixpacks), no Dockerfile required. This repo doesn't
have one.

**Render:**
1. Go to [render.com](https://render.com), sign in with GitHub
2. "New" → "Web Service" → select `agentic-wealth-intelligence`
3. Render detects it's a Python app automatically. Set:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
     (or leave blank — Render also reads the `web:` line in `Procfile`)
4. Under "Environment," set:
   - `LLM_MODE=mock` (or `live` + `GEMINI_API_KEY`)
   - `API_KEYS=<pick a real key, not the dev default>`
5. Deploy. Visit `https://your-service.onrender.com/docs` to confirm the
   live OpenAPI docs render, and `/health` to confirm it's up.

**Railway** works the same way — connect the repo, it detects Python via
Nixpacks (no Dockerfile involved), reads `Procfile`, set the same env vars.

Either way, once you have a public URL, add it to the README and your
LinkedIn post — a project with a live, click-able API is a materially
stronger signal than one that only runs locally.

## 6. What to actually put on LinkedIn / your resume

- Link to the GitHub repo (not just a screenshot)
- If deployed: the live URL
- Mention the tech stack you can actually defend: LangGraph, ChromaDB,
  Pydantic, FastAPI, Gemini/Ollama — not buzzwords you can't explain
- Don't inflate the build timeline — see `docs/INTERVIEW_PREP.md` for
  how to talk about the real arc of the work honestly

## What's genuinely done vs. what would need more work for true production

**Done, verified working:**
- Full 6-agent pipeline (ingestion → extraction → RAG → synthesis →
  comparison → evaluation)
- Authenticated, role-gated, rate-limited REST API with persistence
  (SQLite) and audit logging
- Retry logic, structured logging, Prometheus metrics, OpenTelemetry tracing
- CI: tests, lint, format check, security scan, coverage — all green
- Load testing run for real (Locust) — see `loadtest/RESULTS.md`
- Buildpack-based deployment (Render/Railway), no Dockerfile needed

**Would need real work for a true production system (say this honestly
if asked, don't pretend it's done):**
- Postgres instead of SQLite for concurrent multi-instance deployments
- Real embedding model (`EMBEDDING_MODE=sentence_transformer`) instead
  of the offline hashing placeholder — needs network access to download
  the model
- Multi-tenant identity management instead of API-key RBAC
- Horizontal scaling validation at production traffic levels
- Live SEC EDGAR ingestion instead of local sample filings (code is
  real and tested via mocks, not yet run against live data)
- Trace/log visualization (Jaeger/Tempo/Loki) — the instrumentation is
  there, the visualization backend isn't; a hosted option like Grafana
  Cloud (free tier) is the no-Docker path if you want to see it rendered
