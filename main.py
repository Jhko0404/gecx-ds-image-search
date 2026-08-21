import os
import sys
import datetime
import urllib.parse
import re

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
ENABLE_SIGNED_URL = os.environ.get("ENABLE_SIGNED_URL", "true").lower() in ("true", "1", "yes")
SIGNED_URL_EXPIRATION_MINUTES = int(os.environ.get("SIGNED_URL_EXPIRATION_MINUTES", "60"))
GCS_FALLBACK_URL_PREFIX = os.environ.get("GCS_FALLBACK_URL_PREFIX", "https://storage.cloud.google.com/")

# 버킷별 PDF 파일 목록 캐시 (불필요한 반복 GCS list API 호출 방지)
_BUCKET_PDF_CACHE = {}


def get_project_id(creds, default_project):
    """프로젝트 ID 확인: 환경변수 -> 기본 자격증명 프로젝트 순으로 탐색"""
    if PROJECT_ID:
        return PROJECT_ID
    if default_project:
        return default_project
    raise ValueError("PROJECT_ID가 설정되지 않았습니다. .env 또는 환경변수를 확인해주세요.")


def get_service_account_email(creds) -> str:
    """Cloud Run 인스턴스 또는 ADC에서 실행 중인 서비스 계정 이메일 확인"""
    sa_email = getattr(creds, "service_account_email", None)
    if sa_email and sa_email != "default":
        return sa_email

    # Cloud Run 메타데이터 서버를 통해 조회
    if requests is not None:
        try:
            resp = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                headers={"Metadata-Flavor": "Google"},
                timeout=2
            )
            if resp.status_code == 200:
                return resp.text.strip()
        except Exception:
            pass

    return ""


def convert_gs_uri_to_signed_or_https(gs_uri: str, creds=None, default_project=None, sa_email=None) -> str:
    """
    gs:// URI를 외부 사용자가 열람 가능한 V4 Signed URL 또는 HTTPS URL로 변환.
    - ENABLE_SIGNED_URL=true: 60분 임시 V4 Signed URL 생성 (외부 대중 고객도 접근 가능)
    - 실패 또는 비활성화 시: https://storage.cloud.google.com/... 로 폴백
    """
    if not gs_uri or not gs_uri.startswith("gs://"):
        return gs_uri or ""

    raw_path = gs_uri[5:]  # bucket/path/to/image.png
    parts = raw_path.split("/", 1)
    if len(parts) != 2:
        return GCS_FALLBACK_URL_PREFIX.rstrip("/") + "/" + raw_path

    bucket_name = parts[0]
    blob_name = urllib.parse.unquote(parts[1])

    if ENABLE_SIGNED_URL and google is not None and storage is not None:
        try:
            if creds is None:
                creds, default_project = google.auth.default()
                if not creds.valid:
                    creds.refresh(Request())

            if sa_email is None:
                sa_email = get_service_account_email(creds)

            client = storage.Client(credentials=creds, project=default_project)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            if sa_email:
                signed_url = blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.timedelta(minutes=SIGNED_URL_EXPIRATION_MINUTES),
                    method="GET",
                    service_account_email=sa_email,
                    access_token=creds.token
                )
                return signed_url
        except Exception as e:
            print(f"[SIGNED_URL_WARN] Failed to sign {gs_uri}: {e}", file=sys.stderr)

    return GCS_FALLBACK_URL_PREFIX.rstrip("/") + "/" + raw_path


def find_and_sign_pdf(bucket_name: str, source: str, raw_uri: str, creds=None, default_project=None, sa_email=None) -> str:
    """
    해당 세그먼트에 대응하는 원본 PDF 파일을 찾아 V4 Signed URL을 생성하여 반환.
    - raw_uri가 PDF인 경우 직접 서명
    - 이미지인 경우 버킷 내 매칭되는 모델명 PDF 탐색 및 서명
    """
    if not bucket_name:
        return ""

    # 1. raw_uri 자체가 이미 PDF인 경우
    if raw_uri.lower().endswith(".pdf"):
        return convert_gs_uri_to_signed_or_https(raw_uri, creds, default_project, sa_email)

    if not ENABLE_SIGNED_URL or google is None or storage is None:
        return ""

    try:
        if creds is None:
            creds, default_project = google.auth.default()
            if not creds.valid:
                creds.refresh(Request())

        if sa_email is None:
            sa_email = get_service_account_email(creds)

        client = storage.Client(credentials=creds, project=default_project)
        bucket = client.bucket(bucket_name)

        # 2. 버킷 내 PDF 파일 목록 캐싱
        if bucket_name not in _BUCKET_PDF_CACHE:
            try:
                pdf_list = [b.name for b in bucket.list_blobs() if b.name.lower().endswith(".pdf")]
                _BUCKET_PDF_CACHE[bucket_name] = pdf_list
                print(f"[PDF_CACHE] Cached {len(pdf_list)} PDF files for bucket {bucket_name}: {pdf_list}", file=sys.stderr)
            except Exception as e:
                print(f"[PDF_CACHE_WARN] Failed to list PDFs in {bucket_name}: {e}", file=sys.stderr)
                _BUCKET_PDF_CACHE[bucket_name] = []

        cached_pdfs = _BUCKET_PDF_CACHE.get(bucket_name, [])
        if not cached_pdfs:
            return ""

        # 3. source 또는 raw_uri에서 모델명 추출 (예: CHPI-5820L)
        target_str = f"{source} {raw_uri}"
        model_match = re.search(r"[A-Za-z]+-[0-9A-Za-z]+", target_str)
        model_name = model_match.group(0).lower() if model_match else ""

        matched_pdf_name = None
        if model_name:
            for pdf_name in cached_pdfs:
                if model_name in pdf_name.lower():
                    matched_pdf_name = pdf_name
                    break

        if not matched_pdf_name and cached_pdfs:
            matched_pdf_name = cached_pdfs[0]

        if matched_pdf_name:
            blob = bucket.blob(matched_pdf_name)
            if sa_email:
                signed_pdf_url = blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.timedelta(minutes=SIGNED_URL_EXPIRATION_MINUTES),
                    method="GET",
                    service_account_email=sa_email,
                    access_token=creds.token
                )
                return signed_pdf_url
            else:
                return GCS_FALLBACK_URL_PREFIX.rstrip("/") + "/" + bucket_name + "/" + urllib.parse.quote(matched_pdf_name)
    except Exception as e:
        print(f"[PDF_SIGN_WARN] Error signing PDF for bucket {bucket_name}: {e}", file=sys.stderr)

    return ""


