"""Configuration read/write/validate layer.

Responsibilities (implemented in later milestones):
- ~/.algocoach/config.toml with a schema_version migration field
- chmod 600 on POSIX (Windows relies on storing outside any repo in the user
  home directory; no POSIX permission semantics exist there)
- priority chain: CLI arguments > environment variables > config file
- cookie / LLM key / interface preferences storage
"""

APP_DIR_NAME = ".algocoach"
