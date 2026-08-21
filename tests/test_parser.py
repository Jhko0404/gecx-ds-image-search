import unittest
import json
from main import transform_discovery_engine_response, convert_gs_uri, app


class TestLayoutParserTransformation(unittest.TestCase):
    """Discovery Engine Layout Parser 응답 변환 로직 단위 테스트"""

    def test_layout_parser_extractive_segments_and_image_uri(self):
        """1. Layout Parser 본문 세그먼트 추출 및 gs:// -> https://storage.cloud.google.com/ URL 변환 테스트"""
        mock_raw_response = {
            "results": [
                {
                    "id": "doc-001",
                    "document": {
                        "id": "doc-001",
                        "derivedStructData": {
                            "title": "공기청정기_사용설명서.pdf",
                            "link": "gs://cx-manual-bucket/images/filter_cleaning_guide.png",
                            "extractive_segments": [
                                {
                                    "pageNumber": "12",
                                    "content": "필터 청소 방법: 프리필터는 2주마다 진공청소기 또는 미온수로 세척하십시오."
                                },
                                {
                                    "pageNumber": "12",
                                    "content": "탈취필터 및 헤파필터는 물세척이 불가능하므로 주기적으로 교체해야 합니다."
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
        # 제목 검증
        self.assertEqual(snippet["title"], "공기청정기_사용설명서.pdf")
        # 이미지 URL 변환 검증 (https://storage.cloud.google.com/...)
        self.assertEqual(snippet["uri"], "https://storage.cloud.google.com/cx-manual-bucket/images/filter_cleaning_guide.png")
        # 본문 텍스트 병합 추출 검증
        self.assertIn("프리필터는 2주마다", snippet["text"])
        self.assertIn("헤파필터는 물세척이 불가능하므로", snippet["text"])

    def test_snippets_fallback(self):
        """2. extractive_segments 부재 시 snippets 폴백 검증"""
        mock_raw_response = {
            "results": [
                {
                    "document": {
                        "id": "text-doc-002",
                        "derivedStructData": {
                            "title": "텍스트_문서.pdf",
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
        self.assertEqual(result["snippets"][0]["uri"], "https://storage.googleapis.com/sample/doc.pdf")

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
        self.assertEqual(result["snippets"][0]["uri"], "https://storage.cloud.google.com/my-bucket/diagrams/wiring.png")

    def test_gs_uri_conversion(self):
        """4. gs:// 경로 변환 검증"""
        self.assertEqual(
            convert_gs_uri("gs://my-test-bucket/sub/image.jpg"),
            "https://storage.cloud.google.com/my-test-bucket/sub/image.jpg"
        )
        self.assertEqual(convert_gs_uri("https://example.com/a.png"), "https://example.com/a.png")

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
