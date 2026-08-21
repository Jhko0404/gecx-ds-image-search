#!/bin/bash
# ==============================================================================
# 배포된 Cloud Run 리소스 정리 및 삭제 스크립트 (scripts/cleanup.sh)
# ==============================================================================
set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${RED}${BOLD}======================================================================${NC}"
echo -e "${RED}${BOLD}🗑️  [GCP 리소스 정리 / 삭제] GECX Layout Parser Search API${NC}"
echo -e "${RED}${BOLD}======================================================================${NC}"

# 1. 환경변수 확인
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs -d '\n' 2>/dev/null || true)
fi

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-layout-parser-search-api}

echo -e "📍 ${BOLD}대상 GCP 프로젝트:${NC} ${GREEN}${PROJECT_ID}${NC}"
echo -e "📍 ${BOLD}대상 리전:${NC}         ${GREEN}${REGION}${NC}"
echo -e "📍 ${BOLD}삭제 대상 서비스:${NC}   ${RED}${BOLD}${SERVICE_NAME}${NC}"

# 2. Cloud Run 서비스 존재 여부 확인
if ! gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --project "${PROJECT_ID}" &>/dev/null; then
    echo -e "\n${YELLOW}ℹ️  Cloud Run 서비스 '${SERVICE_NAME}'가 존재하지 않거나 이미 삭제되었습니다.${NC}"
    exit 0
fi

# 3. 사용자 확인 프롬프트 (대화형 안전 장치)
echo -e "\n${YELLOW}${BOLD}⚠️  주의: Cloud Run 서비스를 삭제하면 CXAS에서 이 검색 도구를 더 이상 호출할 수 없게 됩니다.${NC}"
read -p "정말로 Cloud Run 서비스 '${SERVICE_NAME}'를 삭제하시겠습니까? (y/N): " CONFIRM

if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo -e "\n${BLUE}⏳ Cloud Run 서비스 '${SERVICE_NAME}' 삭제 중...${NC}"
    gcloud run services delete "${SERVICE_NAME}" \
        --region "${REGION}" \
        --project "${PROJECT_ID}" \
        --quiet
    echo -e "${GREEN}✔ Cloud Run 서비스가 성공적으로 삭제되었습니다.${NC}"

    # openapi.yaml 파일 초기화
    if [ -f openapi.yaml ]; then
        sed -i "s|url: https://.*|url: https://[YOUR_CLOUD_RUN_SERVICE_URL]|g" openapi.yaml
        echo -e "${GREEN}✔ openapi.yaml 엔드포인트 URL이 템플릿으로 초기화되었습니다.${NC}"
    fi

    echo -e "\n${GREEN}${BOLD}🎉 리소스 정리가 안전하게 완료되었습니다!${NC}"
else
    echo -e "\n${BLUE}작업이 취소되었습니다. 리소스가 그대로 유지됩니다.${NC}"
fi

echo -e "${RED}${BOLD}======================================================================${NC}\n"
