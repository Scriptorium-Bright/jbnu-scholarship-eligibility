# Phase 8.1

## Status
- completed

## Goal
LLM이 따라야 할 structured output schema와 evidence contract를 정의한다.

## Scope
- LLM extraction response schema 추가
- field별 evidence 형식 정의
- schema validation test 추가
- quote text가 아닌 block id 기반 provenance 원칙 확정

## Changes
- `app/schemas/llm_extraction.py` 추가
- `app/schemas/__init__.py` 갱신
- `tests/unit/test_phase8_llm_schema.py` 추가
- `docs/phase-8.1.md` 갱신

## What Changed
- 기존 구조:
  - phase 8.0까지는 extractor contract만 분리되어 있었고, future LLM extractor가 어떤 JSON을 반환해야 하는지는 아직 고정되지 않았다.
  - evidence 형식도 문서 근거를 어떤 필드로 묶을지 명확하지 않아 provider 구현 시 응답 형태가 흔들릴 수 있었다.
- 이번 수정:
  - LLM structured extraction 전용 schema를 `LLMExtractionResponse` 기준으로 정의했다.
  - qualification과 evidence를 하위 schema로 분리하고, 허용 필드 이름을 literal로 제한했다.
  - evidence에는 `document_id`, `block_id`, `quote_text`를 필수로 두고, grade level과 문자열 배열은 validator로 정규화했다.
- 변경 이유:
  - phase 8.3 이후 provider가 어떤 모델을 호출하더라도 같은 structured output contract를 강제하기 위해서다.
  - 이후 정확도, evidence validity, fallback success rate 같은 수치를 같은 기준으로 비교할 수 있게 만들기 위해서다.

## Python File Breakdown
- `app/schemas/llm_extraction.py`: LLM extractor가 따라야 할 최상위 응답 schema와 evidence schema를 정의한 파일
- `app/schemas/__init__.py`: application 전역 import 경계에서 새 LLM extraction schema를 노출하도록 갱신한 파일
- `tests/unit/test_phase8_llm_schema.py`: valid payload, 필수 근거 누락, 허용되지 않은 field name을 검증하는 phase 8.1 전용 테스트 파일

## Added / Updated Methods
### `app/schemas/llm_extraction.py`
- `LLMExtractionQualification._normalize_grade_levels`: 학년 배열을 중복 제거 후 오름차순으로 정리해 downstream deterministic 비교가 흔들리지 않게 만든다.
- `LLMExtractionQualification._remove_blank_strings`: 재학 상태와 제출서류 배열에서 공백 문자열을 제거해 evidence 품질 지표가 의미 없는 값에 오염되지 않게 만든다.

### `tests/unit/test_phase8_llm_schema.py`
- `test_phase8_llm_schema_accepts_valid_structured_output`: 정상 payload가 parse되고 배열 정규화까지 적용되는지 검증한다.
- `test_phase8_llm_schema_rejects_evidence_without_block_id`: block id가 빠진 evidence를 parser 단계에서 바로 차단하는지 검증한다.
- `test_phase8_llm_schema_rejects_unsupported_field_name`: 허용되지 않은 field name이 들어왔을 때 contract 위반으로 실패하는지 검증한다.

## How To Read This Phase
- 먼저 `app/schemas/llm_extraction.py`를 읽고 future provider가 반환해야 할 JSON shape를 확인한다.
- 다음으로 `tests/unit/test_phase8_llm_schema.py`를 읽어 어떤 payload를 성공으로 보고 어떤 contract 위반을 실패로 보는지 본다.
- 마지막으로 `docs/phase-8-portfolio-rubric.md`를 같이 보면 왜 evidence contract를 강하게 잡았는지, 이후 어떤 수치로 이어질지 이해할 수 있다.

## File Guide
- `app/schemas/llm_extraction.py`: LLM structured output용 최상위 schema와 evidence contract
- `app/schemas/__init__.py`: 외부에서 import할 public schema export 정리
- `tests/unit/test_phase8_llm_schema.py`: schema validation 회귀 테스트

## Method Guide
### `app/schemas/llm_extraction.py`
- `LLMExtractionQualification._normalize_grade_levels`: grade level 입력을 중복 없는 안정된 정렬 상태로 바꾼다.
- `LLMExtractionQualification._remove_blank_strings`: 빈 문자열과 공백을 제거해 문자열 배열을 정제한다.

### `tests/unit/test_phase8_llm_schema.py`
- `test_phase8_llm_schema_accepts_valid_structured_output`: valid payload parse와 배열 정규화 검증
- `test_phase8_llm_schema_rejects_evidence_without_block_id`: 근거 block id 누락 차단 검증
- `test_phase8_llm_schema_rejects_unsupported_field_name`: schema 밖 필드명 거부 검증

## Importance
- high: hallucinated free-form 답변을 막고 structured extraction으로 고정
- mid: phase 8.4 provenance 매핑과 evaluation metric 정의의 기준점 확보
- low: future provider 교체 시 schema만 유지하면 되는 안정성 확보

## Problem
LLM을 바로 붙이면 자유형 텍스트 응답 때문에 parsing, validation, provenance 연결이 모두 흔들릴 수 있다.

## Solution
모델이 반환해야 할 JSON schema를 먼저 정의하고, evidence는 반드시 `block_id`를 포함하도록 강제한다.

## Result
future provider는 `LLMExtractionResponse`만 만족하면 되도록 기준점이 생겼고, phase 8.2와 8.3에서는 prompt와 provider를 이 schema 중심으로 구현할 수 있게 되었다.

## Tests
- executed: `pytest tests/unit/test_phase8_llm_schema.py -q`, `pytest -q`
- result: `3 passed`, `36 passed`

## Portfolio Framing
LLM을 “답변기”가 아니라 “검증 가능한 structured extractor”로 제한했다는 점이 중요하다. 이 설계가 있어야 이후 accuracy와 evidence validity를 수치화할 수 있다.

## Open Risks
- schema를 너무 풍부하게 잡으면 첫 구현 난도가 급격히 올라간다.
- block id와 quote text를 동시에 강제할 경우 모델 출력 안정성이 떨어질 수 있다.

## Refactor Priorities
- high: qualification field별 evidence cardinality 규칙 추가 / 성능 영향: 간접 있음
- mid: qualification schema와 기존 `ScholarshipRuleCreate` 사이 mapping helper 분리 / 성능 영향: 없음
- low: schema alias와 field description 보강 / 성능 영향: 없음

## Next Phase Impact
phase 8.2에서는 canonical block을 LLM 입력 context로 만드는 prompt/context builder를 구현한다.
