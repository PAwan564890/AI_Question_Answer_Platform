"""Prometheus metric definitions.

Label values are always drawn from small fixed sets (route templates, provider
names, error class names). Putting user ids, raw URLs or question text in a
label would create one time series per distinct value and eventually exhaust
Prometheus memory ("cardinality explosion").
"""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests handled.", ["method", "route", "status"]
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency.",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 40),
)
HTTP_ERRORS = Counter("http_errors_total", "HTTP responses with status >= 400.", ["route", "code"])

LLM_REQUESTS = Counter("llm_requests_total", "LLM provider calls.", ["provider", "outcome"])
LLM_DURATION = Histogram(
    "llm_request_duration_seconds",
    "Latency of a single LLM provider call.",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40),
)
LLM_FAILURES = Counter("llm_failures_total", "Failed LLM calls.", ["provider", "error_type"])
LLM_RETRIES = Counter("llm_retries_total", "LLM call retries.", ["provider"])
LLM_FALLBACKS = Counter("llm_fallbacks_total", "Requests answered by the fallback provider.")
LLM_TOKENS = Counter("llm_tokens_total", "Tokens reported by the provider.", ["provider", "type"])
LLM_CIRCUIT_STATE = Gauge(
    "llm_circuit_state", "Circuit breaker state: 0=closed, 1=half-open, 2=open.", ["provider"]
)

RATE_LIMIT_EVENTS = Counter("rate_limit_events_total", "Requests rejected by a limiter.", ["scope"])
CACHE_REQUESTS = Counter("cache_requests_total", "Response cache lookups.", ["result"])
RAG_RETRIEVALS = Counter(
    "rag_retrievals_total", "Knowledge-base retrievals for /chat.", ["outcome"]
)
CHAT_PERSIST_FAILURES = Counter(
    "chat_persist_failures_total", "Chat records that could not be written to the database."
)
DEPENDENCY_UP = Gauge(
    "dependency_up", "1 if the dependency answered its last check, else 0.", ["dependency"]
)
