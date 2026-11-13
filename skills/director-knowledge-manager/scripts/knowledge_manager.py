#!/usr/bin/env python3
"""Director knowledge ingestion and user-gated publication using stdlib only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROLE_MAP = {
    "动作导演": ["scene-dongzuo-daoyan", "scene-biaoyan-diaodu-daoyan", "seedance-shot-prompt-compiler"],
    "表演相关": ["scene-biaoyan-diaodu-daoyan", "scene-taici-daoyan", "seedance-shot-prompt-compiler"],
    "三级权重导演": ["scene-texiao-daoyan", "scene-chuangyi-daoyan"],
    "总导演": ["scene-zongdaoyan", "scene-sheying-fenjing-daoyan", "scene-lianxuxing-zhixing-daoyan", "scene-dengguang-daoyan", "scene-tiaose-daoyan", "scene-shengyin-daoyan"],
    "提示词导演": ["seedance-shot-prompt-compiler"],
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slug(value: str) -> str:
    ascii_part = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return ascii_part or sha(value.encode("utf-8"))[:12]


class VisibleHTML(HTMLParser):
    BLOCKED = {"script", "style", "svg", "canvas", "video", "audio", "picture", "nav", "form", "button", "iframe", "noscript"}
    BREAKS = {"h1", "h2", "h3", "h4", "p", "div", "li", "tr", "br", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []
        self.heading: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.BLOCKED:
            self.depth += 1
        if self.depth == 0:
            if tag in self.BREAKS:
                self.parts.append("\n")
            if tag in {"h1", "h2", "h3", "h4"}:
                self.heading = "#" * int(tag[1]) + " "
                self.parts.append(self.heading)
            elif tag == "li":
                self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.BLOCKED and self.depth:
            self.depth -= 1
        if self.depth == 0 and tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.depth == 0 and data.strip():
            self.parts.append(data.strip() + " ")

    def markdown(self) -> str:
        text = "".join(self.parts).replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text + "\n"


def convert(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".md", ".markdown"}:
        return raw.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
    parser = VisibleHTML(); parser.feed(raw)
    return parser.markdown()


def ingest(source_root: Path, catalog_path: Path, converted_root: Path) -> dict[str, Any]:
    prior: dict[str, Any] = {}
    if catalog_path.exists():
        prior_value = json.loads(catalog_path.read_text(encoding="utf-8"))
        prior = {item["source_path"]: item for item in prior_value.get("sources", [])}
    sources = []
    files = sorted(path for path in source_root.rglob("*") if path.is_file() and path.suffix.lower() in {".html", ".htm", ".md", ".markdown"})
    for path in files:
        relative = path.relative_to(source_root)
        directory = relative.parts[0] if len(relative.parts) > 1 else "root"
        data = path.read_bytes(); file_hash = sha(data); text = convert(path)
        source_id = "dks-" + sha(str(relative).encode("utf-8"))[:12]
        converted_rel = Path(directory) / f"{source_id}-{slug(path.stem)}.md"
        target = converted_root / converted_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        header = f"# {path.stem}\n\n来源 ID：`{source_id}`\n\n原文件：`{relative}`\n\n原文件 SHA-256：`{file_hash}`\n\n"
        converted = header + text
        target.write_text(converted, encoding="utf-8")
        previous = prior.get(str(relative), {})
        same = previous.get("file_sha256") == file_hash
        old_published = previous.get("status") == "published" and same
        status = "published" if old_published else "review_pending"
        sources.append({
            "source_id": source_id, "original_directory": directory, "title": path.stem,
            "author": None, "rights_status": "user_asserted", "source_path": str(relative),
            "converted_path": str(converted_rel), "file_sha256": file_hash,
            "conversion_sha256": sha(converted.encode("utf-8")), "role_candidates": ROLE_MAP.get(directory, []),
            "status": status, "isolated": directory == "提示词导演", "reviews": previous.get("reviews", []),
            "supersedes_published_hash": previous.get("file_sha256") if previous.get("status") == "published" and not same else None,
        })
    value = {"schema_version": "DirectorKnowledgeCatalogV1", "catalog_version": now(), "sources": sources}
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return value


def publish(catalog_path: Path, role_path: Path, review_path: Path) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("schema_version") != "DirectorKnowledgeReviewV1" or review.get("reviewer") != "user" or not review.get("confirmed_at"):
        raise ValueError("publication requires an explicit user review record")
    decisions = review.get("decisions", {})
    prompt_only = review.get("publication_scope") == "isolated_prompt_only" and review.get("target_role") == "seedance-shot-prompt-compiler"
    for source in catalog["sources"]:
        decision = decisions.get(source["source_id"])
        if not decision:
            continue
        if source.get("isolated") and decision == "publish" and not prompt_only:
            raise ValueError(f"isolated source cannot publish: {source['source_id']}")
        if source.get("isolated") and decision == "publish" and source.get("original_directory") != "提示词导演":
            raise ValueError(f"only 提示词导演 sources may use isolated prompt publication: {source['source_id']}")
        source["status"] = "published" if decision == "publish" else "rejected"
        source["reviews"].append({"reviewer": "user", "decision": decision, "confirmed_at": review["confirmed_at"], "note": review.get("notes", {}).get(source["source_id"])})
    catalog["catalog_version"] = now()
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_role: dict[str, list[str]] = {}
    for source in catalog["sources"]:
        if source["status"] != "published":
            continue
        if source["isolated"]:
            if source.get("original_directory") == "提示词导演" and "seedance-shot-prompt-compiler" in source.get("role_candidates", []):
                by_role.setdefault("seedance-shot-prompt-compiler", []).append(source["source_id"])
            continue
        for role in source["role_candidates"]:
            by_role.setdefault(role, []).append(source["source_id"])
    roles = []
    for role, ids in sorted(by_role.items()):
        deps = sorted(ids)
        prompt_role = role == "seedance-shot-prompt-compiler"
        roles.append({"role_id": role, "scope": "isolated Seedance prompt compilation" if prompt_role else "published director knowledge", "activation_rule": "explicit seedance prompt compilation only" if prompt_role else "role selected by scene director", "weight": "compiler" if prompt_role else "normal", "source_ids": deps, "published_version": catalog["catalog_version"], "dependency_hash": sha("\n".join(deps).encode("utf-8"))})
    role_catalog = {"schema_version": "DirectorRoleCatalogV1", "release_version": catalog["catalog_version"], "roles": roles}
    role_path.parent.mkdir(parents=True, exist_ok=True)
    role_path.write_text(json.dumps(role_catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return role_catalog


def main() -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("ingest"); item.add_argument("source", type=Path); item.add_argument("catalog", type=Path); item.add_argument("converted", type=Path)
    item = sub.add_parser("publish"); item.add_argument("catalog", type=Path); item.add_argument("roles", type=Path); item.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    value = ingest(args.source, args.catalog, args.converted) if args.command == "ingest" else publish(args.catalog, args.roles, args.review)
    print(json.dumps({"status": "ok", "count": len(value.get("sources", value.get("roles", [])))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
