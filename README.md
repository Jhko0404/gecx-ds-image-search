# CXAS Data Store Layout Parser 데이터 스토어 연동 문제 및 Cloud Run 우회 배포 가이드

본 가이드는 **CXAS (CX Agent Studio / Vertex AI Conversation)**에서 **Layout Parser 형식의 unstructured 데이터 스토어(layout-parser)**를 연동할 때 발생하는 빈 검색 결과(`response: {}`) 문제를 해결하고, 고객사 GCP 리소스에 **Cloud Run 기반 프록시 API**를 손쉽게 배포·테스트·연동할 수 있는 엔드투엔드 절차를 제공합니다.

---

## 📌 목차
1. [개요 및 문제 원인 (Root Cause)](#1-개요-및-문제-원인-root-cause)
2. [아키텍처 개요](#2-아키텍처-개요)
3. [🚀 Claude Code를 활용한 빠른 배포 (추천)](#3--claude-code를-활용한-빠른-배포-추천)
4. [🛠️ 단계별 상세 배포 가이드](#4-️-단계별-상세-배포-가이드)
   - [0단계: 개발 환경 및 GCP 콘솔 로그인](#0단계-개발-환경-및-gcp-콘솔-로그인)
   - [1단계: 환경 설정 및 사전 점검](#1단계-환경-설정-및-사전-점검)
   - [2단계: Cloud Run 배포 및 IAM 권한 자동 설정](#2단계-cloud-run-배포-및-iam-권한-자동-설정)
   - [3단계: 배포된 API 엔드투엔드 테스트](#3단계-배포된-api-엔드투엔드-테스트)
   - [4단계: CXAS OpenAPI 툴 등록](#4단계-cxas-openapi-툴-등록)
   - [5단계: CXAS 에이전트 인스트럭션 수정](#5단계-cxas-에이전트-인스트럭션-수정)
5. [❓ 문제 해결 (Troubleshooting)](#5--문제-해결-troubleshooting)

---

## 1. 개요 및 문제 원인 (Root Cause)

CXAS 기본 **Data Store Tool**을 사용하여 Layout Parser 데이터스토어를 조회하면, 실제 문서가 정상 색인되어 있음에도 빈 응답(`{}`)이 반환됩니다.

### 원인 분석
| 구분 | 일반 Text 데이터스토어 | Layout Parser 데이터스토어 |
| :--- | :--- | :--- |
| **반환 필드** | `derivedStructData.snippets[].snippet` | `derivedStructData.extractive_segments[].content` 또는 `annotationContent` |
| **CXAS 기본 툴 동작** | `snippets` 필드를 자동 매핑하여 결과 반환 | `snippets` 필드만 탐색하므로 `extractive_segments`를 누락하여 **빈 객체(`{}`) 반환** |

---

## 2. 아키텍처 개요

기본 Data Store Tool 대신, **Discovery Engine Search API**를 직접 호출하여 `extractive_segments`와 이미지 링크를 정상 추출하고 CXAS 규격으로 가공해 주는 **경량 Cloud Run API**를 중간 프록시로 연동합니다.

```
[CXAS Agent (Playbook)]
       │
       ▼ (1. OpenAPI Tool 호출: /search)
[Cloud Run Proxy API]
       │
       ▼ (2. Discovery Engine REST Search API: extractiveContentSpec 적용)
[Vertex AI Search (Layout Parser)]
       │
       ▼ (3. extractive_segments + 이미지 GCS URL 반환)
[Cloud Run Proxy API]
       │ (4. 포맷팅 & HTTPS URL 변환: snippets: [{title, uri, text}])
       ▼
[CXAS Agent (Playbook)] ──▶ [최종 마크다운 텍스트 + 이미지 다이어그램 답변]
```

![Architecture](images/image-1.png)

---

## 3. 🚀 Claude Code를 활용한 빠른 배포 (추천)

이 리포지토리는 **Claude Code**가 바로 인식하여 배포를 대화형으로 완수할 수 있도록 [`CLAUDE.md`](CLAUDE.md) 및 자동화 스크립트가 완비되어 있습니다.

### Claude Code 실행 방법
1. 터미널에서 이 프로젝트 폴더로 이동합니다.
   ```bash
   cd gecx-ds-image-search
   ```
2. Claude Code를 실행합니다.
   ```bash
   claude
   ```
3. Claude Code 대화창에 다음과 같이 요청하세요:
   > *"GCP 환경 검증하고 Cloud Run 배포 및 테스트까지 진행해줘"*
4. Claude Code가 자동으로:
   - GCP 로그인 상태 및 활성 프로젝트 확인
   - 필수 API 활성화 및 `.env` 파일 구성
   - Cloud Run 배포 및 필수 IAM(Discovery Engine Admin, GECX run.invoker) 권한 부여
   - 실제 쿼리로 엔드투엔드 테스트 및 OpenAPI 명세 갱신까지 원클릭으로 완료합니다.

---

## 4. 🛠️ 단계별 상세 배포 가이드

직접 CLI 명령어를 통해 단계별로 배포 및 검증하고자 하는 경우 아래 절차를 진행합니다.

### 0단계: 개발 환경 및 GCP 콘솔 로그인

#### 1) Python 가상환경(venv) 생성 및 활성화
```bash
# 1. 가상환경 생성
python3 -m venv .venv

# 2. 가상환경 활성화 (macOS/Linux)
source .venv/bin/activate

# 3. 의존성 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt
```

#### 2) Google Cloud CLI 로그인 및 대상 프로젝트 설정
```bash
# 1. gcloud CLI 사용자 계정 로그인
gcloud auth login

# 2. Application Default Credentials (ADC) 로컬 자격증명 로그인
gcloud auth application-default login

# 3. 배포 대상 고객사 GCP 프로젝트 ID 설정
gcloud config set project [고객사-GCP-프로젝트-ID]
```

---

### 1단계: 환경 설정 및 사전 점검

#### 1) `.env` 파일 설정
`.env.example` 템플릿을 복사하여 `.env` 파일을 생성하고 필수 값을 기재합니다.
```bash
cp .env.example .env
```
`.env` 파일 내용:
```env
PROJECT_ID=고객사-GCP-프로젝트-ID
REGION=us-central1
DATASTORE_ID=고객사-Layout-Parser-데이터스토어-ID
LOCATION=global
COLLECTION_ID=default_collection
SERVING_CONFIG_ID=default_search
SERVICE_NAME=layout-parser-search-api
```

#### 2) 환경 사전 검증 스크립트 실행
GCP 로그인 상태, 프로젝트 설정, 필수 API 활성화 여부(`discoveryengine`, `run`, `cloudbuild` 등)를 한 번에 검증하고 누락된 API를 자동 활성화합니다.
```bash
./scripts/check_env.sh
```

---

### 2단계: Cloud Run 배포 및 IAM 권한 자동 설정

제공되는 자동 배포 스크립트를 실행합니다.
```bash
./scripts/deploy.sh
```

#### 스크립트가 자동 수행하는 작업:
1. **Cloud Run 배포**: 미인증 접근을 차단(`--no-allow-unauthenticated`)하여 안전하게 배포합니다.
2. **Cloud Run SA 권한 부여**: Cloud Run 기본 서비스 계정에 `roles/discoveryengine.admin` 역할을 부여하여 Discovery Engine API 조회를 허용합니다.
3. **GECX 서비스 에이전트 권한 부여**: GECX 서비스 계정(`service-[PROJECT_NUMBER]@gcp-sa-ces.iam.gserviceaccount.com`)에 해당 Cloud Run 서비스 호출자(`roles/run.invoker`) 권한을 부여합니다.
4. **OpenAPI 스펙 갱신**: 배포 완료된 Cloud Run 서비스 URL을 [`openapi.yaml`](openapi.yaml)에 자동 반영합니다.

---

### 3단계: 배포된 API 엔드투엔드 테스트

배포된 Cloud Run 엔드포인트가 실제 Layout Parser 데이터스토어에서 텍스트와 이미지 링크를 정상 추출하는지 테스트 스크립트로 검증합니다.
```bash
# 기본 검색어("필터")로 테스트
./scripts/test_search.sh

# 원하는 특정 검색어로 테스트
./scripts/test_search.sh "전원 안 켜짐"
```

#### 성공 응답 예시:
```json
{
  "snippets": [
    {
      "title": "청정기_사용설명서.pdf",
      "uri": "https://storage.cloud.google.com/my-bucket/manuals/filter_replace.png",
      "text": "필터 교체 주기 및 세척 방법: 프리필터는 2주마다 물세척을 권장하며, 복합헤파필터는 12개월마다 새 필터로 교체하십시오..."
    }
  ]
}
```

---

### 4단계: CXAS OpenAPI 툴 등록

1. **CXAS 콘솔**로 이동합니다:
   - `https://ces.cloud.google.com/projects/[PROJECT_ID]/locations/[LOCATION]/apps/[APP_ID]/tools`
2. 좌측 또는 우측 메뉴의 **Tools** > **"+" (Create)** 버튼을 클릭합니다.
3. 툴 유형을 **OpenAPI**로 선택합니다.
4. 툴 설정 입력:
   - **Tool Name**: `custom_layout_search`
   - **Description**: `Search layout parser unstructured datastore and retrieve manual text and diagrams`
   - **Schema (YAML)**: 프로젝트의 [`openapi.yaml`](openapi.yaml) 파일 내용 전체를 복사하여 붙여넣습니다.
5. **Save**를 눌러 등록합니다.

---

### 5단계: CXAS 에이전트 인스트럭션 수정

에이전트(플레이북)가 새로 생성한 OpenAPI 툴을 호출하고, 시각 자료(이미지)를 마크다운으로 렌더링하며, 무한 루프를 방지하도록 지침(Instruction)을 설정합니다.

1. CXAS 콘솔에서 대상 에이전트(예: FAQ 서브에이전트)를 엽니다.
2. **Tools** 항목에 `custom_layout_search` 툴을 추가합니다.
3. 에이전트 지침서에 아래와 같이 서브태스크를 추가합니다.

#### 📝 에이전트 서브태스크 지침 예시
```markdown
<subtask name="Manual_Lookup">
    <step name="Search_And_Answer">
        <trigger>고객이 제품 사양, 자가 조치, 기기 사용법, 필터 관리에 대해 질문할 때</trigger>
        <action>
            1. 즉시 {@TOOL: custom_layout_search} 도구를 딱 1회 호출하여 매뉴얼 정보를 검색합니다.
            2. 만약 검색 결과(snippets)가 비어 있거나 원하는 정보를 찾을 수 없는 경우:
               - 더 단순하고 일반적인 핵심 명사 위주로 검색어(query)를 변경하여 딱 1회만 추가 검색을 수행하십시오.
               - 2회째 검색 결과도 비어 있거나 매칭되는 내용이 없다면, 절대로 추가 도구 호출을 수행하지 말고 고객에게 "죄송합니다. 관련 매뉴얼 정보를 찾을 수 없습니다."라고 안내한 뒤 즉시 이 플레이북을 리턴(Return)하십시오.
            3. 검색 결과에 유효한 정보가 매칭되는 경우, 반환된 snippets 내용을 바탕으로 자연스럽게 답변을 제공하되 시각적 설명에 해당하는 이미지 주소(uri)가 있다면 마크다운 이미지 형식(![매뉴얼 다이어그램](이미지_주소))으로 텍스트 끝에 반드시 포함하여 출력하십시오.
            4. 답변을 마친 후 "추가로 궁금한 점이 있으신가요?"라고 질문하십시오.
        </action>
    </step>
</subtask>
```

#### 💡 핵심 설계 포인트:
- **이미지 다이어그램 즉시 표시**: API가 반환한 HTTPS 링크를 `![다이어그램](uri)` 마크다운으로 출력하여 웹 채팅 UI에서 이미지가 즉시 렌더링됩니다.
- **추론 루프 방지 (Anti-Looping)**: 매뉴얼에 없는 질문 시 에이전트가 도구를 무한 반복 호출하는 현상을 막기 위해 **최대 1회 재검색 후 강제 Return** 규칙을 명시합니다.

---

## 5. ❓ 문제 해결 (Troubleshooting)

### Q1. `403 Forbidden` 에러가 발생합니다.
- Cloud Run 서비스 계정에 `roles/discoveryengine.admin` 또는 `roles/discoveryengine.viewer` 역할이 부여되어 있는지 확인하세요.
- GECX 서비스 계정(`service-[PROJECT_NUMBER]@gcp-sa-ces.iam.gserviceaccount.com`)에 Cloud Run의 `roles/run.invoker` 권한이 부여되어 있는지 확인하세요 (`./scripts/deploy.sh` 재실행으로 해결 가능).

### Q2. 검색 결과 `snippets`가 빈 배열(`[]`)로 반환됩니다.
- Vertex AI Search 콘솔에서 데이터스토어의 문서 색인(Ingestion)이 완료 상태인지 확인하세요.
- 검색어(query)가 문서 내 실제 존재하는 키워드인지 확인하고, `./scripts/test_search.sh "문서내단어"`로 직접 조회해 보세요.

---

## 📄 라이선스
Apache License 2.0
