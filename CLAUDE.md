# GECX Layout Parser Data Store 연동 가이드 (Claude Code 지침서)

이 프로젝트는 CXAS(Vertex AI Conversation / Agent Studio)에서 Layout Parser 형식의 비정형 데이터스토어를 검색할 때 발생하는 빈 응답(`response: {}`) 문제를 해결하기 위한 Cloud Run 프록시 검색 API입니다.

---

## 🛠️ 프로젝트 핵심 구성 및 파일 역할

- `main.py`: Discovery Engine Search REST API와 통신하여 `extractive_segments` 및 이미지 GCS URL을 추출·변환하여 CXAS 규격(`snippets: [{title, uri, text}]`)으로 가공하는 백엔드 서버.
- `tests/test_parser.py`: 모의(Mock) 데이터를 이용해 텍스트 세그먼트 병합, `gs://` ➔ `https://` 이미지 URL 변환, 폴백 로직을 검증하는 오프라인 단위 테스트 스위트.
- `requirements.txt` / `Dockerfile`: Cloud Run 배포용 의존성 및 컨테이너 빌드 파일.
- `openapi.yaml`: CXAS Tools에 등록하기 위한 OpenAPI 3.0 명세 파일 (배포 시 URL 자동 치환).
- `.env.example` / `.env`: 고객사 GCP 환경 설정 파일 (GCP 프로젝트 ID, 데이터스토어 ID 등).
- `scripts/check_env.sh`: GCP 로그인, 활성 프로젝트, 필수 API(`discoveryengine`, `run`, `cloudbuild` 등) 자동 활성화 및 환경변수 사전 검증.
- `scripts/deploy.sh`: Cloud Run 자동 배포, IAM 권한 자동 설정, `openapi.yaml` URL 자동 갱신.
- `scripts/verify_live.py` / `scripts/test_search.sh`: 단위 테스트 및 배포된 Cloud Run 엔드포인트 종합 검증 (체크리스트 리포트).

---

## 📋 고객사 환경 변수 (.env) 확인 기준표

Claude Code는 사용자가 환경 변수 확인을 어려워할 때 아래 기준에 따라 안내하거나 조회를 돕습니다:

| 환경 변수 | 필수 여부 | 기본값 | 확인 방법 (콘솔 및 CLI) |
| :--- | :---: | :--- | :--- |
| **`PROJECT_ID`** | **필수** | - | **콘솔**: 상단 프로젝트 드롭다운 클릭 ➔ 'ID' 열 값 복사<br>**CLI**: `gcloud config get-value project` |
| **`DATASTORE_ID`** | **필수** | - | **콘솔**: `Vertex AI Search` ➔ 좌측 `Data Stores` 메뉴 ➔ 대상 데이터스토어 클릭 ➔ 상단 `Data store ID` 복사<br>**CLI**: `gcloud discovery-engine data-stores list` (또는 API 조회) |
| **`REGION`** | 선택 | `us-central1` | Cloud Run 배포 리전 (국내 권장: `asia-northeast3`, 기본: `us-central1`) |
| **`LOCATION`** | 선택 | `global` | Discovery Engine 데이터스토어 생성 위치 (기본 `global`) |
| **`COLLECTION_ID`** | 선택 | `default_collection` | Discovery Engine 컬렉션 ID (기본값 유지) |
| **`SERVING_CONFIG_ID`** | 선택 | `default_search` | 서빙 설정 ID (기본값 유지) |
| **`SERVICE_NAME`** | 선택 | `layout-parser-search-api` | 배포할 Cloud Run 서비스 식별명 |
| **`GECX_SERVICE_ACCOUNT`** | 선택 | (자동 계산) | GECX 서비스 에이전트 계정 (`service-[프로젝트번호]@gcp-sa-ces.iam.gserviceaccount.com`). 비워두면 `deploy.sh`가 자동 부여 |

---

## 🤖 Claude Code 대화형 실행 워크플로우 지침 (반드시 준수)

사용자가 "배포해줘", "시작해줘", "환경 설정해줘" 등의 요청을 하면, 아래 워크플로우에 따라 대화형으로 친절하게 진행하세요.

