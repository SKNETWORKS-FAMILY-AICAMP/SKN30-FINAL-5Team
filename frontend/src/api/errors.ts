/**
 * The repository's common error envelope, plus the presentation states the
 * client must be able to show for it.
 *
 * `kind` exists so screens can branch on the *class* of failure (auth, network,
 * validation, ...) without re-implementing server rules. It never changes what
 * the server decided; it only chooses which state to render.
 */

export type ApiErrorKind =
  | 'network'
  | 'auth'
  | 'permission'
  | 'notFound'
  | 'validation'
  | 'stale'
  | 'conflict'
  | 'rateLimited'
  | 'unavailable'
  | 'server';

export type ApiErrorDetail = {
  field?: string;
  type?: string;
  reason_code?: string;
};

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly code: string;
  readonly status: number;
  readonly details: ApiErrorDetail[];
  readonly requestId: string | null;

  constructor(params: {
    kind: ApiErrorKind;
    code: string;
    status: number;
    message: string;
    details?: ApiErrorDetail[];
    requestId?: string | null;
  }) {
    super(params.message);
    this.name = 'ApiError';
    this.kind = params.kind;
    this.code = params.code;
    this.status = params.status;
    this.details = params.details ?? [];
    this.requestId = params.requestId ?? null;
  }
}

const CODE_KIND: Record<string, ApiErrorKind> = {
  AUTHENTICATION_REQUIRED: 'auth',
  INVALID_TOKEN: 'auth',
  ACCOUNT_DISABLED: 'permission',
  AGE_REQUIREMENT_NOT_MET: 'permission',
  STALE_CONTEXT: 'stale',
  STALE_PLAN_REVISION: 'stale',
  OPTION_NOT_SELECTABLE: 'conflict',
  RATE_LIMITED: 'rateLimited',
};

function kindForStatus(status: number, code: string): ApiErrorKind {
  const mapped = CODE_KIND[code];
  if (mapped) {
    return mapped;
  }
  if (status === 401) return 'auth';
  if (status === 403) return 'permission';
  if (status === 404) return 'notFound';
  if (status === 409) return 'conflict';
  if (status === 400 || status === 422) return 'validation';
  if (status === 429) return 'rateLimited';
  if (status === 503) return 'unavailable';
  return 'server';
}

/**
 * Fallback copy for the cases where a screen has nothing better to show. The
 * server already sends Korean messages, so this is only for transport failures
 * and malformed responses.
 */
const FALLBACK_MESSAGE: Record<ApiErrorKind, string> = {
  network: '서버에 연결하지 못했습니다. 네트워크를 확인하고 다시 시도해주세요.',
  auth: '다시 로그인해주세요.',
  permission: '이 계정으로는 접근할 수 없습니다.',
  notFound: '요청한 정보를 찾을 수 없습니다.',
  validation: '입력값을 다시 확인해주세요.',
  stale: '정보가 변경되었습니다. 최신 상태로 다시 시도해주세요.',
  conflict: '요청을 처리할 수 없는 상태입니다.',
  rateLimited: '요청이 많습니다. 잠시 후 다시 시도해주세요.',
  unavailable: '서비스를 일시적으로 사용할 수 없습니다.',
  server: '요청을 처리하지 못했습니다.',
};

/**
 * `fetch` rejects identically for an unreachable host and a blocked
 * cross-origin request, so the message names the address that was tried. That
 * is what distinguishes a wrong `EXPO_PUBLIC_API_BASE_URL` (the usual cause,
 * for example an emulator-only address used in a browser) from a server that
 * is genuinely down.
 */
export function networkError(origin?: string, cause?: unknown): ApiError {
  // The transport's own reason distinguishes a refused connection from a
  // blocked cross-origin request, which otherwise look identical here.
  const reason =
    cause instanceof Error && cause.message ? ` (${cause.message})` : '';
  return new ApiError({
    kind: 'network',
    code: 'NETWORK_UNAVAILABLE',
    status: 0,
    message: origin
      ? `서버(${origin})에 연결하지 못했습니다. 주소와 네트워크를 확인해주세요.${reason}`
      : FALLBACK_MESSAGE.network,
  });
}

export function apiErrorFromResponse(
  status: number,
  payload: unknown,
): ApiError {
  const envelope =
    typeof payload === 'object' && payload !== null && 'error' in payload
      ? (payload as { error: unknown }).error
      : null;

  const body =
    typeof envelope === 'object' && envelope !== null
      ? (envelope as Record<string, unknown>)
      : {};

  const code = typeof body.code === 'string' ? body.code : 'INTERNAL_ERROR';
  const kind = kindForStatus(status, code);
  const message =
    typeof body.message === 'string' && body.message
      ? body.message
      : FALLBACK_MESSAGE[kind];
  const details = Array.isArray(body.details)
    ? (body.details as ApiErrorDetail[])
    : [];
  const requestId =
    typeof body.request_id === 'string' ? body.request_id : null;

  return new ApiError({ kind, code, status, message, details, requestId });
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/**
 * An error that already carries user-safe, localized copy.
 *
 * Adapters outside the API layer (Firebase auth, for one) translate provider
 * codes into Korean sentences at their own boundary. Marking the result lets
 * `messageForError` show that sentence instead of the generic fallback,
 * without `api/` having to import the adapter that produced it.
 */
export interface UserFacingError {
  readonly userMessage: string;
}

export function isUserFacingError(value: unknown): value is UserFacingError {
  if (!(value instanceof Error)) {
    return false;
  }
  const message = (value as Error & Partial<UserFacingError>).userMessage;
  return typeof message === 'string' && message.length > 0;
}

export function messageForError(value: unknown): string {
  if (isApiError(value)) {
    return value.message;
  }
  if (isUserFacingError(value)) {
    return value.userMessage;
  }
  return FALLBACK_MESSAGE.server;
}
