import unittest
import json
from main import transform_discovery_engine_response, convert_gs_uri_to_signed_or_https, parse_source_and_page, app


class TestLayoutParserTransformation(unittest.TestCase):
    """Discovery Engine Layout Parser 응답 변환 로직 단위 테스트"""

    def test_layout_parser_extractive_segments_and_citations(self):
        """1. Layout Parser 본문 세그먼트, 이미지 URL, 출처(source) 및 페이지(page) 추출 검증"""
        mock_raw_response = {
            "results": [
                {
                    "id": "1782537242706-e6cbd739-ef97-426e-8ed6-188b9ae2cef8_36",
                    "document": {
                        "id": "1782537242706-e6cbd739-ef97-426e-8ed6-188b9ae2cef8_36",
                        "derivedStructData": {
                            "link": "gs://layout-parser-bk/coway-img1/CHPI-5820L-Manual(acrobat-png)/1782537242706-e6cbd739-ef97-426e-8ed6-188b9ae2cef8_36.png",
                            "extractive_segments": [
                                {
                                    "pageNumber": "36",
                                    "content": "4. Disposal Method for Used Replacement Filters (사용 후 교체 필터 처리 방법)"
                                }
                            ]
                        }
                    }
                }
            ]
        }

        result = transform_discovery_engine_response(mock_raw_response)

        self.assertIn("snippets", result)
        self.assertEqual(len(result["snippets"]), 1)

        snippet = result["snippets"][0]
        # 출처 및 페이지 검증
        self.assertEqual(snippet["source"], "CHPI-5820L-Manual")
        self.assertEqual(snippet["page"], "36")
        self.assertEqual(snippet["title"], "CHPI-5820L-Manual (p.36)")
        # 본문 및 링크 검증
        self.assertIn("사용 후 교체 필터 처리 방법", snippet["text"])
        self.assertTrue(snippet["uri"].startswith("http"))

    def test_snippets_fallback(self):
        """2. extractive_segments 부재 시 snippets 폴백 검증"""
        mock_raw_response = {
            "results": [
                {
                    "document": {
                        "id": "text-doc-002",
                        "derivedStructData": {
                            "title": "공기청정기_매뉴얼.pdf",
                            "link": "https://storage.googleapis.com/sample/doc.pdf",
                            "snippets": [
                                {"snippet": "일반 텍스트 스니펫 내용입니다."}
                            ]
                        }
                    }
                }
            ]
        }

        result = transform_discovery_engine_response(mock_raw_response)
        self.assertEqual(len(result["snippets"]), 1)
        self.assertEqual(result["snippets"][0]["text"], "일반 텍스트 스니펫 내용입니다.")
        self.assertEqual(result["snippets"][0]["source"], "공기청정기_매뉴얼.pdf")

    def test_annotation_content_fallback(self):
        """3. snippets 부재 시 annotationContent(이미지 OCR 인덱스) 폴백 검증"""
        mock_raw_response = {
            "results": [
                {
                    "document": {
                        "id": "ocr-doc-003",
                        "derivedStructData": {
                            "title": "다이어그램_이미지.png",
                            "link": "gs://my-bucket/diagrams/wiring.png",
                            "annotationContent": [
                                "전원 스위치 ON/OFF 다이어그램",
                                "적색 LED: 필터 점검 요망"
                            ]
                        }
                    }
                }
            ]
        }

        result = transform_discovery_engine_response(mock_raw_response)
        self.assertEqual(len(result["snippets"]), 1)
        self.assertIn("전원 스위치 ON/OFF", result["snippets"][0]["text"])
        self.assertIn("적색 LED", result["snippets"][0]["text"])

    def test_gs_uri_conversion_fallback(self):
        """4. gs:// URI 안전한 HTTPS 폴백 변환 검증"""
        converted = convert_gs_uri_to_signed_or_https("gs://my-test-bucket/sub/image.jpg")
        self.assertTrue(converted.startswith("http"))
        self.assertIn("my-test-bucket/sub/image.jpg", converted)

    def test_empty_and_corrupt_data_handling(self):
        """5. 빈 응답 및 필드 누락 시 안전한 빈 리스트 반환 검증"""
        self.assertEqual(transform_discovery_engine_response({}), {"snippets": []})
        self.assertEqual(transform_discovery_engine_response({"results": []}), {"snippets": []})
        self.assertEqual(transform_discovery_engine_response({"results": [{"document": {"id": "corrupt"}}]}), {"snippets": []})
        self.assertEqual(transform_discovery_engine_response(None), {"snippets": []})


class TestFlaskEndpoints(unittest.TestCase):
    """Flask 웹 서버 엔드포인트 HTTP 레벨 단위 테스트"""

    def setUp(self):
        if app is None:
            self.skipTest("Flask가 설치되지 않아 HTTP 엔드포인트 단위 테스트를 건너뜁니다.")
        self.client = app.test_client()

    def test_health_endpoint(self):
        """헬스체크 /health GET 응답 검증"""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data.get("status"), "healthy")

    def test_search_missing_query(self):
        """검색 /search POST 요청 시 query 파라미터 누락 400 에러 검증"""
        response = self.client.post("/search", json={})
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
