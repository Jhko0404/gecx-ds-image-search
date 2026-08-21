#!/bin/bash
# ==============================================================================
# Cloud Run 검색 엔드포인트 E2E 테스트 스크립트 (scripts/test_search.sh)
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

QUERY="${1:-필터}"

# 1. 환경변수 확인
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs -d '\n' 2>/dev/null || true)
fi

PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-layout-parser-search-api}

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ PROJECT_ID를 찾을 수 없습니다. .env 또는 gcloud 설정을 확인해주세요.${NC}"
    exit 1
fi

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}🧪 Cloud Run 검색 API 엔드포인트 테스트${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "📍 프로젝트 ID: ${GREEN}${PROJECT_ID}${NC}"
echo -e "📍 서비스명: ${GREEN}${SERVICE_NAME}${NC}"
echo -e "📍 검색 쿼리: ${GREEN}'${QUERY}'${NC}"

# 2. 서비스 URL 가져오기
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region "${REGION}" \
    --project "${PROJECT_ID}" \
    --format="value(status.url)" 2>/dev/null || true)

if [ -z "$SERVICE_URL" ]; then
    echo -e "${RED}❌ 배포된 Cloud Run 서비스를 찾을 수 없습니다: ${SERVICE_NAME}${NC}"
    echo " 먼저 ./scripts/deploy.sh 를 실행하여 서비스를 배포해주세요."
    exit 1
fi

echo -e "📍 서비스 URL: ${BLUE}${SERVICE_URL}${NC}"

# 3. 인증 토큰 발급 (ID Token)
echo -e "\n${BLUE}🔑 gcloud 인증 ID 토큰 발급 중...${NC}"
ID_TOKEN=$(gcloud auth print-identity-token 2>/dev/null || true)

if [ -z "$ID_TOKEN" ]; then
    echo -e "${YELLOW}⚠️  ID Token 발급 실패. gcloud auth login 상태를 점검해주세요.${NC}"
    exit 1
fi

# 4. 헬스체크 테스트 (/health)
echo -e "\n${BLUE}🩺 1) 헬스체크 엔드포인트 호출 (/health)...${NC}"
HEALTH_RESP=$(curl -s -H "Authorization: Bearer ${ID_TOKEN}" "${SERVICE_URL}/health")
echo -e "  응답: ${GREEN}${HEALTH_RESP}${NC}"

# 5. 검색 API 테스트 (/search)
echo -e "\n${BLUE}🔍 2) 검색 엔드포인트 호출 (/search)...${NC}"
SEARCH_PAYLOAD=$(python3 -c "import json; print(json.dumps({'query': '$QUERY'}))")

SEARCH_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer ${ID_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$SEARCH_PAYLOAD" \
    "${SERVICE_URL}/search")

HTTP_BODY=$(echo "$SEARCH_RESPONSE" | sed '$d')
HTTP_CODE=$(echo "$SEARCH_RESPONSE" | tail -n1)

echo -e "  HTTP 응답 코드: ${BLUE}${HTTP_CODE}${NC}"

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✅ 검색 API 호출 성공!${NC}"
    echo -e "\n${BLUE}--- 검색 결과 JSON (요약) ---${NC}"
    python3 -c "
import sys, json
try:
    data = json.loads('''$HTTP_BODY''')
    snippets = data.get('snippets', [])
    print(f'총 발견된 세그먼트 개수: {len(snippets)}')
    for i, s in enumerate(snippets, 1):
        print(f'\n[{i}] 제목: {s.get(\"title\")}')
        print(f'    링크: {s.get(\"uri\")}')
        preview = s.get(\"text\", \"\")[:120].replace('\n', ' ')
        print(f'    텍스트 미리보기: {preview}...')
except Exception as e:
    print(f'파싱 에러: {e}')
    print('''$HTTP_BODY''')
"
    echo -e "${BLUE}-----------------------------${NC}"
    echo -e "\n${GREEN}🎉 테스트 검증 성공! 이제 CXAS에서 OpenAPI 툴을 연동할 수 있습니다.${NC}"
else
    echo -e "${RED}❌ 검색 API 호출 실패 (HTTP $HTTP_CODE)${NC}"
    echo -e "응답 본문:"
    echo "$HTTP_BODY"
    exit 1
fi
