# 📜 GECX Layout Parser Search API 리비전 및 변경 이력서 (CHANGELOG)

본 문서는 브랜치별 기능 추가, 버그 수정, 아키텍처 개선 사항 및 Cloud Run 배포 리비전 이력을 체계적으로 관리하기 위한 문서입니다.

---

## 🌿 브랜치별 운영 목적 및 현황

| 브랜치명 | 최신 버전 | 주요 용도 및 특징 | 권장 환경 |
| :--- | :---: | :--- | :--- |
| **`main`** | `v1.0.0` | • 단일 프로젝트 표준 배포<br>• 사내 인증 세션 기반 이미지 링크 (`storage.cloud.google.com`)<br>• 안정화된 프로덕션 기본 브랜치 | 고객사 단일 프로젝트 배포 |
| **`feat/v4-signed-url`** | `v1.2.0` | • **외부 대중 고객(B2C) 지원**<br>• 60분 유효 V4 Signed URL 발급 (로그인 없이 이미지 열람 가능)<br>• 특수문자/괄호 경로 인코딩 정규화 적용 | 대고객 웹 챗봇 서비스 |
| **`test/cross-project-gemeni`** | `v1.1.0` | • 서로 다른 프로젝트 간(Cross-Project) IAM 연동<br>• GECX 앱(gemeni-workshop) ↔ Cloud Run(project-elevate-007) | 멀티 프로젝트 개발/테스트 환경 |

---

## 🚀 세부 버전별 릴리스 노트 (Release History)

### [v1.2.0] - 2026-08-21 (`feat/v4-signed-url`)
> **외부 미인증 고객을 위한 V4 Signed URL 임시 공개 링크 지원**

#### ✨ 주요 변경 사항 (Features)
- **V4 Signed URL 발급 엔진 구현**:
  - `google-cloud-storage` 및 IAM Credentials API를 통한 60분 임시 서명 URL 생성.
  - 구글 로그인이 없는 일반 외부 고객의 브라우저에서도 매뉴얼 다이어그램 이미지가 즉시 렌더링되도록 개선.
- **특수문자 경로 인코딩 정규화 (Bug Fix)**:
  - GCS 파일/폴더 경로에 괄호(`(acrobat-png)`) 또는 공백이 포함된 경우 발생하던 `403 SignatureDoesNotMatch` 오류 해결.
  - `urllib.parse.unquote`를 적용하여 서명 계산 시점과 HTTP 요청 시점의 정규화 일치 보장 (외부 curl 테스트 시 `HTTP/2 200 OK` 확인 완료).
- **설정 옵션화**:
  - `ENABLE_SIGNED_URL` (기본값: `true`): Signed URL 발급 여부 토글.
  - `SIGNED_URL_EXPIRATION_MINUTES` (기본값: `60`): 임시 링크 유효시간 분 단위 설정 지원.

---

### [v1.1.0] - 2026-08-21 (`test/cross-project-gemeni`)
> **멀티 프로젝트(Cross-Project) IAM 연동 및 리소스 관리 자동화**

#### ✨ 주요 변경 사항 (Features)
- **크로스 프로젝트 통신 아키텍처 검증**:
  - `gemeni-workshop` (GECX 앱 & 데이터스토어) ↔ `project-elevate-007` (Cloud Run) 간 보안 호출 성공.
  - GECX 서비스 에이전트에 `roles/run.invoker`, Cloud Run SA에 `roles/discoveryengine.admin` 및 `roles/serviceusage.serviceUsageConsumer` 바인딩 적용.
- **리소스 대시보드 스크립트 추가 (`scripts/status_resources.sh`)**:
  - 배포된 Cloud Run 상태, URL, 최신 리비전, 트래픽 비율, IAM 바인딩 현황을 터미널 대시보드로 실시간 출력.
- **안전 삭제(Teardown) 스크립트 추가 (`scripts/cleanup.sh`)**:
  - 테스트 종료 후 대화형 확인(y/N)을 거쳐 Cloud Run 서비스를 삭제하고 `openapi.yaml`을 템플릿 상태로 초기화.
- **부록(Appendix) 문서화**:
  - 멀티 프로젝트 구성 절차를 `README.md` 부록에 통합.

---

### [v1.0.0] - 2026-08-21 (`main`)
> **GECX Layout Parser 검색 프록시 백엔드 초기 릴리스**

#### ✨ 주요 변경 사항 (Features)
- **3단계 텍스트 추출 및 매핑 엔진 (`main.py`)**:
  - 1순위: `extractive_segments[].content` (Layout Parser 본문 세그먼트)
  - 2순위: `snippets[].snippet` (일반 텍스트 데이터스토어 폴백)
  - 3순위: `annotationContent[]` (이미지 OCR 인덱스 폴백)
- **오프라인 단위 테스트 스위트 (`tests/test_parser.py`)**:
  - 7개 단위 테스트 케이스 구축 (모의 응답 파싱, URL 변환, 결측치 처리 등 100% 통과).
- **자동화 스크립트 파이프라인**:
  - `scripts/check_env.sh`: GCP 계정 및 7개 필수 API 자동 점검/활성화.
  - `scripts/deploy.sh`: Cloud Run 배포, IAM 권한 자동 설정, `openapi.yaml` URL 자동 매핑.
  - `scripts/verify_live.py` / `scripts/test_search.sh`: 실서버 헬스체크 및 쿼리 체크리스트 리포트.
- **문서화**:
  - `CLAUDE.md`: Claude Code 인터뷰 및 배포 지침서.
  - `README.md`: 마스터 고객사 배포 가이드.
  - `openapi.yaml`: CXAS Tools 연동용 표준 OpenAPI 3.0 스펙.

---

## 🔄 배포 리비전 롤백(Rollback) 가이드

배포 후 특정 버전이나 이전 리비전으로 되돌려야 할 경우 아래 명령어를 활용합니다:

```bash
# 1. Cloud Run 리비전 목록 확인
gcloud run revisions list --service=layout-parser-search-api --region=us-central1

# 2. 특정 리비전으로 100% 트래픽 즉시 롤백 (무중단, 1초 소요)
gcloud run services update-traffic layout-parser-search-api \
    --to-revisions=[대상_리비전_이름]=100 \
    --region=us-central1

# 3. 안정 버전(main) 코드로 재배포
git checkout main
./scripts/deploy.sh
```
