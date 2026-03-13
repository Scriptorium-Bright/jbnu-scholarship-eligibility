# JBNU Scholarship Regulation Search & Eligibility Decision System

전북대학교 장학 관련 공지를 수집하고, 원문을 보존형으로 정규화한 뒤, 코드 기반 규칙 엔진으로 지원 가능 여부를 판정하는 시스템이다.

## What This Project Does
- 전북대학교 공식 게시판 공지를 수집한다.
- HTML 본문과 PDF 첨부를 원문 그대로 저장한다.
- 문서를 canonical block 구조로 정규화한다.
- 장학 규정을 구조화 JSON으로 추출한다.
- 검색과 deterministic eligibility 판정을 통해 근거 기반 응답을 제공한다.

## Why This Is Not a Simple Chatbot
- 단순 문서 chunk 검색이 아니라 `문서 인덱스 + 규정 테이블 + 판정 엔진` 구조를 사용한다.
- LLM은 규정 추출과 설명 문장 정리에만 관여한다.
- 최종 지원 가능 여부는 코드 기반 엔진이 `eligible`, `ineligible`, `expired`, `insufficient_info`로 판정한다.
- provenance가 없는 값은 신뢰하지 않는다.

## Target Users
- 장학금 지원 가능 여부를 빠르게 확인하려는 전북대학교 학생
- 장학 공고와 기준을 추적 가능한 구조로 관리하려는 학과/행정 담당자
- 공고 수집, 구조화, 판정 파이프라인을 재현 가능한 형태로 검증하려는 개발자

## Current Scope
- Phase 1.0: 요구사항 분석과 문서 구조 확정
- Phase 1.1: FastAPI, SQLAlchemy, Alembic, pytest 기반 골격 구성
- Phase 1.2: Docker Compose 기반 로컬 실행 환경과 PostgreSQL + pgvector 연결 준비

## Quick Start
```bash
cp .env.example .env
docker compose up --build
```

기본 API:
- `GET /health`
- `GET /ready`

## Repository Layout
```text
app/       FastAPI app and core modules
alembic/   migration skeleton
docs/      requirements, architecture, phase logs, portfolio notes
docker/    Dockerfile and PostgreSQL init scripts
tests/     unit and integration tests
```
