from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

# プロトタイプでは学校種別を大阪教育大学の学生に固定する。
# 他大学に対応する際はこのデフォルト値を撤廃し、呼び出し側で必須指定にする。
DEFAULT_SCHOOL_TYPE = "国立大学"


@dataclass
class UserProfile:
    """レコメンド対象ユーザーの情報。ディスクへの永続化は行わない。"""

    residence: str
    faculty: str
    grade: str
    parent_income: int  # 円
    gpa: float
    major: str  # 例: "教科教育専攻-英語教育コース"
    field_tags: List[str]  # 例: ["理系"]
    school_type: str = DEFAULT_SCHOOL_TYPE


@dataclass
class ScholarshipConditions:
    """奨学金ごとの応募条件。None または空リストはその項目に制限なしを意味する。"""

    grades: Optional[List[str]] = None
    school_types: Optional[List[str]] = None
    faculties: Optional[List[str]] = None
    majors: Optional[List[str]] = None
    field_tags: Optional[List[str]] = None
    residences: Optional[List[str]] = None
    income_max: Optional[int] = None  # 円。世帯収入の上限
    gpa_min: Optional[float] = None


def _extract_section(text: Optional[str], label: str) -> Optional[str]:
    """description内の「【ラベル】本文」から本文だけを取り出す。見つからなければNone。"""
    if not text:
        return None
    match = re.search(rf"【{re.escape(label)}】(.*?)(?=【|\Z)", text, re.S)
    return match.group(1).strip() or None if match else None


@dataclass
class Scholarship:
    id: str
    name: str
    amount: Optional[int] = None  # 円。金額未定/不明の場合は None
    deadline: Optional[date] = None  # 締切未定/不明の場合は None
    deadline_note: Optional[str] = None  # 締切に関する補足（募集時期の目安など）
    url: Optional[str] = None  # 応募先未定/不明の場合は None
    description: Optional[str] = None  # 申込方法・併用可否・支給人数などをまとめた説明文
    num_recipients: Optional[str] = None  # 支給人数。「不明」等の自由文もあるためstr
    application_method: Optional[str] = None  # 申込方法
    combinability_note: Optional[str] = None  # 併用可否（カテゴリ別ではなく1本の自由文）
    conditions: ScholarshipConditions = field(default_factory=ScholarshipConditions)

    @staticmethod
    def from_dict(data: dict) -> "Scholarship":
        conditions = ScholarshipConditions(**data.get("conditions", {}))
        deadline_str = data.get("deadline")
        deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date() if deadline_str else None
        description = data.get("description")
        return Scholarship(
            id=data["id"],
            name=data["name"],
            amount=data.get("amount"),
            deadline=deadline,
            deadline_note=data.get("deadline_note"),
            url=data.get("url"),
            description=description,
            num_recipients=_extract_section(description, "支給人数"),
            application_method=_extract_section(description, "申込方法"),
            combinability_note=_extract_section(description, "併用可否"),
            conditions=conditions,
        )
