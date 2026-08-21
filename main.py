import os
import sys
import requests
import google.auth
from flask import Flask, request, jsonify

# 로컬 개발 환경에서 .env 파일 로드 지원
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# 환경변수 로드 및 기본값 설정
PROJECT_ID = os.environ.get("PROJECT_ID")
DATASTORE_ID = os.environ.get("DATASTORE_ID")
LOCATION = os.environ.get("LOCATION", "global")
COLLECTION_ID = os.environ.get("COLLECTION_ID", "default_collection")
SERVING_CONFIG_ID = os.environ.get("SERVING_CONFIG_ID", "default_search")


def get_project_id(creds, default_project):
    """프로젝트 ID 확인: 환경변수 -> 기본 자격증명 프로젝트 순으로 탐색"""
    if PROJECT_ID:
        return PROJECT_ID
    if default_project:
        return default_project
    raise ValueError("PROJECT_ID가 설정되지 않았습니다. .env 또는 환경변수를 확인해주세요.")


def search_layout_parser(query: str, project_id: str, datastore_id: str) -> dict:
    """Discovery Engine Search API를 호출하여 Layout Parser 텍스트/이미지 추출 및 매핑"""
    # Google ADC 인증 정보 로드
    creds, default_project = google.auth.default()
    if not creds.valid:
        from google.auth.transport.requests import Request
        creds.refresh(Request())

    effective_project_id = project_id or get_project_id(creds, default_project)
    
    if not datastore_id:
        raise ValueError("DATASTORE_ID가 설정되지 않았습니다. .env 또는 환경변수를 확인해주세요.")

    # Discovery Engine REST API 엔드포인트 URL
    url = (
        f"https://discoveryengine.googleapis.com/v1beta/"
        f"projects/{effective_project_id}/locations/{LOCATION}/collections/{COLLECTION_ID}/"
        f"dataStores/{datastore_id}/servingConfigs/{SERVING_CONFIG_ID}:search"
    )

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "x-goog-user-project": effective_project_id,
    }

    # layout-parser 검색 성능 향상을 위해 extractiveContentSpec 지정
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
    snippets = []

    # 반환 형식 매핑 처리
    for result in search_results.get("results", []):
        doc = result.get("document", {})
        struct_data = doc.get("derivedStructData", {})

        # 1순위: extractive_segments의 본문 내용 병합
        text_content = ""
        segments = struct_data.get("extractive_segments", [])
        if segments:
            text_content = " ".join([seg.get("content", "") for seg in segments if seg.get("content")])

        # 2순위: snippets 폴백
        if not text_content:
            raw_snippets = struct_data.get("snippets", [])
            if raw_snippets:
                text_content = " ".join([s.get("snippet", "") for s in raw_snippets if s.get("snippet")])

        # 3순위: annotationContent 폴백 (이미지 텍스트 인덱스 대응)
        if not text_content:
            annotation_content = struct_data.get("annotationContent", [])
            if annotation_content:
                text_content = " ".join(annotation_content)

        # GCS 경로 -> HTTPS 변환
        uri = struct_data.get("link", "")
        if uri.startswith("gs://"):
            uri = "https://storage.cloud.google.com/" + uri[5:]

        title = struct_data.get("title", doc.get("id", ""))

        if text_content:
            snippets.append({
                "title": title,
                "uri": uri,
                "text": text_content
            })

    print(f"[SEARCH_API] Found {len(snippets)} snippets for query: '{query}'", file=sys.stderr)
    return {
        "snippets": snippets
    }


@app.route("/health", methods=["GET"])
def health_check():
    """헬스체크 엔드포인트"""
    return jsonify({
        "status": "healthy",
        "project_id": PROJECT_ID or "(auto-detected)",
        "datastore_id": DATASTORE_ID or "(not-set)"
    }), 200


@app.route("/search", methods=["POST"])
def search_endpoint():
    """GECX/CXAS OpenAPI 연동용 검색 엔드포인트"""
    data = request.get_json() or {}
    query = data.get("query")
    
    # 요청 바디에서 프로젝트 및 데이터스토어 ID를 오버라이드할 수도 있도록 지원
    req_project_id = data.get("project_id", PROJECT_ID)
    req_datastore_id = data.get("datastore_id", DATASTORE_ID)

    print(f"[SEARCH_API] Received search request: query='{query}'", file=sys.stderr)

    if not query:
        return jsonify({"error": "Missing 'query' parameter in request body"}), 400

    try:
        result = search_layout_parser(query, req_project_id, req_datastore_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
