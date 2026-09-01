# Interview prep — anticipated questions

Practice saying these out loud, not just reading them.

**"Walk me through the architecture."**
It's a LangGraph state machine with four agents: ingestion chunks the
filing, extraction pulls structured risk signals into a Pydantic schema,
a RAG agent indexes those chunks for ad-hoc Q&A, and a synthesis agent
turns the structured extraction into an executive memo. State passes
explicitly between nodes so each stage is independently testable.

**"What was the hardest technical decision?"**
Forcing every LLM call into a strict Pydantic schema instead of letting
it return free text. It's more upfront work — you have to design the
schema before you can prompt for it — but it's what makes the pipeline
composable: agent 3 can trust agent 2's output structure instead of
re-parsing prose.

**"How do you test something that calls an LLM?"**
By separating pipeline logic from model behavior. Every agent takes an
injectable `LLMClient` that runs in mock mode by default, returning
realistic fixture data instead of calling Gemini. That lets me unit test
chunking, schema validation, and LangGraph routing without needing a live
API key or eating nondeterminism from the model. Testing the model's
actual output quality (is the extraction accurate) is a separate,
legitimate concern — prompt evaluation — which I'd add as a next step in
a production version.

**"Why not just have one agent do everything?"**
Two reasons: testability (I can assert on extraction output separately
from synthesis output) and prompt quality — asking one model call to
extract facts AND write executive prose in one shot tends to degrade
quality on longer documents.

**"What would you change for production?"**
Three things, in order: (1) real SEC EDGAR API integration instead of a
local sample file, (2) a real embedding model instead of the offline
hashing placeholder, (3) a managed vector store if this needed to serve
concurrent users. I'd also add prompt-level evaluation (accuracy of
extraction against labeled filings), not just the structural tests I have
now.

**"How would you know if the extraction is actually correct?"**
Right now, correctness is enforced structurally (schema validation) not
semantically (is the extracted number actually right). For production,
I'd build an eval set of filings with human-labeled ground truth and
measure extraction accuracy against it — that's a different kind of
testing than what's in this repo today, and I'd say so directly if asked.

**"Is this production-ready / enterprise-grade?"**
It has real production-readiness patterns — authenticated, role-gated,
rate-limited REST API, retry logic with exponential backoff on LLM
calls, structured JSON logging with request correlation IDs, persisted
report history and audit trail, Prometheus metrics, and OpenTelemetry
tracing. What it doesn't have: full multi-tenant identity management, or
validation under real production-scale traffic. I'd say that directly
rather than oversell it — it demonstrates the engineering patterns
production systems need, at the scope appropriate for a portfolio project.

**"Walk me through what happens when I call your API."**
A request hits FastAPI, middleware assigns a request ID and starts a
timer for structured logging. The API-key dependency checks the header
against an allowlist using constant-time comparison before anything else
runs. Rate limiting is enforced per client IP. The endpoint then runs
the actual LangGraph pipeline (or comparison agent, or evaluation
harness) and returns a Pydantic-validated response — the same schema
used internally, so the API contract and the internal data model are
never out of sync.

**"How do you handle a flaky LLM API call?"**
The LLM client wraps live calls in retry logic (tenacity) with
exponential backoff, specifically retrying on JSON-parse failures since
that's the most common failure mode when forcing a non-deterministic
model into structured output. It does not retry on auth/config errors,
since those won't resolve by retrying.

**"How would you scale this to handle real traffic?"**
Today rate limiting is in-process and keyed by IP, and there's no shared
state across instances — the RAG cache is a process-local dict. Scaling
would mean: a shared session/job store (Redis or a database) instead of
the in-memory cache, rate limiting at an API gateway instead of
middleware, and a managed vector store instead of embedded ChromaDB if
serving many concurrent users. I'd say this proactively rather than
wait to be asked — it shows I know where the current design's edges are.


Be direct: this demonstrates the orchestration pattern and engineering
practices (schema enforcement, dependency injection for testability, CI)
on a synthetic filing. A real deployment needs live EDGAR ingestion, a
production embedding model, an evaluation harness for extraction
accuracy, and probably human-in-the-loop review before any output
reaches a real investment decision. Say this proactively — it reads as
engineering maturity, not a weakness.

**"What happens to the data after an API call?"**
Every `/analyze`, `/compare`, and `/evaluate` call persists its report to
a database (SQLite by default, Postgres via one env var change) and logs
an audit entry — endpoint, API key prefix, status, latency. `/reports`
and `/reports/{id}` let you retrieve history. This is a real audit trail,
not just request/response with nothing kept.

**"How do you know your code quality is good, not just that it runs?"**
CI runs four separate gates on every push: `ruff` for linting, `black
--check` for formatting consistency, `bandit` for security scanning (it
caught a real weak-hash usage I fixed — MD5 used for embedding bucketing,
not security, but bandit flags MD5 regardless so I marked it explicitly
non-security), and pytest with coverage reporting (currently 95%).

