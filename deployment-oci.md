# OCI 배포 계획

## 목적

이 문서는 `jbnu-scholarship-eligibility` 프로젝트를 Oracle Cloud Infrastructure(OCI)에 배포하기 위한 실행 기준을 정리한다.

현재 프로젝트는 FastAPI API 서버, PostgreSQL + pgvector, local raw storage, 배치성 수집/정규화/추출/RAG indexing 흐름을 가진다. 따라서 첫 배포 목표는 복잡한 Kubernetes 구성이 아니라, 운영 가능한 최소 구조를 안정적으로 만드는 것이다.

## 결론

초기 배포는 아래 구조를 권장한다.

```text
OCI Load Balancer or public HTTPS endpoint
    |
    v
OCI Compute VM
  - Docker Engine
  - API container
  - scheduler/worker container
  - optional self-hosted postgres container for demo only
    |
    +--> OCI Database with PostgreSQL or self-hosted PostgreSQL
    |
    +--> OCI Object Storage or attached Block Volume for raw files
    |
    +--> OCI Logging / Monitoring
```

추천 단계:

1. `Compute VM + Docker Compose + self-hosted PostgreSQL`로 데모 배포를 먼저 성공시킨다.
2. 운영성을 높일 때 `OCI Database with PostgreSQL`로 DB를 분리한다.
3. raw HTML/첨부파일은 장기적으로 `OCI Object Storage`로 옮긴다.
4. 트래픽이나 운영 복잡도가 커지면 `Container Instances` 또는 `OKE`를 검토한다.

이유:

- 현재 앱은 단일 Python monolith이고, Docker Compose 실행 경로가 이미 있다.
- 수집/정규화/인덱싱은 API 요청 처리와 분리해야 하지만, 초기에는 같은 VM에서 container만 분리해도 충분하다.
- OCI Compute는 VM 형태로 시작하기 쉽고, OCI Container Instances는 서버 관리 없이 container를 실행할 수 있지만 현재 프로젝트의 DB, raw storage, worker 분리를 먼저 정리해야 한다.
- OKE는 현재 단계에서는 운영 복잡도 대비 이득이 작다.

## OCI 서비스 매핑

| 프로젝트 요구 | OCI 후보 | 초기 선택 |
| --- | --- | --- |
| API 실행 | Compute VM, Container Instances, OKE | Compute VM |
| Docker image 저장 | OCI Container Registry | 필요 시 사용 |
| PostgreSQL | OCI Database with PostgreSQL, Compute 내부 Postgres | 운영은 managed PostgreSQL 권장 |
| raw HTML/첨부 저장 | Object Storage, Block Volume, File Storage | 초기 Block Volume, 장기 Object Storage |
| secret 관리 | Secret Management / Vault, instance env file | 운영은 Secret Management 권장 |
| 외부 HTTPS | Load Balancer, VM nginx/caddy | 초기 VM reverse proxy, 운영 Load Balancer |
| 로그 | OCI Logging, VM journald/docker logs | 운영은 OCI Logging |
| metric/alarm | OCI Monitoring | 운영 알림에 사용 |

## 배포 방식 선택

### 1안: Compute VM + Docker Compose

초기 권장안이다.

장점:

- 현재 `docker-compose.yml` 흐름을 가장 적게 바꾼다.
- API, PostgreSQL, worker를 같은 VM에서 빠르게 띄울 수 있다.
- 포트폴리오 데모와 비용 통제에 유리하다.

단점:

- VM patching, Docker daemon, disk 용량, backup을 직접 관리해야 한다.
- self-hosted PostgreSQL을 쓰면 DB 장애 대응과 백업 책임이 커진다.

적합한 상황:

- 첫 배포
- 포트폴리오 시연
- 트래픽이 작고 운영 자동화가 아직 부족한 단계

### 2안: Compute VM + Managed PostgreSQL

운영 v1 권장안이다.

장점:

- API runtime과 DB lifecycle을 분리한다.
- DB backup, sizing, 장애 대응을 관리형 서비스로 넘길 수 있다.
- API container를 재배포해도 DB 데이터가 유지된다.

단점:

- VCN, subnet, security list, DB 접속 정책을 더 신경 써야 한다.
- pgvector extension 지원 여부와 버전은 실제 생성 환경에서 반드시 확인해야 한다.

적합한 상황:

- 실제 사용자에게 공개
- DB 데이터 유실을 피해야 하는 경우
- 배포/재배포를 반복할 예정인 경우

### 3안: OCI Container Instances

컨테이너 실행만 보면 좋은 선택지지만, 현재 프로젝트에는 아직 선행 작업이 있다.

장점:

- 서버를 직접 관리하지 않고 container를 실행할 수 있다.
- 단순 API container 배포에는 Compute VM보다 운영 부담이 작을 수 있다.

