from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

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


COMBINABILITY_OPTIONS = ["JASSO給付との併用可", "民間給付との併用可", "条件付き可", "不可", "不明"]
APPLICATION_METHOD_OPTIONS = ["個人申請", "大学経由"]


def _parse_combinability(note: Optional[str]) -> Dict:
    """併用可否ノートを解析する。categories（分類）とmixed_by_type
    （援助の種類によって可否が異なるため一律に判定できないか）を返す。

    JASSO/民間いずれかを名指ししていない一般的な「他制度併用可」は、
    JASSO・民間の両方に該当するとみなす（要望に基づく仕様）。ただし、同じノートに
    「（給付型は）併用不可だが（貸与型・授業料免除は）併用可」のように
    援助の種類ごとに可否が分かれる記述がある場合は、一律にJASSO/民間可とは
    判定できないため mixed_by_type=True とし、JASSO/民間可のタグ付けを見送る。
    「不可」の言及が併用の文脈と無関係（例:「サイトへのアクセス不可」）な場合は
    誤って「不可」に分類しないよう、各節に「併用」「併給」が含まれる場合のみ判定する。
    """
    if not note:
        return {"categories": frozenset({"不明"}), "mixed_by_type": False}

    has_conditional = False
    has_general_deny = False
    has_general_allow = False
    jasso_allow = jasso_deny = jasso_unstated = False
    minkan_allow = minkan_deny = minkan_unstated = False

    for clause in re.split("[。、]", note):
        if "条件付き" in clause:
            has_conditional = True
        if "併用" not in clause and "併給" not in clause:
            continue
        deny = "不可" in clause
        allow = re.search(r"(?<!不)可(?!否)", clause) is not None
        unstated = ("記載なし" in clause) or ("不明" in clause) or ("要確認" in clause)
        mentions_jasso = "JASSO" in clause
        mentions_minkan = "民間" in clause

        if mentions_jasso:
            if unstated:
                jasso_unstated = True
            elif deny:
                jasso_deny = True
            elif allow:
                jasso_allow = True
        if mentions_minkan:
            if unstated:
                minkan_unstated = True
            elif deny:
                minkan_deny = True
            elif allow:
                minkan_allow = True
        if not mentions_jasso and not mentions_minkan:
            if deny:
                has_general_deny = True
            elif allow:
                has_general_allow = True

    # 援助の種類（給付型/貸与型/授業料免除等）によって可否が割れているノートは、
    # 「一般的な併用可」から一律にJASSO/民間可を推定すると誤りうるため区別する。
    mixed_by_type = has_general_allow and has_general_deny

    cats = set()
    if has_conditional:
        cats.add("条件付き可")
    if has_general_deny or jasso_deny or minkan_deny:
        cats.add("不可")
    if jasso_allow or (has_general_allow and not jasso_deny and not jasso_unstated and not mixed_by_type):
        cats.add("JASSO給付との併用可")
    if minkan_allow or (has_general_allow and not minkan_deny and not minkan_unstated and not mixed_by_type):
        cats.add("民間給付との併用可")
    if not cats:
        cats.add("不明")
    return {"categories": frozenset(cats), "mixed_by_type": mixed_by_type}


def _combinability_categories(note: Optional[str]) -> FrozenSet[str]:
    return _parse_combinability(note)["categories"]


def _combinability_needs_confirmation(note: Optional[str]) -> bool:
    """援助の種類ごとに併用可否が異なり、一律の判定ができないノートかどうか。"""
    return _parse_combinability(note)["mixed_by_type"]


def _application_method_categories(application_method: Optional[str]) -> FrozenSet[str]:
    """申込方法テキストを分類する。判定できない場合は空集合（どのフィルタにも該当しない）。"""
    if not application_method:
        return frozenset()
    cats = set()
    if "個人申請" in application_method:
        cats.add("個人申請")
    if any(kw in application_method for kw in ("大学経由", "大学推薦", "学校経由", "学校推薦")):
        cats.add("大学経由")
    return frozenset(cats)


