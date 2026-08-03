from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

import streamlit as st

from majors import MAJOR_TO_FACULTY, MAJOR_TO_FIELD, MAJORS
from models import DEFAULT_SCHOOL_TYPE, Scholarship, UserProfile
from recommend import load_scholarships, recommend

DATA_PATH = Path(__file__).parent / "data" / "scholarships_sample.json"
STATIC_DIR = Path(__file__).parent / "static"

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


def _amount_display(result: Dict) -> str:
    return f"{result['amount']:,}円" if result["amount"] is not None else "金額要確認"


# ── Industry デザインシステム: インラインSVGアイコン（デザイン案から転記） ──
ICON_CALENDAR = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3" y="4" width="18" height="18" rx="0"></rect><path d="M16 2v4"></path>'
    '<path d="M8 2v4"></path><path d="M3 10h18"></path></svg>'
)
ICON_COIN = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"></circle><path d="M12 7v10"></path>'
    '<path d="M9 10h6"></path><path d="M9 14h3"></path></svg>'
)
ICON_ARROW_RIGHT = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>'
)
CORNER_MARKS = (
    '<i class="corner tl"></i><i class="corner tr"></i>'
    '<i class="corner bl"></i><i class="corner br"></i>'
)

_COMBINABILITY_TAG_CLASS = {
    "JASSO給付との併用可": "tag tag-accent",
    "民間給付との併用可": "tag tag-accent",
    "条件付き可": "tag tag-outline",
    "不可": "tag tag-neutral",
    "不明": "tag tag-neutral",
}


def _tags_html(result: Dict) -> str:
    tags = []
    for category in sorted(_combinability_categories(result["combinability_note"])):
        css_class = _COMBINABILITY_TAG_CLASS.get(category, "tag tag-neutral")
        tags.append(f'<span class="{css_class}">{html.escape(category)}</span>')
    for category in sorted(_application_method_categories(result["application_method"])):
        tags.append(f'<span class="tag tag-neutral">{html.escape(category)}</span>')
    if _combinability_needs_confirmation(result["combinability_note"]):
        tags.append('<span class="tag tag-outline">併用可否は要確認</span>')
    return "".join(tags)


def _inject_industry_css() -> None:
    industry_css = (STATIC_DIR / "industry-styles.css").read_text(encoding="utf-8")
    overrides_css = (STATIC_DIR / "streamlit-overrides.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{industry_css}\n{overrides_css}</style>", unsafe_allow_html=True)


def _render_navbar() -> None:
    st.markdown(
        '<nav class="nav">'
        '<span class="nav-brand">奨学金サーチ</span>'
        '<a href="#" aria-current="page">検索</a>'
        '<a href="#">使い方</a>'
        "</nav>",
        unsafe_allow_html=True,
    )


def _go_to_detail(scholarship_id: str) -> None:
    st.session_state["screen"] = "detail"
    st.session_state["selected_scholarship_id"] = scholarship_id


def _back_to_list() -> None:
    st.session_state["screen"] = "list"


