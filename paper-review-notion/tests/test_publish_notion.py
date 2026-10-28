"""publish_notion.py의 마크다운 → Notion 블록 변환 테스트 (Notion은 호출하지 않는다).

실행: (paper-review-notion 폴더에서)
    C:\\Users\\USER\\Anaconda3\\python.exe -m pytest tests -q
"""

import sys
from pathlib import Path

import json
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import publish_notion as p  # noqa: E402

SAMPLE = """# Test Paper: A Study

- 저자: Kim, Lee (Example University)
- 공개: 2024-03, arXiv:2403.00001 · [논문](https://arxiv.org/abs/2403.00001)
- 태그: LLM, Quantization
- Notion: https://app.notion.com/p/abc

## 3줄 요약

1. 🚀 무엇을 했다. 덧붙인 설명.
2. 💡 핵심 방법은 **A**와 $x^2$이다.
3. 📈 결과는 크기보다 품질이 중요하다는 것이다.

<details><summary><b>용어 정리</b></summary>

| 용어 | 설명 |
|---|---|
| 양자화 $c$ | 비트를 줄인다 |

</details>

## 방법

핵심 두 줄.

![Figure 1: 구조](<ex_extract/figures/figure_01_page001.png>)

<details><summary>자세히 보기</summary>

- 바깥 항목
  - 안쪽 항목

$$
y = Wx \\quad (1)
$$

</details>

## 내 메모
"""


def convert(tmp_path):
    md = tmp_path / "paper_summary_2026-10-27.md"
    md.write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "ex_extract" / "figures").mkdir(parents=True)
    (tmp_path / "ex_extract" / "figures" / "figure_01_page001.png").write_bytes(b"\x89PNG")
    meta, header, body = p.parse_summary(md)
    return meta, body, p.markdown_to_blocks(header + [""] + body, tmp_path)


def test_properties(tmp_path):
    meta, body, _ = convert(tmp_path)
    props = p.build_properties(meta, body, "읽을 예정")
    assert p.summarize_prop(props["제목"]) == "Test Paper: A Study"
    assert props["링크"]["url"] == "https://arxiv.org/abs/2403.00001"
    assert props["연도"]["number"] == 2024
    assert p.summarize_prop(props["기관"]) == "Example University"
    assert p.summarize_prop(props["태그"]) == ["LLM", "Quantization"]
    # 첫 문장만, '크기보다'의 '다'에서 끊지 않는다
    assert p.summarize_prop(props["3줄 요약"]).split("\n") == [
        "🚀 무엇을 했다.",
        "💡 핵심 방법은 A와 $x^2$이다.",
        "📈 결과는 크기보다 품질이 중요하다는 것이다.",
    ]


def test_structure(tmp_path):
    _, _, blocks = convert(tmp_path)
    top = [(b["type"], p.plain_of(b)) for b in blocks]
    # 머리 목록에는 태그·Notion 줄을 넣지 않는다
    assert top[:2] == [("bulleted_list_item", "저자: Kim, Lee (Example University)"), ("bulleted_list_item", "공개: 2024-03, arXiv:2403.00001 · 논문")]
    glossary = next(b for b in blocks if p.plain_of(b) == "용어 정리")
    assert glossary["type"] == "heading_2" and glossary["heading_2"]["is_toggleable"]
    assert glossary["children"][0]["type"] == "table"
    detail = next(b for b in blocks if p.plain_of(b) == "자세히 보기")
    assert detail["type"] == "heading_3" and detail["heading_3"]["is_toggleable"]
    kinds = [c["type"] for c in detail["children"]]
    assert kinds == ["bulleted_list_item", "equation"]
    assert detail["children"][0]["children"][0]["type"] == "bulleted_list_item"  # 중첩 목록
    assert detail["children"][1]["equation"]["expression"] == "y = Wx \\quad (1)"
    assert top[-1] == ("heading_2", "내 메모")


def test_inline_rich_text():
    rt = p.rich_text("**굵게** 그리고 $a+b$ 와 [링크](https://x.org) `code`")
    assert rt[0]["annotations"]["bold"] and rt[0]["text"]["content"] == "굵게"
    assert {"type": "equation", "equation": {"expression": "a+b"}} in rt
    assert any(r.get("text", {}).get("link") == {"url": "https://x.org"} for r in rt)
    assert any(r.get("annotations", {}).get("code") for r in rt)
    long = p.rich_text("가" * 4500)
    assert [len(r["text"]["content"]) for r in long] == [2000, 2000, 500]


def test_validate_and_shallow(tmp_path):
    _, _, blocks = convert(tmp_path)
    assert p.validate(blocks) == []
    img = next(b for b, _ in p.walk(blocks) if b["type"] == "image")
    img["_local"] = str(tmp_path / "missing.png")
    assert any("이미지 파일 없음" in x for x in p.validate(blocks))
    sent = p.shallow(img)
    assert "_local" not in sent and "children" not in sent
    table = next(b for b, _ in p.walk(blocks) if b["type"] == "table")
    assert len(p.shallow(table)["table"]["children"]) == 2  # 표는 행을 함께 보낸다 (구분선 제외)


def test_split_memo(tmp_path):
    _, _, blocks = convert(tmp_path)
    content, memo = p.split_memo(blocks)
    assert p.plain_of(memo[0]) == "내 메모" and len(memo) == 1
    assert len(content) == len(blocks) - 1


@pytest.mark.parametrize("heading", ["## 3줄 요약", "## 3 줄 요약"])
def test_unbulleted_summary_populates_property_and_keeps_lines(tmp_path, heading):
    lines = ["🚀 첫째 문장.", "💡 둘째 문장.", "📈 셋째 문장."]
    body = [heading, *lines, "", "<details><summary>자세히 보기</summary>", "별도 본문", "</details>"]
    assert p.three_lines(body) == lines
    blocks = p.markdown_to_blocks(body, tmp_path)
    assert [p.plain_of(b) for b in blocks[1:4]] == lines
    props = p.build_properties({"title": "Test"}, body, None)
    assert p.summarize_prop(props["3줄 요약"]) == "\n".join(lines)


def test_title_suffix_does_not_rewrite_source(tmp_path):
    md = tmp_path / "summary.md"
    md.write_text("# Original title\n\n## 3줄 요약\n1. One.\n2. Two.\n3. Three.\n", encoding="utf-8")
    before = md.read_bytes()
    p.main(["--summary", str(md), "--title-suffix", "[비교본: chosen model]"])
    preview = json.loads((tmp_path / "summary_notion_preview.json").read_text(encoding="utf-8"))
    assert p.summarize_prop(preview["properties"]["제목"]) == "Original title [비교본: chosen model]"
    assert md.read_bytes() == before
