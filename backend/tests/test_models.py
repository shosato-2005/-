from datetime import date

from models import DEFAULT_SCHOOL_TYPE, Scholarship, ScholarshipConditions, UserProfile


def test_scholarship_from_dict_parses_all_fields():
    data = {
        "id": "S001",
        "name": "テスト奨学金",
        "amount": 100000,
        "deadline": "2026-09-30",
        "url": "https://example.com",
        "description": "【申込方法】個人申請。【併用可否】他制度併用可。【支給人数】10名。",
        "conditions": {
            "grades": ["B1", "B2"],
            "school_types": ["国立大学"],
            "faculties": ["教育学部"],
            "majors": ["教科教育専攻-英語教育コース"],
            "field_tags": ["文系"],
            "residences": ["大阪府"],
            "income_max": 5000000,
            "gpa_min": 3.0,
        },
    }

    s = Scholarship.from_dict(data)

    assert s.id == "S001"
    assert s.name == "テスト奨学金"
    assert s.amount == 100000
    assert s.deadline == date(2026, 9, 30)
    assert s.url == "https://example.com"
    assert s.application_method == "個人申請。"
    assert s.combinability_note == "他制度併用可。"
    assert s.num_recipients == "10名。"
    assert s.conditions.grades == ["B1", "B2"]
    assert s.conditions.income_max == 5000000
    assert s.conditions.gpa_min == 3.0


def test_scholarship_from_dict_missing_deadline_becomes_none():
    data = {"id": "S002", "name": "締切未定奨学金"}

    s = Scholarship.from_dict(data)

    assert s.deadline is None


def test_scholarship_from_dict_null_deadline_becomes_none():
    data = {"id": "S003", "name": "締切null奨学金", "deadline": None}

    s = Scholarship.from_dict(data)

    assert s.deadline is None


def test_scholarship_from_dict_missing_amount_and_url_become_none():
    data = {"id": "S004", "name": "金額・URL未定奨学金"}

    s = Scholarship.from_dict(data)

    assert s.amount is None
    assert s.url is None


def test_scholarship_from_dict_missing_conditions_defaults_to_no_restriction():
    data = {"id": "S005", "name": "条件未指定奨学金"}

    s = Scholarship.from_dict(data)

    assert s.conditions == ScholarshipConditions()
    assert s.conditions.grades is None
    assert s.conditions.gpa_min is None


def test_scholarship_from_dict_missing_description_leaves_sections_none():
    data = {"id": "S006", "name": "説明文なし奨学金"}

    s = Scholarship.from_dict(data)

    assert s.description is None
    assert s.num_recipients is None
    assert s.application_method is None
    assert s.combinability_note is None


def test_scholarship_from_dict_description_without_matching_label_returns_none_for_that_section():
    data = {"id": "S007", "name": "一部ラベル欠落奨学金", "description": "【申込方法】個人申請。"}

    s = Scholarship.from_dict(data)

    assert s.application_method == "個人申請。"
    assert s.combinability_note is None
    assert s.num_recipients is None


def test_scholarship_conditions_none_or_empty_means_no_restriction():
    cond = ScholarshipConditions()

    assert cond.grades is None
    assert cond.school_types is None
    assert cond.faculties is None
    assert cond.majors is None
    assert cond.field_tags is None
    assert cond.residences is None
    assert cond.income_max is None
    assert cond.gpa_min is None


def test_userprofile_defaults_to_hardcoded_school_type():
    profile = UserProfile(
        residence="大阪府",
        faculty="教育学部",
        grade="B1",
        parent_income=5000000,
        gpa=3.0,
        major="教科教育専攻-英語教育コース",
        field_tags=["文系"],
    )

    assert profile.school_type == DEFAULT_SCHOOL_TYPE