def _render_result_card(result: Dict) -> None:
    summary = result["description"] or ""
    if len(summary) > 70:
        summary = summary[:70] + "…"

    # 「詳細を見る」はカードHTMLの外側にある実際のst.buttonが担う（下記コメント参照）。
    # カード全体を<a href="?sid=...">で囲む案は、クリック時にブラウザのフルページ遷移が
    # 発生してStreamlitのセッション(st.session_state["results"])が失われる不具合があった
    # ため撤回し、WebSocket経由でセッションを保ったまま遷移できるst.buttonに統一した。
    card_html = (
        f'<div class="card blueprint elev-sm sr-card">'
        f"{CORNER_MARKS}"
        f'<div class="card-kicker">{html.escape(result["scholarship_id"])} ・ {_stars_display(result["stars"])}</div>'
        f'<div class="card-title">{html.escape(result["name"])}</div>'
        f'<div class="sr-tags">{_tags_html(result)}</div>'
        f'<p class="card-body">{html.escape(summary)}</p>'
        f'<div class="card-meta">{ICON_CALENDAR}<span>締切: {html.escape(_deadline_display(result))}</span></div>'
        f'<div class="card-meta">{ICON_COIN}<span>{html.escape(_amount_display(result))}</span></div>'
        f"</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)
    st.button(
        "詳細を見る",
        key=f"detail_btn_{result['scholarship_id']}",
        on_click=_go_to_detail,
        args=(result["scholarship_id"],),
        use_container_width=True,
    )


def _conditions_bullets(scholarship: Scholarship) -> List[str]:
    """奨学金自体の応募条件を、実データのconditionsから箇条書き文言に変換する。"""
    c = scholarship.conditions
    bullets = []
    if c.grades:
        bullets.append(f"学年: {'、'.join(c.grades)}")
    if c.school_types:
        bullets.append(f"学校種別: {'、'.join(c.school_types)}")
    if c.faculties:
        bullets.append(f"学部: {'、'.join(c.faculties)}")
    if c.majors:
        bullets.append(f"専攻・コース: {'、'.join(c.majors)}")
    if c.field_tags:
        bullets.append(f"分野: {'、'.join(c.field_tags)}")
    if c.residences:
        bullets.append(f"居住地: {'、'.join(c.residences)}")
    if c.income_max is not None:
        bullets.append(f"世帯収入: {c.income_max:,}円以下")
    if c.gpa_min is not None:
        bullets.append(f"GPA: {c.gpa_min}以上")
    if not bullets:
        bullets.append("学校種別・学部以外に特別な条件の指定はありません。")
    return bullets


def _render_detail_screen(scholarships: List[Scholarship]) -> None:
    results = st.session_state.get("results") or []
    selected_id = st.session_state.get("selected_scholarship_id")
    result = next((r for r in results if r["scholarship_id"] == selected_id), None)
    scholarship = next((s for s in scholarships if s.id == selected_id), None)

    st.button("← 検索結果に戻る", key="back_to_list_btn", on_click=_back_to_list)

    if result is None or scholarship is None:
        st.warning("この奨学金の情報が見つかりませんでした。検索結果に戻ってやり直してください。")
        return

    conditions_html = "".join(f"<li>{html.escape(b)}</li>" for b in _conditions_bullets(scholarship))
    steps = [result["application_method"]] if result["application_method"] else ["応募方法の詳細は公式サイトでご確認ください。"]
    steps_html = "".join(f"<li>{html.escape(s)}</li>" for s in steps)
    recipients_html = (
        f'<p class="text-muted" style="font-size:13px;margin-top:-6px">支給人数: {html.escape(result["num_recipients"])}</p>'
        if result["num_recipients"] else ""
    )
    mixed_warning_html = (
        '<p class="text-muted" style="font-size:12px">'
        "⚠️ 援助の種類（給付型／貸与型／授業料免除など）によって併用可否が異なります。各自要確認。</p>"
        if _combinability_needs_confirmation(result["combinability_note"]) else ""
    )
    deductions_html = (
        f'<p class="text-muted" style="font-size:12px">減点項目: {html.escape("、".join(result["deductions"]))}</p>'
        if result["deductions"] else ""
    )

    if result["url"]:
        apply_button_html = (
            f'<a class="btn btn-primary blueprint" href="{html.escape(result["url"])}" target="_blank" rel="noopener noreferrer">'
            f"{CORNER_MARKS}公式サイトで詳細を確認{ICON_ARROW_RIGHT}</a>"
        )
    else:
        apply_button_html = '<p class="text-muted">応募先要確認（公式サイトのURLが未公表です）</p>'

    detail_html = (
        '<div class="card blueprint elev-md sr-detail-card">'
        f"{CORNER_MARKS}"
        f'<div class="card-kicker">{html.escape(result["scholarship_id"])} ・ {_stars_display(result["stars"])}</div>'
        f'<h1 style="font-size:32px;margin:6px 0 14px">{html.escape(result["name"])}</h1>'
        f'<div class="sr-tags" style="margin-bottom:18px">{_tags_html(result)}</div>'
        f'{mixed_warning_html}'
        f'<p style="font-size:15px;line-height:1.75;opacity:0.85;margin:0 0 24px">{html.escape(result["description"] or "説明文は未登録です。")}</p>'
        '<div class="sr-section-label">支給内容</div>'
        f'<p style="font-size:15px;line-height:1.6;margin:0 0 6px">{html.escape(_amount_display(result))}</p>'
        f"{recipients_html}"
        '<div class="sr-section-label" style="margin-top:24px">対象条件</div>'
        f'<ul style="margin:0 0 24px;padding-left:20px;font-size:15px;line-height:1.8">{conditions_html}</ul>'
        '<div class="sr-section-label">応募方法とスケジュール</div>'
        f'<ol style="margin:0 0 12px;padding-left:20px;font-size:15px;line-height:1.8">{steps_html}</ol>'
        f'<div class="card-meta" style="margin-bottom:6px">{ICON_CALENDAR}<span>応募締切: {html.escape(_deadline_display(result))}</span></div>'
        f"{deductions_html}"
        '<div style="margin-top:20px">'
        f"{apply_button_html}"
        "</div>"
        "</div>"
    )
    st.markdown(detail_html, unsafe_allow_html=True)


def _render_sidebar(scholarships: List[Scholarship]) -> None:
    with st.sidebar:
        st.markdown('<div class="card-kicker">絞り込み検索</div>', unsafe_allow_html=True)

        with st.form("user_profile_form"):
            st.text_input("学校種別", value=DEFAULT_SCHOOL_TYPE, disabled=True)
            residence = st.selectbox("居住地", PREFECTURES, index=PREFECTURES.index("大阪府"))
            grade = st.selectbox("学年", GRADES)
            major = st.selectbox("専攻・コース", MAJORS)
            gpa = st.number_input("GPA", min_value=0.0, max_value=4.0, value=3.0, step=0.01, format="%.2f")
            parent_income = st.number_input(
                "両親の年収（世帯収入・円）", min_value=0, max_value=50_000_000, value=5_000_000, step=100_000
            )
            submitted = st.form_submit_button("奨学金をレコメンドする", type="primary")

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        st.markdown('<div class="card-kicker">併用可否</div>', unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        col_a.button(
            "全て選択", key="combinability_all_btn",
            on_click=_select_all, args=("combinability_filter", COMBINABILITY_OPTIONS),
        )
        col_b.button("クリア", key="combinability_clear_btn", on_click=_clear_selection, args=("combinability_filter",))
        st.multiselect("併用可否で絞り込む", COMBINABILITY_OPTIONS, key="combinability_filter", label_visibility="collapsed")

        st.markdown('<div class="card-kicker" style="margin-top:8px">申込方法</div>', unsafe_allow_html=True)
        col_c, col_d = st.columns(2)
        col_c.button(
            "全て選択", key="method_all_btn",
            on_click=_select_all, args=("method_filter", APPLICATION_METHOD_OPTIONS),
        )
        col_d.button("クリア", key="method_clear_btn", on_click=_clear_selection, args=("method_filter",))
        st.multiselect("申込方法で絞り込む", APPLICATION_METHOD_OPTIONS, key="method_filter", label_visibility="collapsed")

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


def _render_list_screen() -> None:
    st.markdown(
        '<div style="padding:8px 0 4px">'
        '<h1 style="font-size:38px;margin:0 0 8px">大教生のための奨学金検索</h1>'
        '<p class="text-muted" style="font-size:15px;line-height:1.6;max-width:64ch">'
        "条件を絞り込んで、大阪教育大学の学生向け奨学金をまとめて比較できます。<br>"
        "入力した情報はこの画面の表示のみに使われ、保存されません。"
        "</p></div>",
        unsafe_allow_html=True,
    )

    results = st.session_state.get("results")
    if results is None:
        st.info("左のサイドバーでプロフィールを入力し、「奨学金をレコメンドする」を押してください。")
        return

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

    st.markdown(
        f'<p style="font-size:13px;letter-spacing:0.05em;opacity:0.6;margin:4px 0 16px;'
        f'text-transform:uppercase">{len(shown)} / {len(filtered_results)} 件表示 '
        f"（★は入力した条件との一致度。★5＝全条件に完全一致）</p>",
        unsafe_allow_html=True,
    )

    if not shown and active_filters:
        st.markdown(
            f'<div class="card blueprint sr-empty">{CORNER_MARKS}'
            '<p class="card-body">この条件に合う奨学金が見つかりませんでした。'
            "サイドバーのフィルタを減らすか「クリア」で条件を緩めてみてください。</p></div>",
            unsafe_allow_html=True,
        )
        return
    if not shown:
        st.markdown(
            f'<div class="card blueprint sr-empty">{CORNER_MARKS}'
            '<p class="card-body">該当する奨学金が見つかりませんでした。</p></div>',
            unsafe_allow_html=True,
        )
        return

    columns_per_row = 3
    for row_start in range(0, len(shown), columns_per_row):
        row = shown[row_start:row_start + columns_per_row]
        cols = st.columns(columns_per_row)
        for col, result in zip(cols, row):
            with col:
                _render_result_card(result)


def main() -> None:
    st.set_page_config(page_title="奨学金サーチ", page_icon="🎓", layout="wide")
    _inject_industry_css()
    _render_navbar()

    st.session_state.setdefault("screen", "list")

    scholarships = _load_scholarships(str(DATA_PATH))

    _render_sidebar(scholarships)

    if st.session_state["screen"] == "detail":
        _render_detail_screen(scholarships)
    else:
        _render_list_screen()


if __name__ == "__main__":
    main()
