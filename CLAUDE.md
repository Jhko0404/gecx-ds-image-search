# GECX Layout Parser Data Store 연동 가이드 (Claude Code 지침서)

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

## 🤖 Claude Code 대화형 실행 가이드라인 (반드시 준수)

사용자가 "배포해줘", "시작해줘", "환경 설정해줘" 등의 요청을 하면, 아래 워크플로우에 따라 대화형으로 친절하게 진행하세요.

### 1단계: 환경 및 필수 정보 확인 (대화형 인터뷰)
1. `./scripts/check_env.sh`를 실행하여 `gcloud` 로그인 계정과 활성 프로젝트를 확인합니다.
2. 만약 `.env` 파일에 `DATASTORE_ID`가 비어있다면, **사용자에게 직접 대화형으로 물어보세요**:
   > *"연동할 Vertex AI Search의 **데이터스토어 ID(DATASTORE_ID)**를 알려주시면 `.env`에 설정하고 배포를 진행하겠습니다. (잘 모르실 경우 콘솔의 'Vertex AI Search > Data Stores' 메뉴에서 확인하시거나, 제가 목록 조회를 시도해 드릴 수 있습니다.)"*
3. 사용자가 데이터스토어 ID를 알려주면 `.env` 파일에 즉시 업데이트합니다.

### 2단계: Cloud Run 자동 배포 및 IAM 설정
1. `.env`가 준비되면 `./scripts/deploy.sh`를 실행합니다.
2. 스크립트가 수행하는 내용:
   - Cloud Run 비공개 배포 (`--no-allow-unauthenticated`)
   - Cloud Run 기본 서비스 계정에 `roles/discoveryengine.admin` 부여
   - GECX 서비스 에이전트에 `roles/run.invoker` 부여
   - 배포 완료된 서비스 URL을 `openapi.yaml`에 자동 반영

### 3단계: 엔드투엔드 검색 테스트
1. 배포가 완료되면 `./scripts/test_search.sh`를 실행하여 실제 데이터스토어에서 레이아웃 텍스트와 이미지 주소(`uri`)가 정상 반환되는지 확인하고 결과를 사용자에게 요약해 보여줍니다.

### 4단계: CXAS 에이전트 연동 안내
1. 테스트가 성공하면 사용자에게 다음 단계를 안내합니다:
   - CXAS 콘솔 > Tools > '+' > **OpenAPI** 선택
   - 툴 이름을 `custom_layout_search`로 지정하고 갱신된 `openapi.yaml` 내용 붙여넣기
   - 에이전트 인스트럭션에 서브태스크(지침서) 반영 및 이미지 마크다운 출력 설정 안내

---

## ⚡ 빠른 명령어 요약

```bash
# 1. 환경 사전 검증
./scripts/check_env.sh

# 2. Cloud Run 배포 및 IAM 설정
./scripts/deploy.sh

# 3. 배포 후 E2E 검색 테스트
./scripts/test_search.sh "필터"
```