단점:

- PostgreSQL, raw storage, migration, scheduler/worker 분리가 먼저 정리되어야 한다.
- Docker Compose로 묶인 현재 구조를 그대로 올리는 방식은 아니다.

적합한 상황:

- DB를 managed PostgreSQL로 분리한 뒤
- raw storage를 Object Storage로 옮긴 뒤
- API container와 worker container 실행 단위를 분리한 뒤

### 4안: OKE

현재 단계에서는 후순위다.

장점:

- 여러 replica, rolling deploy, service discovery, autoscaling을 체계적으로 다룰 수 있다.

단점:

- 클러스터 운영, ingress, secret, volume, observability 설정 부담이 크다.
- 현재 단일 서비스 규모에서는 포트폴리오 핵심보다 운영 복잡도가 먼저 커질 수 있다.

적합한 상황:

- API replica가 여러 개 필요할 때
- worker/scheduler/job이 많아질 때
- 배포 자동화와 관측 가능성이 이미 어느 정도 갖춰졌을 때

## 목표 아키텍처

### 데모 배포

```text
Internet
  |
  v
OCI Compute VM public IP
  |
  +-- reverse proxy :80/:443
  |
  +-- api container :8000
  |
  +-- postgres container :5432
  |
  +-- docker volume: postgres-data
  |
  +-- mounted path: /srv/jbnu/data/raw
```

특징:

- 빠르게 배포할 수 있다.
- 장애 복구와 백업은 약하다.
- 외부 공개 전에는 방화벽, HTTPS, secret, backup을 반드시 보강해야 한다.

### 운영 v1 배포

```text
Internet
  |
  v
OCI Load Balancer / HTTPS
  |
  v
private subnet
  |
  +-- API Compute VM or Container Instance
  |
  +-- Worker/Scheduler Compute VM or Container Instance
  |
  +-- OCI Database with PostgreSQL
  |
  +-- OCI Object Storage bucket for raw files
  |
  +-- OCI Logging / Monitoring / Alarms
```

특징:

- API runtime, DB, raw storage 책임이 분리된다.
- 배포/재배포 시 데이터 유실 가능성이 줄어든다.
- 운영 관측성과 장애 대응이 가능해진다.

## 배포 전 코드/설정 보완

### 1. production Dockerfile 정리

현재 `docker/Dockerfile`은 `pip install .[dev]`를 사용한다. 운영 image에서는 dev dependency를 빼야 한다.

필요한 변경:

- production stage에서는 `pip install .` 사용
- non-root user 추가
- `COPY . /app` 범위 최소화
- `.dockerignore` 추가
- `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1` 유지

완료 기준:

- 테스트 도구가 production image에 들어가지 않는다.
- container가 root 권한으로 실행되지 않는다.

### 2. production compose 분리

현재 `docker-compose.yml`은 개발용이다.

문제:

- `uvicorn --reload` 사용
- source 전체를 volume mount
- DB password가 compose에 직접 들어감
- API와 DB가 같은 compose에 묶임

추가할 것:

- `docker-compose.prod.yml`
- API command에서 `--reload` 제거
- `.env.production` 또는 OCI secret 주입 기준 정리
- raw storage mount 경로 고정
- API container와 worker container 분리

### 3. Alembic migration 실행 경로

배포 절차에 아래 단계를 고정한다.

```bash
alembic upgrade head
```

현재 `alembic.ini`에는 기본 DB URL이 들어 있으므로, 운영에서는 `JBNU_DATABASE_URL` 또는 별도 env 기반 override가 실제로 적용되는지 확인해야 한다.

완료 기준:

- 빈 운영 DB에서 migration만으로 schema가 만들어진다.
- 배포 전 migration smoke test를 실행한다.
- migration 실패 시 API container를 새 버전으로 올리지 않는다.

### 4. raw storage 외부화

현재 `JBNU_RAW_STORAGE_PATH`는 local filesystem 경로다.

초기 선택:

```text
JBNU_RAW_STORAGE_PATH=/srv/jbnu/data/raw
```

운영 선택:

- Object Storage adapter 추가
- 또는 Compute VM에 Block Volume mount

완료 기준:

- container 재생성 후에도 raw HTML/첨부 원본이 남아 있다.
- backup/restore 절차가 있다.
- raw file path가 container 내부 임시 filesystem에만 의존하지 않는다.

### 5. readiness 강화

현재 `/ready`는 DB 상태만 확인한다.

추가할 것:

- raw storage write/read 가능 여부
- embedding provider가 real mode일 때 timeout-safe health check
- DB migration version 확인
- optional: recent pipeline success timestamp

완료 기준:

- Load Balancer health check가 `/ready`를 보고 unhealthy instance를 제외할 수 있다.

### 6. scheduler/worker 분리

