# 바나나 받기 미니게임

끼끼의 집에서 여는 독립형 30초 캐치 게임이다. 운동 완료, 주간 목표, 집의 바나나
재화와 게임 점수는 서로 영향을 주지 않는다.

- `bananaCatchModel.ts`: 화면 크기와 무관한 상대 좌표, 낙하·포획·종료 규칙
- `BananaCatchGameScreen.tsx`: 타이머, 터치·버튼 입력, 일시정지와 화면 표시
- 점수와 최고 기록은 저장하지 않는다.
- 놓친 바나나는 감점하지 않으며 실패·압박 문구를 표시하지 않는다.
- 앱이 비활성화되면 진행을 멈추고 사용자가 직접 이어서 시작한다.

규칙 검증은 `tests/bananaCatchModel.test.ts`, 화면과 타이머 검증은
`tests/BananaCatchGameScreen.test.tsx`에 둔다.
