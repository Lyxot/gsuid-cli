from __future__ import annotations

EXIT_INVALID_INPUT = 1
EXIT_AUTH = 2
EXIT_UPSTREAM = 3
EXIT_NETWORK = 4
EXIT_CACHE = 5
EXIT_NO_RESULT = 6
EXIT_INTERNAL_BUG = 10
EXIT_INTERRUPTED = 130

ERROR_CATALOG = [
    {
        "code": "INVALID_ARGUMENT",
        "exit_code": EXIT_INVALID_INPUT,
        "retryable": False,
        "description": "The command line or request payload is invalid.",
    },
    {
        "code": "REGION_UNSUPPORTED",
        "exit_code": EXIT_INVALID_INPUT,
        "retryable": False,
        "description": "The selected API region is not supported by this MVP.",
    },
    {
        "code": "AUTH_REQUIRED",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": "A required credential is missing.",
    },
    {
        "code": "AUTH_EXPIRED",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": "A stored or supplied credential was rejected by the provider.",
    },
    {
        "code": "KEYRING_UNAVAILABLE",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": "The OS keyring could not read, write, or delete a secret.",
    },
    {
        "code": "AUTH_UID_MISMATCH",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": "The credential is valid but is not linked to the requested UID.",
    },
    {
        "code": "QR_LOGIN_TIMEOUT",
        "exit_code": EXIT_NO_RESULT,
        "retryable": True,
        "description": "Interactive QR login timed out before confirmation.",
    },
    {
        "code": "QR_NOT_CONFIRMED",
        "exit_code": EXIT_NO_RESULT,
        "retryable": True,
        "description": "The QR login session has not been confirmed yet.",
    },
    {
        "code": "UPSTREAM_REJECTED",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": "The provider rejected an otherwise valid request.",
    },
    {
        "code": "UPSTREAM_HTTP_ERROR",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "retryable_condition": "HTTP status code is 500 or greater",
        "description": "The provider returned an HTTP error response.",
    },
    {
        "code": "UPSTREAM_INVALID_RESPONSE",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": "The provider returned an unexpected response shape.",
    },
    {
        "code": "UPSTREAM_VERIFICATION_REQUIRED",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": "The provider requires challenge or device verification.",
    },
    {
        "code": "NETWORK_TIMEOUT",
        "exit_code": EXIT_NETWORK,
        "retryable": True,
        "description": "The provider request timed out.",
    },
    {
        "code": "NETWORK_ERROR",
        "exit_code": EXIT_NETWORK,
        "retryable": True,
        "description": "The provider request failed before a valid response was received.",
    },
    {
        "code": "CACHE_MISS",
        "exit_code": EXIT_CACHE,
        "retryable": False,
        "description": "A cache-only request had no cached response.",
    },
    {
        "code": "NO_RESULT",
        "exit_code": EXIT_NO_RESULT,
        "retryable": False,
        "description": "The request was valid but no matching data was found.",
    },
    {
        "code": "INTERNAL_ERROR",
        "exit_code": EXIT_INTERNAL_BUG,
        "retryable": False,
        "description": "The CLI hit an unexpected internal error.",
    },
    {
        "code": "STATE_SCHEMA_UNSUPPORTED",
        "exit_code": EXIT_INTERNAL_BUG,
        "retryable": False,
        "description": "The local state database schema is newer or unsupported.",
    },
    {
        "code": "INTERRUPTED",
        "exit_code": EXIT_INTERRUPTED,
        "retryable": True,
        "description": "The command was interrupted by the caller.",
    },
]


class CliError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        exit_code: int,
        details: dict[str, object] | None = None,
        retryable: bool = False,
        source: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details or {}
        self.retryable = retryable
        self.source = source
