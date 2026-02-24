from __future__ import annotations

EXIT_INVALID_INPUT = 1
EXIT_AUTH = 2
EXIT_UPSTREAM = 3
EXIT_NETWORK = 4
EXIT_CACHE = 5
EXIT_NO_RESULT = 6
EXIT_INTERNAL_BUG = 10
EXIT_INTERRUPTED = 130


class CliError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        exit_code: int,
        details: dict[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details or {}
        self.retryable = retryable
