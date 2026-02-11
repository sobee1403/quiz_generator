"""
퀴즈 생성 CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.quiz.generator import QuizGenerator
from app.schema.models import QuizRequest, TranscriptData


def parse_question_types(raw: str | None) -> list[str]:
    if not raw:
        return ["multiple_choice"]
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or ["multiple_choice"]


def load_payload(input_path: Path | None, use_stdin: bool) -> dict:
    if use_stdin:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("stdin이 비어 있습니다.")
        return json.loads(raw)

    if not input_path:
        raise ValueError("--input 또는 --stdin 중 하나는 필요합니다.")

    if not input_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {input_path}")
    return json.loads(input_path.read_text(encoding="utf-8"))


def build_request(payload: dict, args: argparse.Namespace) -> QuizRequest:
    try:
        base = QuizRequest.model_validate(payload)
        return apply_overrides(base, args)
    except ValidationError:
        transcript = TranscriptData.model_validate(payload)
        return QuizRequest(
            segments=transcript.segments,
            meta=transcript.meta,
            num_questions=args.num_questions or 5,
            question_types=parse_question_types(args.question_types),
            language=args.language or "ko",
            difficulty=args.difficulty or "medium",
        )


def apply_overrides(base: QuizRequest, args: argparse.Namespace) -> QuizRequest:
    update: dict = {}
    if args.num_questions is not None:
        update["num_questions"] = args.num_questions
    if args.question_types is not None:
        update["question_types"] = parse_question_types(args.question_types)
    if args.language is not None:
        update["language"] = args.language
    if args.difficulty is not None:
        update["difficulty"] = args.difficulty
    return base.model_copy(update=update) if update else base


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="전사 JSON으로 퀴즈를 생성합니다.")
    parser.add_argument("-i", "--input", help="전사 JSON 파일 경로")
    parser.add_argument("--stdin", action="store_true", help="표준 입력에서 JSON 읽기")
    parser.add_argument("--output", help="결과 JSON 저장 경로 (없으면 stdout)")
    parser.add_argument("--num-questions", type=int, help="생성할 질문 수")
    parser.add_argument(
        "--question-types",
        help="질문 유형 CSV (multiple_choice,true_false,short_answer)",
    )
    parser.add_argument("--language", help="언어 (예: ko)")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], help="난이도")
    parser.add_argument("--pretty", action="store_true", help="예쁘게 출력")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        input_path = Path(args.input).expanduser() if args.input else None
        payload = load_payload(input_path, args.stdin)
        req = build_request(payload, args)
    except (ValueError, FileNotFoundError, json.JSONDecodeError, ValidationError) as exc:
        print(f"입력 처리 실패: {exc}", file=sys.stderr)
        sys.exit(1)

    generator = QuizGenerator()
    result = generator.generate(req)
    output = json.dumps(
        result.model_dump(),
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    )

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
