"""퀴즈 개수가 많아질 때의 성능을 측정한다 (표준 라이브러리만 사용).

실행: 프로젝트 루트에서  python3 tools/benchmark.py
실제 state.json은 건드리지 않고 임시 폴더에서 측정한다.

표 1. 현재 구조(JSON 파일 전체 저장)의 저장·불러오기·메모리
표 2. 대표 작업별 시간: 현재 구조(list + JSON) vs SQLite로 바꿨을 때
"""

import contextlib
import io
import os
import sqlite3
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


def best_ms(func):
    """REPEAT번 실행해 가장 빠른 시간을 ms로 돌려준다."""
    times = []
    for _ in range(REPEAT):
        start = time.perf_counter()
        func()
        times.append((time.perf_counter() - start) * 1000)
    return min(times)


def measure_json(count):
    with tempfile.TemporaryDirectory() as tmp:
        store = StateStore(os.path.join(tmp, "state.json"))
        quizzes = make_quizzes(count)
        state = {"quizzes": quizzes, "high_score": 0, "high_score_total": 0, "total_played": 0}
        save_ms = best_ms(lambda: store.save(state))
        size_kb = os.path.getsize(store.path) / 1024
        with contextlib.redirect_stdout(io.StringIO()):
            load_ms = best_ms(store.load)
        tracemalloc.start()
        store.load()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        keyword = f"{count - 1}번"  # 맨 끝 문제 = 가장 오래 걸리는 경우
        search_ms = best_ms(lambda: [q for q in quizzes if keyword in q.question])
        index_ms = best_ms(lambda: quizzes[count - 1])

        def add_one():
            quizzes.append(Quiz("새 문제", ["a", "b", "c", "d"], 1, ""))
            store.save(state)
            quizzes.pop()
        add_ms = best_ms(add_one)
    return save_ms, load_ms, size_kb, peak / 1024 / 1024, search_ms, index_ms, add_ms


def measure_sqlite(count):
    with tempfile.TemporaryDirectory() as tmp:
        db = sqlite3.connect(os.path.join(tmp, "quiz.db"))
        db.execute("CREATE TABLE quiz (id INTEGER PRIMARY KEY, question TEXT, "
                   "o1 TEXT, o2 TEXT, o3 TEXT, o4 TEXT, answer INTEGER, hint TEXT)")
        db.executemany("INSERT INTO quiz (question, o1, o2, o3, o4, answer, hint) VALUES (?,?,?,?,?,?,?)",
                       [(q.question, *q.options, q.answer, q.hint) for q in make_quizzes(count)])
        db.commit()
        keyword = f"%{count - 1}번%"
        search_ms = best_ms(lambda: db.execute("SELECT * FROM quiz WHERE question LIKE ?", (keyword,)).fetchall())
        index_ms = best_ms(lambda: db.execute("SELECT * FROM quiz WHERE id = ?", (count,)).fetchone())

        def add_and_remove():
            cur = db.execute("INSERT INTO quiz (question, o1, o2, o3, o4, answer, hint) "
                             "VALUES ('새 문제', 'a', 'b', 'c', 'd', 1, '')")
            db.commit()
            db.execute("DELETE FROM quiz WHERE id = ?", (cur.lastrowid,))
            db.commit()
        add_ms = best_ms(add_and_remove) / 2  # 추가·삭제 두 번 저장하므로 절반이 추가 1건
        db.close()
    return search_ms, index_ms, add_ms


def main():
    print(f"Python {sys.version.split()[0]}, 각 항목 {REPEAT}회 중 최솟값 (단위 ms)\n")
    json_rows = {count: measure_json(count) for count in SIZES}

    print("[표 1] 현재 구조: JSON 파일 전체 저장")
    print(f"{'퀴즈 수':>8} | {'저장':>7} | {'불러오기':>8} | {'파일(KB)':>8} | {'메모리(MB)':>9}")
    for count, (save, load, size, mem, *_rest) in json_rows.items():
        print(f"{count:>8,} | {save:>7.1f} | {load:>8.1f} | {size:>8,.0f} | {mem:>9.1f}")

    print("\n[표 2] 작업별 시간: 현재 구조(list + JSON) vs SQLite")
    print(f"{'퀴즈 수':>8} | {'검색 list':>9} | {'검색 SQL':>8} | {'번호 list':>9} | {'번호 SQL':>8} "
          f"| {'추가 JSON':>9} | {'추가 SQL':>8}")
    for count in SIZES:
        *_head, search, index, add = json_rows[count]
        s_search, s_index, s_add = measure_sqlite(count)
        print(f"{count:>8,} | {search:>9.2f} | {s_search:>8.2f} | {index:>9.4f} | {s_index:>8.4f} "
              f"| {add:>9.1f} | {s_add:>8.2f}")


if __name__ == "__main__":
    main()
