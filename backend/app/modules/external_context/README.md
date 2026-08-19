# External context module

캘린더와 이후 선택적 외부 컨텍스트의 application port를 둡니다. provider SDK·HTTP 타입과 원시
payload를 domain에 노출하지 않습니다. Wave 9C-1은 `CalendarProviderPort`, unavailable null object와
credential-free synthetic adapter를 제공합니다. `external-context-policy-v2`부터 event/performance는
공식 completion 엔터티인 `workout_session_id`를 사용합니다. 실제 Google Calendar 호출, service,
repository와 API route는 `ACCEPTED` ADR-0010 및 TASK-BACKEND-007의 단계에 따라 추가합니다.
