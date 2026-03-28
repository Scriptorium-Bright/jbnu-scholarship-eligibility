# Phase 8.0

## Status
- completed

## Goal
heuristic extractor와 LLM extractor가 같은 출력 계약을 따르도록 extractor 계층을 분리한다.

## Scope
- extractor 공용 interface 도입
- heuristic extractor를 interface 구현체로 정리
- rule extraction service의 concrete dependency 제거
- phase 8 공통 테스트 진입점 준비

## Changes
- `app/extractors/base.py` 추가
- `app/extractors/__init__.py` 갱신
- `app/extractors/scholarship_rules.py` 갱신
- `app/services/rule_extraction.py` 갱신
- `tests/unit/test_phase8_extractor_contract.py` 추가
- `docs/phase-8.0.md` 추가

## What Changed
- 기존 구조:
  - `ScholarshipRuleExtractionService`가 `HeuristicScholarshipRuleExtractor` concrete class에 직접 의존했다.
  - extractor 결과 dataclass와 구현체가 같은 파일에 묶여 있었다.
- 이번 수정:
  - extractor 결과 계약과 공용 interface를 `app/extractors/base.py`로 분리했다.
  - heuristic extractor는 공용 contract를 구현하는 구현체로 재정리했다.
  - rule extraction service는 concrete class 대신 contract 타입을 주입받도록 바꿨다.
- 변경 이유:
  - phase 8.1 이후 LLM extractor를 붙일 때 service, persistence, search, eligibility를 흔들지 않고 extractor만 교체하기 위해서다.

## How To Read This Phase
- 먼저 `app/extractors/base.py`를 읽고 phase 8 extractor contract가 무엇인지 확인한다.
- 다음으로 `app/extractors/scholarship_rules.py`를 읽어 기존 heuristic 구현이 새 contract에 어떻게 맞춰지는지 본다.
- 마지막으로 `app/services/rule_extraction.py`를 읽어 orchestrator가 concrete class 대신 interface를 어떻게 주입받는지 확인한다.

## File Guide
- `app/extractors/base.py`: structured extraction 공용 protocol 또는 abstract base
- `app/extractors/scholarship_rules.py`: heuristic extractor를 contract 구현체로 정리
- `app/extractors/__init__.py`: extractor public export 경계에 contract 타입 추가
- `app/services/rule_extraction.py`: extractor 주입 지점 정리
- `tests/unit/test_phase8_extractor_contract.py`: heuristic extractor와 future llm extractor가 같은 반환 계약을 지키는지 검증

## Python File Breakdown
- [`app/extractors/base.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/app/extractors/base.py): heuristic와 future LLM extractor가 공통으로 따라야 할 결과 타입과 protocol을 분리한 파일
- [`app/extractors/scholarship_rules.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/app/extractors/scholarship_rules.py): 기존 regex extractor를 공용 contract 구현체로 재배치한 파일
- [`app/extractors/__init__.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/app/extractors/__init__.py): 외부 import 지점에서 contract 타입까지 함께 노출하도록 정리한 파일
- [`app/services/rule_extraction.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/app/services/rule_extraction.py): orchestration service가 concrete extractor 대신 contract에 의존하도록 바꾼 파일
- [`tests/unit/test_phase8_extractor_contract.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/tests/unit/test_phase8_extractor_contract.py): extractor contract와 service 주입 경로를 검증하는 테스트 파일

## Added / Updated Methods
### [`app/extractors/base.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/app/extractors/base.py)
- `StructuredRuleExtractor.extract_notice_rule`: 어떤 extractor 구현체든 동일한 입력과 동일한 반환 계약을 지키게 만드는 공용 메서드 계약

### [`app/extractors/scholarship_rules.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/app/extractors/scholarship_rules.py)
- `HeuristicScholarshipRuleExtractor.extract_notice_rule`: phase 5에서 만든 regex 기반 추출 로직을 유지하되, 이제는 공용 contract 구현체로 동작

### [`app/services/rule_extraction.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/app/services/rule_extraction.py)
- `ScholarshipRuleExtractionService.__init__`: concrete heuristic extractor가 아니라 `StructuredRuleExtractor`를 주입받아 future LLM extractor와 교체 가능하게 만든다
- `ScholarshipRuleExtractionService.extract_notice`: downstream persistence는 그대로 유지하면서도 공용 extractor contract만 호출하도록 orchestration 경계를 유지한다

### [`tests/unit/test_phase8_extractor_contract.py`](/Users/jeonjeonghyeon/studyCollection/jbnu-scholarship-eligibility/tests/unit/test_phase8_extractor_contract.py)
- `test_phase8_heuristic_extractor_satisfies_structured_rule_contract`: 기존 heuristic extractor가 새 protocol을 만족하는지 검증
- `test_phase8_rule_extraction_service_accepts_any_structured_rule_extractor`: service가 concrete extractor가 아니라 contract 구현체를 주입받는지 검증

## Method Guide
### `app/extractors/base.py`
- `StructuredRuleExtractor.extract_notice_rule`: canonical document를 받아 `ExtractedScholarshipRule`을 반환하는 공용 메서드

### `app/extractors/scholarship_rules.py`
- `HeuristicScholarshipRuleExtractor.extract_notice_rule`: contract 구현체로 유지

### `app/services/rule_extraction.py`
- `ScholarshipRuleExtractionService.__init__`: concrete heuristic extractor 대신 contract 타입 의존
- `ScholarshipRuleExtractionService.extract_notice`: downstream persistence는 그대로 유지

## Importance
- high: phase 8 전체가 extractor 교체만으로 흘러가게 만드는 기반
- mid: downstream search/eligibility를 안 건드리고 AI layer를 붙일 수 있는 구조 확보
- low: heuristic extractor 회귀 테스트를 더 명확히 분리

## Problem
현재 rule extraction service는 heuristic extractor concrete class에 직접 묶여 있어, LLM extractor를 끼워 넣으려면 service 코드와 테스트를 함께 흔들 가능성이 있다.

## Solution
structured extraction 결과 계약을 공용 interface로 분리하고, 기존 heuristic extractor를 그 구현체 중 하나로 정리한다.

## Result
phase 8.1부터는 LLM schema와 provider를 추가해도 search/eligibility/persistence는 그대로 둔 채 extractor만 교체할 수 있는 상태가 되었다.

## Tests
- executed: `pytest tests/unit/test_phase5_rule_extractor.py tests/unit/test_phase8_extractor_contract.py`, `pytest`
- result: `3 passed`, `30 passed`

## Portfolio Framing
AI를 붙이기 전에 먼저 추출 계층을 interface로 분리해 기존 결정 엔진과 저장 계층을 안정적으로 보호했다는 점을 말할 수 있다.

## Open Risks
- contract를 너무 넓게 잡으면 fake provider와 llm provider 모두 구현 비용이 커질 수 있다.
- dataclass와 pydantic schema 경계를 이 단계에서 혼동하면 이후 structured output parsing이 복잡해진다.

## Refactor Priorities
- high: extractor result contract를 dataclass 유지 vs pydantic 전환 여부 명확화 / 성능 영향: 간접 있음
- mid: rule extraction service 내부 persistence helper 분리 / 성능 영향: 없음
- low: heuristic extractor 내 한글 장문 docstring 정리 / 성능 영향: 없음

## Next Phase Impact
phase 8.1에서는 LLM이 따라야 할 structured output schema와 evidence contract를 정의한다.
