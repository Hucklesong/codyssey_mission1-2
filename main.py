"""영화 퀴즈 게임.

터미널에서 실행하는 퀴즈 게임입니다. 클래스 세 개가 역할을 나눠 맡습니다.

- Quiz       : 문제 하나 (문제, 선택지 4개, 정답 번호, 힌트)
- StateStore : state.json 읽기/쓰기, 백업과 손상 복구
- QuizGame   : 메뉴, 입력 처리, 게임 진행
"""

import json
import os
import shutil
import signal

from questions import questions as DEFAULT_QUESTIONS

# main.py가 있는 폴더(프로젝트 루트)에 저장한다. 다른 폴더에서 실행해도 위치가 같다.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")

OPTION_COUNT = 4  # 선택지 개수
PAGE_SIZE = 10    # 퀴즈 목록을 한 번에 보여줄 개수
MAX_TEXT_LENGTH = 200  # 문제·선택지·힌트 한 칸의 최대 글자 수
LINE = "=" * 40


class Quiz:
    """문제 하나를 표현합니다."""

    def __init__(self, question, options, answer, hint=""):
        self.question = question  # 문제 내용 (str)
        self.options = options    # 선택지 4개 (list[str])
        self.answer = answer      # 정답 번호 1~4 (int)
        self.hint = hint          # 힌트 (str, 없으면 "")

    def show(self, number):
        """문제와 번호 붙은 선택지를 출력한다."""
        print(f"\n{'-' * 40}")
        print(f"[문제 {number}] {self.question}")
        for i, option in enumerate(self.options, start=1):
            print(f"  {i}. {option}")
        if self.hint:
            print("  (0: 힌트 보기)")

    def show_hint(self):
        print(f"💡 힌트: {self.hint}")

    def is_correct(self, user_answer):
        return user_answer == self.answer

    def to_dict(self):
        """JSON으로 저장하기 위해 dict로 바꾼다."""
        return {
            "question": self.question,
            "options": list(self.options),
            "answer": self.answer,
            "hint": self.hint,
        }

    @classmethod
    def from_dict(cls, data):
        """dict의 형식을 검사한 뒤 Quiz로 만든다. 형식이 틀리면 ValueError를 일으킨다."""
        if not isinstance(data, dict):
            raise ValueError("퀴즈 항목이 객체 형식이 아닙니다.")

        question = data.get("question")
        options = data.get("options")
        answer = data.get("answer")
        hint = data.get("hint", "")

        if not isinstance(question, str) or not question.strip():
            raise ValueError("문제 내용이 비어 있습니다.")
        if (
            not isinstance(options, list)
            or len(options) != OPTION_COUNT
            or not all(isinstance(o, str) and o.strip() for o in options)
        ):
            raise ValueError("선택지는 비어 있지 않은 문자열 4개여야 합니다.")
        # bool은 int의 한 종류라서 True가 1로 통과하지 않도록 따로 막는다.
        if isinstance(answer, bool) or not isinstance(answer, int) or not 1 <= answer <= OPTION_COUNT:
            raise ValueError("정답은 1~4 사이의 정수여야 합니다.")
        if not isinstance(hint, str):
            raise ValueError("힌트는 문자열이어야 합니다.")

        return cls(question, options, answer, hint)


