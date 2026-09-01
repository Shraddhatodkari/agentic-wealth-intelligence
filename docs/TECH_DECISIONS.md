# Tech stack decisions

Every tool in this project was chosen for a specific reason. This doc is
for you, not the recruiter — read it before any interview so you can
answer "why did you use X instead of Y" without hesitating.

## Why LangGraph, not a single prompt or plain LangChain chain?

A single prompt asking the LLM to "extract risks and write a memo" produces
unstructured output you can't validate or reason about programmatically.
LangGraph gives you a **stateful graph**: each agent is a node with a typed
input/output, state passes explicitly between nodes, and you can inspect
or replay any intermediate step. A plain LangChain `Chain` can do
sequential steps too, but LangGraph's explicit state object
(`PipelineState` in `orchestrator.py`) is what makes each stage
independently testable — that's why `tests/test_orchestrator.py` can
assert on `result["extraction"]` and `result["report"]` separately.

**If asked "why not just one big prompt":** because you lose the ability
to validate, retry, or unit test individual stages, and a single prompt
covering extraction + synthesis in one shot degrades quality on longer
documents — the model has to hold too much in one generation.

## Why Pydantic schemas on every LLM call?

LLMs return text, not data. Without a schema, "extract the debt covenants"
might come back as a paragraph, a bullet list, or a table — format varies
run to run, so downstream code can't rely on it. Every agent forces the
LLM response into a Pydantic model (`schemas.py`); if the model returns
something that doesn't fit the schema, `model_validate()` raises instead
of silently passing bad data to the next agent. This is the difference
between "vibes-based" LLM output and something you can build a pipeline on.

## Why ChromaDB over Pinecone/Weaviate/pgvector?

ChromaDB runs embedded, in-process, no external service or account
needed — appropriate for a single-user analysis tool, not a multi-tenant
SaaS product. Pinecone/Weaviate are the right call if this became a
production service serving many users concurrently; for this scope,
running a vector DB as a managed external service would be over-engineering.

**Trade-off to be honest about:** Chroma's local persistence isn't built
for high-concurrency production workloads. If asked "how would you scale
this," the honest answer is "swap ChromaDB for a managed vector store
once there's a real concurrent-user requirement" — not pretend Chroma was
the production-scale choice.

## Why a custom hashing embedding function instead of a real embedding model?

