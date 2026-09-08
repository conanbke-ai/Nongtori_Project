# Nongtori UI Rebuild Plan v1

## 현재 상태

현재 저장소는 구현 코드보다 아키텍처·데이터 전략·디자인 가이드·마이그레이션 문서와 표준 캐릭터 asset 중심이다. 따라서 오래된 화면을 억지로 이어붙이지 않고, 실제 앱 구현을 시작할 때부터 TORI UI System v1을 기준으로 작성한다.

## Theme v1

```css
:root {
  --tori-primary: #78C5E2;
  --tori-primary-deep: #397E99;
  --tori-field: #5F8E68;
  --tori-strawberry: #EA8392;
  --tori-cream: #FFF9EF;
  --tori-soil: #7A5A46;
  --tori-jelly: #F29AAA;
  --tori-jelly-highlight: #FFD0D7;
  --tori-ink: #293B39;
}
```

농장주·현장 작업자가 빠르게 읽을 수 있도록 충분한 대비, 큰 hit area, 짧은 문구와 명확한 상태 표현을 우선한다. 초록색 일변도 UI는 피하고 하늘색 토리 + 농장/딸기 포인트를 균형 있게 사용한다.

## 고양이 젤리발 + 뾰잉

TORI 패밀리 공통 시그니처를 사용한다.

- 4 toe beans + 중앙 고양이 metacarpal pad
- 곰발처럼 두껍고 넓은 중앙 패드 금지
- project jelly color는 strawberry coral 계열
- desktop fine pointer에서만 활성화
- pointer down 시 짧은 `뾰잉!`
- 작업 입력/안전 경고/위험 버튼에서는 장식보다 상태 명료성을 우선
- reduced-motion 대응

## 구현 우선순위

1. theme token / primitive / cursor
2. 로그인·역할 선택
3. 농장 선택/대시보드
4. 오늘 작업/작업 상세/완료 입력
5. 관리자 작업 배정
6. 농장주 현황/작업자 관리
7. 외국인 작업자용 다국어 현장 화면
8. 데이터/분석/알림 화면

## 데이터·기능 보존 원칙

- 테스트용 Google Sheets/원본 외부 데이터는 읽기 전용을 기본으로 한다.
- 관리자/농장주/작업자 권한을 UI 편의를 위해 우회하지 않는다.
- 실제 API/Repository가 생기면 화면은 해당 contract를 소비하고 business rule을 component에 복제하지 않는다.
- 테스트 데이터와 실제 데이터를 명확히 구분한다.

## 완료 기준

- 고령 사용자도 터치하기 쉬운 최소 44px hit area
- 모바일 우선
- 역할별 화면/권한 명확
- loading/empty/error/offline 상태 고려
- 색만으로 상태를 전달하지 않음
- TORI 캐릭터 기준과 고양이 젤리발 cursor contract 준수
- 새 앱 구현 시 거대 global CSS/JS monolith를 만들지 않음
