"""
공통 픽스처: acc 전사 경로, 테스트용 course_id / user_id.
"""

import json
from pathlib import Path

import pytest

# quiz_generator/tests/ -> quiz_generator/ -> 16_langchain/ -> acc
ACC_TRANSCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "acc" / "transcripts" / "gpt-4o-transcribe-diarize"


def _acc_raw_paths():
    """1.aac.raw.json .. 5.aac.raw.json 경로 리스트 (있는 것만)."""
    paths = []
    for n in range(1, 6):
        p = ACC_TRANSCRIPTS_DIR / f"{n}.aac.raw.json"
        if p.exists():
            paths.append((n, p))
    return paths


@pytest.fixture(scope="session")
def acc_transcript_dir():
    """acc 전사 디렉터리. 없으면 skip."""
    if not ACC_TRANSCRIPTS_DIR.exists():
        pytest.skip(f"acc 전사 디렉터리 없음: {ACC_TRANSCRIPTS_DIR}")
    return ACC_TRANSCRIPTS_DIR


@pytest.fixture(scope="session")
def acc_raw_entries():
    """(번호, Path) 리스트. 1.aac.raw.json .. 5.aac.raw.json 중 존재하는 것."""
    entries = _acc_raw_paths()
    if not entries:
        pytest.skip(f"acc raw 전사 파일 없음: {ACC_TRANSCRIPTS_DIR}")
    return entries


@pytest.fixture
def test_course_id():
    return "test_course"


@pytest.fixture
def test_user_id():
    return "test_user"
