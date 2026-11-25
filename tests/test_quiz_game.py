"""퀴즈 게임 자동 테스트.

실행: 프로젝트 루트에서  python3 -m unittest discover -s tests -v
실제 state.json은 건드리지 않도록 모든 테스트는 임시 폴더에서 실행한다.
"""

import io
import json
import os
import signal
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import MAX_TEXT_LENGTH, Quiz, QuizGame, StateStore  # noqa: E402
from questions import questions  # noqa: E402

SAMPLE = {"question": "Q?", "options": ["a", "b", "c", "d"], "answer": 2, "hint": "h"}


def run_quietly(func, *args, inputs=()):
    """input()에 inputs를 차례로 넣고, 출력은 문자열로 모아 돌려준다."""
    buffer = io.StringIO()
    with patch("builtins.input", side_effect=list(inputs)), redirect_stdout(buffer):
        result = func(*args)
    return result, buffer.getvalue()


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write_raw(self, text, path=None):
        with open(path or self.path, "w", encoding="utf-8") as file:
            file.write(text)

    def read_json(self, path=None):
        with open(path or self.path, encoding="utf-8") as file:
            return json.load(file)

    def new_game(self):
        game = QuizGame(StateStore(self.path))
        run_quietly(game.load)
        return game


class QuizTest(unittest.TestCase):
    def test_is_correct(self):
        quiz = Quiz.from_dict(SAMPLE)
        self.assertTrue(quiz.is_correct(2))
        self.assertFalse(quiz.is_correct(3))

    def test_to_dict_round_trip(self):
        self.assertEqual(Quiz.from_dict(SAMPLE).to_dict(), SAMPLE)

    def test_from_dict_rejects_bad_data(self):
        bad_cases = [
            {**SAMPLE, "question": "  "},
            {**SAMPLE, "options": ["a", "b", "c"]},
            {**SAMPLE, "options": ["a", "b", "c", ""]},
            {**SAMPLE, "answer": 5},
            {**SAMPLE, "answer": "2"},
            {**SAMPLE, "answer": True},
            {**SAMPLE, "hint": 3},
            ["not", "a", "dict"],
        ]
        for data in bad_cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                Quiz.from_dict(data)

    def test_default_questions_are_valid(self):
        self.assertGreaterEqual(len(questions), 5)
        for item in questions:
            Quiz.from_dict(item)


class InputTest(unittest.TestCase):
    def test_get_number_retries_until_valid(self):
        # 빈 입력, 문자, 범위 밖 숫자를 거친 뒤 공백이 섞인 " 3 "을 받아들인다.
        number, output = run_quietly(QuizGame.get_number, "선택: ", 1, 5, inputs=["", "abc", "9", "0", " 3 "])
        self.assertEqual(number, 3)
        self.assertIn("입력이 비어 있습니다", output)
        self.assertIn("숫자가 아닙니다", output)
        self.assertEqual(output.count("범위를 벗어났습니다"), 2)

    def test_get_text_rejects_empty(self):
        text, output = run_quietly(QuizGame.get_text, "> ", inputs=["", "   ", " 봉준호 "])
        self.assertEqual(text, "봉준호")
        self.assertEqual(output.count("내용을 입력하세요"), 2)

    def test_get_text_rejects_too_long(self):
        text, output = run_quietly(QuizGame.get_text, "> ", inputs=["가" * (MAX_TEXT_LENGTH + 1), "가" * MAX_TEXT_LENGTH])
        self.assertEqual(len(text), MAX_TEXT_LENGTH)
        self.assertIn("너무 깁니다", output)

    def test_get_number_huge_number_is_out_of_range(self):
        number, output = run_quietly(QuizGame.get_number, "> ", 1, 5, inputs=["9" * 5000, "2"])
        self.assertEqual(number, 2)
        self.assertTrue("범위를 벗어났습니다" in output or "숫자가 아닙니다" in output)

    def test_get_text_allow_empty(self):
        text, _ = run_quietly(QuizGame.get_text, "> ", True, inputs=[""])
        self.assertEqual(text, "")


