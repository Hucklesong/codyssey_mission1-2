import json
import os
from questions import questions

STATE_FILE = "state.json"


class Quiz:
    """문제 하나를 표현합니다."""

    def __init__(self, question, options, answer, hint):
        self.question = question
        self.options = options
        self.answer = answer
        self.hint = hint

    def show(self, number):
        print(f"\n{'='*40}")
        print(f"문제 {number}. {self.question}")
        print(f"{'='*40}")
        for i, option in enumerate(self.options, start=1):
            print(f"  {i}. {option}")
        print("  (0: 힌트 보기)")

    def show_hint(self):
        print(f"💡 힌트: {self.hint}")

    def is_correct(self, ans):
        return ans == self.answer


class QuizGame:
    """퀴즈 게임 진행과 상태 저장을 담당합니다."""

    def __init__(self, quizzes, state_file=STATE_FILE):
        self.quizzes = quizzes
        self.state_file = state_file
        self.state = self.load_state()
        self.score = 0

    def load_state(self):
        if os.path.exists(self.state_file) and os.path.getsize(self.state_file) > 0:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"high_score": 0, "total_played": 0}

    def save_state(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def get_answer():
        while True:
            try:
                ans = int(input("\n정답 입력 (0~4): "))
                if 0 <= ans <= 4:
                    return ans
                print("0~4 사이의 숫자를 입력해주세요.")
            except ValueError:
                print("숫자를 입력해주세요.")

    def print_stats(self):
        print(f"📊 최고 점수: {self.state['high_score']}점 | 총 플레이 횟수: {self.state['total_played']}회")

    def play_quiz(self, quiz, number):
        quiz.show(number)
        ans = self.get_answer()

        if ans == 0:
            quiz.show_hint()
            ans = self.get_answer()

        if quiz.is_correct(ans):
            print("✅ 정답입니다!")
            self.score += 1
        else:
            print(f"❌ 틀렸습니다. 정답은 {quiz.answer}번이에요.")

    def show_result(self):
        print(f"\n{'='*40}")
        print(f"🏆 최종 점수: {self.score} / {len(self.quizzes)}")
        print(f"{'='*40}")

        self.state["total_played"] += 1
        if self.score > self.state["high_score"]:
            self.state["high_score"] = self.score
            print("🎉 새로운 최고 점수입니다!")
        self.save_state()
        self.print_stats()

    def run(self):
        self.score = 0
        print("\n🎬 영화 퀴즈 게임에 오신 것을 환영합니다!")
        self.print_stats()

        for i, quiz in enumerate(self.quizzes, start=1):
            self.play_quiz(quiz, i)

        self.show_result()


if __name__ == "__main__":
    quizzes = [Quiz(**q) for q in questions]
    QuizGame(quizzes).run()
