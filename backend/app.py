from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

from majors import MAJOR_TO_FACULTY, MAJOR_TO_FIELD, MAJORS
from models import DEFAULT_SCHOOL_TYPE, Scholarship, UserProfile
from recommend import load_scholarships, recommend

DATA_PATH = Path(__file__).parent / "data" / "scholarships_sample.json"

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

GRADES = ["B1", "B2", "B3", "B4", "M1", "M2", "D1", "D2", "D3"]

DISPLAY_COUNT_OPTIONS = {"10件": 10, "15件": 15, "全件": None}

_NUMERIC_RECIPIENTS_RE = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*)\s*名")


def _recipients_sort_key(num_recipients: Optional[str]) -> Tuple[int, int]:
    """支給人数の並び替えキー。数字明記 > 若干名 > 未定/不明/記載なし の順。

    テキスト中に複数の人数が出てくる場合（例: 「一般40名、家計急変10名」）は
    最大値を採用する。カンマ区切りの桁（例: 「3,500名」）も数値として扱う。
    """
    if not num_recipients:
        return (2, 0)
    normalized = unicodedata.normalize("NFKC", num_recipients)
    numbers = [int(m.replace(",", "")) for m in _NUMERIC_RECIPIENTS_RE.findall(normalized)]
    if numbers:
        return (0, -max(numbers))
    if "若干名" in normalized:
        return (1, 0)
    return (2, 0)


def _amount_sort_key(amount: Optional[int]) -> Tuple[bool, int]:
    return (amount is None, -(amount or 0))


SORT_OPTIONS = {
    "スコア順": None,
    "総支給金額が多い順": lambda r: _amount_sort_key(r["amount"]),
    "支給人数が多い順": lambda r: _recipients_sort_key(r["num_recipients"]),
}


def _sort_results(results: List[Dict], sort_label: str) -> List[Dict]:
    key_fn = SORT_OPTIONS.get(sort_label)
    if key_fn is None:
        return results
    return sorted(results, key=key_fn)


@st.cache_data
def _load_scholarships(path: str) -> List[Scholarship]:
    return load_scholarships(path)


def _stars_display(stars: int) -> str:
    return "★" * stars + "☆" * (5 - stars)


def _deadline_display(result: Dict) -> str:
    if result["deadline"] and result["deadline_note"]:
        return f"{result['deadline']}（{result['deadline_note']}）"
    if result["deadline"]:
        return result["deadline"]
    if result["deadline_note"]:
        return result["deadline_note"]
    return "締め切り要確認"


def _render_result(result: Dict) -> None:
    amount_display = f"{result['amount']:,}円" if result["amount"] is not None else "金額要確認"

    with st.container(border=True):
        col_main, col_stars = st.columns([3, 1])
        with col_main:
            st.subheader(result["name"])
            st.write(f"金額: {amount_display}　|　締切: {_deadline_display(result)}")
        with col_stars:
            st.markdown(f"### {_stars_display(result['stars'])}")

        if result["num_recipients"]:
            st.write(f"支給人数: {result['num_recipients']}")
        if result["application_method"]:
            st.write(f"申込方法: {result['application_method']}")
        if result["combinability_note"]:
            st.write(f"併用可否: {result['combinability_note']}")
        if result["description"]:
            st.caption(result["description"])

        if result["deductions"]:
            st.caption("減点項目: " + "、".join(result["deductions"]))

        if result["url"]:
            st.link_button("応募ページへ", result["url"])
        else:
            st.caption("応募先要確認")


def main() -> None:
    st.set_page_config(page_title="奨学金レコメンドツール", page_icon="🎓")
    st.title("🎓 奨学金レコメンドツール")
    st.caption("大阪教育大学の学生向けプロトタイプ。入力情報はこの画面の表示のみに使われ、保存されません。")

    scholarships = _load_scholarships(str(DATA_PATH))

    with st.form("user_profile_form"):
        st.text_input("学校種別", value=DEFAULT_SCHOOL_TYPE, disabled=True)

        col1, col2 = st.columns(2)
        with col1:
            residence = st.selectbox("居住地", PREFECTURES, index=PREFECTURES.index("大阪府"))
            grade = st.selectbox("学年", GRADES)
        with col2:
            major = st.selectbox("専攻・コース", MAJORS)
            gpa = st.number_input("GPA", min_value=0.0, max_value=4.0, value=3.0, step=0.01, format="%.2f")

        parent_income = st.number_input(
            "両親の年収（世帯収入・円）", min_value=0, max_value=50_000_000, value=5_000_000, step=100_000
        )

        submitted = st.form_submit_button("奨学金をレコメンドする")

    if submitted:
        user = UserProfile(
            residence=residence,
            faculty=MAJOR_TO_FACULTY.get(major, ""),
            grade=grade,
            parent_income=int(parent_income),
            gpa=float(gpa),
            major=major,
            field_tags=MAJOR_TO_FIELD.get(major, []),
        )
        st.session_state["results"] = recommend(user, scholarships)

    results = st.session_state.get("results")
    if results is not None:
        st.divider()

        col_sort, col_count = st.columns(2)
        with col_sort:
            sort_label = st.selectbox("並び替え", list(SORT_OPTIONS.keys()))
        with col_count:
            count_label = st.selectbox("表示件数", list(DISPLAY_COUNT_OPTIONS.keys()))

        sorted_results = _sort_results(results, sort_label)
        display_count = DISPLAY_COUNT_OPTIONS[count_label]
        shown = sorted_results if display_count is None else sorted_results[:display_count]

        st.subheader(f"あなたへのおすすめ奨学金（{len(shown)}/{len(results)}件表示）")
        st.caption("★は入力した条件との一致度を表します（★5＝全条件に完全一致、外れる条件が増えるほど星が減ります）。")

        if not shown:
            st.info("該当する奨学金が見つかりませんでした。")
        for result in shown:
            _render_result(result)


if __name__ == "__main__":
    main()
