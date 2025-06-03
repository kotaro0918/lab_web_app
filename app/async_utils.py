# async_utils.py
"""同期パイプラインをスレッドにオフロードして並列実行するヘルパー"""
import asyncio
import time  # ★ 時間計測のためにインポート

from pipeline.activity_pipeline import (
    weekly_activity_pipeline,
    monthly_activity_pipeline,
)
from pipeline.sleep_pipeline import (
    weekly_sleep_pipeline,
    monthly_sleep_pipeline,
)
from pipeline.nutrition_pipeline import weekly_nutrition_pipeline


async def _run_pipeline_with_timing(pipeline_name: str, sync_pipeline_func, *args):
    """
    指定された同期パイプライン関数を別スレッドで実行し、その実行時間を計測・表示します。
    パイプライン関数自体は変更しません。
    """
    start_time = time.perf_counter()
    print(f"[パイプライン計測] '{pipeline_name}' 開始...")
    try:
        # 同期関数を別スレッドで実行
        result = await asyncio.to_thread(sync_pipeline_func, *args)
        duration = time.perf_counter() - start_time
        print(f"[パイプライン計測] '{pipeline_name}' 正常終了 ({duration:.4f} 秒)")
        return result
    except Exception as e:
        duration = time.perf_counter() - start_time
        # エラーが発生した場合も、ここまでの時間を表示
        print(
            f"[パイプライン計測] '{pipeline_name}' でエラー発生 ({duration:.4f} 秒): {e!r}"
        )
        raise  # 元のコードと同様に例外を再送出


async def fetch_all(user_id: str, today):
    """
    5本のパイプラインを並列で実行し、それぞれの実行時間を計測して結果を返します。
    各パイプラインの内部処理は変更しません。
    """
    overall_start_time = time.perf_counter()
    print(
        f"[fetch_all] 全パイプライン処理開始 (User: {user_id}) at {time.strftime('%X')}"
    )

    # 各パイプラインを時間計測ラッパー経由で呼び出すタスクリストを作成
    tasks = [
        _run_pipeline_with_timing(
            "weekly_activity", weekly_activity_pipeline, user_id, today
        ),
        _run_pipeline_with_timing(
            "weekly_sleep", weekly_sleep_pipeline, user_id, today
        ),
        _run_pipeline_with_timing(
            "weekly_nutrition",
            weekly_nutrition_pipeline,
            user_id.replace("@gmail.com", ""),
            today,
        ),
        _run_pipeline_with_timing(
            "monthly_activity", monthly_activity_pipeline, user_id, today
        ),
        _run_pipeline_with_timing(
            "monthly_sleep", monthly_sleep_pipeline, user_id, today
        ),
    ]

    # asyncio.gather を使ってタスクを並列実行
    # return_exceptions=True にすると、一部のタスクが失敗しても他のタスクの結果（または例外）を収集できます。
    # これにより、失敗したタスクも含めて全てのタスクの試行と時間計測が可能です。
    # 元のコードは return_exceptions=False でしたので、例外発生時の挙動を合わせるために後処理をします。
    print(
        f"[fetch_all] asyncio.gather で {len(tasks)} 本のパイプラインを並列実行開始..."
    )
    results_or_exceptions = await asyncio.gather(*tasks, return_exceptions=True)

    overall_duration = time.perf_counter() - overall_start_time
    print(
        f"[fetch_all] 全パイプラインの asyncio.gather 完了 ({overall_duration:.4f} 秒)"
    )

    # 結果の処理: return_exceptions=True のため、リストには結果または例外オブジェクトが含まれる
    # 元のコード (return_exceptions=False) の挙動に合わせるため、
    # 最初に発生した例外があればそれを送出し、なければ結果のタプルを返す。
    processed_results = []
    first_exception_encountered = None

    pipeline_names_for_logging = [
        "weekly_activity",
        "weekly_sleep",
        "weekly_nutrition",
        "monthly_activity",
        "monthly_sleep",
    ]
    for i, res_or_exc in enumerate(results_or_exceptions):
        pipeline_name = pipeline_names_for_logging[i]
        if isinstance(res_or_exc, Exception):
            print(
                f"[fetch_all] パイプライン '{pipeline_name}' の結果: 例外 ({res_or_exc!r})"
            )
            if first_exception_encountered is None:
                first_exception_encountered = res_or_exc
            processed_results.append(
                None
            )  # エラーの場合はNone、または適切なエラーを示す値を設定
        else:
            # print(f"[fetch_all] パイプライン '{pipeline_name}' の結果: 正常に取得") # _run_pipeline_with_timing 内で出力済み
            processed_results.append(res_or_exc)

    if first_exception_encountered is not None:
        # 元の asyncio.gather(*tasks, return_exceptions=False) と同じように、
        # 最初に発生した例外を送出します。
        print(
            f"[fetch_all] 少なくとも1つのパイプラインでエラーが発生したため、最初の例外を送出します: {first_exception_encountered!r}"
        )
        raise first_exception_encountered

    return tuple(processed_results)  # 全て成功した場合、結果のタプルを返す
