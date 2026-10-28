# Rico — Zero-Downtime Multi-Model LLM Gateway Demo Script

## 1. The 30-Second Elevator Pitch
> *"Relying on a single AI provider in production creates a single point of failure and vulnerability to upstream rate limits and outages. **Rico** is an enterprise multi-model proxy gateway built on FastAPI, Redis, and Prometheus. It exposes a unified OpenAI-compatible interface backed by a resilient fallback mesh: Primary (GPT-4o) → Secondary (Claude 3.5 Sonnet) → Local (Ollama Llama-3). It features stateful circuit breakers (Closed → Open → Half-Open), per-team sliding-window RPM quotas, token-bucket TPM limits, and real-time chaos simulation."*

---

## 2. Senior Architecture Deep Dive

```
Client App -> [/v1/chat/completions]
                     |
                     v
          [Tenant Auth & Quota Guard]
  • Per-team sliding-window RPM quota (Redis / Memory)
  • Token-Bucket TPM budget enforcement
                     |
                     v
        [Circuit Breaker Model Mesh]
         Tier 1: GPT-4o (Primary)
           | (Fails >= 3 times -> Circuit Trips OPEN)
           v
         Tier 2: Claude 3.5 Sonnet (Secondary Fallback)
           | (Fails -> Fallback)
           v
         Tier 3: Ollama / Local Model (Air-gapped)
                     |
                     v
      [Prometheus /metrics & Mission Control UI]
```

---

## 3. How to Run & Demo

```powershell
Set-Location "C:\Users\HP\Documents\Exquisapps\ID's\lekeOmotayo\rico"
$env:REDIS_URL = ""
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **`http://localhost:8000`** in your browser.

### Demo Flow in Mission Control:
1. **Normal Request Flow**: Send `"What are the key differences between ACID and BASE?"`. Point out the primary model (`gpt-4o`) handling the request with normal latency and token counters incrementing.
2. **Inject Upstream Chaos**: In the Mission Control panel, toggle **"Simulate Provider Outage (503 Service Unavailable)"** on Tier 1.
3. **Automatic Circuit Trip & Failover**: Send the request again. Point to:
   - Tier 1 circuit breaker transitioning to **OPEN** (red badge).
   - Traffic seamlessly routing to Tier 2 (`claude-3-5-sonnet`) with zero dropped requests.
4. **Half-Open Recovery Probe**: Wait for the recovery cooldown. Send a request to show the circuit testing the probe and returning to **CLOSED**.
5. **Team Quotas**: Show per-tenant rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`).
6. **Prometheus Telemetry**: Open `http://localhost:8000/metrics` to show Prometheus metrics (`llm_requests_total`, `llm_circuit_breaker_state`, `llm_fallback_events_total`).

---

## 4. Senior Defense Questions & Answers

### Q: "How does Rico prevent a failing provider from being flooded with retries?"
> **Answer:** *"The circuit breaker pattern strictly stops all traffic to a tripped provider immediately upon entering the OPEN state. No requests reach the failing upstream until the `recovery_cooldown` expires, at which point exactly ONE probe request is permitted in HALF-OPEN state."*

### Q: "Does Rico require Redis or Docker to demonstrate?"
> **Answer:** *"No. By leaving `REDIS_URL` empty, Rico automatically falls back to its in-memory sliding window rate limiter and token bucket. Model responses default to simulated realistic text when external API keys are omitted, ensuring 100% offline demo reliability."*
