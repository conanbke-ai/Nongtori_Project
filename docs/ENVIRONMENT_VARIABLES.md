# Nongtori Environment & Secret Contract

이 문서는 농토리 애플리케이션과 로컬 데이터 연구에서 사용하는 환경 값의 canonical 기준입니다.

실제 값은 Git에 저장하지 않습니다. 새 환경변수는 코드에 먼저 임의 추가하지 않고 `configs/environment-contract.json`, 이 문서, `env.d.ts`를 함께 갱신합니다.

## 배포 기준

현재 농토리 애플리케이션의 기본 배포 대상은 **Cloudflare 계열**입니다.

- D1: 애플리케이션 DB
- R2: 이미지·영상·증거 프레임
- Runtime secret/config: Cloudflare 배포 환경에서 관리
- Render: 농토리 canonical 배포 대상이 아님
- Dryad/학습 데이터 수집: 운영 서버와 분리된 로컬 연구 작업

## 1. 필수 Cloudflare resource binding

| 이름 | 종류 | 필수 | 비밀값 | 용도 |
|---|---|---:|---:|---|
| `DB` | D1 binding | O | X | 계정·농가·예찰·수확·workflow 상태 |
| `FILES` | R2 binding | O | X | 사진·영상·증거 프레임 |

`DB`와 `FILES`는 문자열 환경변수가 아니라 Cloudflare resource binding입니다. 로컬/배포 환경의 D1·R2 연결 설정으로 관리합니다.

## 2. Runtime secret / config

모든 값은 현재 기능별 **optional capability**입니다. 해당 기능을 켤 때 필요한 세트만 설정합니다.

| 변수 | 분류 | 기능 | 조건 |
|---|---|---|---|
| `GOOGLE_TRANSLATE_API_KEY` | Secret | 현장 메모 번역 | 번역 기능 사용 시 |
| `SMS_VERIFICATION_URL` | Config | 휴대폰 인증 | 아래 3개를 한 세트로 사용 |
| `SMS_VERIFICATION_TOKEN` | Secret | 휴대폰 인증 | `SMS_VERIFICATION_URL`과 함께 |
| `PHONE_VERIFICATION_PEPPER` | Secret | 인증코드 hash | 위 두 값과 함께 |
| `NOTIFICATION_WORKER_TOKEN` | Secret | 알림 worker | 외부 worker 호출 시 |
| `SMS_ALERT_URL` | Config | 예찰 SMS 발송 | `SMS_ALERT_TOKEN`과 함께 |
| `SMS_ALERT_TOKEN` | Secret | 예찰 SMS 발송 | `SMS_ALERT_URL`과 함께 |
| `FORECAST_WORKER_TOKEN` | Secret | 시세/수익 예측 worker | 외부 worker 연결 시 |
| `ROBOT_INGEST_TOKEN` | Secret | 수확 로봇 결과 ingest | 외부 로봇 연동 시 |
| `VENDOR_IMPORT_TOKEN` | Secret | 업체 농가 구성 import | 업체 연동 시 |

### 관리 원칙

- URL류는 configuration입니다. 토큰·API key·pepper는 secret입니다.
- Secret 실제 값은 README, JSON contract, issue, PR, log에 기록하지 않습니다.
- 로컬 개발에서는 ignored local secret file 또는 shell/OS secret을 사용합니다.
- 배포에서는 Cloudflare의 secret/config 관리 기능으로 이전합니다.
- 하나의 secret을 여러 의미의 변수에 복제하지 않습니다. 실제 공급자가 같더라도 capability 경계를 유지합니다.

## 3. 로컬 연구 전용

### Dryad

`DRYAD_TOKEN`은 **농토리 운영 환경변수가 아닙니다.**

현재 canonical flow:

```text
Dryad/외부 공개 데이터
→ 필요한 파일 수동 다운로드
→ Git-ignored local data directory
→ checksum / schema / join audit
→ immutable snapshot descriptor
→ local GPU training
```

기존 `ml/data_pipeline/dryad_acquisition.py`의 token-aware 다운로드 helper는 보조 경로로만 유지합니다. Render/Cloudflare에 Dryad 자격증명을 지금 등록하지 않습니다. 자동 수집이 실제로 필요해질 때 별도 migration으로 다룹니다.

## 4. Tooling-only 값

아래 값은 애플리케이션 기능 변수가 아니므로 운영 secret inventory에 넣지 않습니다.

- `CODEX_SANDBOX`
- `WRANGLER_WRITE_LOGS`
- `WRANGLER_LOG_PATH`
- `MINIFLARE_REGISTRY_PATH`

후자의 Wrangler/Miniflare 값은 현재 `vite.config.ts`가 프로젝트 로컬 경로로 설정합니다.

## 5. 지금 만들지 않는 변수

현재 코드가 소비하지 않는 키는 선제적으로 추가하지 않습니다.

예:

- `OPENAI_API_KEY`
- 임의의 Weather API key
- 임의의 model endpoint URL
- Dryad client ID / client secret

새 외부 서비스가 실제 Adapter/Service에 연결되는 작업에서 계약을 추가합니다.

## 6. 로컬 secret template

`.dev.vars.example`은 **이름만 제공하는 템플릿**입니다.

실제 로컬 값 파일은 Git에서 제외합니다. Cloudflare binding인 `DB`, `FILES`는 이 템플릿에 문자열 값으로 넣지 않습니다.

## 변경 체크리스트

새 환경값 추가 시:

1. 실제 코드 사용처 확인
2. `configs/environment-contract.json` 갱신
3. `env.d.ts` 타입 갱신
4. secret/config/resource binding 분류
5. local example이 필요한 경우 `.dev.vars.example` 갱신
6. README/ACTIVE_WORK와 배포 대상 불일치가 없는지 확인
7. 실제 secret 값은 Git에 커밋하지 않음