현재 수집/정규화/추출/RAG indexing은 운영형 job으로 닫혀 있지 않다.

추가할 것:

- `scripts/run_pipeline.py`
- `scripts/rebuild_rag_index.py`
- `worker` 또는 `scheduler` container
- 중복 실행 방지 lock
- pipeline run log

완료 기준:

- API container는 사용자 요청만 처리한다.
- ETL성 작업은 worker/scheduler container에서 실행한다.

## OCI 리소스 준비 체크리스트

### Compartment / IAM

- 프로젝트용 compartment 생성
- 배포 사용자 또는 group 생성
- Compute, Network, Object Storage, Container Registry, Database, Logging, Monitoring 권한 분리
- production secret 접근 권한 최소화

### Network

- VCN 생성
- public subnet: Load Balancer 또는 bastion
- private subnet: API/worker/DB
- Internet Gateway 또는 NAT Gateway 구성
- Service Gateway 구성 검토
- Security List 또는 Network Security Group 설정

권장 공개 포트:

- `80`, `443`: reverse proxy 또는 Load Balancer
- `22`: 관리자 IP에서만 SSH 허용
- `8000`: 외부 직접 공개 금지, reverse proxy 내부에서만 접근
- `5432`: 외부 공개 금지

### Compute

- Ubuntu 또는 Oracle Linux VM 생성
- Docker Engine 설치
- project directory 배치
- `/srv/jbnu/data/raw` 같은 영속 경로 생성
- systemd로 compose 자동 시작 설정

### Database

선택지:

- 데모: compose의 PostgreSQL container
- 운영: OCI Database with PostgreSQL

확인할 것:

- PostgreSQL version
- pgvector extension 사용 가능 여부
- backup 정책
- private endpoint 접속
- application user 권한

### Object Storage

운영에서 raw file을 Object Storage로 옮길 경우:

- bucket 생성
- lifecycle policy 검토
- write/read IAM policy 설정
- private access를 위해 Service Gateway 검토
- object key naming 정책 정리

### Container Registry

image를 OCI Container Registry에 둘 경우:

- repository 생성
- Docker login용 auth token 준비
- image tag 규칙 설정
- `latest`만 쓰지 않고 release tag 사용

예시 tag:

```text
jbnu-scholarship-api:2026-06-24-001
jbnu-scholarship-worker:2026-06-24-001
```

### Logging / Monitoring

추가할 것:

- API access/error log 수집
- worker pipeline log 수집
- Load Balancer access log
- DB metric 확인
- CPU/memory/disk alarm
- `/ready` 실패 alarm
- pipeline 연속 실패 alarm

## 환경변수 기준

운영 환경변수 예시:

```dotenv
JBNU_APP_NAME=JBNU Scholarship Regulation Search & Eligibility Decision System
JBNU_ENV=production
JBNU_LOG_LEVEL=INFO
JBNU_API_PREFIX=/api/v1
JBNU_DATABASE_URL=postgresql+psycopg://APP_USER:APP_PASSWORD@DB_HOST:5432/jbnu_scholarship
JBNU_RAW_STORAGE_PATH=/srv/jbnu/data/raw
JBNU_EXTRACTOR_MODE=hybrid
JBNU_LLM_PROVIDER=openai_compatible
JBNU_LLM_API_BASE_URL=https://api.openai.com/v1
JBNU_LLM_API_KEY=<secret>
JBNU_LLM_MODEL=gpt-4.1-mini
JBNU_LLM_TIMEOUT_SECONDS=30
JBNU_LLM_RETRY_ATTEMPTS=2
JBNU_LLM_MAX_CONTEXT_CHARACTERS=6000
JBNU_EMBEDDING_PROVIDER=openai_compatible
JBNU_EMBEDDING_API_BASE_URL=https://api.openai.com/v1
JBNU_EMBEDDING_API_KEY=<secret>
JBNU_EMBEDDING_MODEL=text-embedding-3-small
JBNU_EMBEDDING_TIMEOUT_SECONDS=30
```

주의:

- `.env` 파일은 repo에 커밋하지 않는다.
- LLM/embedding API key는 OCI Secret Management 또는 배포 플랫폼 secret으로 관리한다.
- profile request body는 로그에 남기지 않는다.

## 배포 절차

### 1. OCI 기본 리소스 생성

```text
1. compartment 생성
2. VCN/subnet/security rule 생성
3. Compute VM 생성
4. optional: OCI Database with PostgreSQL 생성
5. optional: Object Storage bucket 생성
6. optional: Container Registry repository 생성
```

### 2. VM bootstrap

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
sudo mkdir -p /srv/jbnu/data/raw
sudo chown -R $USER:$USER /srv/jbnu
```

Oracle Linux를 쓰면 package manager 명령은 `dnf` 기준으로 바꾼다.

### 3. application 배포

```bash
git clone <repo-url>
cd jbnu-scholarship-eligibility
cp .env.example .env.production
vi .env.production
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

