/** 统一 API 错误：网络错误没有 status，业务错误带 HTTP 状态与后端 code。 */
export class ApiError extends Error {
  readonly status: number | undefined;
  readonly code: string;
  readonly details: unknown;

  constructor(
    message: string,
    options: {
      status?: number;
      code?: string;
      details?: unknown;
      cause?: unknown;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code ?? (options.status ? `http_${options.status}` : "network_error");
    this.details = options.details;
    if (options.cause !== undefined) {
      (this as { cause?: unknown }).cause = options.cause;
    }
  }
}

/** 只有网络层失败（超时、断连）才值得自动重试；4xx 重试没有意义。 */
export function isRetryableNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.status === undefined;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return String(error);
}