### 1단계: 환경 및 필수 정보 확인 (대화형 인터뷰)
1. `./scripts/check_env.sh`를 실행하여 `gcloud` 로그인 계정과 활성 프로젝트, 필수 API 활성화 상태를 확인합니다.
2. 만약 `.env` 파일에 `DATASTORE_ID`가 비어있다면, **사용자에게 직접 대화형으로 물어보세요**:
   > *"연동할 Vertex AI Search의 **데이터스토어 ID(DATASTORE_ID)**를 알려주시면 `.env`에 설정하고 배포를 진행하겠습니다. (어디서 확인하는지 모르실 경우 'Vertex AI Search > Data Stores' 메뉴에서 확인하시거나, 제가 조회를 도와드릴 수 있습니다.)"*
3. 사용자가 데이터스토어 ID를 알려주면 `.env` 파일에 즉시 업데이트합니다.

### 2단계: 오프라인 단위 테스트 실행
1. `python3 -m unittest discover tests -v`를 실행하여 파싱 로직(텍스트 세그먼트 병합 및 `gs://` ➔ `https://` 링크 변환)에 이상이 없는지 먼저 확인합니다.

### 3단계: Cloud Run 자동 배포 및 IAM 설정
1. `./scripts/deploy.sh`를 실행합니다.
2. 스크립트가 수행하는 내용:
   - Cloud Run 비공개 배포 (`--no-allow-unauthenticated`)
   - Cloud Run 기본 서비스 계정에 `roles/discoveryengine.admin` 부여
   - GECX 서비스 에이전트에 `roles/run.invoker` 부여
   - 배포 완료된 서비스 URL을 `openapi.yaml`에 자동 반영

### 4단계: 실서버 라이브 검증 테스트
1. 배포가 완료되면 `./scripts/test_search.sh`를 실행하여 실제 데이터스토어에서 텍스트와 이미지 주소(`uri`)가 정상 반환되는지 확인하고 결과를 사용자에게 [PASS/FAIL] 체크리스트 요약으로 보여줍니다.

### 5단계: CXAS 에이전트 연동 안내
1. 테스트가 성공하면 사용자에게 다음 단계를 안내합니다:
   - CXAS 콘솔 > Tools > '+' > **OpenAPI** 선택
   - 툴 이름을 `custom_layout_search`로 지정하고 갱신된 `openapi.yaml` 내용 붙여넣기
   - 에이전트 인스트럭션에 아래의 서브태스크(지침서) 반영 및 이미지 마크다운 출력 설정 안내:

```markdown
<subtask name="Manual_Lookup">
    <step name="Search_And_Answer">
        <trigger>고객이 제품 사양, 자가 조치, 기기 사용법, 필터 관리에 대해 질문할 때</trigger>
        <action>
            1. 즉시 {@TOOL: custom_layout_search} 도구를 딱 1회 호출하여 매뉴얼 정보를 검색합니다.
            2. 만약 검색 결과(snippets)가 비어 있거나 원하는 정보를 찾을 수 없는 경우:
               - 더 단순하고 일반적인 핵심 명사 위주로 검색어(query)를 변경하여 딱 1회만 추가 검색을 수행하십시오.
               - 2회째 검색 결과도 비어 있다면, 절대로 추가 도구 호출을 수행하지 말고 고객에게 "죄송합니다. 관련 매뉴얼 정보를 찾을 수 없습니다."라고 안내한 뒤 즉시 이 플레이북을 리턴(Return)하십시오.
            3. 검색 결과에 유효한 정보가 매칭되는 경우, 반환된 snippets 내용을 바탕으로 답변을 제공하되 시각적 설명에 해당하는 이미지 주소(uri)가 있다면 마크다운 이미지 형식(![매뉴얼 다이어그램](이미지_주소))으로 텍스트 끝에 반드시 포함하여 출력하십시오.
            4. 답변을 마친 후 "추가로 궁금한 점이 있으신가요?"라고 질문하십시오.
        </action>
    </step>
</subtask>
```

---

## ❓ 트러블슈팅 지침 (Claude Code 대응 가이드)

- **403 Forbidden 에러 발생 시**: Cloud Run 기본 서비스 계정에 `roles/discoveryengine.admin`이 부여되었는지 확인하고, GECX 서비스 계정에 `roles/run.invoker`가 설정되었는지 점검합니다.
- **404 DataStore Not Found 에러 시**: `.env`에 입력된 `DATASTORE_ID`와 `PROJECT_ID`, `LOCATION`이 Vertex AI Search 콘솔상의 값과 일치하는지 사용자에게 재확인을 요청합니다.
