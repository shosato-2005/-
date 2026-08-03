import pytest

from models import Scholarship, ScholarshipConditions, UserProfile
from scoring import MAX_SCORE, WEIGHT_PER_CRITERION, calculate_score, score_to_stars


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


def make_scholarship(**condition_overrides):
    conditions = ScholarshipConditions(
        grades=["B1", "B2"],
        school_types=["国立大学"],
        faculties=["教育学部"],
        majors=["教科教育専攻-英語教育コース"],
        field_tags=["文系"],
        residences=["大阪府"],
        income_max=5000000,
        gpa_min=3.0,
    )
    for key, value in condition_overrides.items():
        setattr(conditions, key, value)
    return Scholarship(id="S001", name="テスト奨学金", conditions=conditions)


def test_calculate_score_full_match_gives_max_score_and_no_deductions():
    user = make_user()
    scholarship = make_scholarship()

    score, deductions = calculate_score(user, scholarship)

    assert score == MAX_SCORE
    assert deductions == []


def test_calculate_score_all_conditions_unrestricted_gives_max_score():
    user = make_user(residence="東京都", grade="D3", gpa=0.0, parent_income=50_000_000)
    scholarship = Scholarship(id="S002", name="無条件奨学金", conditions=ScholarshipConditions())

    score, deductions = calculate_score(user, scholarship)

    assert score == MAX_SCORE
    assert deductions == []


@pytest.mark.parametrize(
    "overrides,expected_label",
    [
        ({"grade": "B4"}, "学年"),
        ({"school_type": "私立大学"}, "学校種別"),
        ({"faculty": "理工学部"}, "学部・専攻"),
        ({"major": "教科教育専攻-数学教育コース"}, "専攻・コース"),
        ({"field_tags": ["理系"]}, "分野"),
        ({"residence": "三重県"}, "居住地"),
        ({"parent_income": 6_000_000}, "家計基準"),
        ({"gpa": 2.5}, "GPA"),
    ],
)
def test_calculate_score_deducts_exactly_one_criterion_on_single_mismatch(overrides, expected_label):
    user = make_user(**overrides)
    scholarship = make_scholarship()

    score, deductions = calculate_score(user, scholarship)

    assert score == MAX_SCORE - WEIGHT_PER_CRITERION
    assert deductions == [expected_label]


def test_calculate_score_field_tags_partial_overlap_counts_as_match():
    user = make_user(field_tags=["理系", "文系"])
    scholarship = make_scholarship(field_tags=["文系"])

    score, deductions = calculate_score(user, scholarship)

    assert score == MAX_SCORE
    assert deductions == []


def test_calculate_score_income_exactly_at_max_is_still_a_match():
    user = make_user(parent_income=5_000_000)
    scholarship = make_scholarship(income_max=5_000_000)

    score, _ = calculate_score(user, scholarship)

    assert score == MAX_SCORE


def test_calculate_score_gpa_exactly_at_min_is_still_a_match():
    user = make_user(gpa=3.0)
    scholarship = make_scholarship(gpa_min=3.0)

    score, _ = calculate_score(user, scholarship)

    assert score == MAX_SCORE


@pytest.mark.parametrize(
    "score,expected_stars",
    [
        (40, 5),
        (39, 4),
        (35, 4),
        (34, 3),
        (30, 3),
        (29, 2),
        (25, 2),
        (24, 1),
        (0, 1),
    ],
)
def test_score_to_stars_thresholds(score, expected_stars):
    assert score_to_stars(score) == expected_stars
