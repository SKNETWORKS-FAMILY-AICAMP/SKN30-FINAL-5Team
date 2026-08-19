# Identity module

Firebase ID Token 검증 결과와 내부 사용자 identity 연결, 비활성 계정 접근 차단을 담당합니다.

- `codes.py`: `identity-mvp-v1` machine code 집합
- `ports.py`: Firebase verifier와 persistence 경계
- `service.py`: 최초 사용자 생성과 현재 사용자 판정

이 모듈은 token, 이메일, 전체 이름을 받거나 저장하지 않습니다. provider SDK와 credential 처리는
`integrations`에만 존재하며 공개 `/me`, 온보딩, social exchange endpoint는 후속 작업입니다.
