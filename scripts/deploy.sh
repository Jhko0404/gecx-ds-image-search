#!/bin/bash
# ==============================================================================
# Cloud Run 자동 배포 및 IAM 설정 스크립트 (scripts/deploy.sh)
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}🚀 Cloud Run 서비스 배포 및 IAM 설정을 시작합니다...${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. 환경변수 점검
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env 파일이 없습니다. 먼저 ./scripts/check_env.sh 를 실행하세요.${NC}"
    exit 1
fi

export $(grep -v '^#' .env | xargs -d '\n' 2>/dev/null || true)

if [ -z "$PROJECT_ID" ] || [ -z "$DATASTORE_ID" ]; then
    echo -e "${RED}❌ PROJECT_ID 또는 DATASTORE_ID가 .env에 정의되지 않았습니다.${NC}"
    echo " .env 파일을 열어 필수 값들을 기재해주세요."
    exit 1
fi

REGION=${REGION:-us-central1}
LOCATION=${LOCATION:-global}
COLLECTION_ID=${COLLECTION_ID:-default_collection}
SERVING_CONFIG_ID=${SERVING_CONFIG_ID:-default_search}
SERVICE_NAME=${SERVICE_NAME:-layout-parser-search-api}

echo -e "📍 프로젝트 ID: ${GREEN}${PROJECT_ID}${NC}"
echo -e "📍 리전: ${GREEN}${REGION}${NC}"
echo -e "📍 서비스 이름: ${GREEN}${SERVICE_NAME}${NC}"
echo -e "📍 데이터스토어 ID: ${GREEN}${DATASTORE_ID}${NC}"

# 2. Cloud Run 배포
echo -e "\n${BLUE}🔨 Cloud Run에 소스 배포 중... (잠시 시간이 소요될 수 있습니다)${NC}"
gcloud run deploy "${SERVICE_NAME}" \
    --source . \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --no-allow-unauthenticated \
    --set-env-vars "PROJECT_ID=${PROJECT_ID},DATASTORE_ID=${DATASTORE_ID},LOCATION=${LOCATION},COLLECTION_ID=${COLLECTION_ID},SERVING_CONFIG_ID=${SERVING_CONFIG_ID}" \
    --quiet

# 배포된 서비스 URL 확인
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --format="value(status.url)")

echo -e "\n${GREEN}✅ Cloud Run 배포 완료!${NC}"
echo -e "🌐 서비스 URL: ${BLUE}${SERVICE_URL}${NC}"

# 3. IAM 권한 자동 부여
echo -e "\n${BLUE}🔑 필요한 IAM 권한을 구성합니다...${NC}"

# 3-1. 프로젝트 번호 조회
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
GECX_SA="${GECX_SERVICE_ACCOUNT:-service-${PROJECT_NUMBER}@gcp-sa-ces.iam.gserviceaccount.com}"
CURRENT_USER=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || true)

# 3-2. Cloud Run SA에 Discovery Engine Admin 권한 부여
echo -e "  👉 1) Cloud Run 서비스 계정(${COMPUTE_SA})에 Discovery Engine 조회/관리 권한 부여..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/discoveryengine.admin" \
    --condition=None \
    --quiet || true

# 3-3. GECX Service Agent에 Cloud Run Invoker 권한 부여
echo -e "  👉 2) GECX 에이전트(${GECX_SA})에 Cloud Run 호출자(run.invoker) 권한 부여..."
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --member="serviceAccount:${GECX_SA}" \
    --role="roles/run.invoker" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --quiet || true

# 3-4. 현재 로그인 계정에도 run.invoker 권한 부여 (로컬 테스트용)
if [ -n "$CURRENT_USER" ]; then
    MEMBER_PREFIX="user:"
    if [[ "$CURRENT_USER" == *"gserviceaccount.com" ]]; then
        MEMBER_PREFIX="serviceAccount:"
    fi
    echo -e "  👉 3) 현재 사용자(${MEMBER_PREFIX}${CURRENT_USER})에 테스트용 호출자(run.invoker) 권한 부여..."
    gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
        --member="${MEMBER_PREFIX}${CURRENT_USER}" \
        --role="roles/run.invoker" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --quiet || true
fi

# 4. openapi.yaml 파일 자동 업데이트
if [ -f openapi.yaml ]; then
    echo -e "\n${BLUE}📝 openapi.yaml 파일의 서버 URL을 업데이트합니다...${NC}"
    sed -i "s|url: https://.*|url: ${SERVICE_URL}|g" openapi.yaml
    echo -e "${GREEN}✅ openapi.yaml 업데이트 완료 (${SERVICE_URL})${NC}"
fi

echo -e "\n${BLUE}======================================================${NC}"
echo -e "${GREEN}🎉 모든 배포 및 IAM 권한 설정이 완료되었습니다!${NC}"
echo -e "다음 단계로 배포된 API 테스트를 진행하세요:"
echo -e "👉 ${BLUE}./scripts/test_search.sh \"필터\"${NC}"
echo -e "${BLUE}======================================================${NC}"
