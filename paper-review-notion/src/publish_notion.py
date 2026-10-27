"""요약 마크다운(output/<논문>_summary_*.md)을 Notion "논문 리뷰" 데이터베이스에 페이지로 올린다.

기본은 미리보기(dry run)다. Notion을 호출하지 않고 변환한 블록을 output/<요약 파일 이름>_notion_preview.json에
저장하고 개요를 출력한다. 실제로 올리려면 --publish를 붙인다.

변환 규칙 (prompts/summary_format.md 기준)
- 맨 위 메타데이터 목록 → 페이지 속성(제목·링크·연도·기관·태그·3줄 요약·정리일·상태)과 본문 첫 목록
- ## / ### 제목 → heading_2 / heading_3
- <details><summary>용어 정리</summary> → 접히는 heading_2, <summary>자세히 보기</summary> → 접히는 heading_3
- 표 → table, $$ … $$ → equation, 문장 속 $…$ → 인라인 수식, ![캡션](경로) → 이미지 업로드 + 캡션
- 목록(-, 1.), **굵게**/<b>굵게</b>, [링크](주소), `코드`

같은 제목의 페이지가 이미 있으면 새로 만들지 않고 멈춘다. --update-existing을 주면 '내 메모' 제목 앞의 내용만
새 내용으로 바꾸고 '내 메모' 이하와 '상태' 속성은 그대로 둔다.

필요한 환경변수 (저장소 최상위 .env): NOTION_TOKEN, NOTION_DATABASE_ID

실행 예:
    python publish_notion.py --summary "../output/<논문>_summary_<날짜>.md"            # 미리보기
    python publish_notion.py --summary "../output/<논문>_summary_<날짜>.md" --publish  # 발행
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

from generate_summary import load_env

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
# Notion API 제한 (https://developers.notion.com/reference/request-limits)
MAX_TEXT = 2000
MAX_EQUATION = 1000
MAX_CHILDREN = 100
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MEMO_HEADING = "내 메모"
INITIAL_STATUS = "읽을 예정"

META_RE = re.compile(r"^- (저자|기관|공개|링크|태그|Notion):\s*(.*)$")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(<?([^)>]+)>?\)\s*$")
LIST_RE = re.compile(r"^(\s*)(?:[-*]|(\d+)\.)\s+(.*)$")
INLINE_RE = re.compile(
    r"\*\*(?P<b1>.+?)\*\*|<b>(?P<b2>.+?)</b>|(?<![\\$])\$(?P<eq>[^$\n]+?)\$|\[(?P<lt>[^\]]+)\]\((?P<lu>[^)\s]+)\)|`(?P<code>[^`]+)`"
)


# ---------- 마크다운 → 블록 ----------


def rich_text(text: str) -> list[dict]:
    """한 줄 마크다운을 Notion rich_text 배열로 바꾼다. 2000자가 넘는 조각은 나눈다."""
    parts, pos = [], 0
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            parts.append(("text", text[pos : m.start()], {}))
        if m.group("eq") is not None:
            parts.append(("equation", m.group("eq"), {}))
        elif m.group("lt") is not None:
            parts.append(("text", m.group("lt"), {"link": m.group("lu")}))
        elif m.group("code") is not None:
            parts.append(("text", m.group("code"), {"code": True}))
        else:
            parts.append(("text", m.group("b1") or m.group("b2"), {"bold": True}))
        pos = m.end()
    if pos < len(text):
        parts.append(("text", text[pos:], {}))

    out = []
    for kind, content, style in parts:
        if kind == "equation":
            out.append({"type": "equation", "equation": {"expression": content}})
            continue
        for i in range(0, len(content), MAX_TEXT):
            item = {"type": "text", "text": {"content": content[i : i + MAX_TEXT]}}
            if "link" in style:
                item["text"]["link"] = {"url": style["link"]}
            if style.get("bold") or style.get("code"):
                item["annotations"] = {"bold": bool(style.get("bold")), "code": bool(style.get("code"))}
            out.append(item)
    return out


def text_block(kind: str, text: str, **extra) -> dict:
    return {"type": kind, kind: {"rich_text": rich_text(text), **extra}}


def table_block(rows: list[str]) -> dict:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [r for r in cells if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]  # 구분선 |---|
    width = max(len(r) for r in cells)
    children = [
        {"type": "table_row", "table_row": {"cells": [rich_text(c) for c in r + [""] * (width - len(r))]}}
        for r in cells
    ]
    return {
        "type": "table",
        "table": {"table_width": width, "has_column_header": True, "has_row_header": False},
        "children": children,
    }


def image_block(caption: str, path: Path) -> dict:
    # 실제 업로드 id는 발행할 때 채운다. _local은 Notion에 보내지 않는 내부 표시.
    return {
        "type": "image",
        "image": {"type": "file_upload", "file_upload": {"id": None}, "caption": rich_text(caption)},
        "_local": str(path),
    }


def markdown_to_blocks(lines: list[str], base_dir: Path) -> list[dict]:
    """요약 본문(메타데이터 다음부터)을 블록 트리로 바꾼다. 접기 블록은 children에 넣는다."""
    root: list[dict] = []
    stack: list[list[dict]] = [root]  # 현재 블록을 붙일 목록 (접기 블록 안이면 그 children)
    para: list[str] = []
    list_stack: list[tuple[int, dict]] = []  # (들여쓰기, 목록 블록)
    i = 0

    def flush_para() -> None:
        if para:
            stack[-1].append(text_block("paragraph", " ".join(s.strip() for s in para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("<!--"):
            flush_para()
            list_stack.clear()
            i += 1
            continue

        m = re.match(r"^<details>\s*<summary>(.*?)</summary>\s*$", stripped)
        if m:
            flush_para()
            list_stack.clear()
            title = re.sub(r"</?b>", "", m.group(1)).strip()
            level = "heading_2" if title != "자세히 보기" else "heading_3"
            block = text_block(level, title, is_toggleable=True)
            block["children"] = []
            stack[-1].append(block)
            stack.append(block["children"])
            i += 1
            continue
        if stripped == "</details>":
            flush_para()
            list_stack.clear()
            if len(stack) > 1:
                stack.pop()
            i += 1
            continue

        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            flush_para()
            list_stack.clear()
            level = {1: "heading_1", 2: "heading_2", 3: "heading_3"}[len(m.group(1))]
            stack[-1].append(text_block(level, m.group(2)))
            i += 1
            continue

        if stripped.startswith("$$"):
            flush_para()
            list_stack.clear()
            expr_lines = [stripped[2:]]
            if not (stripped.endswith("$$") and len(stripped) > 2):
                i += 1
                while i < len(lines) and not lines[i].strip().endswith("$$"):
                    expr_lines.append(lines[i])
                    i += 1
                if i < len(lines):
                    expr_lines.append(lines[i].strip()[:-2])
            else:
                expr_lines = [stripped[2:-2]]
            expr = "\n".join(l for l in expr_lines if l.strip()).strip()
            stack[-1].append({"type": "equation", "equation": {"expression": expr}})
            i += 1
            continue

        if stripped.startswith("|"):
            flush_para()
            list_stack.clear()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            stack[-1].append(table_block(rows))
            continue

        m = IMAGE_RE.match(stripped)
        if m:
            flush_para()
            list_stack.clear()
            stack[-1].append(image_block(m.group(1), base_dir / m.group(2)))
            i += 1
            continue

        m = LIST_RE.match(line)
        if m:
            flush_para()
            indent = len(m.group(1).replace("\t", "    "))
            kind = "numbered_list_item" if m.group(2) else "bulleted_list_item"
            block = text_block(kind, m.group(3))
            while list_stack and list_stack[-1][0] >= indent:
                list_stack.pop()
            if list_stack:
                list_stack[-1][1].setdefault("children", []).append(block)
            else:
                stack[-1].append(block)
            list_stack.append((indent, block))
            i += 1
            continue

        list_stack.clear()
        para.append(line)
        i += 1

    flush_para()
    return root


# ---------- 메타데이터 → 속성 ----------


def parse_summary(md_path: Path) -> tuple[dict, list[str], list[str]]:
    """(메타데이터, 본문 머리 목록 줄, 본문 줄)로 나눈다."""
    lines = md_path.read_text(encoding="utf-8").splitlines()
    title_idx = next(i for i, l in enumerate(lines) if l.startswith("# "))
    meta = {"title": lines[title_idx][2:].strip()}
    header, i = [], title_idx + 1
    while i < len(lines) and not lines[i].startswith("## "):
        m = META_RE.match(lines[i].strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
            if m.group(1) not in ("태그", "Notion"):  # 태그는 속성으로, Notion 주소는 로컬용
                header.append(lines[i].strip())
        i += 1
    return meta, header, lines[i:]


def three_lines(body: list[str]) -> list[str]:
    """'## 3줄 요약' 아래 목록 3줄."""
    out, inside = [], False
    for line in body:
        if line.startswith("## "):
            if inside:
                break
            inside = line.strip() == "## 3줄 요약"
            continue
        m = LIST_RE.match(line)
        if inside and m and not m.group(1):
            out.append(m.group(3))
    return out[:3]


def plain(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*|<b>(.+?)</b>", lambda m: m.group(1) or m.group(2), text)
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text).strip()


def short_line(text: str, limit: int = 150) -> str:
    """3줄 요약 속성용: 첫 문장(마침표까지)만, 아주 길면 자른다."""
    text = plain(text)
    m = re.search(r"\.\s", text + " ")
    first = text[: m.end()].strip() if m else text
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def build_properties(meta: dict, body: list[str], status: str | None) -> dict:
    link_src = meta.get("링크") or meta.get("공개") or ""
    urls = URL_RE.findall(link_src)
    year = re.search(r"\b(19|20)\d\d\b", meta.get("공개", ""))
    org = meta.get("기관")
    if not org:
        m = re.search(r"\(([^)]+)\)\s*$", meta.get("저자", ""))
        org = m.group(1) if m else ""
    tags = [t.strip() for t in meta.get("태그", "").split(",") if t.strip()]
    summary3 = "\n".join(short_line(l) for l in three_lines(body))

    props = {
        "제목": {"title": rich_text(meta["title"])},
        "링크": {"url": urls[0] if urls else None},
        "연도": {"number": int(year.group(0)) if year else None},
        "기관": {"rich_text": rich_text(org) if org and org != "확인 필요" else []},
        "태그": {"multi_select": [{"name": t.replace(",", " ")[:100]} for t in tags]},
        "3줄 요약": {"rich_text": rich_text(summary3)},
        "정리일": {"date": {"start": date.today().isoformat()}},
    }
    if status:
        props["상태"] = {"select": {"name": status}}
    return props


def split_memo(blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    """'내 메모' 제목 앞(요약)과 '내 메모' 이하로 나눈다."""
    for i, b in enumerate(blocks):
        if b["type"].startswith("heading") and plain_of(b) == MEMO_HEADING:
            return blocks[:i], blocks[i:]
    return blocks, []


def plain_of(block: dict) -> str:
    rt = block.get(block["type"], {}).get("rich_text", [])
    return "".join(r.get("text", {}).get("content", "") or r.get("plain_text", "") for r in rt).strip()


# ---------- 검증과 미리보기 ----------


def walk(blocks: list[dict], depth: int = 0):
    for b in blocks:
        yield b, depth
        yield from walk(b.get("children", []), depth + 1)


def validate(blocks: list[dict]) -> list[str]:
    problems = []
    for b, _ in walk(blocks):
        t = b["type"]
        if t == "equation" and len(b["equation"]["expression"]) > MAX_EQUATION:
            problems.append(f"수식이 {MAX_EQUATION}자를 넘음: {b['equation']['expression'][:40]}…")
        if t == "image":
            p = Path(b["_local"])
            if not p.is_file():
                problems.append(f"이미지 파일 없음: {p}")
            elif p.stat().st_size > MAX_UPLOAD_BYTES:
                problems.append(f"이미지가 20MB를 넘음: {p}")
        if t == "table" and not b["children"]:
            problems.append("빈 표")
        if len(b.get("children", [])) > MAX_CHILDREN and t != "table":
            pass  # 발행할 때 100개씩 나눠 보낸다
        if t == "table" and len(b["children"]) > MAX_CHILDREN:
            problems.append(f"표 행이 {MAX_CHILDREN}개를 넘음")
    return problems


def outline(blocks: list[dict]) -> str:
    lines = []
    for b, depth in walk(blocks):
        t = b["type"]
        if t == "table_row":
            continue
        if t == "image":
            desc = Path(b["_local"]).name
        elif t == "equation":
            desc = b["equation"]["expression"][:60].replace("\n", " ")
        elif t == "table":
            desc = f"{len(b['children'])}행 × {b['table']['table_width']}열"
        else:
            desc = plain_of(b)[:60]
        toggle = " [접기]" if b.get(t, {}).get("is_toggleable") else ""
        lines.append(f"{'  ' * depth}- {t}{toggle}: {desc}")
    return "\n".join(lines)


# ---------- Notion API ----------


class Notion:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION})

    def call(self, method: str, path: str, **kw) -> dict:
        for attempt in range(5):
            r = self.s.request(method, f"{NOTION_API}{path}", timeout=120, **kw)
            if r.status_code in (429, 500, 502, 503, 529):
                time.sleep(float(r.headers.get("Retry-After", 2 ** attempt)))
                continue
            if not r.ok:
                sys.exit(f"Notion API 오류 {r.status_code} ({method} {path}): {r.text[:500]}")
            return r.json()
        sys.exit(f"Notion API가 계속 응답하지 않습니다: {method} {path}")

    def data_source_id(self, database_id: str) -> str:
        db = self.call("GET", f"/databases/{database_id}")
        sources = db.get("data_sources") or []
        if not sources:
            sys.exit("데이터베이스에서 data source를 찾지 못했습니다. 통합이 데이터베이스에 연결됐는지 확인하세요.")
        return sources[0]["id"]

    def find_page(self, ds_id: str, title: str) -> dict | None:
        res = self.call(
            "POST", f"/data_sources/{ds_id}/query", json={"filter": {"property": "제목", "title": {"equals": title}}}
        )
        pages = [p for p in res.get("results", []) if not p.get("in_trash") and not p.get("archived")]
        return pages[0] if pages else None

    def upload(self, path: Path) -> str:
        ctype = mimetypes.guess_type(path.name)[0] or "image/png"
        fu = self.call("POST", "/file_uploads", json={"filename": path.name, "content_type": ctype})
        with path.open("rb") as f:
            self.call("POST", f"/file_uploads/{fu['id']}/send", files={"file": (path.name, f, ctype)})
        return fu["id"]

    def children(self, block_id: str) -> list[dict]:
        out, cursor = [], None
        while True:
            q = f"?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            res = self.call("GET", f"/blocks/{block_id}/children{q}")
            out += res["results"]
            if not res.get("has_more"):
                return out
            cursor = res["next_cursor"]

    def append(self, parent_id: str, blocks: list[dict], after: str | None = None) -> list[dict]:
        """블록을 100개씩 붙인다. 중첩 제한(2단계)을 피하려고 자식은 부모를 만든 뒤 따로 붙인다(표 행은 함께)."""
        created = []
        for i in range(0, len(blocks), MAX_CHILDREN):
            batch = blocks[i : i + MAX_CHILDREN]
            body = {"children": [shallow(b) for b in batch]}
            if after:
                body["position"] = {"type": "after_block", "after_block": {"id": after}}
            res = self.call("PATCH", f"/blocks/{parent_id}/children", json=body)
            results = res["results"]
            for src, made in zip(batch, results):
                kids = src.get("children", [])
                if kids and src["type"] != "table":
                    self.append(made["id"], kids)
            created += results
            after = results[-1]["id"] if after else None
        return created


def shallow(block: dict) -> dict:
    """보낼 블록: 내부 표시(_local)와 자식을 뺀다. 표는 행을 같이 보낸다."""
    b = {k: v for k, v in block.items() if k not in ("children", "_local")}
    if block["type"] == "table":
        b["table"] = {**block["table"], "children": block["children"]}
    return b


def fill_uploads(api: Notion, blocks: list[dict]) -> int:
    n = 0
    for b, _ in walk(blocks):
        if b["type"] == "image" and b["image"]["file_upload"]["id"] is None:
            b["image"]["file_upload"]["id"] = api.upload(Path(b["_local"]))
            n += 1
    return n


# ---------- 실행 ----------


def main() -> None:
    parser = argparse.ArgumentParser(description="요약 md를 Notion '논문 리뷰'에 올린다 (기본은 미리보기).")
    parser.add_argument("--summary", required=True, help="output/<논문>_summary_*.md")
    parser.add_argument("--publish", action="store_true", help="실제로 Notion에 올린다")
    parser.add_argument(
        "--update-existing", action="store_true", help="같은 제목 페이지가 있으면 '내 메모' 앞 내용만 바꾼다"
    )
    parser.add_argument("--database", help="데이터베이스 ID (생략하면 환경변수 NOTION_DATABASE_ID)")
    args = parser.parse_args()

    md_path = Path(args.summary).resolve()
    meta, header, body = parse_summary(md_path)
    blocks = markdown_to_blocks(header + [""] + body, md_path.parent)
    props = build_properties(meta, body, INITIAL_STATUS)
    problems = validate(blocks)

    n_img = sum(1 for b, _ in walk(blocks) if b["type"] == "image")
    n_eq = sum(1 for b, _ in walk(blocks) if b["type"] == "equation")
    n_toggle = sum(1 for b, _ in walk(blocks) if b.get(b["type"], {}).get("is_toggleable"))
    print(f"[변환] {meta['title']}")
    print(f"[변환] 블록 {sum(1 for _ in walk(blocks))}개 (접기 {n_toggle}, 이미지 {n_img}, 수식 블록 {n_eq})")
    print("[속성] " + json.dumps({k: summarize_prop(v) for k, v in props.items()}, ensure_ascii=False))
    for p in problems:
        print(f"[문제] {p}")

    if not args.publish:
        preview = md_path.with_name(md_path.stem + "_notion_preview.json")
        preview.write_text(
            json.dumps({"properties": props, "children": blocks}, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(outline(blocks))
        print(f"[미리보기] {preview.name} 저장. Notion은 호출하지 않았습니다. 올리려면 --publish를 붙이세요.")
        return
    if problems:
        sys.exit("위 문제를 고친 뒤 다시 실행하세요.")

    load_env()
    token = os.environ.get("NOTION_TOKEN")
    database_id = args.database or os.environ.get("NOTION_DATABASE_ID")
    if not token or not database_id:
        sys.exit("NOTION_TOKEN과 NOTION_DATABASE_ID를 저장소 최상위 .env에 넣어 주세요 (README '방법 3' 참고).")

    api = Notion(token)
    ds_id = api.data_source_id(database_id)
    existing = api.find_page(ds_id, meta["title"])
    content, _memo = split_memo(blocks)

    if existing and not args.update_existing:
        sys.exit(
            f"같은 제목의 페이지가 이미 있습니다: {existing.get('url')}\n"
            "새로 만들지 않았습니다. 내용을 바꾸려면 --update-existing을 붙이세요 ('내 메모'와 '상태'는 유지)."
        )

    uploaded = fill_uploads(api, blocks)
    print(f"[발행] 이미지 {uploaded}개 업로드")

    if existing:
        page_id = existing["id"]
        del props["상태"]  # 읽는 중·완료 등 사용자가 바꾼 상태를 유지
        api.call("PATCH", f"/pages/{page_id}", json={"properties": props})
        old = api.children(page_id)
        old_content, old_memo = split_memo(old)
        if not old_memo:
            sys.exit("기존 페이지에서 '내 메모' 제목을 찾지 못해 본문은 바꾸지 않았습니다 (속성만 갱신).")
        for b in old_content:
            api.call("DELETE", f"/blocks/{b['id']}")
        first = api.call(
            "PATCH",
            f"/blocks/{page_id}/children",
            json={"children": [shallow(content[0])], "position": {"type": "start"}},
        )["results"][0]
        if content[0].get("children") and content[0]["type"] != "table":
            api.append(first["id"], content[0]["children"])
        api.append(page_id, content[1:], after=first["id"])
        print(f"[발행] 기존 페이지 갱신 ('내 메모' 이하 {len(old_memo)}개 블록 유지): {existing.get('url')}")
    else:
        page = api.call(
            "POST",
            "/pages",
            json={"parent": {"data_source_id": ds_id}, "icon": {"type": "emoji", "emoji": "📄"}, "properties": props},
        )
        api.append(page["id"], blocks)
        print(f"[발행] 새 페이지: {page.get('url')}")


def summarize_prop(v: dict):
    kind = next(iter(v))
    val = v[kind]
    if kind in ("title", "rich_text"):
        return "".join(
            f"${r['equation']['expression']}$" if r["type"] == "equation" else r["text"]["content"] for r in val
        )
    if kind == "multi_select":
        return [t["name"] for t in val]
    if kind in ("select",):
        return val["name"]
    if kind == "date":
        return val["start"]
    return val


if __name__ == "__main__":
    main()
