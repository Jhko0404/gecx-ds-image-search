#!/bin/bash
# ==============================================================================
# 배포된 GCP 리소스 및 IAM 권한 현황 종합 조회 스크립트 (scripts/status_resources.sh)
# ==============================================================================
set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BLUE}${BOLD}======================================================================${NC}"
echo -e "${BLUE}${BOLD}📊 [GCP 리소스 현황 대시보드] GECX Layout Parser Search API${NC}"
echo -e "${BLUE}${BOLD}======================================================================${NC}"

# 1. 환경변수 확인
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs -d '\n' 2>/dev/null || true)
fi

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-layout-parser-search-api}
DATASTORE_ID=${DATASTORE_ID:-"(미지정)"}
LOCATION=${LOCATION:-global}

echo -e "📍 ${BOLD}GCP 프로젝트 ID:${NC} ${GREEN}${PROJECT_ID}${NC}"
echo -e "📍 ${BOLD}배포 리전:${NC}       ${GREEN}${REGION}${NC}"
echo -e "📍 ${BOLD}서비스 이름:${NC}     ${GREEN}${SERVICE_NAME}${NC}"
echo -e "📍 ${BOLD}데이터스토어 ID:${NC} ${GREEN}${DATASTORE_ID}${NC}"
echo -e "📍 ${BOLD}데이터스토어 위치:${NC} ${GREEN}${LOCATION}${NC}"

# 2. Cloud Run 서비스 상태 조회
echo -e "\n${CYAN}${BOLD}[1] Cloud Run 서비스 현황${NC}"
echo -e "----------------------------------------------------------------------"

if gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --project "${PROJECT_ID}" &>/dev/null; then
    RUN_INFO=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --project "${PROJECT_ID}" --format="json")
    
    SERVICE_URL=$(echo "$RUN_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', {}).get('url', 'N/A'))")
    LATEST_REV=$(echo "$RUN_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', {}).get('latestReadyRevisionName', 'N/A'))")
    TRAFFIC_PCT=$(echo "$RUN_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', {}).get('traffic', [{}])[0].get('percent', '100'))")
    INGRESS=$(echo "$RUN_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('spec', {}).get('template', {}).get('metadata', {}).get('annotations', {}).get('run.googleapis.com/ingress', 'all'))")
    
    echo -e "  ✔ ${BOLD}상태:${NC}           ${GREEN}정상 가동 중 (Serving 100%)${NC}"
    echo -e "  ✔ ${BOLD}서비스 URL:${NC}     ${BLUE}${BOLD}${SERVICE_URL}${NC}"
    echo -e "  ✔ ${BOLD}최신 리비전:${NC}    ${LATEST_REV}"
    echo -e "  ✔ ${BOLD}트래픽 할당:${NC}    ${TRAFFIC_PCT}%"
    echo -e "  ✔ ${BOLD}인그레스 정책:${NC}  ${INGRESS}"
else
    echo -e "  ✖ ${RED}Cloud Run 서비스가 배포되지 않았거나 조회할 수 없습니다.${NC}"
    echo -e "    👉 배포 명령어: ${BLUE}./scripts/deploy.sh${NC}"
fi

# 3. IAM 바인딩 상태 점검
echo -e "\n${CYAN}${BOLD}[2] IAM 권한 구성 현황${NC}"
echo -e "----------------------------------------------------------------------"

PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)" 2>/dev/null || true)
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Cloud Run 서비스의 invoker 목록
echo -e "  👉 ${BOLD}Cloud Run 서비스 호출자 (roles/run.invoker):${NC}"
INVOKERS=$(gcloud run services get-iam-policy "${SERVICE_NAME}" --region "${REGION}" --project "${PROJECT_ID}" --format="json" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for b in data.get('bindings', []):
        if b.get('role') == 'roles/run.invoker':
            for m in b.get('members', []):
                print(f'     - {m}')
except Exception:
    pass
" || true)

if [ -n "$INVOKERS" ]; then
    echo -e "${GREEN}${INVOKERS}${NC}"
else
    echo -e "     ${YELLOW}(설정된 호출자 없음 또는 조회 권한 부족)${NC}"
fi

# Discovery Engine 권한 점검
echo -e "  👉 ${BOLD}Cloud Run SA (${COMPUTE_SA}) 권한:${NC}"
ROLES=$(gcloud projects get-iam-policy "${PROJECT_ID}" --format="json" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    sa = '$COMPUTE_SA'
    matched = []
    for b in data.get('bindings', []):
        if any(sa in m for m in b.get('members', [])):
            matched.append(b.get('role'))
    if matched:
        for r in matched:
            print(f'     - {r}')
    else:
        print('     (부여된 역할 없음)')
except Exception as e:
    print(f'     (조회 실패: {e})')
" || true)
echo -e "${GREEN}${ROLES}${NC}"

# 4. OpenAPI 연동 파일 점검
echo -e "\n${CYAN}${BOLD}[3] CXAS 연동 파일 (openapi.yaml)${NC}"
echo -e "----------------------------------------------------------------------"
if [ -f openapi.yaml ]; then
    OPENAPI_URL=$(grep "url:" openapi.yaml | head -n 1 | awk '{print $2}')
    echo -e "  ✔ ${BOLD}설정된 엔드포인트 URL:${NC} ${BLUE}${OPENAPI_URL}${NC}"
else
    echo -e "  ✖ ${YELLOW}openapi.yaml 파일이 없습니다.${NC}"
fi

echo -e "\n${BLUE}${BOLD}======================================================================${NC}"
echo -e "${GREEN}${BOLD}💡 리소스 관리 팁:${NC}"
echo -e "  - 실서버 쿼리 테스트: ${BLUE}./scripts/test_search.sh \"필터\"${NC}"
echo -e "  - 리소스 전체 삭제:   ${RED}./scripts/cleanup.sh${NC}"
echo -e "${BLUE}${BOLD}======================================================================${NC}\n"
