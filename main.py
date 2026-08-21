import os
import sys
import io
import urllib.parse

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
    from google.cloud import storage
except ImportError:
    google = None
    storage = None

try:
    from flask import Flask, request, jsonify, Response, send_file
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
SERVICE_URL = os.environ.get("SERVICE_URL", "")
GCS_FALLBACK_URL_PREFIX = os.environ.get("GCS_FALLBACK_URL_PREFIX", "https://storage.cloud.google.com/")


def get_project_id(creds, default_project):
    """프로젝트 ID 확인: 환경변수 -> 기본 자격증명 프로젝트 순으로 탐색"""
    if PROJECT_ID:
        return PROJECT_ID
    if default_project:
        return default_project
    raise ValueError("PROJECT_ID가 설정되지 않았습니다. .env 또는 환경변수를 확인해주세요.")


def convert_gs_uri_to_proxy_url(gs_uri: str, base_url: str = "") -> str:
    """
    gs:// 경로를 Cloud Run 자체 이미지 프록시 단축 URL로 변환.
    - 예시: gs://layout-parser-bk/coway-img1/manual.png
      -> https://[CLOUD_RUN_URL]/image/layout-parser-bk/coway-img1/manual.png
    """
    if not gs_uri or not gs_uri.startswith("gs://"):
        return gs_uri or ""

    raw_path = gs_uri[5:]  # bucket/path/to/image.png
    
    # Cloud Run 서비스 URL이 환경변수나 요청 컨텍스트에서 확인되는 경우 프록시 URL 생성
    effective_base = SERVICE_URL or base_url
    if effective_base:
        return f"{effective_base.rstrip('/')}/image/{raw_path}"

    # 기본 폴백: https://storage.cloud.google.com/...
    return GCS_FALLBACK_URL_PREFIX.rstrip("/") + "/" + raw_path


def transform_discovery_engine_response(search_results: dict, base_url: str = "") -> dict:
    """
    Discovery Engine 검색 응답을 파싱하여 CXAS 규격({ "snippets": [...] })으로 변환.
    - 텍스트 추출 우선순위:
      1) extractive_segments[].content (Layout Parser 본문)
      2) snippets[].snippet (일반 텍스트 폴백)
      3) annotationContent[] (이미지 텍스트 인덱스 폴백)
    - 링크 변환: Cloud Run 자체 초경량 이미지 프록시 URL
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

        # 3순위: annotationContent 폴백
        if not text_content:
            annotation_content = struct_data.get("annotationContent", [])
            if annotation_content:
                text_content = " ".join([str(item).strip() for item in annotation_content if item])

        # 이미지/문서 링크 변환 (Cloud Run 이미지 프록시 단축 URL)
        raw_uri = struct_data.get("link", "")
        uri = convert_gs_uri_to_proxy_url(raw_uri, base_url=base_url)

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


def search_layout_parser(query: str, project_id: str, datastore_id: str, location: str = None, base_url: str = "") -> dict:
    """Discovery Engine Search API를 호출하여 Layout Parser 텍스트/이미지 추출 및 매핑"""
    if google is None or requests is None:
        raise ImportError("google-auth 및 requests 패키지가 필요합니다.")

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
    result = transform_discovery_engine_response(search_results, base_url=base_url)
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
            "location": LOCATION,
            "service_url": SERVICE_URL or "(auto-detect)"
        }), 200


    @app.route("/search", methods=["POST"])
    def search_endpoint():
        """GECX/CXAS OpenAPI 연동용 검색 엔드포인트"""
        data = request.get_json() or {}
        query = data.get("query")
        
        req_project_id = data.get("project_id", PROJECT_ID)
        req_datastore_id = data.get("datastore_id", DATASTORE_ID)
        req_location = data.get("location", LOCATION)

        # 요청의 호스트 기반 URL 자동 감지
        base_url = SERVICE_URL or request.host_url.rstrip("/")

        print(f"[SEARCH_API] Received search request: query='{query}'", file=sys.stderr)

        if not query:
            return jsonify({"error": "Missing 'query' parameter in request body"}), 400

        try:
            result = search_layout_parser(query, req_project_id, req_datastore_id, req_location, base_url=base_url)
            return jsonify(result), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500


    @app.route("/image/<path:img_path>", methods=["GET"])
    def image_proxy(img_path):
        """
        Cloud Run 자체 이미지 프록시 서빙 엔드포인트.
        - GCS 버킷의 이미지를 내부 권한으로 직접 읽어 브라우저에 바이너리로 반환.
        - 외부에 버킷을 공개하지 않고도 로그인 없이 초고속 이미지 렌더링 지원.
        """
        try:
            # URL 디코딩 정규화
            decoded_path = urllib.parse.unquote(img_path)
            parts = decoded_path.split("/", 1)
            if len(parts) != 2:
                return jsonify({"error": "Invalid image path format. Expected bucket/object_name"}), 400

            bucket_name, blob_name = parts[0], parts[1]

            if google is None or storage is None:
                return jsonify({"error": "Google Cloud Storage SDK not installed"}), 500

            creds, default_project = google.auth.default()
            if not creds.valid:
                creds.refresh(Request())

            client = storage.Client(credentials=creds, project=default_project)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            if not blob.exists():
                return jsonify({"error": f"Image '{blob_name}' not found in bucket '{bucket_name}'"}), 404

            # 이미지 바이너리 다운로드 및 스트리밍 응답
            img_bytes = blob.download_as_bytes()
            content_type = blob.content_type or "image/png"

            response = Response(img_bytes, mimetype=content_type)
            # 브라우저 및 CDN 24시간 캐싱 헤더 부여
            response.headers["Cache-Control"] = "public, max-age=86400"
            return response

        except Exception as e:
            print(f"[IMAGE_PROXY_ERROR] Failed to serve image '{img_path}': {e}", file=sys.stderr)
            return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    if app:
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
    else:
        print("Flask is not installed. Please install requirements.txt to run the server.")
