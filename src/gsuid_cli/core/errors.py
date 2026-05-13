from __future__ import annotations

from gsuid_cli.text import t as _t

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
        "description": _t("gsuid.core.errors.17_23.b2ae39ed"),
    },
    {
        "code": "REGION_UNSUPPORTED",
        "exit_code": EXIT_INVALID_INPUT,
        "retryable": False,
        "description": _t("gsuid.core.errors.23_23.20f9f710"),
    },
    {
        "code": "AUTH_REQUIRED",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": _t("gsuid.core.errors.29_23.bdffca16"),
    },
    {
        "code": "AUTH_EXPIRED",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": _t("gsuid.core.errors.35_23.68d4757e"),
    },
    {
        "code": "KEYRING_UNAVAILABLE",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": _t("gsuid.core.errors.41_23.8d8db7a8"),
    },
    {
        "code": "AUTH_UID_MISMATCH",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": _t("gsuid.core.errors.47_23.f79aeac8"),
    },
    {
        "code": "QR_LOGIN_TIMEOUT",
        "exit_code": EXIT_NO_RESULT,
        "retryable": True,
        "description": _t("gsuid.core.errors.53_23.da8895f0"),
    },
    {
        "code": "QR_NOT_CONFIRMED",
        "exit_code": EXIT_NO_RESULT,
        "retryable": True,
        "description": _t("gsuid.core.errors.59_23.a26f0ea6"),
    },
    {
        "code": "UPSTREAM_REJECTED",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": _t("gsuid.core.errors.65_23.b74e1f6d"),
    },
    {
        "code": "UPSTREAM_HTTP_ERROR",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "retryable_condition": _t("gsuid.core.errors.71_31.70016246"),
        "description": _t("gsuid.core.errors.72_23.ebf4b66c"),
    },
    {
        "code": "UPSTREAM_INVALID_RESPONSE",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": _t("gsuid.core.errors.78_23.187ec657"),
    },
    {
        "code": "UPSTREAM_VERIFICATION_REQUIRED",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": _t("gsuid.core.errors.84_23.df18a328"),
    },
    {
        "code": "NETWORK_TIMEOUT",
        "exit_code": EXIT_NETWORK,
        "retryable": True,
        "description": _t("gsuid.core.errors.90_23.d92b735e"),
    },
    {
        "code": "NETWORK_ERROR",
        "exit_code": EXIT_NETWORK,
        "retryable": True,
        "description": _t("gsuid.core.errors.96_23.1cccf236"),
    },
    {
        "code": "CACHE_MISS",
        "exit_code": EXIT_CACHE,
        "retryable": False,
        "description": _t("gsuid.core.errors.102_23.18174ab9"),
    },
    {
        "code": "NO_RESULT",
        "exit_code": EXIT_NO_RESULT,
        "retryable": False,
        "description": _t("gsuid.core.errors.108_23.6263e305"),
    },
    {
        "code": "INTERNAL_ERROR",
        "exit_code": EXIT_INTERNAL_BUG,
        "retryable": False,
        "description": _t("gsuid.core.errors.114_23.5e1e5187"),
    },
    {
        "code": "STATE_SCHEMA_UNSUPPORTED",
        "exit_code": EXIT_INTERNAL_BUG,
        "retryable": False,
        "description": _t("gsuid.core.errors.120_23.ef8ec0f1"),
    },
    {
        "code": "INTERRUPTED",
        "exit_code": EXIT_INTERRUPTED,
        "retryable": True,
        "description": _t("gsuid.core.errors.126_23.be424d6b"),
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
