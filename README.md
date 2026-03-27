# JBNU Scholarship Regulation Search & Eligibility Decision System

전북대학교 장학 공지를 자동 수집하고, 원문을 보존형으로 정규화한 뒤, 구조화 규정과 deterministic engine으로 검색과 지원 가능 여부를 제공하는 시스템이다.

## Why This Project Exists
전북대학교 장학 공지는 게시판, HTML 본문, PDF/HWP 첨부로 분산되어 있고 기준도 비정형 문장으로 흩어져 있다. 학생은 여러 공고를 직접 읽으면서 학점, 학년, 학적, 소득분위를 대조해야 하고, 기준이 모호하면 판단이 어렵다.

이 프로젝트는 그 문제를 아래 방식으로 바꾼다.
- 공식 공지를 자동 수집한다.
- 원문 HTML과 attachment를 그대로 보존한다.
- 검색 가능한 canonical document와 판정 가능한 structured rule을 분리 저장한다.
- provenance가 포함된 근거 기반 검색 결과를 제공한다.
- 최종 eligibility는 코드 기반 엔진이 `eligible`, `ineligible`, `expired`, `insufficient_info`로 판정한다.

## What This Project Does
- 전북대학교 공식 게시판 공지를 수집한다.
- HTML 본문과 PDF/HWP attachment를 raw 파일로 저장한다.
- notice/attachment를 canonical block 구조로 정규화한다.
- 장학명, 평점, 소득분위, 학년, 학적, 제출서류를 structured rule JSON으로 추출한다.
- search API와 open scholarship API를 제공한다.
- student profile 기반 eligibility API와 explanation 응답을 제공한다.

## Why This Is Not a Simple Chatbot
- 단순 문서 chunk 검색이 아니라 `원문 저장 + 구조화 규정 + 판정 엔진` 구조를 사용한다.
- raw document, canonical document, structured rule, provenance를 분리 저장한다.
- 최종 지원 가능 여부는 LLM이 아니라 deterministic code가 판정한다.
- explanation도 provenance와 condition diagnostics를 기준으로 만든다.

## High-Level Architecture
```text
[JBNU Boards]
    |
    v
[Collectors / Parsers]
    |
    v
[Raw Storage]
  - notice HTML
  - attachment bytes
    |
    v
[Normalizers]
  -> canonical documents
    |
    v
[Rule Extractor]
  -> scholarship rules
  -> provenance anchors
    |
    v
[Search Read Model]
  -> search API
  -> open scholarship API
    |
    v
[Eligibility Engine]
  -> eligibility API
```

아키텍처 상세 문서는 [docs/system-architecture.md](docs/system-architecture.md)에 정리되어 있다.

## How It Works
### 1. Collection
- JBNU 본부/K2Web 게시판에서 장학 관련 공지를 찾는다.
- notice metadata와 attachment metadata를 DB에 저장한다.

### 2. Raw Preservation
- notice 상세 HTML을 raw 파일로 보관한다.
- attachment 원본 bytes를 파일로 보관한다.

### 3. Normalization
- raw HTML을 canonical block 구조로 변환한다.
- PDF/HWP/text attachment를 canonical document로 변환한다.

### 4. Rule Extraction
- canonical document에서 장학 조건을 heuristic rule로 추출한다.
- 추출된 값마다 provenance anchor를 만든다.

### 5. Search
- published rule을 notice/provenance와 함께 읽어 search read model을 만든다.
- 후보 탐색 단계에서는 provenance를 지연 로딩하고, 최종 응답 item에만 hydrate한다.
- lexical scoring으로 검색 결과를 정렬한다.
- 현재 신청 가능한 공고 목록을 계산한다.

### 6. Eligibility
- student profile과 structured qualification JSON을 직접 비교한다.
- decision과 explanation, condition diagnostics를 함께 반환한다.

## Runtime Shape
- Application style: Python monolith + FastAPI
- API layer: FastAPI routers
- Domain / orchestration layer: services
- Persistence layer: SQLAlchemy repositories + Alembic migrations
- Raw storage layer: local filesystem adapter
- Data store:
  - PostgreSQL 16 + pgvector가 기본 운영 스택
  - SQLite는 테스트와 로컬 단순 검증에 사용

