# 끼끼 합치기

React Native 뷰 위에 Matter.js의 원형 강체 계산만 사용하는 미니게임이다.
WebView, Canvas 렌더러, 외부 게임 저장소의 코드는 포함하지 않는다. 렌더링은
기존 `Image`와 `View`로 처리하고, 물리 좌표만 Matter.js에서 받는다.

- 런타임 에셋: `assets/mascot/monkey/kkikki/kkikki_drops/kkikki_stage_01~11.png`
- 제외 에셋: `11concepts.png`, `temp_01_step.png`
- 라운드: 시간 제한 없이 위험선 초과 시 종료
- 점수: 끼끼의 단계와 무관하게 합치기 1회마다 1점을 누적하고 보상 API 계약에 맞춰 최대 200점으로 제한
- 총 합치기: 200점에 도달한 뒤에도 실제 합치기 횟수를 계속 누적해 결과에 표시
- 기록: 한 판 동안 합치기로 만든 9~11단계 끼끼의 개수를 각각 누적하고, 단계 이미지와 개수를 게임 화면과 결과에 표시
- 보상: 종료 점수를 기존 `/api/v1/rewards/mini-game/claim`에 보고하며, 모든
  미니게임을 통틀어 하루 첫 보너스만 지급. 현재 서버 환산은 `점수 // 2`, 최대 25개
- 물리 라이브러리: Matter.js 0.20.0 (MIT)