현재 repo에는 아직 `docker-compose.prod.yml`이 없으므로 먼저 추가해야 한다.

### 4. DB migration

```bash
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

또는 release job에서 migration container를 일회성으로 실행한다.

### 5. smoke test

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
curl -fsS "http://localhost:8000/api/v1/scholarships/open?limit=1"
```

외부 공개 후:

```bash
curl -fsS https://<domain>/health
curl -fsS https://<domain>/ready
```

### 6. pipeline bootstrap

아직 운영형 pipeline command가 없으므로, 배포 전 아래를 구현해야 한다.

```bash
python scripts/run_pipeline.py --mode full
python scripts/rebuild_rag_index.py --all
```

현재 있는 smoke script는 검증용으로 유지하고, 운영 pipeline script는 별도로 둔다.

## HTTPS / Domain

초기:

- VM에 Caddy 또는 Nginx 배치
- `80 -> 443` redirect
- reverse proxy가 `127.0.0.1:8000`으로 전달

운영:

- OCI Load Balancer에서 TLS termination
- backend health check는 `/ready`
- API VM은 private subnet에 배치

## Backup / Restore

### DB

필수:

- daily backup
- 배포 전 manual backup
- restore rehearsal

self-hosted PostgreSQL을 쓸 경우:

```bash
pg_dump
```

managed PostgreSQL을 쓸 경우:

- OCI backup 기능 사용
- backup retention 정책 설정

### Raw Storage

Block Volume 사용 시:

- volume backup 정책 설정
- Object Storage로 주기적 복사 검토

Object Storage 사용 시:

- lifecycle policy
- retention policy
- bucket replication 필요 여부 검토

## 장애 대응 Runbook

### API가 내려간 경우

확인 순서:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs api --tail=200
curl -v http://localhost:8000/ready
```

확인 지점:

- container restart loop
- DB 접속 실패
- env 누락
- raw storage permission 문제

### DB migration 실패

조치:

- 새 API 버전 rollout 중단
- migration error log 확인
- backup에서 restore 가능 여부 확인
- destructive migration이면 수동 검토

### pipeline 실패

조치:

- pipeline run log 확인
- 실패 단계가 collection, normalization, extraction, indexing 중 어디인지 확인
- 외부 dependency 실패면 retry
- deterministic transform 실패면 raw input과 parser를 확인

### LLM/embedding provider 장애

조치:

- extractor mode를 `heuristic`으로 낮춰 API 핵심 기능 유지
- RAG indexing은 provider 복구 후 재실행
- 사용자-facing `/ask`는 no-evidence 또는 provider failure 사유를 구분해 반환

## 배포 전 구현 TODO

우선순위 높은 순서:

1. `docker-compose.prod.yml` 추가
2. production Dockerfile에서 dev dependency 제거
3. non-root container 실행
4. `.dockerignore` 추가
5. `alembic upgrade head`가 운영 DB URL을 확실히 사용하도록 정리
6. `/ready`에 raw storage check 추가
7. pipeline 실행 script 추가
8. API container와 worker/scheduler container 분리
9. pipeline run log table 추가
10. deployment smoke script 추가
11. OCI Object Storage adapter 검토
12. Logging/Monitoring alarm 기준 문서화

## 배포 가능한 OCI v1 기준

아래가 충족되면 `OCI에 배포 가능한 v1`로 볼 수 있다.

- OCI Compute VM에서 production compose로 API가 실행된다.
- `/health`, `/ready`가 외부 또는 Load Balancer에서 통과한다.
- DB migration이 배포 절차에 포함된다.
- PostgreSQL 데이터와 raw storage가 container 재생성 후에도 유지된다.
- secret이 repo와 Docker image에 포함되지 않는다.
- API port 8000과 DB port 5432가 외부에 직접 노출되지 않는다.
- HTTPS가 적용된다.
- 배포 후 smoke test가 문서화되어 있다.
- pipeline을 수동으로 실행하고 실패 로그를 확인할 수 있다.
- 최소 DB backup/restore 절차가 있다.

## OCI 공식 문서 참고

- OCI Compute: https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm
- OCI Container Instances: https://docs.oracle.com/en-us/iaas/Content/container-instances/home.htm
- OCI Database with PostgreSQL: https://docs.oracle.com/en-us/iaas/Content/postgresql/home.htm
- OCI Container Registry: https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm
- OCI Object Storage: https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm
- OCI Load Balancer: https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/balanceoverview.htm
- OCI Key Management / Vault: https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Concepts/keyoverview.htm
- OCI Logging: https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm
- OCI Monitoring: https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm
