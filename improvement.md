# 고도화 및 배포 준비 문서

## 목적

이 문서는 현재 프로젝트를 더 발전시키기 위해 무엇을 보강해야 하는지, 그리고 실제 배포 가능한 서비스로 만들려면 어떤 준비가 필요한지 정리한다.

핵심 방향은 단순히 기능을 늘리는 것이 아니라, 아래 역량을 강화하는 것이다.

- 비정형 공지를 안정적으로 수집하고 재처리하는 데이터 파이프라인
- 구조화된 규칙을 기반으로 한 결정론적 판정 엔진
- 근거 기반 검색/RAG 응답의 품질 검증 체계
- 운영 환경에서 장애를 추적하고 복구할 수 있는 배포 구조

## 현재 기준선

현재 프로젝트는 아래 흐름까지 구현되어 있다.

```text
공지 수집
-> 원문 HTML/첨부파일 저장
-> canonical document 정규화
-> 장학 조건 구조화
-> 검색 / RAG 질의응답 / eligibility 판정 API
```

강점:

- 공지 원문, 정규화 문서, 구조화 규칙, 근거 포인터를 분리했다.
- 최종 지원 가능 여부는 LLM이 아니라 규칙 기반 엔진이 판정한다.
- RAG 응답은 근거가 없으면 답변하지 않는 방향으로 설계되어 있다.
- extraction, RAG answer, search 성능에 대한 synthetic benchmark가 있다.

한계:

- 운영형 ETL 파이프라인은 아직 서비스 단위 호출 수준이다.
- scheduler, pipeline run log, incremental ingestion, 실패 재처리 정책이 부족하다.
- RAG 품질 평가는 아직 작은 fixture와 fake provider 중심이다.
- Docker Compose는 개발 환경 중심이며, 운영 배포 설정은 분리되어 있지 않다.
- 모니터링, 알림, 보안, 개인정보 처리 정책이 아직 명확하지 않다.

## 우선순위 요약

| 우선순위 | 항목 | 이유 |
| --- | --- | --- |
| P0 | 배포 가능한 기본 운영 구조 | 서버 실행, DB migration, 환경변수, health check, raw storage가 안정화되어야 한다. |
| P1 | ETL 파이프라인 운영화 | 공지 수집부터 RAG indexing까지 자동 실행, 실패 추적, 재처리가 가능해야 한다. |
| P1 | 데이터 품질 검증 | 빈 문서, 누락된 provenance, embedding 실패 같은 문제를 API 응답 전에 잡아야 한다. |
| P2 | RAG 평가/검색 고도화 | threshold, refusal, citation 품질을 감이 아니라 데이터로 조정해야 한다. |
| P2 | eligibility 설명력 강화 | 단순 가능/불가능이 아니라 어떤 조건 때문에 탈락했는지 명확히 보여줘야 한다. |
| P3 | 사용자 기능 확장 | 개인화 피드, 비교 화면, 제출서류 체크리스트 등 제품 완성도를 높인다. |

## 1. 제품 기능 고도화

### 1.1 개인화 장학금 피드

현재는 사용자가 검색하거나 eligibility API를 직접 호출해야 한다. 다음 단계에서는 학생 프로필을 기준으로 `지금 지원 가능성이 높은 공고`를 먼저 보여주는 feed가 필요하다.

추가할 것:

- 사용자 프로필 기반 open scholarship ranking
- `eligible`, `ineligible`, `insufficient_info`, `expired` 상태별 그룹화
- 부족한 정보가 있는 경우 추가 입력 필드 안내

기술적 의미:

- 단순 검색 기능을 넘어 rule engine을 실제 제품 흐름에 연결한다.
- read model, eligibility engine, application window filter를 재사용할 수 있다.

### 1.2 탈락 사유 설명 강화

eligibility 결과에서 조건별 pass/fail/missing을 더 명확히 분리한다.

추가할 것:

- 탈락 조건 우선순위 정렬
- 사용자의 입력값과 요구 조건을 함께 표시
- `정보 부족으로 판단 불가`와 `조건 미충족`을 분리
- provenance anchor가 있는 조건은 원문 근거 링크 제공

기술적 의미:

- 판정 결과의 설명 가능성을 높인다.
- 면접에서는 `결정론적 판정 + 근거 기반 explanation` 구조로 설명하기 좋다.

### 1.3 장학금 비교 기능

여러 장학금을 자격 요건, 신청 기간, 제출서류, 소득분위, 학년 기준으로 비교한다.

추가할 것:

- scholarship compare API
- 비교 가능한 normalized field 확장
- 공통 조건과 차이 조건 분리

