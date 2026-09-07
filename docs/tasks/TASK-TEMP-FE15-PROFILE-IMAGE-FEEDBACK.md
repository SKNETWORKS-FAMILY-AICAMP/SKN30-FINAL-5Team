# TASK-TEMP-FE15-PROFILE-IMAGE-FEEDBACK

## 목적

`docs/tasks/2026-09-improvements/FRONTEND.md`의 FE-15 중 프론트엔드가 독립적으로 처리할 수 있는
프로필 사진 저장 실패 표시와 재시도 흐름을 보강한다.

## 계약 확인

- BL-5 이후 `POST /api/v1/me/profile-image`는 객체 저장 또는 새 객체의 presigned URL 발급 실패 시
  `503 PROFILE_IMAGE_STORAGE_UNAVAILABLE`을 반환하고 새 객체를 정리한다. 업로드 성공 응답은 더 이상
  `profile_image_url: null`을 반환하지 않는다. 따라서 사진 단계 실패와 프로필 필드 `PATCH` 실패를
  프론트에서 구분할 수 있다.
- `GET /api/v1/me`의 `profile_image_url: null`은 저장 이미지 없음과 조회 시점 URL 발급 실패를 모두
  포함한다. 프론트는 이 읽기 응답만으로 저장 실패를 추론하지 않는다.
- 사진 URL과 사용자 식별자는 로그에 남기지 않는다.

## 구현 계획

1. 기본 프로필 저장에서 프로필 필드 단계와 사진 단계의 오류를 구분한다.
2. 사진 단계 실패 시 선택한 로컬 미리보기를 유지하고 명시적 재시도 안내를 표시한다.
3. 프로필 필드 저장 후 사진만 실패한 부분 성공 상태를 별도 문구로 표시한다.
4. 컴포넌트 테스트로 실패·부분 성공·재시도·성공 표시 억제를 검증한다.

## 예상 변경 파일

- `frontend/src/features/home/MyPageContainer.tsx`
- `frontend/tests/MyPageContainer.test.tsx`
- 이 작업 문서

## 위험과 호환성

- 공개 API와 DB 스키마는 변경하지 않는다.
- 삭제 응답과 `GET /me`의 nullable URL 의미를 유지한다.
- 실제 저장소/IAM 구성 정상화는 BL-5 배포 범위이며 프론트가 대체하지 않는다.

## 검증

- formatter
- linter
- TypeScript typecheck
- `MyPageContainer` 컴포넌트 테스트
- 전체 프론트 테스트
- 프로덕션 빌드
