"""커밋 기록을 텍스트 증빙으로 남긴다.

`git log --oneline --graph --all` 결과를
  1) docs/git_log.txt 에 저장하고
  2) README.md 의 <!-- GIT_LOG_START --> ~ <!-- GIT_LOG_END --> 사이에 넣는다.

실행: 프로젝트 루트에서  python3 tools/update_git_log.py
커밋 뒤에 실행하고, 바뀐 두 파일을 다시 커밋한다. (그 커밋은 다음 실행 때 반영된다)
"""

import os
import re
import subprocess
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")
LOG_FILE = os.path.join(ROOT, "docs", "git_log.txt")
START, END = "<!-- GIT_LOG_START -->", "<!-- GIT_LOG_END -->"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.rstrip()


def main():
    graph = git("log", "--oneline", "--graph", "--all")
    count = git("rev-list", "--count", "HEAD")
    merges = git("rev-list", "--count", "--merges", "HEAD")
    summary = f"{date.today()} 기준 · main 커밋 {count}개 · 병합 {merges}회"

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as file:
        file.write(f"# git log --oneline --graph --all ({summary})\n\n{graph}\n")

    with open(README, encoding="utf-8") as file:
        text = file.read()
    if START not in text or END not in text:
        raise SystemExit("README.md에 GIT_LOG_START/END 표시가 없습니다.")
    block = f"{START}\n{summary}\n\n```\n{graph}\n```\n{END}"
    text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    with open(README, "w", encoding="utf-8") as file:
        file.write(text)

    print(f"✅ {summary}")
    print("   docs/git_log.txt, README.md를 갱신했습니다.")


if __name__ == "__main__":
    main()