def _filter_results(
    results: List[Dict],
    combinability_selected: List[str],
    method_selected: List[str],
) -> List[Dict]:
    filtered = results
    if combinability_selected:
        wanted = set(combinability_selected)
        filtered = [r for r in filtered if _combinability_categories(r["combinability_note"]) & wanted]
    if method_selected:
        wanted = set(method_selected)
        filtered = [r for r in filtered if _application_method_categories(r["application_method"]) & wanted]
    return filtered


def _select_all(key: str, options: List[str]) -> None:
    st.session_state[key] = list(options)


def _clear_selection(key: str) -> None:
    st.session_state[key] = []


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
            if _combinability_needs_confirmation(result["combinability_note"]):
                st.caption("⚠️ 援助の種類（給付型／貸与型／授業料免除など）によって併用可否が異なります。各自要確認。")
        if result["description"]:
            st.caption(result["description"])

        if result["deductions"]:
            st.caption("減点項目: " + "、".join(result["deductions"]))

        if result["url"]:
            st.link_button("応募ページへ", result["url"])
        else:
            st.caption("応募先要確認")


def _render_sidebar_filters() -> None:
    with st.sidebar:
        st.header("絞り込み")

        st.subheader("併用可否")
        col_a, col_b = st.columns(2)
        col_a.button(
            "全て選択", key="combinability_all_btn",
            on_click=_select_all, args=("combinability_filter", COMBINABILITY_OPTIONS),
        )
        col_b.button("クリア", key="combinability_clear_btn", on_click=_clear_selection, args=("combinability_filter",))
        st.multiselect("併用可否で絞り込む", COMBINABILITY_OPTIONS, key="combinability_filter", label_visibility="collapsed")

        st.subheader("申込方法")
        col_c, col_d = st.columns(2)
        col_c.button(
            "全て選択", key="method_all_btn",
            on_click=_select_all, args=("method_filter", APPLICATION_METHOD_OPTIONS),
        )
        col_d.button("クリア", key="method_clear_btn", on_click=_clear_selection, args=("method_filter",))
        st.multiselect("申込方法で絞り込む", APPLICATION_METHOD_OPTIONS, key="method_filter", label_visibility="collapsed")


def main() -> None:
    st.set_page_config(page_title="奨学金レコメンドツール", page_icon="🎓")
    st.title("🎓 奨学金レコメンドツール")
    st.caption("大阪教育大学の学生向けプロトタイプ。入力情報はこの画面の表示のみに使われ、保存されません。")

    _render_sidebar_filters()

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

        combinability_selected = st.session_state.get("combinability_filter", [])
        method_selected = st.session_state.get("method_filter", [])
        active_filters = combinability_selected or method_selected

        filtered_results = _filter_results(results, combinability_selected, method_selected)

        col_sort, col_count = st.columns(2)
        with col_sort:
            sort_label = st.selectbox("並び替え", list(SORT_OPTIONS.keys()))
        with col_count:
            count_label = st.selectbox("表示件数", list(DISPLAY_COUNT_OPTIONS.keys()))

        sorted_results = _sort_results(filtered_results, sort_label)
        display_count = DISPLAY_COUNT_OPTIONS[count_label]
        shown = sorted_results if display_count is None else sorted_results[:display_count]

        if active_filters:
            applied = "、".join(combinability_selected + method_selected)
            st.info(f"🔍 フィルタ適用中: {applied}（全{len(results)}件中{len(filtered_results)}件が該当）")

        st.subheader(f"あなたへのおすすめ奨学金（{len(shown)}/{len(filtered_results)}件表示）")
        st.caption("★は入力した条件との一致度を表します（★5＝全条件に完全一致、外れる条件が増えるほど星が減ります）。")

        if not shown and active_filters:
            st.warning("この条件に合う奨学金が見つかりませんでした。サイドバーのフィルタを減らすか「クリア」で条件を緩めてみてください。")
        elif not shown:
            st.info("該当する奨学金が見つかりませんでした。")
        for result in shown:
            _render_result(result)


if __name__ == "__main__":
    main()