class PersistenceTest(TempDirTestCase):
    def test_first_run_uses_default_quizzes(self):
        game = self.new_game()
        self.assertEqual(len(game.quizzes), len(questions))
        self.assertFalse(os.path.exists(self.path))

    def test_added_quiz_survives_restart(self):
        game = self.new_game()
        run_quietly(game.add_quiz, inputs=["새 문제", "가", "나", "다", "라", "3", "힌트"])
        restarted = self.new_game()
        self.assertEqual(len(restarted.quizzes), len(questions) + 1)
        self.assertEqual(restarted.quizzes[-1].to_dict(),
                         {"question": "새 문제", "options": ["가", "나", "다", "라"], "answer": 3, "hint": "힌트"})

    def test_high_score_updates_and_survives_restart(self):
        game = self.new_game()
        answers = [str(item["answer"]) for item in questions]
        run_quietly(game.play, inputs=answers)
        self.assertEqual(game.high_score, len(questions))
        restarted = self.new_game()
        self.assertEqual((restarted.high_score, restarted.high_score_total, restarted.total_played),
                         (len(questions), len(questions), 1))

    def test_lower_score_does_not_replace_high_score(self):
        game = self.new_game()
        run_quietly(game.play, inputs=[str(item["answer"]) for item in questions])
        wrong = [str(item["answer"] % 4 + 1) for item in questions]
        _, output = run_quietly(game.play, inputs=wrong)
        self.assertEqual(game.high_score, len(questions))
        self.assertEqual(game.total_played, 2)
        self.assertNotIn("새로운 최고 점수", output)

    def test_legacy_high_score_total_is_filled_on_equal_score(self):
        self.write_raw('{"high_score": 7, "total_played": 2}')
        game = self.new_game()
        self.assertEqual(game.high_score_total, 0)
        _, output = run_quietly(game.play, inputs=[str(item["answer"]) for item in questions])
        self.assertEqual((game.high_score, game.high_score_total), (7, 7))
        self.assertNotIn("새로운 최고 점수", output)
        _, output = run_quietly(game.show_score)
        self.assertIn("100점 (7문제 중 7문제 정답)", output)

    def test_hint_then_answer(self):
        game = self.new_game()
        correct, output = run_quietly(game.ask, game.quizzes[0], 1, inputs=["0", str(game.quizzes[0].answer)])
        self.assertTrue(correct)
        self.assertIn("힌트", output)

    def test_saved_file_is_utf8_with_korean(self):
        game = self.new_game()
        run_quietly(game.save)
        with open(self.path, encoding="utf-8") as file:
            self.assertIn("기생충", file.read())  # ensure_ascii=False 확인

    def test_legacy_file_without_quizzes(self):
        self.write_raw('{"high_score": 7, "total_played": 2}')
        game = self.new_game()
        self.assertEqual(len(game.quizzes), len(questions))
        self.assertEqual((game.high_score, game.total_played), (7, 2))


class RecoveryTest(TempDirTestCase):
    def test_corrupted_json_restores_from_backup(self):
        game = self.new_game()
        run_quietly(game.add_quiz, inputs=["백업될 문제", "1", "2", "3", "4", "1", ""])
        run_quietly(game.save)  # 두 번째 저장에서 직전 정상본이 .bak으로 복사된다.
        self.write_raw("{ 깨진 파일")
        _, output = run_quietly(StateStore(self.path).load)
        self.assertIn("손상", output)
        restarted = self.new_game()
        self.assertEqual(restarted.quizzes[-1].question, "백업될 문제")
        self.assertTrue(os.path.exists(self.path + ".corrupted"))

    def test_corrupted_without_backup_falls_back_to_defaults(self):
        self.write_raw("not json")
        game = self.new_game()
        self.assertEqual(len(game.quizzes), len(questions))
        self.assertTrue(os.path.exists(self.path + ".corrupted"))

    def test_invalid_schema_is_treated_as_corrupted(self):
        self.write_raw(json.dumps({"quizzes": [{"question": "Q", "options": ["a"], "answer": 9}]}))
        game = self.new_game()
        self.assertEqual(len(game.quizzes), len(questions))

    def test_wrong_encoding_is_treated_as_corrupted(self):
        with open(self.path, "wb") as file:
            file.write('{"high_score": 1}'.encode("utf-16"))
        game = self.new_game()
        self.assertEqual(len(game.quizzes), len(questions))

    def test_permission_error_on_read_disables_save(self):
        self.write_raw('{"high_score": 3}')
        store = StateStore(self.path)
        with patch("builtins.open", side_effect=PermissionError(13, "Permission denied")):
            state, output = run_quietly(store.load)
        self.assertIsNone(state)
        self.assertIn("읽을 수 없습니다", output)
        self.assertFalse(store.can_save)
        self.assertFalse(run_quietly(store.save, {"quizzes": [], "high_score": 0,
                                                   "high_score_total": 0, "total_played": 0})[0])
        self.assertEqual(self.read_json(), {"high_score": 3})  # 원본을 덮어쓰지 않았다.

    def test_write_error_returns_false_and_keeps_original(self):
        game = self.new_game()
        run_quietly(game.save)
        before = self.read_json()
        with patch("main.os.replace", side_effect=OSError(28, "No space left on device")):
            ok, output = run_quietly(game.save)
        self.assertFalse(ok)
        self.assertIn("저장하지 못했습니다", output)
        self.assertEqual(self.read_json(), before)
        self.assertFalse(os.path.exists(self.path + ".tmp"))


