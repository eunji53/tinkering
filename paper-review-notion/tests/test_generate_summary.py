"""generate_summary.py의 입력 준비(참고문헌 제외, .env 탐색) 회귀 테스트.

실행: (paper-review-notion 폴더에서)
    C:\\Users\\USER\\Anaconda3\\python.exe -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import generate_summary as g  # noqa: E402

REFS = "\n".join(f"[{i}] Author {i}. Some paper title. In Venue, 2024." for i in range(1, 9))


def make_extract(tmp_path: Path, pages: list[str]) -> Path:
    text = "\n\n".join(f"## Page {i}\n\n{body}" for i, body in enumerate(pages, start=1))
    (tmp_path / "full_text.md").write_text(text, encoding="utf-8")
    return tmp_path


def test_reference_pages_dropped_and_appendix_page_kept(tmp_path):
    d = make_extract(tmp_path, ["Intro text.", f"Conclusion.\nReferences\n{REFS}", REFS, "A\nExperimental Details\nBody."])
    kept = g.read_pages(d)
    assert [n for n, _ in kept] == [1, 2, 4]
    assert kept[1][1] == "Conclusion."


def test_appendix_starting_mid_reference_page_is_kept(tmp_path):
    # Anemoi 10쪽: 참고문헌 뒤 같은 쪽에서 "A / Case Study: …" 부록이 시작한다.
    d = make_extract(tmp_path, ["Intro.", f"References\n{REFS}", f"{REFS}\nA\nCase Study: X vs. Y\nTask: …"])
    kept = dict(g.read_pages(d))
    assert kept[3].startswith("A\nCase Study")
    assert "[1]" not in kept[3]


def test_appendix_on_reference_heading_page_is_kept(tmp_path):
    d = make_extract(tmp_path, [f"Body.\nReferences\n{REFS}\nAppendix A: Proofs\nLemma 1."])
    kept = g.read_pages(d)
    assert [t for _, t in kept] == ["Body.", "Appendix A: Proofs\nLemma 1."]


def test_wrapped_reference_title_is_not_appendix(tmp_path):
    # 참고문헌 제목이 줄바꿈되어 "A Survey of …"로 시작하는 줄은 부록이 아니다.
    refs = f"{REFS}\n[9] Kim, Lee, and Park.\nA Survey of Agents\nIn ACL, 2025."
    d = make_extract(tmp_path, ["Intro.", f"References\n{refs}"])
    assert [n for n, _ in g.read_pages(d)] == [1]


def test_env_search_stops_at_repo_root(tmp_path):
    outer = tmp_path / "outer"
    repo = outer / "repo"
    src = repo / "proj" / "src"
    src.mkdir(parents=True)
    (outer / ".env").write_text("X=outer", encoding="utf-8")
    (repo / ".git").mkdir()
    assert g.find_env_file(src) is None  # 저장소 밖 .env는 읽지 않는다
    (repo / ".env").write_text("X=repo", encoding="utf-8")
    assert g.find_env_file(src) == repo / ".env"
