import os
import sys

# 로컬 개발 환경에서 .env 파일 로드 지원
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    requests = None

try:
    import google.auth
    from google.auth.transport.requests import Request
except ImportError:
    google = None

try:
    from flask import Flask, request, jsonify
    app = Flask(__name__)
except ImportError:
    Flask = None
    app = None

# 환경변수 로드 및 기본값 설정
PROJECT_ID = os.environ.get("PROJECT_ID")
DATASTORE_ID = os.environ.get("DATASTORE_ID")
LOCATION = os.environ.get("LOCATION", "global")
COLLECTION_ID = os.environ.get("COLLECTION_ID", "default_collection")
SERVING_CONFIG_ID = os.environ.get("SERVING_CONFIG_ID", "default_search")
GCS_URL_PREFIX = os.environ.get("GCS_URL_PREFIX", "https://storage.cloud.google.com/")


def get_project_id(creds, default_project):
    """프로젝트 ID 확인: 환경변수 -> 기본 자격증명 프로젝트 순으로 탐색"""
    if PROJECT_ID:
        return PROJECT_ID
    if default_project:
        return default_project
    raise ValueError("PROJECT_ID가 설정되지 않았습니다. .env 또는 환경변수를 확인해주세요.")


def convert_gs_uri(uri: str) -> str:
    """gs:// 경로를 HTTPS 주소(https://storage.cloud.google.com/...)로 변환"""
    if uri and uri.startswith("gs://"):
        return GCS_URL_PREFIX.rstrip("/") + "/" + uri[5:]
    return uri or ""


def transform_discovery_engine_response(search_results: dict) -> dict:
    """
    Discovery Engine 검색 응답을 파싱하여 CXAS 규격({ "snippets": [...] })으로 변환.
    - 텍스트 추출 우선순위:
      1) extractive_segments[].content (Layout Parser 본문)
      2) snippets[].snippet (일반 텍스트 폴백)
      3) annotationContent[] (이미지 텍스트 인덱스 폴백)
    - 링크 변환: gs:// 경로를 https://storage.cloud.google.com/... URL로 변환
    """
    snippets = []
    if not isinstance(search_results, dict):
        return {"snippets": []}

    for result in search_results.get("results", []):
        doc = result.get("document", {})
        struct_data = doc.get("derivedStructData", {})

        # 1순위: extractive_segments의 본문 내용 병합
        text_content = ""
        segments = struct_data.get("extractive_segments", [])
        if segments:
            text_content = " ".join([seg.get("content", "").strip() for seg in segments if seg.get("content")])

        # 2순위: snippets 폴백
        if not text_content:
            raw_snippets = struct_data.get("snippets", [])
            if raw_snippets:
                text_content = " ".join([s.get("snippet", "").strip() for s in raw_snippets if s.get("snippet")])

        # 3순위: annotationContent 폴백 (이미지 텍스트 인덱스 대응)
        if not text_content:
            annotation_content = struct_data.get("annotationContent", [])
            if annotation_content:
                text_content = " ".join([str(item).strip() for item in annotation_content if item])

        # GCS 경로 -> HTTPS 변환 (https://storage.cloud.google.com/...)
        raw_uri = struct_data.get("link", "")
        uri = convert_gs_uri(raw_uri)

        title = struct_data.get("title", doc.get("id", ""))

        if text_content:
            snippets.append({
                "title": title,
                "uri": uri,
                "text": text_content
            })

    return {
        "snippets": snippets
    }


def get_discovery_engine_host(location: str) -> str:
    """리전별 Discovery Engine 엔드포인트 호스트 반환"""
    loc = (location or "global").lower()
    if loc in ("global", ""):
        return "discoveryengine.googleapis.com"
    return f"{loc}-discoveryengine.googleapis.com"


def search_layout_parser(query: str, project_id: str, datastore_id: str, location: str = None) -> dict:
    """Discovery Engine Search API를 호출하여 Layout Parser 텍스트/이미지 추출 및 매핑"""
    if google is None or requests is None:
        raise ImportError("google-auth 및 requests 패키지가 필요합니다.")

    # Google ADC 인증 정보 로드
    creds, default_project = google.auth.default()
    if not creds.valid:
        creds.refresh(Request())

    effective_project_id = project_id or get_project_id(creds, default_project)
    effective_location = location or LOCATION or "global"
    
    if not datastore_id:
        raise ValueError("DATASTORE_ID가 설정되지 않았습니다. .env 또는 환경변수를 확인해주세요.")

    host = get_discovery_engine_host(effective_location)
    url = (
        f"https://{host}/v1beta/"
        f"projects/{effective_project_id}/locations/{effective_location}/collections/{COLLECTION_ID}/"
        f"dataStores/{datastore_id}/servingConfigs/{SERVING_CONFIG_ID}:search"
    )

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "x-goog-user-project": effective_project_id,
    }

    payload = {
        "query": query,
        "pageSize": 5,
        "contentSearchSpec": {
            "extractiveContentSpec": {
                "maxExtractiveSegmentCount": 10
            },
            "snippetSpec": {
                "maxSnippetCount": 1
            }
        }
    }

    print(f"[SEARCH_API] Calling Discovery Engine: url={url}, query='{query}'", file=sys.stderr)
    response = requests.post(url, headers=headers, json=payload, timeout=15)
    
    if response.status_code != 200:
        error_msg = f"Search API failed with status {response.status_code}: {response.text}"
        print(f"[SEARCH_API_ERROR] {error_msg}", file=sys.stderr)
        raise Exception(error_msg)

    search_results = response.json()
    result = transform_discovery_engine_response(search_results)
    print(f"[SEARCH_API] Found {len(result['snippets'])} snippets for query: '{query}'", file=sys.stderr)
    return result


if app:
    @app.route("/health", methods=["GET"])
    def health_check():
        """헬스체크 엔드포인트"""
        return jsonify({
            "status": "healthy",
            "project_id": PROJECT_ID or "(auto-detected)",
            "datastore_id": DATASTORE_ID or "(not-set)",
            "location": LOCATION
        }), 200


    @app.route("/search", methods=["POST"])
    def search_endpoint():
        """GECX/CXAS OpenAPI 연동용 검색 엔드포인트"""
        data = request.get_json() or {}
        query = data.get("query")
        
        req_project_id = data.get("project_id", PROJECT_ID)
        req_datastore_id = data.get("datastore_id", DATASTORE_ID)
        req_location = data.get("location", LOCATION)

        print(f"[SEARCH_API] Received search request: query='{query}'", file=sys.stderr)

        if not query:
            return jsonify({"error": "Missing 'query' parameter in request body"}), 400

        try:
            result = search_layout_parser(query, req_project_id, req_datastore_id, req_location)
            return jsonify(result), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    if app:
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
    else:
        print("Flask is not installed. Please install requirements.txt to run the server.")
