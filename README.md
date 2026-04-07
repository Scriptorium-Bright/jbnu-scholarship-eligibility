# Scholarship Search & Eligibility System

장학 공지를 자동으로 모으고, 흩어진 지원 조건을 읽기 쉬운 형태로 정리한 뒤, 검색과 AI 질의응답, 지원 가능 여부 확인까지 제공하는 백엔드 시스템입니다.

핵심은 단순히 "장학 공지를 보여주는 서비스"가 아니라, 사람이 여러 공지를 직접 읽고 비교해야 하던 문제를 `검색 가능한 정보`와 `판단 가능한 기준`으로 나눠 다룬 점입니다.

## 한눈에 보기

- 전북대 장학 공지를 자동 수집합니다.
- 게시판 본문과 첨부 PDF/HWP를 함께 보관합니다.
- 장학 조건을 구조화해 검색과 판정에 재사용합니다.
- 질문에 대해 근거가 있는 답변만 하도록 설계했습니다.
- 최종 지원 가능 여부는 AI가 아니라 규칙 기반 로직으로 판정합니다.

## 어떤 문제를 풀었나

장학 공지는 보통 이런 식으로 흩어져 있습니다.

- 게시판 본문에 일부 조건이 적혀 있음
- PDF나 HWP 첨부에 더 중요한 기준이 들어 있음
- 같은 의미도 공지마다 표현이 다름
- 사용자는 학점, 학년, 학적, 소득분위를 직접 대조해야 함

그래서 단순 키워드 검색만으로는 아래 질문에 답하기 어렵습니다.

- "지금 신청 가능한 장학금이 뭐지?"
- "이 장학금은 학점 기준이 어떻게 되지?"
- "나는 지원 가능할까?"

이 프로젝트는 그 문제를 `공식 원문 수집 -> 문서 정리 -> 조건 구조화 -> 검색/질의응답 -> 규칙 기반 판정` 흐름으로 바꿉니다.

## 무엇을 만들었나

### 1. 공지 수집

- 장학 관련 게시글과 첨부파일을 자동으로 수집합니다.
- 게시글 본문 HTML과 첨부 원문 파일을 함께 저장합니다.

### 2. 문서 정리

- HTML, PDF, HWP처럼 형식이 다른 문서를 같은 형태의 텍스트로 정리합니다.
- 이후 검색과 AI 처리에 쓸 수 있도록 문단 단위로 나눕니다.

### 3. 지원 조건 구조화

- 장학명, 평점 기준, 소득분위, 학년, 학적, 제출서류 같은 조건을 정해진 형식으로 추출합니다.
- 규칙 기반 방식과 LLM 기반 방식을 모두 비교할 수 있게 만들었습니다.

### 4. 검색과 질문 응답

- 사용자는 장학금을 검색할 수 있습니다.
- 자연어 질문을 하면, 공식 공지에서 찾은 근거를 바탕으로 답변과 출처를 함께 반환합니다.

### 5. 지원 가능 여부 판정

- 사용자의 프로필을 입력하면, 장학 조건과 직접 비교해 지원 가능 여부를 반환합니다.
- 이 단계는 AI가 아니라 코드 기반 규칙 엔진이 처리합니다.

## 왜 단순 챗봇이 아닌가

이 프로젝트는 AI에게 모든 판단을 맡기지 않습니다.

- AI는 문서를 읽기 쉬운 형태로 정리하거나, 공식 공지를 바탕으로 답변하는 데 사용합니다.
- 최종 지원 가능 여부는 같은 입력에 같은 결과가 나와야 하므로 규칙 기반으로 분리했습니다.
- 근거가 부족하면 답을 지어내지 않고, 답변을 거절하도록 설계했습니다.

즉 "그럴듯한 답변"보다 `근거`, `재현 가능성`, `설명 가능성`을 더 중요하게 본 구조입니다.

## 구조를 쉽게 설명하면

```text
[학교 장학 공지]
    |
    v
[공지 본문 / 첨부파일 수집]
    |
    v
[형식이 다른 문서를 같은 텍스트 형태로 정리]
    |
    v
[장학 조건 추출]
    |
    +-------------------+
    |                   |
    v                   v
[검색 / 질문 응답]   [지원 가능 여부 판정]
```

조금 더 자세히 보면 아래와 같습니다.

```text
[JBNU Notice Boards]
    |
    v
[Collectors / Parsers]
    |
    v
[Raw Source Storage]
  - notice HTML
  - attachment files
    |
    v
[Document Normalization]
  - unified text documents
  - paragraph-level chunks
    |
    v
[Rule Extraction]
  - scholarship requirements
  - evidence locations
    |
    +----------------------+
    |                      |
    v                      v
[Search / Ask]        [Eligibility Engine]
  - search API          - deterministic decision
  - grounded answer     - explanation
```