def parse_source_and_page(struct_data: dict, doc_id: str):
    """
    Discovery Engine 메타데이터에서 직관적인 문서명(source)과 실제 페이지 번호(page)를 추출.
    - source: 문서명 (예: CHPI-5820L-Manual)
    - page: 페이지 번호 (예: 37)
    - title: 화면 표시용 종합 타이틀 (예: CHPI-5820L-Manual (p.37))
    """
    raw_uri = struct_data.get("link", "")
    title_field = struct_data.get("title", "")
    segments = struct_data.get("extractive_segments", [])
    annotation_content = struct_data.get("annotationContent", [])

    # 1. 실제 매뉴얼 페이지 번호 추출 (1순위: 파일명/doc_id의 _접미사, 2순위: extractive_segments, 3순위: annotationContent)
    page = ""
    target_str = raw_uri or doc_id
    m = re.search(r"_(\d+)(?:\.png|\.pdf)?(?:\?|$)", target_str)
    if m:
        page = m.group(1)

    if not page and segments and isinstance(segments, list):
        first_seg = segments[0]
        if first_seg.get("pageNumber"):
            page = str(first_seg.get("pageNumber")).strip()

    if not page and annotation_content:
        for ann in annotation_content:
            m = re.search(r"(?:page number is|페이지(?:는)?\s*)(\d+)", str(ann), re.IGNORECASE)
            if m:
                page = m.group(1)
                break

    # 2. 문서명(출처) 추출
    source = ""
    if title_field and not re.match(r"^\d{10,}-[a-f0-9-]+", title_field):
        source = title_field
    elif raw_uri.startswith("gs://"):
        path_parts = raw_uri[5:].split("/")
        if len(path_parts) >= 3:
            raw_folder = path_parts[-2]
            cleaned = re.sub(r"\(.*?\)", "", raw_folder).strip()
            source = cleaned or raw_folder
        else:
            source = path_parts[-1]

    if not source:
        source = "제품 매뉴얼"

    # 3. 에이전트 가독성을 위한 직관적인 title 구성
    if page:
        display_title = f"{source} (p.{page})"
    else:
        display_title = source

    return source, page, display_title


def transform_discovery_engine_response(search_results: dict) -> dict:
    """
    Discovery Engine 검색 응답을 파싱하여 CXAS 규격({ "snippets": [...] })으로 변환.
    - 텍스트 추출 우선순위:
      1) extractive_segments[].content (Layout Parser 본문)
      2) snippets[].snippet (일반 텍스트 폴백)
      3) annotationContent[] (이미지 텍스트 인덱스 폴백)
    - 출처 및 링크:
      - source: 문서명 (예: CHPI-5820L-Manual)
      - page: 페이지 번호 (예: 37)
      - title: 직관적인 출처 타이틀 (예: CHPI-5820L-Manual (p.37))
      - uri: 다이어그램 이미지 V4 Signed URL
      - pdf_uri: 원본 매뉴얼 PDF V4 Signed URL
    """
    snippets = []
    if not isinstance(search_results, dict):
        return {"snippets": []}

    # 자격증명 1회 초기화로 서명 속도 극대화
    creds = None
    default_project = None
    sa_email = None
    if ENABLE_SIGNED_URL and google is not None:
        try:
            creds, default_project = google.auth.default()
            if not creds.valid:
                creds.refresh(Request())
            sa_email = get_service_account_email(creds)
        except Exception:
            pass

    for result in search_results.get("results", []):
        doc = result.get("document", {})
        struct_data = doc.get("derivedStructData", {})
        doc_id = doc.get("id", "")

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

        # 이미지 및 PDF 서명 링크 생성
        raw_uri = struct_data.get("link", "")
        bucket_name = ""
        if raw_uri.startswith("gs://"):
            bucket_name = raw_uri[5:].split("/")[0]

        uri = convert_gs_uri_to_signed_or_https(raw_uri, creds, default_project, sa_email)

        # 출처(문서명, 페이지, 직관적 타이틀) 파싱
        source, page, title = parse_source_and_page(struct_data, doc_id)

        # 원본 PDF 파일 검색 및 V4 Signed URL 발급
        pdf_uri = find_and_sign_pdf(bucket_name, source, raw_uri, creds, default_project, sa_email)

        if text_content:
            snippet_item = {
                "title": title,
                "source": source,
                "page": page,
                "uri": uri,
                "pdf_uri": pdf_uri,
                "text": text_content
            }
            snippets.append(snippet_item)

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
    """Discovery Engine Search API를 호출하여 Layout Parser 텍스트/이미지/PDF출처 추출 및 매핑"""
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
            "location": LOCATION,
            "signed_url_enabled": ENABLE_SIGNED_URL,
            "signed_url_expiration_minutes": SIGNED_URL_EXPIRATION_MINUTES
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
