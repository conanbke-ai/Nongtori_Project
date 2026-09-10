# 다농가 운영 데이터 모델

## 역할 분리

- 업체 운영자: 농가, 하우스, 베드, 구역, 품종, 카메라 연결을 등록하고 변경한다.
- 농민: 자동수확로봇을 운용하거나 직접 촬영 판독을 실행하고 결과를 확인한다.
- 서비스: 영상 세션, 프레임 번호, 객체 추적 ID, RGB·열화상 대응 관계를 자동 생성한다.

농민용 화면이나 요청에서는 내부 ID를 입력받지 않는다. 업체가 카메라를 구역에 한 번 연결하면 이후 로봇 영상 세션은 카메라가 가진 농가·하우스·베드·구역을 상속한다.

## 관계형 데이터 구조

```text
farms
├─ farm_members
├─ farm_items ─ crop_types / cultivars
├─ farm_cultivars ─ cultivars
├─ houses
│  └─ beds
│     └─ zones
├─ cameras
└─ capture_sessions
   ├─ video_assets
   │  └─ frames
   └─ inference_runs
      └─ frame_predictions
```

- `cultivars`는 전역 품종 목록이다. 설향은 이 목록의 한 항목이다.
- `farm_items`는 한 농가가 재배하는 여러 품목·품종을 앱 선택 항목으로 제공한다.
- `farm_members`는 계약 계정과 접근 가능한 농장을 연결한다. 비밀번호 검증은 인증 제공자가 담당하고 DB에는 제공자 사용자 식별자만 저장한다.
- `farm_cultivars`는 농장별 재배 품종을 연결한다.
- `cameras`는 로봇, 고정형, RGB, 열화상, 이중 센서 장비를 같은 계약으로 관리한다.
- 카메라의 `stream_url`, `connection_status`, `last_seen_at`으로 앱의 실시간 화면과 장비 상태를 구성한다.
- `capture_sessions`는 로봇 운행 또는 직접 촬영 1회를 나타낸다.
- `video_assets`와 실제 영상 파일은 분리한다. 메타데이터는 D1, 큰 원본은 R2에 저장한다.
- `frames`와 `frame_predictions`는 연속 프레임을 저장하지만 농민 화면에서는 같은 추적 대상을 한 사건으로 묶는다.

## Google Sheets 가져오기

`POST /api/vendor/farm-import`는 업체용 정규화 스냅샷을 받는다.

- 지원 원본: `GOOGLE_SHEET_SNAPSHOT`, `CSV_SNAPSHOT`
- 접근 방식: 항상 `READ_ONLY`
- 쓰기 대상: 서비스 D1 데이터베이스만
- 원본 시트 수정, 셀 업데이트, 역동기화: 금지
- 실행 이력: `config_sources`, `config_import_runs`

현재 API는 시트를 직접 읽는 OAuth 연결 대신, 업체가 읽기 전용으로 읽어 정규화한 JSON 스냅샷을 받는다. 실제 Google Sheets API 연결 시에도 같은 입력 계약을 사용하면 DB 구조를 바꾸지 않고 교체할 수 있다.

## 영상 세션 생성

`POST /api/video-sessions`는 `farmId`, 등록된 `cameraId`, 수집 방식과 영상 메타데이터만 받는다.

서버가 다음 값을 생성하거나 상속한다.

- 영상 세션 ID
- RGB·열화상 영상 자산 ID
- 농가·하우스·베드·구역 연결
- 추출 프레임 ID와 프레임 번호
- 추론 실행 ID와 객체 추적 ID

큰 영상의 직접 업로드는 Worker API를 거치지 않고 R2 직접 업로드 또는 재개 가능한 업로드로 추가한다.

## 설치형 앱과 현장 입력

- 앱은 홈 화면에 설치 가능한 PWA로 실행한다.
- `홈`, `실시간`, `알림`, `기록`, `직접 판독`은 각각 별도 앱 화면으로 전환된다.
- 과실 사진은 휴대전화 카메라 권한으로 촬영해 R2에 저장한다.
- 잎의 RGB·열화상 사진은 서버가 한 세션으로 자동 연결한다.
- RGB·열화상 영상도 별도의 페어링 ID 입력 없이 한 영상 세션으로 접수한다.
- 검증된 모델이 연결되기 전에는 임의의 결과를 만들지 않고 분석 대기 상태만 표시한다.
