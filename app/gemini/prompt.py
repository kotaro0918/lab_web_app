MONTHLY_ACTIVE_PROMPT = """以下のデータは高齢者一人のの1ヶ月の運動時間のデータを表したものです。

今月のデータ: {this_month_data}
今月の平均運動時間: {this_month_mean}
健康状態を改善するためにアドバイスを出力してください。

字数は100字以内にして要約してください。"""
WEEKLY_ACTIVE_PROMPT = """以下のデータは高齢者一人のの1週間の運動時間のデータを表したものです。

2週間前のデータ: {previous_two_week_data}
2週間前の平均運動時間: {previous_two_week_mean}
今週のデータ: {this_week_data}
今週の平均運動時間: {this_week_mean}
健康状態を改善するためにアドバイスを出力してください。

字数は100字以内にして要約してください。"""
MONTHLY_ACTIVE_INFORMATION = """
以下の方針に沿って、アドバイスを行なってください
系列	条件	内容
1	daily active minutes<45	運動時間上昇を促す
2	45 ≤daily active minute<90	運動時間上昇を促す
3	90 ≤daily active minute<150	運動時間上昇を促す
4	150 ≤daily active minute	達成のお祝いと維持を促す
"""
WEEKLY_ACTIVE_INFORMATION = """
以下の方針に沿って、アドバイスを行なってください
系列	条件	内容
5	daily active minute <150 and count increased by <10% compared to prior week	運動時間上昇を促す
6	daily active minute<150,step count increased by ≥10% compared to prior week	達成のお祝いと維持を促す
7	150≤daily steps	達成のお祝いと維持を促す
"""
MONTHLY_STEP_PROMPT = """以下のデータは高齢者一人のの1ヶ月の歩数のデータを表したものです。
今月のデータ: {this_month_data}
今月の平均歩数: {this_month_mean}
健康状態を改善するためにアドバイスを出力してください。
字数は100字以内にして要約してください。"""

WEEKLY_STEP_PROMPT = """以下のデータは高齢者一人のの1週間の歩数のデータを表したものです。
2週間前のデータ: {previous_two_week_data}
2週間前の平均歩数: {previous_two_week_mean}
今週のデータ: {this_week_data}
今週の平均歩数: {this_week_mean}
健康状態を改善するためにアドバイスを出力してください。
字数は100字以内にして要約してください。"""
MONTHLY_STEP_INFORMATION = """
以下の方針に沿って、アドバイスを行なってください
系列	条件	内容
1	daily steps<3000	歩数上昇を促す
2	3000≤daily steps<6000	歩数上昇を促す
3	6000≤daily steps<8000	歩数上昇を促す
4	8000≤daily steps	達成のお祝いと維持を促す
"""
WEEKLY_STEP_INFORMATION = """
以下の方針に沿って、アドバイスを行なってください
系列	条件	内容
5	daily steps<8000 and count increased by <10% compared to two weeks prior	歩数上昇を促す
6	daily steps<8000,step count increased by ≥10% compared to two weeks prior	達成のお祝いと維持を促す
7	8000≤daily steps	達成のお祝いと維持を促す
"""
WEEKLY_SLEEP_PROMPT = """以下のデータは高齢者一人のの1週間の睡眠時間のデータを表したものです。
今週のデータ: {this_week_data}
今週の平均睡眠時間: {this_week_mean}
健康状態を改善するためにアドバイスを出力してください。
字数は100字以内にして要約してください。"""
WEEKLY_SLEEP_INFORMATION = """
以下の方針に沿って、アドバイスを行なってください
系列	条件	内容
1	Average sleep time<300minutes	睡眠時間上昇を促す
2	300minutes≤Average sleep time<360minutes	睡眠時間上昇を促す
3	360minutes≤Average sleep time<540minutes	達成のお祝いと維持を促す
4	540 minutes≤Average sleep time	睡眠時間の減少を促す
"""
MONTHLY_SLEEP_PROMPT = """以下のデータは高齢者一人のの1ヶ月の睡眠時間のデータを表したものです。
今月のデータ: {this_month_data}
今月の平均睡眠時間: {this_month_mean}
健康状態を改善するためにアドバイスを出力してください。
字数は100字以内にして要約してください。"""
MONTHLY_SLEEP_INFORMATION = """
以下の方針に沿って、アドバイスを行なってください
系列	条件	内容
1	Average sleep time<300minutes	睡眠時間上昇を促す
2	300minutes≤Average sleep time<360minutes	睡眠時間上昇を促す
3	360minutes≤Average sleep time<540minutes	達成のお祝いと維持を促す
4	540 minutes≤Average sleep time	睡眠時間の減少を促す
"""
NUTRION_PROMPT = """
以下のデータは高齢者一人の1週間の栄養素のデータを表したものです。
タンパク質摂取量を整えるようにアドバイスを出力してください。
字数は100字以内にして要約してください。
今週のデータ: {this_week_data}
今週のタンパク質摂取量の割合: {this_week_protein_ratio}
"""

NUTRITION_INFORMATION = """
以下の方針に沿って、アドバイスを行なってください
系列	条件	内容
1	総カロリーのうちタンパク質由来の比率<10%	タンパク質摂取量上昇を促す
2	10%≤総カロリーのうちタンパク質由来の比率<15%	タンパク質摂取量上昇を促す
3	15%≤総カロリーのうちタンパク質由来の比率<20%	達成のお祝いと維持を促す
4	20%≤総カロリーのうちタンパク質由来の比率	タンパク質摂取量の減少を促す

"""
