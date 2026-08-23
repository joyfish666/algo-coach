"""Domain exceptions, translated to structured error JSON at the API layer."""


class AlgoCoachError(Exception):
    """Base class for all domain errors."""


class AuthError(AlgoCoachError):
    """Cookie invalid or expired; the frontend should guide re-paste."""


class RateLimitError(AlgoCoachError):
    """Remote site returned 429 after exhausting backoff attempts."""


class PremiumProblemError(AlgoCoachError):
    """Paid problem; skipped gracefully where applicable."""


class NetworkError(AlgoCoachError):
    """Connection failure or timeout."""


class ProblemNotFoundError(AlgoCoachError):
    """Unknown slug/qid."""


class JudgeError(AlgoCoachError):
    """Judge submission or polling failure."""