주의할 점:

- 현재 qualification schema가 핵심 필드 중심이므로, 비교 기능 전에 schema 보강이 필요하다.

### 1.4 제출서류 체크리스트

공지에서 추출한 제출서류를 사용자 준비 상태와 연결한다.

추가할 것:

- required documents field 정규화
- 사용자별 document preparation status
- 마감일 기준 reminder 후보

기술적 의미:

- 구조화 데이터가 검색/판정을 넘어 신청 준비 workflow로 확장된다.

### 1.5 공지 변경 diff

동일 공지의 본문이나 첨부가 변경되었을 때 어떤 조건이 바뀌었는지 보여준다.

추가할 것:

- raw document versioning
- canonical block versioning
- rule extraction result diff
- 변경된 provenance anchor 추적

주의할 점:

- 난이도가 높으므로 pipeline run log와 idempotent reprocessing이 먼저 필요하다.

## 2. ETL 파이프라인 운영화

현재는 수집, 정규화, 추출, RAG indexing 서비스가 각각 존재하지만 운영형 파이프라인 entrypoint는 부족하다.

### 2.1 Pipeline Orchestrator

추가할 것:

- `ScholarshipPipelineService`
- collect -> normalize -> extract -> index 순차 실행
- notice 단위 재처리
- failed-only retry
- 단계별 실행 결과 summary

완료 기준:

- command 하나로 신규 공지 수집부터 RAG chunk 적재까지 실행된다.
- 특정 notice만 재처리할 수 있다.
- 실패한 단계와 실패 원인을 반환한다.

### 2.2 Pipeline Run Log

추가할 것:

- `pipeline_runs` table
- `pipeline_run_steps` table
- run status, trigger type, started_at, finished_at, success_count, failed_count
- notice별 마지막 성공 단계와 실패 단계

완료 기준:

- 운영자가 DB에서 최근 실행 결과와 실패 notice를 조회할 수 있다.
- 재처리 대상이 감이 아니라 run log 기준으로 결정된다.

### 2.3 Incremental Ingestion

현재는 source별 limit 기반 수집 성격이 강하다. 배포 후에는 이미 처리한 공지를 반복 처리하지 않도록 watermark가 필요하다.

추가할 것:

- `collector_watermarks` table
- source별 `last_seen_notice_id`
- source별 `last_successful_run_at`
- full refresh와 incremental mode 분리

완료 기준:

- 기본 실행은 신규/변경 공지만 처리한다.
- 필요할 때만 전체 재수집을 실행한다.

### 2.4 Data Quality Checks

추가할 것:

- raw HTML 존재 여부 검사
- canonical document block 수 검사
- 빈 normalized text 감지
- rule field별 provenance coverage 검사
- RAG chunk 수와 embedding dimension 검사
- eligibility에 필요한 qualification field coverage 검사

완료 기준:

- 품질 기준 미달 notice는 published 상태로 넘어가지 않는다.
- 실패 원인이 collection, normalization, extraction, indexing 중 어디인지 구분된다.

### 2.5 Retry / Failure Policy

추가할 것:

- 외부 게시판 요청 retry
- 첨부파일 다운로드 retry
- LLM/embedding provider timeout과 retry
- deterministic transform 실패와 외부 dependency 실패 구분
- retry 초과 시 failed 상태 저장

완료 기준:

- 일시적 실패는 자동 재시도한다.
- 반복 실패는 다음 run에서 재처리 후보로 남는다.
- 실패가 조용히 무시되지 않는다.

## 3. RAG / 검색 품질 고도화

### 3.1 평가셋 확장

현재 RAG 평가는 작은 synthetic fixture 중심이다. threshold와 refusal 정책을 방어하려면 최소한 라벨링된 질문셋이 필요하다.

추가할 것:

- 질문 100~300개 수준의 offline eval set
- `in_scope`, `out_of_scope`
- `answerable`, `unanswerable`
- `route_to_rag`, `route_to_eligibility`
- `citation_sufficient`, `citation_insufficient`

완료 기준:

- retrieval threshold 변경 전후 false accept / false reject를 비교할 수 있다.
- guardrail이 정상 질문을 과하게 막는지 측정할 수 있다.

### 3.2 Reranker 또는 Answerability Checker

현재 retrieval은 관련 문서를 찾는 데 집중한다. 다음 단계에서는 `정답을 직접 지지하는 근거인가`를 별도로 판단해야 한다.

추가할 것:

- retrieval top-k 이후 reranking
- 질문과 chunk의 direct support score
- 핵심 조건 누락 여부 검사
- answerability checker

완료 기준:

