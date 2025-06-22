import json


if __name__ == "__main__":

    with open("data/acitivity_user.json", encoding="utf-8") as f1:  # ファイル名修正
        data1 = json.load(f1)  # list[dict]

    with open("data/nutrition_user.json", encoding="utf-8") as f2:
        data2 = json.load(f2)
    # ------- 2 つの集合を作る (week_start, login_id) -------
    set1 = {(d["week_start"], d["login_id"]) for d in data1}
    set2 = {(d["week_start"], d["login_id"]) for d in data2}

    # ------- 共通キーを持つレコードを抽出 -------
    matches = [d for d in data1 if (d["week_start"], d["login_id"]) in set2]

    print(f"{len(matches)=}")
    for row in matches:
        print(row)
# ------- 共通キーを持つレコードを抽出して表示 -------
