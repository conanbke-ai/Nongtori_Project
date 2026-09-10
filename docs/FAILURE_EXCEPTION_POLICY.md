# Nongtori Failure & Exception Policy

## 1. 공통 원칙

- 실패를 임의 label/confidence/가격으로 덮지 않는다.
- 자동화 영역은 사람 호출 전에 재관측/재시도/temporal aggregation을 수행한다.
- 병해충 field verification은 실패가 아니라 정상 정책이다.
- 데이터/모델/외부 API 오류는 명시 상태 코드로 남긴다.

## 2. Data ingestion / Snapshot

대표 상태:

- `SOURCE_UNAVAILABLE`
- `SOURCE_FORMAT_CHANGED`
- `LICENSE_REVIEW_REQUIRED`
- `CHECKSUM_MISMATCH`
- `CORRUPT_FILE`
- `LABEL_MAPPING_ERROR`
- `DUPLICATE_CONFLICT`
- `SCHEMA_MISMATCH`
- `LOCATION_PARSE_ERROR`

실패 source는 Registry에서 삭제하지 않고 상태/사유를 남긴다.

## 3. 숙도 / 등급

```text
low confidence / inconsistent frames
→ additional frame observation
→ temporal aggregation
→ retry/re-evaluate
→ still unresolved
→ SYSTEM_EXCEPTION
```

한 frame confidence만으로 농민에게 개별 딸기 재확인을 요구하지 않는다.

## 4. Tracking

대표 실패:

- excessive ID switches
- fragmentation
- track too short
- detector miss burst
- severe occlusion

V1은 ByteTrack/BoT-SORT baseline 결과를 비교하고, custom persistent ReID를 자동 fallback으로 만들지 않는다.

## 5. 병해충

```text
risk / ambiguous
→ VERIFY_ZONE
```

`VERIFY_ZONE`은 정상 업무 상태다.

가능 상태:
- `VERIFY_ZONE`
- `CONFIRMED`
- `REJECTED`
- `RECHECK_REQUIRED`
- `RECORD_ONLY`

## 6. 가격

- `NO_MARKET_TRADE`
- `UNSUPPORTED_ITEM`
- `VARIETY_MAPPING_ERROR`
- `UNIT_NORMALIZATION_ERROR`
- `SOURCE_UNAVAILABLE`
- `MODEL_UNAVAILABLE`
- `OUT_OF_DISTRIBUTION`

실패 시 이전 가격/평균값을 현재 예측인 것처럼 반환하지 않는다.

## 7. UI

사용자 메시지는 가능한 한 다음 순서를 따른다.

```text
무슨 상태인가
→ 왜 그런가
→ 사용자가 지금 무엇을 하면 되는가
```

기술 stack trace는 사용자 화면에 직접 노출하지 않는다.
