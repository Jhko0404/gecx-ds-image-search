# GECX Layout Parser Data Store 연동 가이드 (Claude Code 지침)

이 프로젝트는 CXAS(Vertex AI Conversation / Agent Studio)에서 Layout Parser 형식의 비정형 데이터스토어를 검색할 때 발생하는 빈 응답(`response: {}`) 문제를 해결하기 위한 Cloud Run 프록시 검색 API입니다.

---

## 🛠️ 주요 프로젝트 구성 및 구조

- `main.py`: Discovery Engine Search REST API와 통신하여 `extractive_segments`를 추출 및 가공해 반환하는 Flask API 서버.
- `requirements.txt`: Flask, requests, google-auth, gunicorn 등 의존성.
- `Dockerfile`: Cloud Run 배포용 컨테이너 이미지 빌드 파일.
- `openapi.yaml`: CXAS Tools에 등록하기 위한 OpenAPI 3.0 명세 파일.
- `.env.example` / `.env`: GCP 프로젝트 ID, 리전, 데이터스토어 ID 등 환경변수 설정 파일.
- `scripts/check_env.sh`: GCP 로그인, 활성 프로젝트, 필수 API, 환경변수 자동 검증 스크립트.
- `scripts/deploy.sh`: Cloud Run 자동 배포, IAM 권한 자동 설정, `openapi.yaml` URL 자동 갱신 스크립트.
- `scripts/test_search.sh`: 배포된 Cloud Run 검색 엔드포인트 E2E 테스트 스크립트 (인증 토큰 자동 주입).

---

## 🤖 Claude Code 실행 워크플로우 지침

사용자가 배포, 점검, 테스트를 요청할 때 아래 단계에 따라 대화형으로 안내하고 작업을 수행하세요.

### 1단계: 환경 점검 (`check_env.sh`)
- 사용자가 "환경 설정해줘", "배포 준비해줘", 또는 "배포해줘"라고 요청하면 먼저 `./scripts/check_env.sh`를 실행합니다.
- 만약 `.env` 파일에 `DATASTORE_ID` 또는 `PROJECT_ID`가 비어있다면, 사용자에게 해당 정보를 확인하여 `.env`에 입력하도록 돕습니다.
  - 데이터스토어 ID 목록 확인 팁: `gcloud discovery-engine data-stores list` 또는 Vertex AI Search 콘솔 안내.

### 2단계: Cloud Run 배포 (`deploy.sh`)
- 환경 검증이 완료되면 `./scripts/deploy.sh`를 실행합니다.
- 이 스크립트는 다음 작업을 자동으로 처리합니다:
  1. Cloud Run에 비공개(`--no-allow-unauthenticated`) 모드로 소스 배포
  2. Cloud Run 서비스 계정에 `roles/discoveryengine.admin` 부여
  3. GECX 서비스 에이전트(`service-[PROJECT_NUMBER]@gcp-sa-ces.iam.gserviceaccount.com`)에 `roles/run.invoker` 부여
  4. 테스트 사용자에게 `roles/run.invoker` 부여
  5. 배포된 URL을 `openapi.yaml` 파일에 자동 반영

### 3단계: 엔드투엔드 테스트 (`test_search.sh`)
- 배포가 완료되면 `./scripts/test_search.sh "검색어"`를 실행하여 실제 데이터스토어에서 텍스트 및 이미지 링크가 정상 조회되는지 확인합니다.

### 4단계: CXAS 연동 안내
- 테스트가 성공하면 사용자에게 다음 단계를 안내합니다:
  1. CXAS 콘솔 > Tools > '+' 버튼 > **OpenAPI** 선택
  2. 툴 이름을 `custom_layout_search`로 지정하고 갱신된 `openapi.yaml` 내용을 붙여넣기
  3. 에이전트 인스트럭션에 서브태스크(지침서) 반영 및 이미지 마크다운 출력 설정

---

## ⚡ 빠른 명령어 요약

```bash
# 1. 가상환경 활성화 (필요시)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 환경 사전 검증
./scripts/check_env.sh

# 3. Cloud Run 배포 및 IAM 설정
./scripts/deploy.sh

# 4. 배포 후 E2E 검색 테스트
./scripts/test_search.sh "필터"
```
