from fastapi.testclient import TestClient

from app.main import create_app
from tests.support.eligibility_seed import seed_phase7_eligibility_data
from tests.support.search_seed import REFERENCE_TIME


def test_phase7_eligibility_api_returns_decisions_and_explanations(monkeypatch, tmp_path):
    seed_phase7_eligibility_data(monkeypatch, tmp_path)
    monkeypatch.setattr("app.services.search.now_in_seoul", lambda: REFERENCE_TIME)
    monkeypatch.setattr("app.services.eligibility.now_in_seoul", lambda: REFERENCE_TIME)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/scholarships/eligibility",
        json={
            "profile": {
                "gpa": 3.5,
                "income_bracket": 6,
                "enrollment_status": "재학생",
            },
            "limit": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    decision_by_name = {
        item["scholarship_name"]: item["decision"]
        for item in body["items"]
    }

    assert body["count"] == 4
    assert decision_by_name["송은장학금"] == "eligible"
    assert decision_by_name["최우수성적장학금"] == "ineligible"
    assert decision_by_name["국가근로장학금"] == "expired"
    assert decision_by_name["새내기장학금"] == "insufficient_info"
    assert body["items"][0]["explanation"]


def test_phase7_eligibility_api_accepts_query(monkeypatch, tmp_path):
    seed_phase7_eligibility_data(monkeypatch, tmp_path)
    monkeypatch.setattr("app.services.search.now_in_seoul", lambda: REFERENCE_TIME)
    monkeypatch.setattr("app.services.eligibility.now_in_seoul", lambda: REFERENCE_TIME)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/scholarships/eligibility",
        json={
            "profile": {
                "gpa": 3.5,
                "income_bracket": 6,
                "enrollment_status": "재학생",
            },
            "query": "송은장학금 소득분위 8분위",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert body["items"][0]["scholarship_name"] == "송은장학금"
    assert body["items"][0]["decision"] == "eligible"
