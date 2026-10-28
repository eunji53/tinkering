"""실행 경로·실패 중단·PowerShell 인자 전달 검증. 모델/Notion 네트워크 요청은 차단한다."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import generate_summary as g
import publish_notion as p
import review_paper as r

SUMMARY = "# Test paper\n\n- 공개: 2023-05\n\n## 3줄 요약\n\n1. One.\n2. Two.\n3. Three.\n\n## 내 메모\n"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not contact model or Notion services")

    monkeypatch.setattr(g.requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(g, "load_env", lambda: None)
    for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "NOTION_TOKEN", "NOTION_DATABASE_ID"):
        monkeypatch.delenv(name, raising=False)


def extract_fixture(tmp_path):
    directory = tmp_path / "[논문] sample_extract_2026-10-28"
    directory.mkdir()
    (directory / "full_text.md").write_text("## Page 1\nPaper body.\n", encoding="utf-8")
    (directory / "extraction_report.md").write_text("# Report\n", encoding="utf-8")
    return directory


@pytest.mark.parametrize("alias,provider,model", [
    ("gpt", "openai", "gpt-5.4-mini"),
    ("claude", "openrouter", "anthropic/claude-sonnet-5.5"),
    ("ollama", "ollama", "qwen3.5:9b"),
])
def test_model_selection_and_default_preview(tmp_path, monkeypatch, alias, provider, model):
    extract = extract_fixture(tmp_path)
    summary = tmp_path / "result.md"
    summary.write_text(SUMMARY, encoding="utf-8")
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(g, "main", lambda argv: calls.append(("generate", argv)) or summary)
    monkeypatch.setattr(p, "main", lambda argv: calls.append(("publish", argv)))
    args = ["--extract", str(extract), "--provider", alias]
    if alias == "ollama":
        args += ["--model", model, "--num-ctx", "8192", "--think"]
    assert r.main(args) == summary
    gen_args = calls[0][1]
    assert gen_args[gen_args.index("--provider") + 1] == provider
    assert gen_args[gen_args.index("--model") + 1] == model
    if alias == "ollama":
        assert "--think" in gen_args and "8192" in gen_args
    assert calls[1] == ("publish", ["--summary", str(summary)])


def test_missing_notion_key_stops_before_generation(tmp_path, monkeypatch):
    extract = extract_fixture(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(g, "main", lambda _: pytest.fail("Must check Notion config before paid generation"))
    with pytest.raises(SystemExit) as err:
        r.main(["--extract", str(extract), "--provider", "gpt", "--publish"])
    assert err.value.code == 2


def test_summary_publish_reuses_file_and_adds_recorded_model(tmp_path, monkeypatch):
    summary = tmp_path / "existing.md"
    summary.write_text(SUMMARY, encoding="utf-8")
    summary.with_suffix(".json").write_text(json.dumps({"provider": "openai", "model": "chosen-gpt"}))
    before = summary.read_bytes()
    monkeypatch.setenv("NOTION_TOKEN", "test")
    monkeypatch.setenv("NOTION_DATABASE_ID", "test")
    monkeypatch.setattr(g, "main", lambda _: pytest.fail("Existing summary must not call a model"))
    calls = []
    monkeypatch.setattr(p, "main", lambda argv: calls.append(argv))
    r.main(["--summary", str(summary), "--compare", "--publish"])
    assert calls == [["--summary", str(summary), "--title-suffix", "[비교본: OpenAI chosen-gpt]", "--publish"]]
    assert summary.read_bytes() == before


def test_compare_without_record_stops_before_any_step(tmp_path, monkeypatch):
    summary = tmp_path / "manual.md"
    summary.write_text(SUMMARY, encoding="utf-8")
    monkeypatch.setattr(p, "main", lambda _: pytest.fail("No preview without a model record"))
    with pytest.raises(SystemExit) as err:
        r.main(["--summary", str(summary), "--compare"])
    assert err.value.code == 2
    assert sorted(x.name for x in tmp_path.iterdir()) == ["manual.md"]


def test_truncated_summary_is_not_published(tmp_path, monkeypatch):
    summary = tmp_path / "truncated.md"
    summary.write_text(SUMMARY, encoding="utf-8")
    summary.with_suffix(".json").write_text('{"finish_reason": "length"}')
    monkeypatch.setenv("NOTION_TOKEN", "test")
    monkeypatch.setenv("NOTION_DATABASE_ID", "test")
    monkeypatch.setattr(p, "main", lambda _: pytest.fail("Truncated summary must not be published"))
    with pytest.raises(SystemExit):
        r.main(["--summary", str(summary), "--publish"])
    assert summary.read_text(encoding="utf-8") == SUMMARY


def test_generation_failure_stops_pipeline(tmp_path, monkeypatch):
    extract = extract_fixture(tmp_path)

    def failed(_):
        raise SystemExit("model failed")

    monkeypatch.setattr(g, "main", failed)
    monkeypatch.setattr(p, "main", lambda _: pytest.fail("No publish after generation failure"))
    with pytest.raises(SystemExit, match="model failed"):
        r.main(["--extract", str(extract), "--provider", "ollama"])


def test_dry_run_has_no_output_and_rejects_publish(tmp_path):
    extract = extract_fixture(tmp_path)
    before = set(tmp_path.rglob("*"))
    r.main(["--extract", str(extract), "--provider", "gpt", "--dry-run"])
    assert set(tmp_path.rglob("*")) == before
    with pytest.raises(SystemExit):
        r.main(["--extract", str(extract), "--dry-run", "--publish"])


def test_pdf_pipeline_preserves_existing_extraction_and_summary(tmp_path, monkeypatch):
    import fitz
    import extract_pdf as e

    monkeypatch.setattr(e, "PROJECT_DIR", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    pdf = tmp_path / "[논문] sample.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), "A small paper for pipeline testing.")
        doc.save(pdf)
    old = e.output_path(pdf)
    old.mkdir(parents=True)
    (old / "sentinel.txt").write_text("keep")
    monkeypatch.setattr(g, "chat_openai_compatible", lambda *args: (SUMMARY, {"finish_reason": "stop"}))
    first = r.main(["--pdf", str(pdf), "--provider", "gpt"])
    original_bytes = first.read_bytes()
    extracted = old.with_name(old.name + "_2")
    assert (old / "sentinel.txt").read_text() == "keep"
    assert (extracted / "full_text.md").is_file()
    assert first.with_name(first.stem + "_notion_preview.json").is_file()
    second = r.main(["--extract", str(extracted), "--provider", "gpt"])
    assert first != second and first.read_bytes() == original_bytes
    assert second.with_suffix(".json").is_file()


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell.exe"), reason="Windows PowerShell smoke test")
@pytest.mark.parametrize("provider,model", [("gpt", "custom-gpt"), ("claude", "anthropic/custom"), ("ollama", "qwen3.5:9b")])
def test_powershell_passes_literal_paths_and_models(tmp_path, provider, model):
    extract = extract_fixture(tmp_path)
    script = Path(__file__).resolve().parents[1] / "review.ps1"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(script), "-Extract", extract.name,
         "-Provider", provider, "-Model", model, "-Python", sys.executable, "-DryRun"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert str(extract) in result.stdout and model in result.stdout
    assert "[dry-run]" in result.stdout


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell.exe"), reason="Windows PowerShell smoke test")
def test_powershell_summary_dry_run_with_unbulleted_local_summary(tmp_path):
    folder = tmp_path / "[결과] 폴더 A"
    folder.mkdir()
    summary = folder / "[논문] 요약 ollama.md"
    summary.write_text("# Paper\n\n## 3 줄 요약\n🚀 하나.\n💡 둘.\n📈 셋.\n\n## 내 메모\n", encoding="utf-8")
    summary.with_suffix(".json").write_text('{"provider": "ollama", "model": "qwen3.5:9b"}', encoding="utf-8")
    before = sorted(tmp_path.rglob("*"))
    script = Path(__file__).resolve().parents[1] / "review.ps1"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(script), "-Summary", str(summary.relative_to(tmp_path)),
         "-Compare", "-Python", sys.executable, "-DryRun"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[비교본: Ollama qwen3.5:9b]" in result.stdout and "모델 호출 없음" in result.stdout
    assert sorted(tmp_path.rglob("*")) == before


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell.exe"), reason="Windows PowerShell smoke test")
def test_powershell_propagates_failure(tmp_path):
    script = Path(__file__).resolve().parents[1] / "review.ps1"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(script), "-Extract", "missing [folder]",
         "-Python", sys.executable, "-DryRun"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=40,
    )
    assert result.returncode != 0
