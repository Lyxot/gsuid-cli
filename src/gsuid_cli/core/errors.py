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
        "description": "命令行或请求参数无效。",
    },
    {
        "code": "REGION_UNSUPPORTED",
        "exit_code": EXIT_INVALID_INPUT,
        "retryable": False,
        "description": "当前版本不支持所选的 API 区服。",
    },
    {
        "code": "AUTH_REQUIRED",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": "缺少必要的凭据。",
    },
    {
        "code": "AUTH_EXPIRED",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": "已存储或提供的凭据被数据源拒绝。",
    },
    {
        "code": "KEYRING_UNAVAILABLE",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": "操作系统密钥环无法读取、写入或删除机密信息。",
    },
    {
        "code": "AUTH_UID_MISMATCH",
        "exit_code": EXIT_AUTH,
        "retryable": False,
        "description": "凭据有效，但未与请求的 UID 关联。",
    },
    {
        "code": "QR_LOGIN_TIMEOUT",
        "exit_code": EXIT_NO_RESULT,
        "retryable": True,
        "description": "交互式二维码登录在确认前已超时。",
    },
    {
        "code": "QR_NOT_CONFIRMED",
        "exit_code": EXIT_NO_RESULT,
        "retryable": True,
        "description": "二维码登录会话尚未被确认。",
    },
    {
        "code": "UPSTREAM_REJECTED",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": "数据源拒绝了原本有效的请求。",
    },
    {
        "code": "UPSTREAM_HTTP_ERROR",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "retryable_condition": "HTTP 状态码为 500 或更高",
        "description": "数据源返回了 HTTP 错误响应。",
    },
    {
        "code": "UPSTREAM_INVALID_RESPONSE",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": "数据源返回了非预期的响应数据格式。",
    },
    {
        "code": "UPSTREAM_VERIFICATION_REQUIRED",
        "exit_code": EXIT_UPSTREAM,
        "retryable": False,
        "description": "数据源需要挑战或设备验证。",
    },
    {
        "code": "NETWORK_TIMEOUT",
        "exit_code": EXIT_NETWORK,
        "retryable": True,
        "description": "数据源请求超时。",
    },
    {
        "code": "NETWORK_ERROR",
        "exit_code": EXIT_NETWORK,
        "retryable": True,
        "description": "数据源请求在收到有效响应前失败。",
    },
    {
        "code": "CACHE_MISS",
        "exit_code": EXIT_CACHE,
        "retryable": False,
        "description": "强制走缓存的请求未命中缓存响应。",
    },
    {
        "code": "NO_RESULT",
        "exit_code": EXIT_NO_RESULT,
        "retryable": False,
        "description": "请求有效，但未找到匹配的数据。",
    },
    {
        "code": "INTERNAL_ERROR",
        "exit_code": EXIT_INTERNAL_BUG,
        "retryable": False,
        "description": "CLI 遇到意外的内部错误。",
    },
    {
        "code": "STATE_SCHEMA_UNSUPPORTED",
        "exit_code": EXIT_INTERNAL_BUG,
        "retryable": False,
        "description": "本地状态数据库 schema 较新或不受支持。",
    },
    {
        "code": "INTERRUPTED",
        "exit_code": EXIT_INTERRUPTED,
        "retryable": True,
        "description": "命令已被调用者中断。",
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
