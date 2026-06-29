#!/usr/bin/env python3
"""
glossary_lookup.py - 术语查询模块
接收 translation_tasks.jsonl 文件路径和 ID 范围，查询术语表返回多义词 JSON 数组。
使用 Pickle 缓存加速，避免每次重复读取 CSV。
"""

import sys
import os
import json
import csv
import pickle
import argparse
from collections import defaultdict
from pathlib import Path

# 插件目录（脚本所在目录的父目录）
PLUGIN_DIR = Path(__file__).resolve().parent.parent
GLOSSARY_CSV = PLUGIN_DIR / "glossary.csv"
CACHE_FILE = PLUGIN_DIR / "glossary.csv.pkl"


def build_glossary_index(csv_path: Path) -> dict:
    """读取 CSV 术语表，构建 EN -> [ZH 列表] 索引"""
    glossary = defaultdict(list)
    if not csv_path.exists():
        print(f"[警告] 术语表不存在: {csv_path}", file=sys.stderr)
        return glossary

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                en = row[0].strip()
                zh = row[1].strip()
                if en and zh:
                    glossary[en].append(zh)

    return dict(glossary)  # 转普通 dict 便于 pickle


def load_glossary() -> dict:
    """加载术语表索引（优先使用 Pickle 缓存）"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"[警告] 缓存读取失败，重新构建: {e}", file=sys.stderr)

    glossary = build_glossary_index(GLOSSARY_CSV)
    try:
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(glossary, f)
        print(f"[缓存] 索引已缓存至 {CACHE_FILE}", file=sys.stderr)
    except Exception as e:
        print(f"[警告] 缓存写入失败: {e}", file=sys.stderr)

    return glossary


def lookup_terms(glossary: dict, texts: list) -> list:
    """批量查询术语，返回多义词结果列表"""
    results = []
    for text in texts:
        # 精确匹配
        if text in glossary:
            results.append(glossary[text])
        else:
            # 尝试小写匹配
            lower_text = text.lower()
            if lower_text in glossary:
                results.append(glossary[lower_text])
            else:
                # 标记无匹配
                results.append([])
    return results


def parse_ids(id_range: str) -> tuple:
    """解析 --ids 参数，如 '1-200' -> (1, 200)"""
    parts = id_range.split("-")
    if len(parts) == 1:
        start = int(parts[0])
        end = start
    elif len(parts) == 2:
        start = int(parts[0])
        end = int(parts[1])
    else:
        raise ValueError(f"无效的 ID 范围格式: {id_range}")
    return start, end


def main():
    parser = argparse.ArgumentParser(description="术语查询模块")
    parser.add_argument("jsonl_path", type=str, help="translation_tasks.jsonl 文件路径")
    parser.add_argument("--ids", type=str, required=True, help="ID 范围，如 '1-200'")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl_path).resolve()
    if not jsonl_path.exists():
        print(f"错误: JSONL 文件不存在: {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    # 解析 ID 范围
    start_id, end_id = parse_ids(args.ids)

    # 加载术语表
    print(f"[加载] 加载术语表索引 ...", file=sys.stderr)
    glossary = load_glossary()
    print(f"[加载] 术语表加载完成，共 {len(glossary)} 个词条", file=sys.stderr)

    # 读取 JSONL 中对应 ID 范围的 original 字段
    texts_to_lookup = []
    id_mapping = []  # 保持 ID 顺序

    with open(jsonl_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                task_id = data.get("id")
                if task_id is None:
                    continue
                if start_id <= task_id <= end_id:
                    texts_to_lookup.append(data.get("original", ""))
                    id_mapping.append(task_id)
            except json.JSONDecodeError:
                continue

    if not texts_to_lookup:
        print(f"[结果] ID 范围 {start_id}-{end_id} 内未找到记录", file=sys.stderr)
        return

    # 查询术语
    print(f"[查询] 正在查询 {len(texts_to_lookup)} 条术语 ...", file=sys.stderr)
    term_results = lookup_terms(glossary, texts_to_lookup)

    # 输出结果 (JSONL 格式，每行一个 ID 对应的多义词数组)
    for tid, terms in zip(id_mapping, term_results):
        output = {
            "id": tid,
            "translations": terms if terms else []
        }
        print(json.dumps(output, ensure_ascii=False))

    print(f"[完成] 共处理 {len(id_mapping)} 条", file=sys.stderr)


if __name__ == "__main__":
    main()