**"Why SQLite instead of Postgres from the start?"**
Right-sized for a single-instance deployment with no concurrent-write
requirements. The code doesn't hardcode SQLite — `DATABASE_URL` is read
once in `src/db.py`, and SQLAlchemy handles the driver difference. Moving
to Postgres for a multi-instance deployment is an environment variable
change, not a rewrite. I'd say this proactively rather than wait to be
asked — it shows the boundary was a deliberate choice, not an oversight.

**"Walk me through how you'd deploy this."**
`Procfile` declares process types (`web`, `worker`, `dashboard`) — the
same format Heroku popularized. Render and Railway both auto-detect a
Python app from `requirements.txt` + `Procfile` and build it with a
buildpack, no Dockerfile needed. Locally, Honcho reads the same
`Procfile` to run everything from one terminal. Important honest caveat
I'd raise unprompted: the default in-memory cache and SQLite are
process-local — running multiple instances for real would need
`CACHE_BACKEND=redis` and `DATABASE_URL` pointed at a shared Postgres
instance first.

**"Why not Docker/Kubernetes?"**
Practical reason as much as a technical one: Docker Desktop caused real
stability issues on the machine this was built on (a BSOD tied to a
graphics driver, consistent with a known Docker Desktop/GPU driver
conflict on some Windows laptops), so I chose a deployment path that
doesn't need it — Procfile + a buildpack host. Technically, Kubernetes
solves multi-node scheduling and complex orchestration problems this
project's scale doesn't have yet; Render/Railway's built-in autoscaling
covers horizontal scaling for a single-service API without that
operational overhead. If this needed true multi-service orchestration
at real scale, Kubernetes would be the right next step — I'd say that
directly rather than pretend the current scope needs it.

**"Why Celery/Redis for async jobs instead of just background tasks?"**
FastAPI's built-in BackgroundTasks doesn't survive a process restart and
isn't independently scalable. Celery with Redis as broker/backend is a
real job queue - a client submits via `/analyze/async`, gets a task ID
back immediately, and polls `/tasks/{id}` for the result, while the
actual work happens in a separate worker process (the `worker:` line in
`Procfile`) that can scale independently of the API.

**"What's the difference between your metrics and your tracing?"**
Metrics (Prometheus) give aggregates - request rate, latency
percentiles, error rate, broken down by endpoint and now by agent
stage. Tracing (OpenTelemetry) gives per-request causality - for one
specific slow request, which of the four agent stages was the
bottleneck. I'd reach for metrics to notice something's wrong and
tracing to find out where, in a specific request.

**"Is the Grafana dashboard showing real data or a mockup?"**
Real - every panel's PromQL expression queries a metric this app
actually exports (`awi_requests_total`, `awi_request_duration_seconds`,
`awi_agent_stage_duration_seconds`), and there's a test
(`test_monitoring_config.py`) that fails if a panel ever references a
metric that doesn't exist. What it doesn't show yet: Redis cache hit
rate, Celery queue depth, or host CPU/memory - those need additional
exporters (redis_exporter, Celery's Prometheus integration,
node_exporter) that aren't wired up. I'd say that directly rather than
imply full infrastructure observability that isn't there.

**"Walk me through the human-in-the-loop approval workflow."**
Every synthesis report includes a self-assessed confidence score. If
it's at or above 90% (configurable), the report auto-approves. Below
that, it's routed to a `/reports/pending-review` queue, and a human
reviewer must approve or reject it - optionally editing the
recommendation - before it's considered final. I verified this live: a
report with 78% confidence (driven by a genuinely unresolved FTC
investigation) correctly routed to review, appeared in the queue,
and disappeared once I submitted an approval through the API.

**"Is this genuinely 'responsible AI,' or just a status flag?"**
It's a real control point, not decoration: a report below the
confidence threshold literally cannot reach `approved` status without
going through `POST /reports/{id}/review` - there's no path around it
in the code. What I'd be careful not to overclaim: the confidence score
is the LLM's own self-assessment, not a calibrated statistical
confidence interval, and reviewer feedback is captured as labeled data
(`FeedbackRecord`) for future prompt/model improvement, not an active
learning loop today. Both are honest v1 choices, not gaps I'd hide.

**"Walk me through the portfolio intelligence feature."**
Given multiple companies' extracted filings, three rankings are computed
deterministically: average revenue growth, legal-risk severity (weighted
by severity, not just count), and debt covenant non-compliance. In the
demo data, three different companies top three different rankings -
Solara Energy leads growth, Nimbus Dynamics has the highest legal risk
(an active FTC inquiry), and Vantage Robotics has the highest debt risk
(a covenant breach). That's a deliberate demonstration that these are
genuinely different risk dimensions a portfolio manager needs to see
separately, not one blended "risk score."

**"Why compute the rankings deterministically instead of asking the LLM to rank?"**
Reproducibility and auditability. If this ranking ever influenced which
company gets reviewed first, it needs to give the same answer on the
same data every time - an LLM re-ranking call doesn't guarantee that.
The one LLM-generated piece is the sector narrative, which needs
synthesis judgment the deterministic scoring can't provide.
