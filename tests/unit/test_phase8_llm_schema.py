from pydantic import ValidationError

from app.schemas import LLMExtractionResponse


def test_phase8_llm_schema_accepts_valid_structured_output():
    payload = {
        "scholarship_name": "송은장학금",
        "summary_text": "평점과 소득분위를 함께 보는 장학금",
        "qualification": {
            "gpa_min": 3.2,
            "income_bracket_max": 8,
            "grade_levels": [3, 1, 3, 2],
            "enrollment_status": ["재학생", " ", "재학생"],
            "required_documents": ["장학금지원서", "", "성적증명서"],
        },
        "evidence": [
            {
                "field_name": "qualification.gpa_min",
                "document_id": 101,
                "block_id": "block-1",
                "page_number": 1,
                "quote_text": "직전학기 평점평균 3.20 이상인 재학생",
            }
        ],
    }

    response = LLMExtractionResponse.model_validate(payload)

    assert response.qualification.grade_levels == [1, 2, 3]
    assert response.qualification.enrollment_status == ["재학생", "재학생"]
    assert response.qualification.required_documents == ["장학금지원서", "성적증명서"]
    assert response.evidence[0].block_id == "block-1"


def test_phase8_llm_schema_rejects_evidence_without_block_id():
    payload = {
        "scholarship_name": "송은장학금",
        "qualification": {},
        "evidence": [
            {
                "field_name": "qualification.gpa_min",
                "document_id": 101,
                "page_number": 1,
                "quote_text": "직전학기 평점평균 3.20 이상인 재학생",
            }
        ],
    }

    try:
        LLMExtractionResponse.model_validate(payload)
    except ValidationError as exc:
        assert "block_id" in str(exc)
    else:
        raise AssertionError("Expected evidence without block_id to fail validation")


def test_phase8_llm_schema_rejects_unsupported_field_name():
    payload = {
        "scholarship_name": "송은장학금",
        "qualification": {},
        "evidence": [
            {
                "field_name": "qualification.unknown_field",
                "document_id": 101,
                "block_id": "block-1",
                "quote_text": "알 수 없는 필드",
            }
        ],
    }

    try:
        LLMExtractionResponse.model_validate(payload)
    except ValidationError as exc:
        assert "field_name" in str(exc)
    else:
        raise AssertionError("Expected unsupported field_name to fail validation")

