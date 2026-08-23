"""Language registry: slug <-> file extension mapping.

Static table implemented in code; extend row by row for new languages.
Go is intentionally absent from v0.1.0: there is no official
@codemirror/lang-go package yet (see ROADMAP).
"""

LANGUAGE_REGISTRY = {
    "cpp": ".cpp",
    "python3": ".py",
    "java": ".java",
}

DEFAULT_LANGUAGE = "cpp"


def extension_for(slug):
    return LANGUAGE_REGISTRY.get(slug)


def is_supported(slug):
    return slug in LANGUAGE_REGISTRY
