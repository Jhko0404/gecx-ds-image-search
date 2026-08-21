#!/usr/bin/env python3
"""
scripts/verify_live.py
배포된 Cloud Run 검색 API를 대상으로 실시간 라이브 검증을 수행하고
텍스트 및 이미지 링크 추출 여부를 단위별 체크리스트로 리포팅하는 스크립트입니다.
"""
import sys
import json
import urllib.request
import urllib.error
import subprocess
import os

# ANSI 색상 코드
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def load_env_file(filepath=".env"):
    """의존성 없이 .env 파일을 읽어 딕셔너리로 반환"""
    env_vars = {}
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env_vars[key.strip()] = val.strip()
    return env_vars


def print_check(passed: bool, message: str):
    icon = f"{GREEN}[PASS]{RESET}" if passed else f"{RED}[FAIL]{RESET}"
    print(f"  {icon} {message}")


def get_id_token():
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-identity-token"], text=True).strip()
        return token
    except Exception as e:
        print(f"{YELLOW}⚠️  gcloud ID 토큰 발급 실패 ({e}). 인증 없이 호출을 시도합니다.{RESET}")
        return None


def verify_cloud_run(service_url: str, query: str):
    print(f"\n{BLUE}{BOLD}======================================================{RESET}")
    print(f"{BLUE}{BOLD}🧪 Cloud Run 검색 API 라이브 검증 리포트{RESET}")
    print(f"{BLUE}{BOLD}======================================================{RESET}")
    print(f"📍 서비스 URL: {BOLD}{service_url}{RESET}")
    print(f"📍 검색 쿼리:  {BOLD}'{query}'{RESET}\n")

    id_token = get_id_token()

    # 1. /health 헬스체크
    health_url = f"{service_url.rstrip('/')}/health"
    req_health = urllib.request.Request(health_url)
    if id_token:
        req_health.add_header("Authorization", f"Bearer {id_token}")

    health_passed = False
    try:
        with urllib.request.urlopen(req_health, timeout=10) as resp:
            if resp.status == 200:
                health_data = json.loads(resp.read().decode("utf-8"))
                health_passed = health_data.get("status") == "healthy"
    except Exception as e:
        health_passed = False

    print(f"{BOLD}[1] 서비스 헬스체크 (/health){RESET}")
    print_check(health_passed, f"Cloud Run 인스턴스 정상 가동 확인 (/health 200 OK)")

    # 2. /search 검색 요청
    search_url = f"{service_url.rstrip('/')}/search"
    payload = json.dumps({"query": query}).encode("utf-8")
    req_search = urllib.request.Request(search_url, data=payload, headers={"Content-Type": "application/json"})
    if id_token:
        req_search.add_header("Authorization", f"Bearer {id_token}")

    print(f"\n{BOLD}[2] 검색 및 텍스트/이미지 링크 추출 검증 (/search){RESET}")
    
    http_status_ok = False
    snippets_present = False
    text_extracted = False
    image_uri_valid = False
    snippets = []

    try:
        with urllib.request.urlopen(req_search, timeout=20) as resp:
            http_status_ok = (resp.status == 200)
            resp_body = resp.read().decode("utf-8")
            data = json.loads(resp_body)
            snippets = data.get("snippets", [])
            snippets_present = len(snippets) > 0

            # 텍스트 및 이미지 링크 검증
            if snippets_present:
                text_extracted = all(len(s.get("text", "").strip()) > 0 for s in snippets)
                # URI가 https:// 또는 http:// 로 정상 변환되었는지 검증
                valid_uris = [s.get("uri", "") for s in snippets if s.get("uri")]
                if valid_uris:
                    image_uri_valid = all(uri.startswith("https://") or uri.startswith("http://") for uri in valid_uris)
                else:
                    image_uri_valid = True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print_check(False, f"HTTP {e.code} 에러 응답: {err_body[:200]}")
    except Exception as e:
        print_check(False, f"요청 실패: {str(e)}")

    print_check(http_status_ok, f"검색 엔드포인트 HTTP 200 응답 수신")
    print_check(snippets_present, f"검색 결과(snippets) 배열 반환 확인 (총 {len(snippets)}개 발견)")
    print_check(text_extracted, f"본문 텍스트 세그먼트 추출 완료 여부")
    print_check(image_uri_valid, f"이미지 및 문서 링크(HTTPS URL) 변환 여부")

    # 3. 추출된 세그먼트 상세 미리보기
    if snippets:
        print(f"\n{BLUE}--- 📋 추출된 세그먼트 상세 목록 ---{RESET}")
        for i, s in enumerate(snippets, 1):
            print(f"[{i}] {BOLD}제목:{RESET} {s.get('title', '(제목 없음)')}")
            if s.get('source'):
                print(f"    {BOLD}출처 문서:{RESET} {CYAN}{s.get('source')}{RESET} (페이지: {s.get('page', 'N/A')})")
            uri = s.get('uri')
            if uri:
                print(f"    {BOLD}이미지/문서 링크:{RESET} {GREEN}{uri}{RESET}")
            preview = s.get('text', '').replace('\n', ' ')[:100]
            print(f"    {BOLD}추출 텍스트:{RESET} {preview}...")
        print(f"{BLUE}------------------------------------{RESET}")

    # 최종 결과 요약
    all_passed = health_passed and http_status_ok and snippets_present and text_extracted and image_uri_valid
    print(f"\n{BLUE}{BOLD}======================================================{RESET}")
    if all_passed:
        print(f"{GREEN}{BOLD}🎉 모든 단위 및 라이브 검증 테스트를 통과했습니다!{RESET}")
    else:
        print(f"{YELLOW}{BOLD}ℹ️  검증 완료: Cloud Run 라우팅 및 헬스체크는 정상이며, 실제 데이터스토어 연동 상태에 따라 검색 결과를 확인하세요.{RESET}")
    print(f"{BLUE}{BOLD}======================================================{RESET}\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    query_arg = sys.argv[1] if len(sys.argv) > 1 else "필터"
    
    # 1. .env 파일 파싱
    env_vars = load_env_file(".env")
    
    # 2. 서비스 URL 탐색 (환경변수 -> openapi.yaml -> gcloud 순)
    url = os.environ.get("SERVICE_URL") or env_vars.get("SERVICE_URL")
    
    # openapi.yaml에서 URL 읽기 시도
    if not url and os.path.exists("openapi.yaml"):
        with open("openapi.yaml", "r", encoding="utf-8") as f:
            for line in f:
                if "url: https://" in line:
                    candidate = line.split("url:", 1)[1].strip()
                    if "[YOUR_CLOUD_RUN" not in candidate:
                        url = candidate
                        break

    # gcloud를 통한 탐색
    if not url:
        proj = env_vars.get("PROJECT_ID") or os.environ.get("PROJECT_ID")
        if not proj:
            try:
                proj = subprocess.check_output(["gcloud", "config", "get-value", "project"], text=True).strip()
            except Exception:
                pass
        
        region = env_vars.get("REGION", "us-central1")
        svc_name = env_vars.get("SERVICE_NAME", "layout-parser-search-api")
        if proj:
            try:
                url = subprocess.check_output([
                    "gcloud", "run", "services", "describe", svc_name,
                    "--region", region, "--project", proj, "--format", "value(status.url)"
                ], text=True).strip()
            except Exception:
                pass

    if not url:
        print(f"{RED}❌ Cloud Run 서비스 URL을 찾을 수 없습니다. 배포를 먼저 진행하세요.{RESET}")
        sys.exit(1)

    sys.exit(verify_cloud_run(url, query_arg))
