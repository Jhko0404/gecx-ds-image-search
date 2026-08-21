#!/bin/bash
# ==============================================================================
# 자체 단위 테스트 및 Cloud Run 검색 엔드포인트 종합 검증 스크립트
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

QUERY="${1:-필터}"

echo -e "${BLUE}${BOLD}======================================================${NC}"
echo -e "${BLUE}${BOLD}🧪 [1단계] 오프라인 단위 테스트(Unit Tests) 실행${NC}"
echo -e "${BLUE}${BOLD}======================================================${NC}"
echo "Layout Parser 텍스트 세그먼트, 이미지 URL 변환, 폴백 로직을 검증합니다..."

if python3 -m unittest discover tests -v; then
    echo -e "\n${GREEN}✅ 오프라인 단위 테스트 완료!${NC}"
else
    echo -e "\n${RED}❌ 단위 테스트 실패!${NC}"
    exit 1
fi

echo -e "\n${BLUE}${BOLD}======================================================${NC}"
echo -e "${BLUE}${BOLD}🧪 [2단계] 배포된 Cloud Run 라이브 엔드포인트 종합 검증${NC}"
echo -e "${BLUE}${BOLD}======================================================${NC}"

# .env 로드
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs -d '\n' 2>/dev/null || true)
fi

python3 scripts/verify_live.py "${QUERY}" || true