- 비슷하지만 답을 직접 포함하지 않는 chunk가 LLM context로 들어가는 비율을 줄인다.

### 3.3 Refusal Reason Taxonomy

답변 거절 사유를 구조화한다.

예시:

- 범위 밖 질문
- 검색 근거 없음
- 관련 문서는 있으나 핵심 조건 근거 부족
- 개인 조건 판정이 필요한 질문
- provider 오류

완료 기준:

- 사용자 응답과 운영 로그에서 거절 사유를 구분할 수 있다.
- 어떤 유형의 질문에서 실패가 많은지 집계할 수 있다.

### 3.4 Citation-level Grounding 검증

추가할 것:

- 답변 문장과 citation chunk 간 정합성 검사
- citation coverage metric
- unsupported claim 탐지

주의할 점:

- 현재 `근거를 붙인다`와 `근거가 답변 문장을 실제로 지지한다`는 다른 문제다.

## 4. Eligibility 엔진 고도화

### 4.1 Qualification Schema 확장

현재 schema는 핵심 조건 중심이다. 실제 배포 수준에서는 더 다양한 조건을 구조화해야 한다.

추가 후보:

- 학과/단과대 제한
- 재학/휴학/졸업예정 상태
- 직전 학기 이수학점
- 중복 수혜 제한
- 교내/교외 장학금 구분
- 신청 제외 조건
- 우대 조건

완료 기준:

- rule extraction 결과가 eligibility engine에서 직접 소비 가능한 형태로 유지된다.
- schema가 늘어나도 `unknown`, `missing`, `not_applicable` 상태를 구분한다.

### 4.2 상태와 이력 보존

추가할 것:

- rule version
- notice version
- extraction run version
- eligibility decision input/output snapshot

기술적 의미:

- 나중에 공지가 바뀌어도 과거에 어떤 기준으로 판정했는지 추적할 수 있다.

### 4.3 충돌 정책

동일 장학금의 조건이 본문과 첨부에서 다르게 추출될 수 있다.

정리할 것:

- 첨부 우선인지, 최신 문서 우선인지
- 더 엄격한 조건을 우선할지
- 사람이 검수해야 하는 conflict 상태를 둘지

완료 기준:

- 상충 조건을 조용히 덮어쓰지 않는다.
- conflict가 API 응답 또는 admin 검수 대상으로 드러난다.

## 5. API / 백엔드 품질 보강

### 5.1 응답과 에러 스키마 안정화

추가할 것:

- 공통 error response schema
- validation error message 정책
- provider failure, no evidence, bad request, conflict 구분
- request id 반환

### 5.2 Pagination / Cursor

검색 결과와 open scholarship 목록은 데이터가 늘어나면 limit만으로 부족할 수 있다.

추가할 것:

- cursor-based pagination
- stable sort key
- total count 제공 여부 정책

### 5.3 비동기 처리와 timeout

외부 요청, LLM 호출, embedding 호출은 API 요청 안에서 길게 묶이면 장애 전파가 커진다.

추가할 것:

- provider timeout profile
- background job 분리
- 긴 작업은 pipeline/worker로 이동
- API request timeout 정책

### 5.4 관리자 기능

운영자는 데이터 상태를 확인하고 재처리할 수 있어야 한다.

추가할 것:

- pipeline run 조회 API
- failed notice 재처리 API 또는 CLI
- extraction 결과 검수 화면 후보
- 수동 publish/unpublish 상태 변경

## 6. 성능과 확장성

### 6.1 DB Index 점검

추가할 것:

- search query에서 자주 쓰는 column index 점검
- application window filter index
- notice status / source / published_at index
- provenance, canonical block join path index
- pgvector index 전략 검토

완료 기준:

- 실제 query plan 기준으로 병목을 설명할 수 있다.

### 6.2 Read Model 최적화

현재 검색 성능 개선은 provenance eager assembly 제거로 효과를 봤다. 다음 단계는 read model 자체를 더 명확히 분리하는 것이다.

추가할 것:

- 검색용 materialized view 또는 denormalized table 검토
- RAG chunk rebuild와 search read model rebuild 분리
- 인기 검색어 cache

주의할 점:

- cache를 넣기 전에 invalidation 기준을 먼저 정해야 한다.

### 6.3 부하 테스트

추가할 것:

- search API k6 시나리오
- eligibility API k6 시나리오
- ask API는 fake provider와 real provider를 분리 측정
- p50/p95/p99, error rate, throughput 기록

완료 기준:

- 병목이 DB, application, provider 중 어디인지 구분한다.
- 측정 없는 성능 개선 주장을 하지 않는다.

## 7. 관측 가능성