## 신뢰성을 위해 어떤 선택을 했나

### 공식 원문을 먼저 저장

나중에 정리 로직이나 추출 로직이 바뀌어도, 다시 수집하지 않고 같은 원문으로 재처리할 수 있게 했습니다.

### AI 출력은 그대로 믿지 않음

- LLM 기반 추출은 정해진 형식의 결과를 내도록 만들었습니다.
- 원문 근거와 연결되지 않거나 호출이 실패하면 규칙 기반 추출로 되돌아가도록 만들었습니다.

### 질문 응답과 최종 판정을 분리

- 질문 응답은 공식 공지를 바탕으로 답변과 출처를 제공합니다.
- 최종 자격 판정은 별도 규칙 엔진으로 처리합니다.

### 근거가 없으면 답하지 않음

RAG의 핵심은 "무조건 답하는 것"이 아니라, 공식 공지에서 근거를 찾지 못하면 답변을 거절하는 것입니다.

## 주요 결과

### 1. 장학 조건 추출 정확도 개선

사전 정의한 테스트 공지 `4건`을 기준으로 비교한 결과:

- 규칙 기반 추출 정확도: `54.17%`
- LLM 단독 추출 정확도: `50.00%`
- hybrid 추출 정확도: `79.17%`
- fallback recovery: `100.00%`

해석:

- LLM을 무조건 신뢰하지 않고, 검증과 fallback을 함께 붙인 hybrid 방식이 가장 안정적이었습니다.

### 2. 근거 기반 질문 응답 검증

사전 정의한 질문 `4건` 기준:

- groundedness: `100.00%`
- citation coverage: `100.00%`
- refusal precision: `100.00%`

해석:

- 근거가 있는 질문에는 출처와 함께 답했고
- 근거가 없거나 최종 자격 판정이 필요한 질문은 안전하게 거절하거나 별도 판정 경로로 넘겼습니다.

### 3. 검색 성능 개선

synthetic benchmark `1,500 rules / 12,000 evidence records` 기준:

- p95: `12.66s -> 5.07s`
- avg: `11.13s -> 4.20s`
- throughput: `0.876 req/s -> 2.331 req/s`

해석:

- 검색 후보 전체에 근거를 미리 붙이던 구조를 바꾸고, 최종 결과에만 근거를 붙이도록 변경해 응답 속도를 줄였습니다.

## API

- `GET /health`
- `GET /ready`
- `GET /api/v1/scholarships/search?query=장학금`
- `GET /api/v1/scholarships/open`
- `POST /api/v1/scholarships/ask`
- `POST /api/v1/scholarships/eligibility`

## 기술 스택

### Backend

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
- local filesystem storage

### Testing / Tooling

- pytest
- Docker Compose
- Uvicorn

## 실행 방법

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

### Test

```bash
pytest
```

## 이 프로젝트의 강점

- 공지 수집부터 질문 응답, 최종 판정까지 한 흐름으로 이어집니다.
- 형식이 다른 문서를 같은 방식으로 다룰 수 있게 정리했습니다.
- AI를 쓰되, 최종 판정은 규칙 로직으로 분리해 신뢰성을 높였습니다.
- 질문 응답은 공식 공지를 근거로만 하도록 설계했습니다.
- 성능, 품질, fallback까지 함께 측정할 수 있는 구조를 만들었습니다.

## 현재 한계

- 검색 API 전체는 아직 키워드 검색 중심이며, 의미 기반 검색은 질문 응답 경로에 먼저 적용되어 있습니다.
- 추출과 질문 응답 평가는 현재 사전 정의한 테스트 데이터와 fake provider 기준입니다.
- 지원 조건 스키마는 현재 핵심 필드 중심입니다.

## 앞으로 더 확장할 수 있는 방향

- 질문 유형을 먼저 분기하는 오케스트레이션 계층 추가
- 누락된 정보를 되묻는 대화형 eligibility 흐름 추가
- 의미가 비슷한 질문을 빠르게 처리하는 semantic cache 추가
- 라우팅, 캐시, 대화 흐름에 대한 평가와 trace 보강

## 요약

이 프로젝트의 핵심은 장학 공지를 단순히 모아 보여주는 것이 아니라, 비정형 공지를 `검색 가능한 정보`, `근거 기반 답변`, `규칙 기반 판정`으로 나눠 신뢰할 수 있는 서비스 흐름으로 바꾼 점입니다.
