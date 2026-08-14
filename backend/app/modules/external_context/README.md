# External context module

캘린더와 이후 선택적 외부 컨텍스트의 application port를 둡니다. provider SDK·HTTP 타입과 원시
payload를 domain에 노출하지 않습니다. Wave 9C-1은 `CalendarProviderPort`와 unavailable null object만
제공하며 실제 Google Calendar 호출, service, repository와 API route는 ADR-0010 승인 뒤 추가합니다.
