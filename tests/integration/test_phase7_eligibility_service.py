from app.schemas import StudentProfile
from app.services import ScholarshipEligibilityService
from tests.support.eligibility_seed import seed_phase7_eligibility_data
from tests.support.search_seed import REFERENCE_TIME


def test_phase7_eligibility_service_returns_all_decision_types(monkeypatch, tmp_path):
    seed_phase7_eligibility_data(monkeypatch, tmp_path)

    response = ScholarshipEligibilityService().evaluate_profile(
        StudentProfile(
            gpa=3.5,
            income_bracket=6,
            enrollment_status="재학생",
        ),
        reference_time=REFERENCE_TIME,
        limit=10,
    )

    decision_by_name = {
        item.scholarship_name: item.decision
        for item in response.items
    }
    explanation_by_name = {
        item.scholarship_name: item.explanation
        for item in response.items
    }
    missing_fields_by_name = {
        item.scholarship_name: item.missing_fields
        for item in response.items
    }

    assert decision_by_name["송은장학금"] == "eligible"
    assert decision_by_name["최우수성적장학금"] == "ineligible"
    assert decision_by_name["국가근로장학금"] == "expired"
    assert decision_by_name["새내기장학금"] == "insufficient_info"
    assert "지원 자격을 충족" in explanation_by_name["송은장학금"]
    assert "평점 3.50" in explanation_by_name["최우수성적장학금"]
    assert missing_fields_by_name["새내기장학금"] == ["grade_level"]


def test_phase7_eligibility_service_prioritizes_query_matches(monkeypatch, tmp_path):
    seed_phase7_eligibility_data(monkeypatch, tmp_path)

    response = ScholarshipEligibilityService().evaluate_profile(
        StudentProfile(
            gpa=3.5,
            income_bracket=6,
            enrollment_status="재학생",
        ),
        query="송은장학금 소득분위 8분위",
        reference_time=REFERENCE_TIME,
        limit=10,
    )

    assert response.count >= 1
    assert response.items[0].scholarship_name == "송은장학금"
    assert response.items[0].decision == "eligible"
    assert response.items[0].provenance
