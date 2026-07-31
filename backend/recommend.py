from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import Scholarship, UserProfile
from scoring import calculate_score, score_to_stars

TOP_N: Optional[int] = None  # None = 件数上限なし（全件を返す）


def load_scholarships(json_path: str | Path) -> List[Scholarship]:
    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)
    return [Scholarship.from_dict(item) for item in raw]


def _format_result(scholarship: Scholarship, score: int, stars: int, deductions: List[str]) -> Dict[str, Any]:
    return {
        "scholarship_id": scholarship.id,
        "name": scholarship.name,
        "amount": scholarship.amount,
        "deadline": scholarship.deadline.isoformat() if scholarship.deadline else None,
        "deadline_note": scholarship.deadline_note,
        "stars": stars,
        # 星5つ（条件を完全に満たす）の場合は減点項目なし
        "deductions": deductions if stars <= 4 else [],
        "url": scholarship.url,
        "description": scholarship.description,
        "num_recipients": scholarship.num_recipients,
        "application_method": scholarship.application_method,
        "combinability_note": scholarship.combinability_note,
    }


def recommend(
    user: UserProfile,
    scholarships: List[Scholarship],
    top_n: Optional[int] = TOP_N,
) -> List[Dict[str, Any]]:
    """ユーザー情報と奨学金一覧から、星の高い順に並べて返す。

    top_n が None の場合は件数上限なしで全件を返す。
    同スコアの場合は締め切りが近いものを優先する。締切未定（None）のものは
    日付同士の比較ができないため、同スコア内では締切が判明しているものより後に置く。
    """
    scored = []
    for scholarship in scholarships:
        score, deductions = calculate_score(user, scholarship)
        stars = score_to_stars(score)
        scored.append((score, scholarship.deadline, scholarship, stars, deductions))

    scored.sort(key=lambda row: (-row[0], row[1] is None, row[1] or date.max))
    limited = scored if top_n is None else scored[:top_n]

    return [
        _format_result(scholarship, score, stars, deductions)
        for score, _deadline, scholarship, stars, deductions in limited
    ]
