import json
from pathlib import Path

from models import UserProfile
from recommend import load_scholarships, recommend

if __name__ == "__main__":
    data_path = Path(__file__).parent / "data" / "scholarships_sample.json"
    scholarships = load_scholarships(data_path)

    # ユーザー情報はここでのみ保持し、ファイルには書き出さない
    user = UserProfile(
        residence="大阪府",
        faculty="教育学部",
        grade="B3",
        parent_income=4500000,
        gpa=3.2,
        major="教科教育専攻-数学教育コース",
        field_tags=["理系"],
    )

    results = recommend(user, scholarships)
    print(json.dumps(results, ensure_ascii=False, indent=2))
