# Load testing results

Run with Locust, no Docker required. Reproduce with:

```bash
uvicorn src.api.main:app --port 8000 &
locust -f loadtest/locustfile.py --host http://localhost:8000 \
    --users 15 --spawn-rate 5 --run-time 20s --headless
```

## Sample run (mock mode, 15 concurrent users, 20 seconds, this machine)

| Endpoint | Requests | Failures | p50 | p95 | p99 | req/s |
|---|---|---|---|---|---|---|
| `POST /analyze` | 87 | 58 (all `429`) | 11ms | 49ms | 190ms | 3.06 |
| `POST /compare` | 29 | 0 | 17ms | 48ms | 180ms | 1.53 |
| `GET /evaluate` | 13 | 0 | 15ms | 150ms | 150ms | 0.69 |
| `GET /health` | 43 | 0 | 4ms | 7ms | 47ms | 2.27 |
| `GET /metrics` | 21 | 0 | 7ms | 13ms | 21ms | 1.11 |
| `GET /reports` | 33 | 0 | 12ms | 38ms | 39ms | 1.74 |

## What this actually shows

**The 58 failures on `/analyze` are the rate limiter working as designed,
not a bug.** At 15 concurrent users hammering `/analyze` (the heaviest-
weighted task in the locustfile), the default `RATE_LIMIT_PER_MINUTE=30`
was exceeded, and slowapi correctly returned `429 Too Many Requests`
instead of letting the pipeline run unbounded. This is exactly the
protection rate limiting exists for — an LLM-backed endpoint without a
cap is a cost/abuse incident waiting to happen (see
`docs/TECH_DECISIONS.md`).

Every other endpoint held a sub-20ms median with zero failures under the
same load. `/health` and `/metrics` (no LLM call, no DB write) stayed
fastest, as expected.

## Honest caveats about this benchmark

- Run in **mock mode** — no real Gemini API latency is reflected here.
  Live mode would be meaningfully slower per `/analyze` call (a real LLM
  round-trip), and that's the number that would actually matter for
  capacity planning in production.
- Run against a **single process, single machine**, not a multi-replica
  deployment topology. Real capacity testing would run against however
  many instances a production deployment actually uses (Render/Railway's
  autoscaling, for example), not a local dev server.
- `RATE_LIMIT_PER_MINUTE` can be raised via config if 30/min is too
  conservative for a given deployment — this run demonstrates the limiter
  functions correctly, not that 30/min is the "right" number for every use case.

## If you want to push past the rate limit deliberately

```bash
export RATE_LIMIT_PER_MINUTE=1000
uvicorn src.api.main:app --port 8000 &
locust -f loadtest/locustfile.py --host http://localhost:8000 \
    --users 15 --spawn-rate 5 --run-time 20s --headless
```

This isolates actual pipeline throughput from the rate limiter's effect.

## Confirming run — same load, rate limit raised to 1000/min

This run used identical load parameters with `RATE_LIMIT_PER_MINUTE=1000`,
confirming the earlier `429`s were entirely the rate limiter, not an
underlying failure:

| Endpoint | Requests | Failures | p50 | p95 | req/s |
|---|---|---|---|---|---|
| `POST /analyze` | 82 | **0** | 12ms | 33ms | ~4.1 |
| `POST /compare` | 28 | 0 | 18ms | 61ms | 1.41 |
| `GET /evaluate` | 14 | 0 | 18ms | 21ms | 0.70 |
| `GET /health` | 46 | 0 | 5ms | 20ms | 2.31 |
| `GET /metrics` | 24 | 0 | 8ms | 36ms | 1.21 |
| `GET /reports` | 36 | 0 | 13ms | 31ms | 1.81 |

Zero failures across 230 total requests once the rate limit was no
longer the binding constraint — confirms the pipeline itself handles
this load cleanly in mock mode; the earlier failures were specifically
the `429`s from the default 30/min cap, exactly as designed.
