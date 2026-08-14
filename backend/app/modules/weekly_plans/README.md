# Weekly plans module

다음 주 `INITIAL` 계획과 `AI`·`USER` revision, AI 성공 수정 최대 2회, 직전 리포트
acknowledgement 기반 finalize gate를 관리합니다.

`INITIAL`과 `AI`는 서버가 현재 유효한 routine version을 선택합니다. `USER`는 사용자 소유의
저장된 routine version과 실행 장소만 지정할 수 있으며, 서버가 routine의 요청 시간·지원 장소·
필요 장비와 저장된 SafetyAgent 제외 의견을 다시 검증합니다. 임의 운동 JSON, 안전 상태 또는
SafetyAgent 의견을 클라이언트 입력으로 받지 않습니다.