This is the one place in the project you should be upfront about a
limitation rather than oversell it. `HashingEmbeddingFunction` in
`rag_agent.py` is a hashed-word-n-gram embedding — it's deterministic and
requires no model download or API key, which kept the project runnable
offline in a sandboxed dev environment with restricted network access.
It is **not** semantically meaningful the way a real embedding model
(all-MiniLM-L6-v2, or Gemini's embedding endpoint) is — it can find exact
or near-exact word overlap, not paraphrases or synonyms.

**If asked "does this actually do semantic search":** no, not yet in the
mock-mode default — be honest that it's a placeholder and the real
embedding function (`SentenceTransformerEmbeddingFunction`, already
supported since `RAGAgent` takes `embedding_function` as a constructor
argument) is a one-line swap once you have real network/model access.
This is a better answer than claiming it's production-grade semantic
search when it isn't.

## Why Gemini 2.0 Flash and not GPT-4 or Claude?

Free tier availability for a personal project without ongoing API cost,
and fast/cheap enough for iterative development. The choice is not load-
bearing to the architecture — `llm_client.py` isolates all model-specific
code behind one class, so swapping providers means changing one file, not
the pipeline.

## Why mock mode by default?

Two reasons, both legitimate to state in an interview:
1. **Cost/reproducibility** — tests that call a real LLM are slow, cost
   money, and can flake on nondeterministic output. Mock mode makes the
   test suite fast, free, and deterministic.
2. **Separation of concerns** — the tests are verifying pipeline logic
   (chunking, schema validation, state passing, LangGraph routing), not
   whether Gemini can write a good memo. That's a different kind of
   testing (prompt evaluation), which is a legitimate next step but a
   distinct concern from unit/integration testing the code.

## What you should NOT claim in an interview

- Don't say this has been used on real financial data — it's demonstrated
  on a synthetic filing.
- Don't say the RAG retrieval is production-grade semantic search — see
  above.
- Don't claim a specific "% time saved" number unless you can explain how
  you'd measure it; if pushed, say "estimated based on manual read time
  vs. pipeline run time for a filing of this length" rather than citing
  a precise, unverifiable percentage.
- Don't call this "enterprise-grade" without qualification. It has real
  production-readiness patterns (auth, RBAC, rate limiting, retries,
  structured logging, persistence, metrics, tracing) but no multi-tenant
  identity management and no test under real production-scale traffic.
  Say what's there and what isn't — see below.

## Why add a REST API layer (FastAPI) on top of the pipeline?

Scripts (`run_demo.py`) are fine for a personal demo but don't reflect how
this would actually be consumed — another service, or a frontend, calling
it over HTTP. Wrapping the pipeline in FastAPI endpoints (`/analyze`,
`/compare`, `/evaluate`, `/ask`) is what turns "a pipeline that runs" into
"a service something else can integrate with."

**If asked "why FastAPI and not Flask/Django":** FastAPI gives you
request/response validation via Pydantic for free (the same schemas used
internally double as the API contract), automatic OpenAPI docs at `/docs`,
and native async support — relevant since LLM calls are I/O-bound.

## Why API-key auth instead of OAuth2/JWT?

Honest answer, not a dodge: a static API-key allowlist checked with
constant-time comparison (`hmac.compare_digest`, in `src/api/auth.py`) is
the right scope for a single-service portfolio project with no real user
accounts. **If asked "how would you make this multi-tenant":** swap in a
real identity provider (Auth0, AWS Cognito, or a JWT-based auth service)
backed by a user database with per-tenant key scoping and revocation —
that's a different, larger piece of infrastructure than this project
needed to demonstrate the pattern.

## Why rate limiting (slowapi)?

Any public-facing API that fans out to an LLM needs to protect against
both abuse and runaway cost — an unthrottled endpoint calling Gemini per
request is a cost incident waiting to happen. `slowapi` gives per-client
rate limiting keyed by IP; a production version would key by API key/tenant
instead and probably move enforcement to an API gateway rather than
in-process middleware.

## Why retry logic (tenacity) on the LLM client?

Transient failures (rate limits, brief timeouts, malformed JSON from a
non-deterministic model) are the norm for external API calls, not the
exception. `_live_call_with_retry` in `llm_client.py` retries up to 3
times with exponential backoff specifically on JSON-parsing failures —
the most common failure mode when forcing an LLM into structured output.
It does **not** retry on auth or configuration errors, since those won't
resolve on retry.

## Why structured (JSON) logging?

Print statements don't work as an operational tool once something runs
as a service — you need log lines a system like CloudWatch or Datadog can
parse, filter, and alert on. `src/logging_config.py` emits JSON with a
per-request `request_id` (assigned in middleware) so every log line from
a single HTTP request can be correlated, which matters once requests are
concurrent.

## What's honestly still missing for real "enterprise" status

Say this proactively — it reads as maturity, not weakness:
- No persistent database (extraction results, job history) — everything
  is either mock fixtures or held in an in-memory dict per process
- No test under real concurrent load — rate limiting is implemented but
  not load-tested
- No horizontal scaling validation (multiple API instances, shared cache)
- Auth is API-key-only, not full multi-tenant identity management
- No CI/CD deployment pipeline beyond the test-running GitHub Action —
  no automated deploy to a cloud target

## Why a real SEC EDGAR client instead of another synthetic stub?

`src/edgar_client.py` genuinely calls SEC's public APIs (ticker lookup,
submissions JSON, filing document download) - it's not a placeholder.
It isn't exercised against the live network in CI (see
`tests/test_edgar_client.py`, which mocks `requests.get` against
realistic response shapes), for the same reason LLM calls are mocked by
default: fast, deterministic, no external dependency for the test suite
to pass. Running it for real requires your own network access and a
`SEC_USER_AGENT` (SEC requires a descriptive identifier for API access).
No filing text from this client ships in the repo - real filing text
belongs to the filer, so a public portfolio repo doesn't reproduce it.

**If asked "have you actually run this against a real company":** be
honest either way. If you have, say which company and what worked. If
you haven't yet, say the code is real and tested via mocks, and running
it live is a `SEC_USER_AGENT` env var away - don't claim you've fetched
real filings if you haven't actually done it.

## Why role-based access control (RBAC)?

Real systems rarely have one undifferentiated API key - a viewer
shouldn't be able to trigger expensive LLM-backed analysis, and only an
admin should be able to delete records. `src/api/auth.py` implements a
three-tier hierarchy (viewer < analyst < admin) via `key:role` pairs in
`API_KEYS`. This demonstrates the *pattern* (hierarchical role checks as
a FastAPI dependency) at the scope appropriate for a single-service
project - a real multi-tenant system would back this with a database-
backed roles table, not a static env var.