class StateStore:
    """state.json 파일의 읽기/쓰기와 백업·복구를 담당합니다.

    - 저장 직전에 기존 state.json을 state.json.bak으로 복사한다 (직전 정상본 백업).
    - 임시 파일에 먼저 쓰고 교체하므로, 쓰는 도중 꺼져도 원본이 반쯤 쓰인 채 남지 않는다.
    - 손상된 파일은 state.json.corrupted로 옮겨 보관하고, 백업에서 복구를 시도한다.
    """

    def __init__(self, path=STATE_FILE):
        self.path = path
        self.backup_path = path + ".bak"
        self.corrupted_path = path + ".corrupted"
        self.temp_path = path + ".tmp"
        self.can_save = True  # 읽기 오류가 나면 원본을 덮어쓰지 않도록 False로 바꾼다.

    def load(self):
        """저장된 상태를 dict로 반환한다. 쓸 수 있는 데이터가 없으면 None을 반환한다."""
        if not os.path.exists(self.path):
            return None  # 첫 실행

        try:
            return self._read(self.path)
        except ValueError as error:
            # JSON 문법 오류, 한글 인코딩 오류, 스키마 오류 모두 ValueError의 한 종류다.
            print(f"⚠️ 데이터 파일이 손상되었습니다. ({error})")
            self._keep_corrupted()
            return self._restore_from_backup()
        except OSError as error:
            # 권한 없음 등. 원본은 멀쩡할 수 있으므로 덮어쓰지 않는다.
            print(f"⚠️ 데이터 파일을 읽을 수 없습니다. ({error.strerror})")
            print("   기본 퀴즈로 실행하며, 원본 보호를 위해 이번 실행에서는 저장하지 않습니다.")
            self.can_save = False
            return None

    def save(self, state):
        """상태를 파일에 저장한다. 성공하면 True, 실패하면 False를 반환한다."""
        if not self.can_save:
            return False

        data = {
            "quizzes": [quiz.to_dict() for quiz in state["quizzes"]],
            "high_score": state["high_score"],
            "high_score_total": state["high_score_total"],
            "total_played": state["total_played"],
        }
        try:
            with open(self.temp_path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            if os.path.exists(self.path):
                shutil.copy2(self.path, self.backup_path)
            os.replace(self.temp_path, self.path)
            return True
        except OSError as error:
            print(f"⚠️ 데이터를 저장하지 못했습니다. ({error.strerror})")
            self._remove_quietly(self.temp_path)
            return False

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return self._parse(data)

    @staticmethod
    def _parse(data):
        """JSON에서 읽은 값을 검사하고 Quiz 객체 목록으로 바꾼다."""
        if not isinstance(data, dict):
            raise ValueError("최상위 형식이 객체가 아닙니다.")

        quizzes = None  # None = 예전 형식(점수만 저장) → 기본 퀴즈를 사용
        if "quizzes" in data:
            if not isinstance(data["quizzes"], list):
                raise ValueError("quizzes가 목록 형식이 아닙니다.")
            quizzes = [Quiz.from_dict(item) for item in data["quizzes"]]

        numbers = {}
        for key in ("high_score", "high_score_total", "total_played"):
            value = data.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{key} 값이 올바르지 않습니다.")
            numbers[key] = value

        return {"quizzes": quizzes, **numbers}

    def _keep_corrupted(self):
        try:
            os.replace(self.path, self.corrupted_path)
            print(f"   손상된 파일은 {os.path.basename(self.corrupted_path)}(으)로 옮겨 보관했습니다.")
        except OSError:
            pass

    def _restore_from_backup(self):
        if os.path.exists(self.backup_path):
            try:
                state = self._read(self.backup_path)
            except (OSError, ValueError):
                print("   백업 파일도 사용할 수 없습니다.")
            else:
                print(f"   백업 파일({os.path.basename(self.backup_path)})에서 데이터를 복구했습니다.")
                # 복구한 백업을 바로 state.json으로 되돌려 놓아, 저장 전에 꺼져도 다음 실행에 남게 한다.
                try:
                    shutil.copy2(self.backup_path, self.path)
                except OSError:
                    pass
                return state
        print("   기본 퀴즈 데이터로 초기화합니다.")
        return None

    @staticmethod
    def _remove_quietly(path):
        try:
            os.remove(path)
        except OSError:
            pass


class QuizGame:
    """메뉴, 입력 처리, 게임 진행을 담당합니다."""

    def __init__(self, store=None, default_questions=DEFAULT_QUESTIONS):
        self.store = store if store is not None else StateStore()
        self.default_questions = default_questions
        self.quizzes = []
        self.high_score = 0        # 최고 정답 수
        self.high_score_total = 0  # 최고 점수를 낸 판의 문제 수
        self.total_played = 0      # 끝까지 푼 횟수

    # ---------- 데이터 불러오기 / 저장 ----------

    def load(self):
        state = self.store.load()
        if state is None:
            self.quizzes = self.default_quizzes()
            print(f"📂 기본 퀴즈 {len(self.quizzes)}개로 시작합니다.")
            return

        if state["quizzes"] is None:
            self.quizzes = self.default_quizzes()
        else:
            self.quizzes = state["quizzes"]
        self.high_score = state["high_score"]
        self.high_score_total = state["high_score_total"]
        self.total_played = state["total_played"]
        print(f"📂 저장된 데이터를 불러왔습니다. (퀴즈 {len(self.quizzes)}개, 최고 점수 {self.high_score}문제 정답)")

    def default_quizzes(self):
        return [Quiz.from_dict(item) for item in self.default_questions]

    def save(self):
        return self.store.save({
            "quizzes": self.quizzes,
            "high_score": self.high_score,
            "high_score_total": self.high_score_total,
            "total_played": self.total_played,
        })

    # ---------- 입력 처리 ----------

    @staticmethod
    def get_number(prompt, min_value, max_value):
        """min_value~max_value 사이의 정수를 입력받을 때까지 반복한다."""
        while True:
            text = input(prompt).strip()
            if text == "":
                print(f"⚠️ 입력이 비어 있습니다. {min_value}-{max_value} 사이의 숫자를 입력하세요.")
                continue
            try:
                number = int(text)
            except ValueError:
                print(f"⚠️ 숫자가 아닙니다. {min_value}-{max_value} 사이의 숫자를 입력하세요.")
                continue
            if not min_value <= number <= max_value:
                print(f"⚠️ 범위를 벗어났습니다. {min_value}-{max_value} 사이의 숫자를 입력하세요.")
                continue
            return number

    @staticmethod
    def get_text(prompt, allow_empty=False):
        """문자열을 입력받는다. 빈 입력(allow_empty가 False일 때)과 너무 긴 입력은 다시 받는다."""
        while True:
            text = input(prompt).strip()
            if len(text) > MAX_TEXT_LENGTH:
                print(f"⚠️ 너무 깁니다. {MAX_TEXT_LENGTH}자 이내로 입력하세요. (지금 {len(text)}자)")
                continue
            if text or allow_empty:
                return text
            print("⚠️ 내용을 입력하세요.")

    # ---------- 메뉴 ----------

    def run(self):
        print(f"\n{LINE}\n       🎬 영화 퀴즈 게임 🎬\n{LINE}")
        self.load()
        # kill 명령 등 외부 종료 신호(SIGTERM)도 Ctrl+C와 같은 방식으로 저장 후 종료한다.
        previous_handler = signal.signal(signal.SIGTERM, self.on_terminate)
        try:
            while True:
                self.show_menu()
                choice = self.get_number("선택: ", 1, 5)
                if choice == 1:
                    self.play()
                elif choice == 2:
                    self.add_quiz()
                elif choice == 3:
                    self.list_quizzes()
                elif choice == 4:
                    self.show_score()
                else:
                    self.save()
                    print("👋 게임을 종료합니다. 다음에 또 만나요!")
                    break
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C(KeyboardInterrupt), 입력 스트림 종료(EOFError)에도 저장 후 종료한다.
            print("\n\n⚠️ 입력이 중단되어 프로그램을 종료합니다.")
            if self.save():
                print("💾 데이터를 저장했습니다.")
        finally:
            signal.signal(signal.SIGTERM, previous_handler)

    @staticmethod
    def on_terminate(signum, frame):
        """SIGTERM을 받으면 KeyboardInterrupt로 바꿔 run()의 저장 후 종료 흐름을 탄다."""
        print("\n⚠️ 종료 신호(SIGTERM)를 받았습니다.")
        raise KeyboardInterrupt

    @staticmethod
    def show_menu():
        print(f"\n{LINE}")
        print("1. 퀴즈 풀기")
        print("2. 퀴즈 추가")
        print("3. 퀴즈 목록")
        print("4. 점수 확인")
        print("5. 종료")
        print(LINE)

    # ---------- 1. 퀴즈 풀기 ----------

    def play(self):
        if not self.quizzes:
            print("📭 등록된 퀴즈가 없습니다. 2번 메뉴에서 퀴즈를 추가해 주세요.")
            return

        total = len(self.quizzes)
        print(f"\n📝 퀴즈를 시작합니다! (총 {total}문제)")
        correct = 0
        for number, quiz in enumerate(self.quizzes, start=1):
            if self.ask(quiz, number):
                correct += 1
        self.finish_game(correct, total)

    def ask(self, quiz, number):
        """문제 하나를 출제하고 맞혔으면 True를 반환한다."""
        quiz.show(number)
        min_answer = 0 if quiz.hint else 1
        while True:
            answer = self.get_number(f"정답 입력 ({min_answer}-{OPTION_COUNT}): ", min_answer, OPTION_COUNT)
            if answer != 0:
                break
            quiz.show_hint()

        if quiz.is_correct(answer):
            print("✅ 정답입니다!")
            return True
        print(f"❌ 오답입니다. 정답은 {quiz.answer}번 ({quiz.options[quiz.answer - 1]})입니다.")
        return False

    def finish_game(self, correct, total):
        """결과를 출력하고 최고 점수를 비교·갱신한 뒤 저장한다."""
        percent = round(correct / total * 100)
        print(f"\n{LINE}")
        print(f"🏆 결과: {total}문제 중 {correct}문제 정답! ({percent}점)")
        self.total_played += 1
        if correct > self.high_score:
            self.high_score = correct
            self.high_score_total = total
            print("🎉 새로운 최고 점수입니다!")
        print(LINE)
        self.save()

    # ---------- 2. 퀴즈 추가 ----------

    def add_quiz(self):
        print("\n📌 새로운 퀴즈를 추가합니다.")
        question = self.get_text("문제를 입력하세요: ")
        options = [self.get_text(f"선택지 {i}: ") for i in range(1, OPTION_COUNT + 1)]
        answer = self.get_number(f"정답 번호 (1-{OPTION_COUNT}): ", 1, OPTION_COUNT)
        hint = self.get_text("힌트 (없으면 Enter): ", allow_empty=True)

        self.quizzes.append(Quiz(question, options, answer, hint))
        if self.save():
            print(f"✅ 퀴즈가 추가되었습니다! (총 {len(self.quizzes)}개)")
        else:
            print("⚠️ 퀴즈는 이번 실행에만 추가되었고 파일에는 저장되지 않았습니다.")

    # ---------- 3. 퀴즈 목록 ----------

    def list_quizzes(self):
        if not self.quizzes:
            print("📭 등록된 퀴즈가 없습니다.")
            return

        total = len(self.quizzes)
        print(f"\n📋 등록된 퀴즈 목록 (총 {total}개)")
        print("-" * 40)
        # 퀴즈가 많아도 화면이 넘치지 않도록 PAGE_SIZE개씩 끊어서 보여준다.
        for start in range(0, total, PAGE_SIZE):
            page = self.quizzes[start:start + PAGE_SIZE]
            for number, quiz in enumerate(page, start=start + 1):
                print(f"[{number}] {quiz.question}")
            shown = start + len(page)
            if shown < total:
                more = input(f"-- {shown}/{total}개 표시. Enter: 다음, q: 그만 보기 -- ").strip().lower()
                if more == "q":
                    break
        print("-" * 40)

    # ---------- 4. 점수 확인 ----------

    def show_score(self):
        if self.total_played == 0:
            print("📭 아직 퀴즈를 풀지 않았습니다. 1번 메뉴에서 도전해 보세요!")
            return
        if self.high_score_total:
            percent = round(self.high_score / self.high_score_total * 100)
            print(f"🏆 최고 점수: {percent}점 ({self.high_score_total}문제 중 {self.high_score}문제 정답)")
        else:
            print(f"🏆 최고 점수: {self.high_score}문제 정답")
        print(f"🎮 총 플레이 횟수: {self.total_played}회")


if __name__ == "__main__":
    QuizGame().run()
