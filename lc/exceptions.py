"""Domain exceptions, translated to structured error JSON at the API layer."""


class AlgoCoachError(Exception):
    """Base class for all domain errors."""

    message_key = "error"

    def __init__(self, message: str = "", *, detail=None):
        super().__init__(message or self.__class__.message_key)
        self.detail = detail


class AuthError(AlgoCoachError):
    """Cookie invalid or expired; the frontend should guide re-paste."""

    message_key = "cookie_invalid"


class RateLimitError(AlgoCoachError):
    """Remote site returned 429 after exhausting backoff attempts."""

    message_key = "rate_limited"

    def __init__(self, message: str = "", *, retry_after=None, detail=None):
        super().__init__(message, detail=detail)
        self.retry_after = retry_after


class PremiumProblemError(AlgoCoachError):
    """Paid problem; skipped gracefully where applicable."""

    message_key = "premium_problem"


class NetworkError(AlgoCoachError):
    """Connection failure, timeout, or an unusable remote response shape."""

    message_key = "network_error"


class ProblemNotFoundError(AlgoCoachError):
    """Unknown slug/qid."""

    message_key = "problem_not_found"


class JudgeError(AlgoCoachError):
    """Judge submission or polling failure."""

    message_key = "judge_timeout_unknown"


class GroupNotFoundError(AlgoCoachError):
    """Unknown group id."""

    message_key = "group_not_found"


class GroupCycleError(AlgoCoachError):
    """A group cannot be moved into its own subtree."""

    message_key = "group_cycle"


class GroupDepthError(AlgoCoachError):
    """The nesting cap (lc.groups.MAX_DEPTH) would be exceeded."""

    message_key = "group_depth_limit"


class GroupShareCodeError(AlgoCoachError):
    """Malformed, corrupted or oversized group share code."""

    message_key = "group_invalid_code"
