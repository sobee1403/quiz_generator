"""
Span Chunking: 전사 segments를 구간 단위 청크로 나눔.
"""

from typing import Any


def chunk_by_max_chars(
    segments: list[dict[str, Any]],
    max_chars: int = 1500,
) -> list[dict[str, Any]]:
    """
    segments를 max_chars 이하로 묶어 청크 리스트 반환.
    각 청크: { "text", "start", "end", "segment_indices" }.
    """
    if not segments:
        return []
    chunks: list[dict[str, Any]] = []
    current_texts: list[str] = []
    current_start: float | None = None
    current_end: float = 0.0
    current_indices: list[int] = []
    total_len = 0

    for i, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start", 0))
        end = float(seg.get("end", 0))
        seg_len = len(text) + (1 if current_texts else 0)

        if total_len + seg_len > max_chars and current_texts:
            chunks.append({
                "text": "\n".join(current_texts),
                "start": current_start if current_start is not None else start,
                "end": current_end,
                "segment_indices": current_indices.copy(),
            })
            current_texts = []
            current_start = start
            current_end = end
            current_indices = [i]
            total_len = len(text)
        else:
            if current_start is None:
                current_start = start
            current_texts.append(text)
            current_end = end
            current_indices.append(i)
            total_len += seg_len

    if current_texts:
        chunks.append({
            "text": "\n".join(current_texts),
            "start": current_start if current_start is not None else 0.0,
            "end": current_end,
            "segment_indices": current_indices,
        })
    return chunks
