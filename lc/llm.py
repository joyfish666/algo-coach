"""OpenAI-compatible LLM client (stateless).

Responsibilities (implemented in later milestones):
- user-provided Key/URL via config or environment variable override
- reuses httpclient timeout / exception translation / log redaction
  infrastructure but disables rate limiting and site-specific header injection
- separate configurable request timeout, default 120s (long answers take tens
  of seconds); v0.1 is non-streaming
"""
