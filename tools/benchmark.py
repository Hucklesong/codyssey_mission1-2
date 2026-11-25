"""퀴즈 개수가 많아질 때 저장/불러오기 성능을 측정한다 (표준 라이브러리만 사용).

실행: 프로젝트 루트에서  python3 tools/benchmark.py
실제 state.json은 건드리지 않고 임시 폴더에서 측정한다.
"""

import contextlib
import io
import os
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import Quiz, StateStore  # noqa: E402

SIZES = [1_000, 10_000, 100_000]
REPEAT = 5


def make_quizzes(count):
    return [
        Quiz(f"{i}번 영화 퀴즈: 이 영화의 감독은 누구인가요?",
             ["박찬욱", "봉준호", "크리스토퍼 놀란", "스티븐 스필버그"],
             i % 4 + 1, "힌트 문장입니다.")
        for i in range(count)
    ]


def best_time(func):
    """REPEAT번 실행해 가장 빠른 시간을 ms로 돌려준다."""
    times = []
    for _ in range(REPEAT):
        start = time.perf_counter()
        func()
        times.append((time.perf_counter() - start) * 1000)
    return min(times)


def measure(count):
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(os.path.join(tmp, "state.json"))
        state = {"quizzes": make_quizzes(count), "high_score": 0, "high_score_total": 0, "total_played": 0}
        save_ms = best_time(lambda: store.save(state))
        size_kb = os.path.getsize(store.path) / 1024
        with contextlib.redirect_stdout(io.StringIO()):
            load_ms = best_time(store.load)
        tracemalloc.start()
        store.load()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return save_ms, load_ms, size_kb, peak / 1024 / 1024


def main():
    print(f"Python {sys.version.split()[0]}, 각 항목 {REPEAT}회 중 최솟값")
    print(f"{'퀴즈 수':>8} | {'저장(ms)':>9} | {'불러오기(ms)':>11} | {'파일(KB)':>9} | {'최대 메모리(MB)':>13}")
    for count in SIZES:
        save_ms, load_ms, size_kb, peak_mb = measure(count)
        print(f"{count:>8,} | {save_ms:>9.1f} | {load_ms:>11.1f} | {size_kb:>9,.0f} | {peak_mb:>13.1f}")


if __name__ == "__main__":
    main()
