export const LOGIN_PREVIEW_OPTIONS = [
  { id: 'idle', label: '입력 전' },
  { id: 'validation', label: '입력 오류' },
  { id: 'loading', label: '로그인 중' },
  { id: 'credentials-error', label: '로그인 실패' },
  { id: 'network-error', label: '네트워크 오류' },
  { id: 'notice', label: '안내' },
  { id: 'blocked', label: '차단 안내' },
  { id: 'linked', label: 'SNS 연결됨' },
  { id: 'social-loading', label: 'SNS 인증 중' },
] as const;

export type LoginPreviewState = (typeof LOGIN_PREVIEW_OPTIONS)[number]['id'];

export const SIGN_UP_PREVIEW_OPTIONS = [
  { id: 'idle', label: '입력 전' },
  { id: 'id-invalid', label: '아이디 형식 오류' },
  { id: 'id-taken', label: '아이디 중복' },
  { id: 'id-available', label: '아이디 사용 가능' },
  { id: 'password-invalid', label: '비밀번호 규칙 오류' },
  { id: 'password-mismatch', label: '비밀번호 불일치' },
  { id: 'ready', label: '제출 가능' },
  { id: 'loading', label: '가입 처리 중' },
  { id: 'failed', label: '가입 실패' },
] as const;

export type SignUpPreviewState = (typeof SIGN_UP_PREVIEW_OPTIONS)[number]['id'];