class MenuTest(TempDirTestCase):
    def test_menu_runs_every_feature_then_exits(self):
        game = QuizGame(StateStore(self.path))
        inputs = (["4", "3", "2", "메뉴 문제", "a", "b", "c", "d", "4", ""]
                  + ["1"] + ["1"] * (len(questions) + 1) + ["4", "9", "5"])
        _, output = run_quietly(game.run, inputs=inputs)
        for text in ("아직 퀴즈를 풀지 않았습니다", "등록된 퀴즈 목록", "퀴즈가 추가되었습니다",
                     "퀴즈를 시작합니다", "총 플레이 횟수: 1회", "범위를 벗어났습니다", "게임을 종료합니다"):
            self.assertIn(text, output)
        self.assertEqual(len(self.read_json()["quizzes"]), len(questions) + 1)

    def test_ctrl_c_saves_and_exits(self):
        game = QuizGame(StateStore(self.path))
        inputs = ["2", "중단 전 문제", "a", "b", "c", "d", "1", "", KeyboardInterrupt()]
        _, output = run_quietly(game.run, inputs=inputs)
        self.assertIn("입력이 중단되어", output)
        self.assertEqual(self.read_json()["quizzes"][-1]["question"], "중단 전 문제")

    def test_sigterm_saves_and_exits(self):
        game = QuizGame(StateStore(self.path))

        def send_sigterm(prompt=""):
            os.kill(os.getpid(), signal.SIGTERM)  # 입력을 기다리는 중에 종료 신호가 온 상황
            return "1"

        buffer = io.StringIO()
        with patch("builtins.input", side_effect=send_sigterm), redirect_stdout(buffer):
            game.run()
        self.assertIn("종료 신호(SIGTERM)", buffer.getvalue())
        self.assertIn("데이터를 저장했습니다", buffer.getvalue())
        self.assertTrue(os.path.exists(self.path))
        self.assertIs(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)  # 원래 처리 방식으로 복구

    def test_eof_saves_and_exits(self):
        game = QuizGame(StateStore(self.path))
        _, output = run_quietly(game.run, inputs=[EOFError()])
        self.assertIn("데이터를 저장했습니다", output)
        self.assertTrue(os.path.exists(self.path))

    def test_empty_quiz_list_is_handled(self):
        game = QuizGame(StateStore(self.path), default_questions=[])
        run_quietly(game.load)
        _, output = run_quietly(game.play)
        self.assertIn("등록된 퀴즈가 없습니다", output)
        _, output = run_quietly(game.list_quizzes)
        self.assertIn("등록된 퀴즈가 없습니다", output)

    def test_list_pages_and_can_stop(self):
        game = QuizGame(StateStore(self.path), default_questions=[{**SAMPLE, "question": f"Q{i}"} for i in range(25)])
        run_quietly(game.load)
        _, output = run_quietly(game.list_quizzes, inputs=["", "q"])
        self.assertIn("[20] Q19", output)
        self.assertNotIn("[21] Q20", output)


if __name__ == "__main__":
    unittest.main()
