# 백엔드 인계: 주간 퀘스트 진행률과 보상

- 작성일: 2026-09-09
- 상태: 제안(PROPOSED), 제품 정책 및 공동 계약 승인 전
- 후속 구현 주 담당: 백엔드 담당자 지정 필요
- 관련 화면: 끼끼의 집 > 퀘스트 > 주간 퀘스트

## 1. 현재 프런트 반영

프런트는 주간 퀘스트를 다음과 같이 표시한다.

- `주 4회 앱 접속`
- `주간 리포트 확인`
- `운동 목표 달성`

지급액과 지급 시점은 아직 제품 정책으로 확정되지 않았다. 따라서 프런트는 임의의
`25 · 15 · 30` 값을 표시하거나 바나나 잔액에 더하지 않고 `보상 준비 중`으로 표시한다.
앱 접속 횟수도 서버 근거가 없으므로 `진행 정보 없음`으로 표시한다.

기존 `POST /api/v1/rewards/daily-reward/claim`의 매일 15개 수동 수령은 별도 기능이다.
앱 접속 기록이나 주간 퀘스트 처리에서 이 API를 호출하면 안 된다.

이번 프런트 작업은 공개 API와 DB를 변경하지 않는다. 아래 내용은 백엔드와 프런트가
함께 검토할 후속 계약 초안이다.

## 2. 먼저 확정할 제품 정책

다음 항목이 확정되기 전에는 주간 보상을 지급하지 않는다.

1. 퀘스트별 지급액
2. 목표 달성 즉시 지급할지, 주 마감 후 지급할지
3. 한 주의 시작 요일과 사용자 timezone 경계
4. 목표를 달성한 뒤 정책이 바뀌었을 때 적용할 정책 버전
5. 주간 운동 목표가 변경된 경우 목표 수와 진행률을 어느 시점의 값으로 고정할지

## 3. 제안 API 계약

### 3.1 앱 접속 기록

`POST /api/v1/rewards/app-visits`

- 인증된 사용자의 현재 서버 시각과 저장된 timezone으로 local date를 계산한다.
- 클라이언트가 날짜, 횟수, 보상액을 보내지 않는다.
- 사용자와 local date 조합으로 멱등 처리한다.
- 앱의 인증 복원과 초기 데이터 로딩이 성공한 뒤 한 번 호출한다.
- 같은 날 재접속, 재시도, 여러 기기 동시 호출은 접속 일수를 한 번만 늘린다.
- 이 호출 자체는 일일 15개 보상을 청구하지 않는다.

응답 예시:

```json
{
  "local_date": "2026-09-09",
  "recorded": true,
  "weekly_visit_days": 2
}
```

### 3.2 주간 퀘스트 상태 조회

기존 `GET /api/v1/rewards` 응답에 다음 optional 필드를 추가하는 방식을 우선 검토한다.
기존 클라이언트 호환을 위해 승인·배포 순서는 백엔드 additive 응답 배포 후 프런트 연결로
한다.

```json
{
  "weekly_quests": [
    {
      "quest_code": "APP_VISIT_4_DAYS",
      "progress": 2,
      "target": 4,
      "status_code": "IN_PROGRESS",
      "reward_amount": null,
      "granted_at": null
    },
    {
      "quest_code": "WEEKLY_REPORT_ACKNOWLEDGED",
      "progress": 1,
      "target": 1,
      "status_code": "ACHIEVED",
      "reward_amount": null,
      "granted_at": null
    },
    {
      "quest_code": "WEEKLY_WORKOUT_GOAL",
      "progress": 2,
      "target": 3,
      "status_code": "IN_PROGRESS",
      "reward_amount": null,
      "granted_at": null
    }
  ]
}
```

제안 상태 코드는 `IN_PROGRESS`, `ACHIEVED`, `GRANTED`,
`REWARD_NOT_CONFIGURED`이다. `reward_amount`는 정책 미확정 시 `null`이어야 하며,
프런트는 `null`을 `보상 준비 중`으로 표시한다. 지급 정책이 확정된 뒤에는 서버가
진행률, 목표, 지급 여부, 잔액 변경을 모두 소유한다.

## 4. DB 및 멱등성 고려사항

- 앱 접속 기록은 사용자 ID와 local date에 명시적 unique 제약이 필요하다.
- 주간 퀘스트 결과에는 week start, quest code, policy version, target snapshot을 보존한다.
- 지급 트랜잭션은 사용자·주·퀘스트 조합의 idempotency key 또는 unique 제약으로 중복
  지급을 막는다.
- 접속 기록만으로 금액 0의 바나나 거래를 만들지 않는다.
- 기존 거래 타입이나 CHECK 제약을 변경하면 Alembic migration과 rollback 또는
  forward-fix 전략을 함께 작성한다.
- 조회 API에서 새로운 지급 mutation을 수행하는 방식은 피한다. 기존 운동 보상 정합화와
  결합해야 한다면 그 멱등 경계를 별도로 문서화한다.

## 5. 보안과 개인정보

- 접속 일수 집계에 기기 식별자, GPS, 원시 활동 기록은 필요하지 않다.
- 인증 토큰, 이메일, 이름을 로그에 남기지 않는다.
- 클라이언트가 보낸 날짜나 횟수를 신뢰하지 않는다.
- 접속 기록은 보상과 화면 진행률에 필요한 최소 필드만 저장한다.

## 6. 인수 조건

- 같은 사용자·같은 local date의 접속 요청을 반복해도 주간 접속 일수는 한 번만 증가한다.
- 여러 기기에서 동시에 요청해도 한 번만 기록된다.
- timezone 날짜 경계와 주 경계가 서버 기준으로 일관된다.
- 앱 접속 기록은 일일 15개 수동 수령 상태와 잔액을 바꾸지 않는다.
- 미확정 보상은 지급되지 않고 `reward_amount=null`로 반환된다.
- 확정 후에는 각 주간 퀘스트가 정확히 한 번만 지급되고 거래 후 잔액이 일치한다.
- 주간 리포트 확인은 서버의 acknowledgement 상태를 사용한다.
- 운동 목표 진행률은 공식 완료 상태와 해당 주의 목표 snapshot을 사용한다.
- formatter, linter, type checker, unit/API/integration test와 migration 검증을 통과한다.

## 7. 프런트 후속 연결

백엔드 계약이 승인되고 배포되면 프런트는 typed API 응답에 `weekly_quests`를 추가하고,
현재의 `진행 정보 없음`과 `보상 준비 중`을 서버 값으로 교체한다. 이때 로컬 집 방문
기록으로 앱 접속 횟수를 계산하는 코드는 추가하지 않는다. 백엔드 필드가 없거나 요청이
실패하면 현재 준비 상태를 유지해 기존 서버와의 호환성을 보장한다.
