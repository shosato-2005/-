from __future__ import annotations

import streamlit as st

MAJORS = [
    # 幼小教育専攻
    "幼小教育専攻-幼児教育コース",
    "幼小教育専攻-小学校教育コース",

    # 次世代教育専攻
    "次世代教育専攻-教育探究コース",
    "次世代教育専攻-ICT教育コース",

    # 教科教育専攻
    "教科教育専攻-国語教育コース",
    "教科教育専攻-英語教育コース",
    "教科教育専攻-社会科教育コース",
    "教科教育専攻-数学教育コース",
    "教科教育専攻-理科教育コース",
    "教科教育専攻-技術教育コース",
    "教科教育専攻-家政教育コース",
    "教科教育専攻-保健体育コース",
    "教科教育専攻-音楽教育コース",
    "教科教育専攻-美術・書道教育コース",

    # 例外（専攻名だけ）
    "特別支援教育専攻",

    # 例外（夜間）
    "小学校教育（夜間）5年専攻",

    # 教育イノベーション専攻
    "教育イノベーション専攻-数理・知能情報コース",
    "教育イノベーション専攻-環境安全科学コース",

    # 教育コミュニティ支援専攻
    "教育コミュニティ支援専攻-心理科学コース",
    "教育コミュニティ支援専攻-スポーツ健康コース",
    "教育コミュニティ支援専攻-芸術表現コース＜音楽＞",
    "教育コミュニティ支援専攻-芸術表現コース＜美術＞",

    # グローバル教育専攻
    "グローバル教育専攻-日本語教育コース",
    "グローバル教育専攻-国際協働英語コース",
]


def render_form_and_filter_scholarships(scholarships: list[dict]) -> None:
    user_major = st.selectbox("学部・専攻", MAJORS)

    submitted = st.button("検索する")
    if not submitted:
        return

    matches = [s for s in scholarships if user_major == s.get("major")]

    if not matches:
        st.info("該当する奨学金が見つかりませんでした。")
        return

    st.subheader(f"該当する奨学金（{len(matches)}件）")
    for scholarship in matches:
        st.write(f"{scholarship.get('name')}（{scholarship.get('major')}）")