## Core Components
- Collectors: `app/collectors/`
- Storage: `app/storage/`
- Normalizers: `app/normalizers/`
- Extractors: `app/extractors/`
- Services: `app/services/`
- API routers: `app/api/routers/`
- ORM models: `app/models/`
- Repositories: `app/repositories/`
- Schemas: `app/schemas/`

## Tech Stack
### Core / API
- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic

### Collection / Parsing
- requests / httpx
- BeautifulSoup4
- pypdf
- olefile

### Storage / Search
- PostgreSQL 16
- pgvector
- local filesystem raw storage

### Testing / Tooling
- pytest
- Docker Compose
- Uvicorn

기술 스택 상세 선택 이유는 [docs/tech-stack.md](docs/tech-stack.md)에 정리되어 있다.

## API Overview
- `GET /health`
- `GET /ready`
- `GET /api/v1/scholarships/search?query=장학금`
- `GET /api/v1/scholarships/open`
- `POST /api/v1/scholarships/eligibility`

## Measured Performance
- synthetic benchmark dataset `1,500 rules / 12,000 provenance anchors` 기준
- `GET /api/v1/scholarships/search`에서 provenance eager assembly를 제거하고 최종 응답에만 hydrate하도록 변경
- 같은 k6 시나리오에서 `p95 12.66s -> 5.07s`, `avg 11.13s -> 4.20s`, `throughput 0.876 req/s -> 2.331 req/s`

상세 측정 방법과 결과는 [docs/performance-benchmark.md](docs/performance-benchmark.md)에 정리되어 있다.

## Quick Start
### Docker Compose
```bash
cp .env.example .env
docker compose up --build
```

실행 후:
- API base: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- PostgreSQL: `localhost:54329`

### Local Development
```bash
python3 -m pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

### Run Tests
```bash
pytest
```

## Configuration
기본 환경 변수는 [.env.example](.env.example)에 있다.

- `JBNU_APP_NAME`
- `JBNU_ENV`
- `JBNU_LOG_LEVEL`
- `JBNU_API_PREFIX`
- `JBNU_DATABASE_URL`
- `JBNU_RAW_STORAGE_PATH`

## Current Implementation Status
- Phase 1.x: 요구사항, 앱 골격, Docker Compose, PostgreSQL + pgvector 준비
- Phase 2.x: domain model, migration, repository
- Phase 3.x: collector
- Phase 4.x: raw storage, HTML/PDF/HWP normalization
- Phase 5.x: structured rule extraction, provenance persistence
- Phase 6.x: search/open scholarship APIs
- Phase 7.x: eligibility engine, explanation builder, eligibility API

진행 이력은 [docs/implementation-plan.md](docs/implementation-plan.md)과 각 `docs/phase-n.x.md` 문서에 남겨두었다.

## Strengths
- 수집부터 판정 API까지 end-to-end 흐름이 구현되어 있다.
- HTML/PDF/HWP를 같은 canonical document 계층으로 수렴시켰다.
- search와 eligibility가 같은 structured rule 계층을 재사용한다.
- provenance anchor를 통해 결과 근거를 추적할 수 있다.

## Current Limits
- search는 아직 semantic embedding 없이 lexical scoring 중심이다.
- rule extractor는 heuristic 기반이라 복수 규정 공지와 예외 조항 표현력이 제한적이다.
- eligibility qualification schema는 현재 핵심 필드 중심이다.

## Repository Layout
```text
app/       FastAPI app and domain modules
alembic/   migration definitions
docs/      requirements, architecture, phase logs, portfolio notes
docker/    Dockerfile and PostgreSQL init scripts
perf/      benchmark seed data and k6 scenarios
tests/     unit and integration tests
gs/        job/application reference materials kept outside product scope
```

## Documentation Map
- Overview: [docs/project-overview.md](docs/project-overview.md)
- Requirements: [docs/requirements-analysis.md](docs/requirements-analysis.md)
- System architecture: [docs/system-architecture.md](docs/system-architecture.md)
- Performance benchmark: [docs/performance-benchmark.md](docs/performance-benchmark.md)
- Tech stack: [docs/tech-stack.md](docs/tech-stack.md)
- Phase logs: [docs/phase-1.0.md](docs/phase-1.0.md) ~ [docs/phase-7.1.md](docs/phase-7.1.md)