## Why caching, and why in-memory rather than Redis?

Identical `/analyze` calls (same company/fiscal_year/filing_path) within
a short window are pure waste to recompute. `src/cache.py` uses
`cachetools.TTLCache`, in-process, 5-minute TTL. Honest limitation: this
cache doesn't share state across multiple API instances - a production
multi-instance deployment would use Redis so all instances share one
cache. Say this proactively if asked "does this work if you scale to
multiple instances" - it doesn't, and the fix is a known, small change
(swap TTLCache for a Redis client behind the same two functions).

## Why export to Markdown/PDF/DOCX instead of just JSON?

An analyst receiving this output wants something to forward or file, not
a JSON blob. `src/report_export.py` renders any persisted report into
all three formats from the same source data - one function per format,
sharing the same report_type branching logic, so adding a fourth format
later means adding one function, not restructuring the pipeline.

## Why Procfile + buildpack deployment instead of Docker/Kubernetes?

Docker Desktop caused real stability problems on the machine this
project was built on (a BSOD tied to `dxgmms2.sys`, consistent with a
known Docker Desktop WSL2/Hyper-V + GPU driver conflict on some Windows
laptops) - not a reason to avoid containerization on principle, but a
concrete, practical reason to choose a path that doesn't need it here.
`Procfile` declares process types (`web`, `worker`, `dashboard`) in the
same format Heroku popularized; Render and Railway both auto-detect a
Python app via `requirements.txt` + `Procfile` and build it with a
buildpack (Nixpacks/similar), no Dockerfile needed. Locally,
[Honcho](https://github.com/nickstenning/honcho) reads the same
`Procfile` to run multiple processes from one terminal - also just a
pip package, no daemon, no virtualization layer.

**If asked "why not Kubernetes for orchestration/scaling":** Kubernetes
solves problems (multi-node scheduling, complex networking, rolling
deployments across many replicas) this project's actual scale doesn't
have yet. Render/Railway's built-in autoscaling covers horizontal
scaling for a single-service API without that operational overhead -
the right-sized choice here, not a limitation to apologize for. If this
needed true multi-service, multi-team orchestration at real scale,
Kubernetes would be the right escalation - that's a distinct problem
from "does this app run reliably," which Procfile + a buildpack host
already answers.

## Why Celery for async jobs instead of FastAPI's own BackgroundTasks?

FastAPI's `BackgroundTasks` runs in the same process and is lost if that
process restarts - fine for fire-and-forget logging, not for a job a
client wants to poll and retrieve results from later. Celery with Redis
as broker/backend gives a real job queue: the task survives API process
restarts, can be retried, and scales by adding worker processes
independently of API processes. The `worker:` line in `Procfile` runs it
as a separate process type from `web:` for exactly this reason - same
separation of concerns Docker Compose would have given, without needing
Docker to get it.

## Why OpenTelemetry tracing in addition to Prometheus metrics?

They answer different questions. Prometheus/`metrics.py` gives
aggregate numbers - "what's the p95 latency of `/analyze` over the last
hour." Tracing (`tracing.py`) gives per-request causality - "for this
one slow request, which of the four agent stages took the time." Both
matter in production; metrics tell you something's wrong, traces tell
you where.

## Why Grafana dashboard panels only use metrics this app actually exports?

`tests/test_monitoring_config.py` asserts every PromQL expression in the
dashboard JSON references a real exported metric name from
`src/metrics.py`. It would be easy to build a dashboard with plausible-
looking panels for things not actually instrumented (Redis hit rate,
Celery queue depth, CPU/memory) - those need `redis_exporter`,
Celery's Flower/prometheus exporter, and `node_exporter`/cAdvisor
respectively, none of which are wired up here. The shipped dashboard
only shows what's real: HTTP request rate/latency/errors and per-agent-
stage execution time. Extending it with Redis/Celery/system metrics is
a legitimate next step - say that directly if asked, rather than
implying the dashboard already covers infrastructure it doesn't.

## Why a confidence-threshold approval workflow instead of always trusting the AI output?

Regulated-industry decision-makers (credit committees, M&A due diligence
teams) don't accept an AI recommendation unreviewed - that's not a
technology limitation, it's a governance requirement. `src/approval_workflow.py`
implements the simplest defensible version: the synthesis agent
self-assesses confidence (0-1) as part of its structured output, and
anything below a threshold (default 90%, configurable) is held for a
human reviewer instead of reaching a decision-maker automatically.

**If asked "how is confidence actually calculated":** it's the LLM's
own self-assessment, prompted explicitly to be conservative about
genuine uncertainty (unresolved legal outcomes, sparse data) rather than
a separately-computed statistical confidence interval. That's an honest
limitation to name directly - a more rigorous version might calibrate
against historical accuracy (comparing past auto-approved recommendations
to actual outcomes) rather than relying on self-report. Say that
directly if pushed on rigor; the routing *mechanism* is real and tested,
the confidence *source* is a reasonable v1, not a calibrated model.

**If asked "does the AI learn from reviewer feedback":** be precise -
every reviewer decision is persisted (`FeedbackRecord` in `db.py`) with
the original recommendation, the reviewer's edit, and their notes. That
is real, labeled training data. What doesn't happen: no weights update,
no prompt automatically changes, no online learning. The data pipeline
for a future fine-tuning or prompt-improvement pass exists; the learning
loop itself is a next step, not something already built. Overclaiming
this in an interview is an easy way to get caught out by a follow-up
question - don't.

## Why deterministic ranking for the portfolio feature instead of another LLM call?

`src/portfolio_agent.py` computes growth/risk/debt rankings directly
from each company's already-extracted, schema-validated data - average
revenue YoY%, legal-risk severity weighted sum, count of non-compliant
covenants - rather than asking an LLM to rank companies. This is
deliberate: a ranking used to prioritize which companies get closer
scrutiny should be reproducible and auditable. Two runs against the same
extracted data must produce the same ranking; an LLM re-ranking call
wouldn't guarantee that. The one genuinely LLM-generated piece is the
`sector_narrative` - a field that needs synthesis/judgment a
deterministic aggregation can't provide, requested as its own small
schema (`SectorNarrative`) so that call can't alter the rankings
themselves.

**If asked "why not have the LLM do the ranking too":** because
non-determinism is the wrong property for a ranking that might drive a
"which company gets reviewed first" decision. Deterministic code is also
faster and cheaper - no LLM round-trip needed for the numeric part.

## Real bugs found and fixed from live-ticker testing (AAPL, MSFT, NVDA, AMZN, TSLA)

Running real companies through Ollama surfaced failure modes the
synthetic sample filings never exposed. Each is fixed structurally,
not just prompted against, with a test reproducing the exact observed bug:

- **"Company Name" / wrong fiscal year placeholders.** The extraction and
  synthesis schemas required the LLM to echo back `company`/`fiscal_year`
  it was already given as input - exactly the field a smaller model is
  most likely to hallucinate a generic placeholder for. Fixed by having
  each agent override these fields with the known-correct values via
  `model_copy(update=...)` after the LLM call, eliminating the
  hallucination vector structurally rather than relying on prompt wording.
- **Leverage ratio unit confusion ("8.5%" instead of "8.5x").** No schema
  constraint caught a nonsensical unit on a debt covenant threshold.
  `src/output_validation.py` now flags this pattern explicitly.
- **FX/market risk force-fit into "legal" category.** The `RiskFlag`
  schema only had `revenue`/`debt`/`legal` categories - real filings have
  operational/market risk that doesn't fit any of them. Added a `market`
  category and updated the prompt to say so explicitly.
- **Empty `current_value` in trend shifts** (rendering as `metric: value
  → (deteriorating)` with nothing after the arrow). Fixed with a Pydantic
  `min_length=1` constraint - Pydantic itself now rejects the malformed
  output, triggering the existing retry logic instead of silently passing
  it through.
- **"0.0% growth" ambiguity.** When extraction found no revenue signals
  at all for a company, the growth ranking silently showed 0.0% -
  visually identical to genuinely flat growth. Added a `data_available`
  boolean to `CompanyRank` so these are distinguishable.
- **Fabricated-looking accuracy metrics for real companies.** A prior
  iteration of the Evaluate tab showed "Extraction Accuracy: 94.2%,
  Hallucination Rate: 1.8%" for real tickers - numbers with no ground
  truth behind them, since this system only has hand-labeled ground
  truth for the synthetic sample filings. Replaced with
  `src/quality_report.py`: a structural completeness/consistency check
  explicitly labeled as NOT an accuracy score, since none can be honestly
  computed without ground truth for a real company's filing.
