import json
from datetime import date

from models import Scholarship, ScholarshipConditions, UserProfile
from recommend import load_scholarships, recommend


def make_user(**overrides):
    defaults = dict(
        residence="大阪府",
        faculty="教育学部",
        grade="B2",
        parent_income=4000000,
        gpa=3.2,
        major="教科教育専攻-英語教育コース",
        field_tags=["文系"],
        school_type="国立大学",
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def make_scholarship(id_, *, deadline=None, grades=None, amount=None, deadline_note=None, description=None):
    return Scholarship(
        id=id_,
        name=f"奨学金{id_}",
        amount=amount,
        deadline=deadline,
        deadline_note=deadline_note,
        description=description,
        conditions=ScholarshipConditions(grades=grades),
    )


def test_recommend_sorts_by_score_descending():
    user = make_user(grade="B2")
    low_score = make_scholarship("LOW", grades=["B4"])  # 学年が不一致で減点
    high_score = make_scholarship("HIGH", grades=["B2"])  # 完全一致

    results = recommend(user, [low_score, high_score])

    assert [r["scholarship_id"] for r in results] == ["HIGH", "LOW"]


def test_recommend_deadline_ascending_is_tiebreak_within_same_score():
    user = make_user()
    later = make_scholarship("LATER", deadline=date(2026, 12, 1))
    sooner = make_scholarship("SOONER", deadline=date(2026, 9, 1))

    results = recommend(user, [later, sooner])

    assert [r["scholarship_id"] for r in results] == ["SOONER", "LATER"]


def test_recommend_unknown_deadline_sorts_after_known_deadline_within_same_score():
    user = make_user()
    unknown = make_scholarship("UNKNOWN", deadline=None)
    known = make_scholarship("KNOWN", deadline=date(2026, 9, 1))

    # 締切不明を先に渡しても、既知の締切が前に来ることを確認する
    results = recommend(user, [unknown, known])

    assert [r["scholarship_id"] for r in results] == ["KNOWN", "UNKNOWN"]


def test_recommend_top_n_limits_number_of_results():
    user = make_user()
    scholarships = [make_scholarship(f"S{i}") for i in range(5)]

    results = recommend(user, scholarships, top_n=2)

    assert len(results) == 2


def test_recommend_top_n_none_returns_all_results():
    user = make_user()
    scholarships = [make_scholarship(f"S{i}") for i in range(5)]

    results = recommend(user, scholarships, top_n=None)

    assert len(results) == 5


def test_recommend_deductions_hidden_when_stars_is_five():
    user = make_user(grade="B2")
    scholarship = make_scholarship("PERFECT", grades=["B2"])

    result = recommend(user, [scholarship])[0]

    assert result["stars"] == 5
    assert result["deductions"] == []


def test_recommend_deductions_shown_when_stars_below_five():
    user = make_user(grade="B2")
    scholarship = make_scholarship("MISMATCH", grades=["B4"])

    result = recommend(user, [scholarship])[0]

    assert result["stars"] < 5
    assert "学年" in result["deductions"]


def test_recommend_passes_through_optional_fields():
    user = make_user()
    scholarship = make_scholarship(
        "FULL",
        amount=None,
        deadline=None,
        deadline_note="随時",
        description="【申込方法】個人申請。",
    )

    result = recommend(user, [scholarship])[0]

    assert result["amount"] is None
    assert result["deadline"] is None
    assert result["deadline_note"] == "随時"
    assert result["description"] == "【申込方法】個人申請。"


def test_load_scholarships_reads_json_file(tmp_path):
    data = [
        {
            "id": "S001",
            "name": "テスト奨学金",
            "amount": 100000,
            "deadline": "2026-10-01",
            "url": "https://example.com",
            "conditions": {},
        }
    ]
    json_path = tmp_path / "scholarships.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    scholarships = load_scholarships(json_path)

    assert len(scholarships) == 1
    assert scholarships[0].id == "S001"
    assert scholarships[0].deadline == date(2026, 10, 1)
