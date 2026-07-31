from __future__ import annotations

from typing import Callable, List, Tuple

from models import Scholarship, ScholarshipConditions, UserProfile

WEIGHT_PER_CRITERION = 5
MAX_SCORE = 40  # 8項目 x 5点


def _match_grade(user: UserProfile, cond: ScholarshipConditions) -> bool:
    return not cond.grades or user.grade in cond.grades


def _match_school_type(user: UserProfile, cond: ScholarshipConditions) -> bool:
    return not cond.school_types or user.school_type in cond.school_types


def _match_faculty(user: UserProfile, cond: ScholarshipConditions) -> bool:
    return not cond.faculties or user.faculty in cond.faculties


def _match_major(user: UserProfile, cond: ScholarshipConditions) -> bool:
    return not cond.majors or user.major in cond.majors


def _match_field_tags(user: UserProfile, cond: ScholarshipConditions) -> bool:
    return not cond.field_tags or bool(set(user.field_tags) & set(cond.field_tags))


def _match_residence(user: UserProfile, cond: ScholarshipConditions) -> bool:
    return not cond.residences or user.residence in cond.residences


def _match_income(user: UserProfile, cond: ScholarshipConditions) -> bool:
    return cond.income_max is None or user.parent_income <= cond.income_max


def _match_gpa(user: UserProfile, cond: ScholarshipConditions) -> bool:
    return cond.gpa_min is None or user.gpa >= cond.gpa_min


# (内部キー, 表示ラベル, 判定関数) の順で評価する
CRITERIA: List[Tuple[str, str, Callable[[UserProfile, ScholarshipConditions], bool]]] = [
    ("grade", "学年", _match_grade),
    ("school_type", "学校種別", _match_school_type),
    ("faculty", "学部・専攻", _match_faculty),
    ("major", "専攻・コース", _match_major),
    ("field_tags", "分野", _match_field_tags),
    ("residence", "居住地", _match_residence),
    ("income", "家計基準", _match_income),
    ("gpa", "GPA", _match_gpa),
]


def calculate_score(user: UserProfile, scholarship: Scholarship) -> Tuple[int, List[str]]:
    """合計点と、条件を満たさなかった項目のラベル一覧を返す。"""
    score = 0
    deductions: List[str] = []
    for _key, label, match_fn in CRITERIA:
        if match_fn(user, scholarship.conditions):
            score += WEIGHT_PER_CRITERION
        else:
            deductions.append(label)
    return score, deductions


def score_to_stars(score: int) -> int:
    # 星5つは満点（全項目が条件を満たす）の場合のみ。1項目でも外れれば星が1段階下がる。
    if score >= MAX_SCORE:
        return 5
    if score >= MAX_SCORE - WEIGHT_PER_CRITERION:
        return 4
    if score >= MAX_SCORE - 2 * WEIGHT_PER_CRITERION:
        return 3
    if score >= MAX_SCORE - 3 * WEIGHT_PER_CRITERION:
        return 2
    return 1
