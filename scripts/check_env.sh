#!/bin/bash
# ==============================================================================
# 환경 사전 점검 및 초기화 스크립트 (scripts/check_env.sh)
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}🔍 GCP 및 프로젝트 환경 사전 점검을 시작합니다...${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. gcloud CLI 설치 확인
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI가 설치되어 있지 않습니다.${NC}"
    echo "Google Cloud SDK를 먼저 설치해주세요: https://cloud.google.com/sdk/docs/install"
    exit 1
fi
echo -e "${GREEN}✅ gcloud CLI 설치 확인 완료: $(gcloud --version | head -n 1)${NC}"

# 2. gcloud 인증 상태 확인
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || true)
if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo -e "${YELLOW}⚠️  gcloud에 로그인된 활성 계정이 없습니다.${NC}"
    echo -e "👉 아래 명령어로 로그인을 먼저 진행해주세요:"
    echo -e "   ${BLUE}gcloud auth login${NC}"
    echo -e "   ${BLUE}gcloud auth application-default login${NC}"
    exit 1
fi
echo -e "${GREEN}✅ gcloud 활성 계정: ${ACTIVE_ACCOUNT}${NC}"

# 3. .env 파일 확인 및 로드
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo -e "${YELLOW}⚠️  .env 파일이 없어 .env.example에서 복사하여 생성합니다.${NC}"
        cp .env.example .env
    else
        echo -e "${RED}❌ .env 및 .env.example 파일이 존재하지 않습니다.${NC}"
        exit 1
    fi
fi

export $(grep -v '^#' .env | xargs -d '\n' 2>/dev/null || true)

# 4. GCP Project ID 확인 및 자동 설정
GCLOUD_PROJECT=$(gcloud config get-value project 2>/dev/null || true)

if [ -z "$PROJECT_ID" ]; then
    if [ -n "$GCLOUD_PROJECT" ]; then
        PROJECT_ID="$GCLOUD_PROJECT"
        sed -i "s/^PROJECT_ID=.*/PROJECT_ID=${PROJECT_ID}/" .env
        echo -e "${GREEN}✅ gcloud 기본 프로젝트(${PROJECT_ID})를 .env에 자동 설정했습니다.${NC}"
    else
        echo -e "${RED}❌ PROJECT_ID가 .env에 설정되지 않았고 gcloud 기본 프로젝트도 없습니다.${NC}"
        echo -e "👉 .env 파일에 'PROJECT_ID=당신의-프로젝트-ID'를 기재하거나"
        echo -e "   ${BLUE}gcloud config set project [YOUR_PROJECT_ID]${NC} 를 실행해주세요."
        exit 1
    fi
fi
echo -e "${GREEN}✅ 대상 GCP 프로젝트 ID: ${PROJECT_ID}${NC}"

# 5. Data Store ID 확인
if [ -z "$DATASTORE_ID" ]; then
    echo -e "${YELLOW}⚠️  DATASTORE_ID가 .env에 비어 있습니다.${NC}"
    echo -e "👉 Vertex AI Search 콘솔에서 확인한 데이터스토어 ID를 .env 파일의 DATASTORE_ID= 항목에 기재해주세요."
else
    echo -e "${GREEN}✅ Discovery Engine 데이터스토어 ID: ${DATASTORE_ID}${NC}"
fi

# 6. 필수 GCP API 활성화 점검
echo -e "\n${BLUE}📦 필수 GCP API 활성화 상태 점검 중...${NC}"
REQUIRED_APIS=(
    "discoveryengine.googleapis.com"
    "run.googleapis.com"
    "cloudbuild.googleapis.com"
    "artifactregistry.googleapis.com"
    "iam.googleapis.com"
    "iamcredentials.googleapis.com"
    "storage.googleapis.com"
)

APIS_TO_ENABLE=()
for api in "${REQUIRED_APIS[@]}"; do
    if gcloud services list --enabled --project="${PROJECT_ID}" --filter="config.name:${api}" --format="value(config.name)" 2>/dev/null | grep -q "${api}"; then
        echo -e "  ${GREEN}✔ ${api} (활성화됨)${NC}"
    else
        echo -e "  ${YELLOW}✖ ${api} (비활성화됨)${NC}"
        APIS_TO_ENABLE+=("${api}")
    fi
done

if [ ${#APIS_TO_ENABLE[@]} -gt 0 ]; then
    echo -e "\n${YELLOW}⚠️  비활성화된 필수 API들을 활성화합니다: ${APIS_TO_ENABLE[*]}${NC}"
    gcloud services enable "${APIS_TO_ENABLE[@]}" --project="${PROJECT_ID}" || {
        echo -e "${YELLOW}⚠️  일부 API 자동 활성화 권한이 부족할 수 있습니다. GCP 관리자에게 API 활성화를 요청하세요.${NC}"
    }
    echo -e "${GREEN}✅ 필수 API 점검 완료!${NC}"
else
    echo -e "${GREEN}✅ 모든 필수 API가 이미 활성화되어 있습니다.${NC}"
fi

echo -e "\n${BLUE}======================================================${NC}"
echo -e "${GREEN}🎉 모든 환경 사전 검증이 완료되었습니다!${NC}"
echo -e "다음 단계로 Cloud Run 배포를 진행할 수 있습니다:"
echo -e "👉 ${BLUE}./scripts/deploy.sh${NC} (또는 Claude Code에게 '배포 진행해줘' 요청)"
echo -e "${BLUE}======================================================${NC}"