### 7.1 Structured Logging

추가할 것:

- request id
- pipeline run id
- notice id
- provider name
- latency
- refusal reason
- fallback reason

### 7.2 Metrics

추가할 것:

- API latency
- API error rate
- pipeline success/failure count
- collected notice count
- normalized document count
- extracted rule count
- indexed chunk count
- fallback rate
- no-evidence refusal rate
- provider timeout count

### 7.3 Alert

알림 후보:

- readiness 실패
- pipeline 연속 실패
- 수집량 급감
- provider timeout 급증
- DB connection failure
- raw storage write failure

## 8. 보안 / 개인정보 / 신뢰성

### 8.1 Secret 관리

배포 전 해야 할 것:

- `.env` 파일을 서버에 직접 커밋하지 않는다.
- LLM API key, DB password는 secret manager 또는 배포 플랫폼 secret으로 관리한다.
- Docker image에 secret이 포함되지 않도록 확인한다.

### 8.2 개인정보 최소화

eligibility profile에는 학점, 학년, 학적, 소득분위 같은 민감할 수 있는 입력이 들어간다.

정리할 것:

- 저장하지 않고 요청 단위로만 처리할지
- 저장한다면 암호화와 보존 기간을 둘지
- 로그에 profile raw payload를 남기지 않는 정책

### 8.3 외부 입력 방어

추가할 것:

- attachment file size 제한
- 허용 source domain 목록
- 다운로드 timeout
- content type 검증
- HTML/script 저장 시 serving path 분리

### 8.4 API 보호

추가할 것:

- rate limit
- CORS 허용 origin 분리
- admin 기능 인증
- public API와 internal operation API 분리

## 9. 배포 준비 체크리스트

OCI에 배포할 경우 구체적인 리소스 선택, 네트워크, 환경변수, migration, smoke test 기준은 [deployment-oci.md](deployment-oci.md)에 별도로 정리한다.

### 9.1 현재 상태 판단

현재 구성은 로컬 개발과 데모에는 적합하지만, 그대로 운영 배포하기에는 부족하다.

현재 있는 것:

- Dockerfile
- docker-compose 기반 API/PostgreSQL 실행
- `/health`, `/ready`
- Alembic migration
- PostgreSQL + pgvector 사용 구조

부족한 것:

- production용 Dockerfile/compose 분리
- `uvicorn --reload` 제거
- dev dependency 제외
- DB migration 실행 전략
- raw storage 영속화 전략
- scheduler/worker 분리
- secret 관리
- logging/metrics/alert
- HTTPS/reverse proxy/domain 설정
- backup/restore runbook

### 9.2 Production Runtime

배포 전 해야 할 것:

- production image에서는 `.[dev]` 설치를 제거한다.
- `uvicorn --reload`를 사용하지 않는다.
- container를 non-root user로 실행한다.
- CPU/memory limit을 설정한다.
- readiness probe가 DB와 storage를 확인하도록 확장한다.
- API server와 pipeline worker/scheduler를 분리한다.

권장 형태:

```text
api container
worker or scheduler container
postgres or managed postgres
raw storage volume or object storage
reverse proxy / load balancer
```

### 9.3 DB Migration

배포 전 해야 할 것:

- release 시점에 `alembic upgrade head` 실행 절차를 고정한다.
- migration 실패 시 rollback 또는 배포 중단 정책을 정한다.
- 운영 DB backup을 먼저 수행한다.
- destructive migration은 별도 검토 절차를 둔다.

완료 기준:

- 새 서버에서 DB를 빈 상태로 띄워도 migration으로 schema가 구성된다.
- 기존 DB에 migration을 적용해도 데이터가 보존된다.

### 9.4 Raw Storage

현재 raw file은 local filesystem path에 저장된다. 배포 후 container filesystem에만 저장하면 재시작이나 재배포 때 데이터 유실 위험이 있다.

선택지:

- persistent volume
- S3 호환 object storage
- NAS 또는 서버 디스크 mount

정리할 것:

- 저장 경로 정책
- 파일명 충돌 방지
- backup 정책
- 원본 파일 재처리 정책

### 9.5 Scheduler / Worker

배포 전 해야 할 것:

- API process 안에서 장시간 ETL을 직접 실행하지 않는다.
- scheduler/worker process를 분리한다.
- pipeline run이 중복 실행되지 않도록 lock을 둔다.
- failed-only retry command를 만든다.

완료 기준:

- API 요청 처리와 주기 수집 작업이 서로 영향을 덜 준다.
- 배포 직후 수동으로 pipeline bootstrap을 실행할 수 있다.

### 9.6 CI/CD

추가할 것:

- pytest 자동 실행
- Docker image build 검증
- Alembic migration smoke test
- 최소 API smoke test
- 배포 전 환경변수 누락 검사

권장 smoke test:

```text
GET /health
GET /ready
GET /api/v1/scholarships/open
POST /api/v1/scholarships/ask
POST /api/v1/scholarships/eligibility
```

### 9.7 운영 Runbook

배포 전 문서화할 것:

- 서버 시작/중지 방법
- migration 실행 방법
- pipeline 수동 실행 방법
- 실패 notice 재처리 방법
- RAG index rebuild 방법
- backup/restore 방법
- provider 장애 시 fallback 정책

## 10. 추천 로드맵

### Phase 10.0: Pipeline Orchestrator

목표:

- collection -> normalization -> extraction -> indexing을 하나의 실행 흐름으로 묶는다.

주요 산출물:

- `ScholarshipPipelineService`
- notice 단위 재처리
- run summary
- 관련 integration test

### Phase 10.1: Run Log / Data Quality

목표:

- 운영자가 실패 원인과 재처리 대상을 알 수 있게 한다.

주요 산출물:

- pipeline run table
- pipeline step table
- data quality check
- failed-only retry 기준

### Phase 10.2: Production Deployment Baseline

목표:

- 개발용 Docker Compose와 운영용 실행 구성을 분리한다.

주요 산출물:

- production Dockerfile 개선
- production compose 또는 배포 예시
- migration 실행 절차
- secret/env 문서
- deployment smoke test

### Phase 10.3: Scheduler / Incremental Ingestion

목표:

- 주기 실행과 신규/변경 공지만 처리하는 구조를 만든다.

주요 산출물:

- APScheduler job
- collector watermark
- full refresh / incremental mode 분리
- 중복 실행 방지 lock

### Phase 10.4: RAG Evaluation / Reranking

목표:

- 검색과 답변 거절 정책을 정량적으로 튜닝한다.

주요 산출물:

- 100개 이상 eval question set
- answerability label
- refusal reason taxonomy
- reranker 또는 direct support checker

### Phase 10.5: Product Feature Expansion

목표:

- 구조화 데이터와 eligibility engine을 사용자 가치로 연결한다.

주요 산출물:

- 개인화 장학금 피드
- 탈락 사유 설명 강화
- 장학금 비교 API
- 제출서류 체크리스트

## 11. 배포 가능한 v1의 정의

이 프로젝트를 `배포 가능한 v1`이라고 부르려면 최소한 아래 기준은 만족해야 한다.

- production 환경변수로 API 서버가 실행된다.
- DB migration 절차가 고정되어 있다.
- raw storage가 container 재배포 후에도 보존된다.
- `/ready`가 DB와 필수 storage 상태를 확인한다.
- 공지 수집부터 RAG indexing까지 수동 command로 실행 가능하다.
- 실패한 pipeline run을 조회하고 재처리할 수 있다.
- secret이 repo와 image에 들어가지 않는다.
- 기본 smoke test가 배포 후 통과한다.
- 개인정보성 profile 입력이 로그에 남지 않는다.
- 장애 시 확인할 runbook이 있다.

## 12. 포트폴리오 표현 방향

약하게 보이는 표현:

```text
장학금 검색 기능과 챗봇을 구현했습니다.
```

더 나은 표현:

```text
비정형 장학 공지를 raw document, canonical block, structured rule, provenance anchor로 분해하고,
검색/RAG 응답과 deterministic eligibility 판정을 분리한 정보 시스템을 설계했습니다.
```

배포/운영 보강 후 표현:

```text
공지 수집부터 정규화, 규칙 추출, RAG indexing까지 이어지는 ETL 파이프라인을 scheduler와 run log 기반으로 운영화하고,
실패 추적, 데이터 품질 검증, 재처리 전략을 통해 배포 가능한 백엔드 서비스 구조로 확장했습니다.
```

면접 방어 질문:

- retrieval threshold는 어떤 데이터로 정했는가?
- 근거가 비슷하지만 답을 직접 지지하지 않는 경우를 어떻게 막는가?
- LLM 추출 결과가 원문 근거와 맞지 않으면 어떻게 처리하는가?
- 공지가 수정되었을 때 기존 판정 결과의 이력은 어떻게 보존하는가?
- pipeline 중간 단계가 실패하면 어디서부터 재처리하는가?
- raw storage가 유실되면 어떤 데이터까지 복구 가능한가?
- 개인정보성 profile 입력은 저장하는가, 저장하지 않는가?
- 운영 DB migration 실패 시 배포는 어떻게 중단하거나 복구하는가?
