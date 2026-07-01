#!/usr/bin/env python3
"""
extract_texts.py - 粗提取模块
在模型介入前，用正则/结构化方式尽可能多地提取待翻译文本。
提取结果写入 translation_tasks.jsonl，模型后续精筛并翻译。

提取范围：
1. 模组语言文件 (.json/.lang) — 与已有 zh_cn 比 key，只提缺失的
2. FTB Quests (.snbt) — title/subtitle/description/text
3. CraftTweaker (.zs) — translate()/setName()/addTooltip()
4. KubeJS (.js) — 所有字符串字面量（标记 js_auto，模型精筛）
5. 配置文件 (.toml/.cfg) — 字符串值和注释
"""

import sys
import os
import json
import re
from pathlib import Path
from collections import defaultdict

TARGET_DIR = Path(sys.argv[1]).resolve()
JSONL_PATH = TARGET_DIR / "translation_tasks.jsonl"

# 统计
stats = defaultdict(int)
next_id = 1


def add_entry(source_file: str, key: str, original: str, context_hint: str = ""):
    """向 JSONL 追加一条记录"""
    global next_id
    entry = {
        "id": next_id,
        "source_file": source_file,
        "key": key,
        "original": original,
        "translated": "",
        "status": "pending",
        "context_hint": context_hint,
    }
    with open(JSONL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    next_id += 1


def find_zh_cn(target: Path, modid: str) -> Path | None:
    """查找某模组已有的 zh_cn.json（kubejs 覆盖目录中）"""
    candidates = [
        target / "kubejs" / "assets" / modid / "lang" / "zh_cn.json",
        target / "kubejs" / "assets" / modid / "lang" / "zh_CN.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ─── 1. 模组语言文件 ───────────────────────────────────────

def extract_lang_files():
    temp = TARGET_DIR / "_temp_extracted"
    if not temp.is_dir():
        print("[跳过] _temp_extracted 目录不存在")
        return

    for mod_dir in sorted(temp.iterdir()):
        if not mod_dir.is_dir():
            continue
        modid = mod_dir.name

        en_json = mod_dir / "lang" / "en_us.json"
        en_lang = mod_dir / "lang" / "en_us.lang"
        en_us_lang = mod_dir / "lang" / "en_US.lang"

        zh_path = find_zh_cn(TARGET_DIR, modid)

        # ── JSON 格式 ──
        if en_json.exists():
            try:
                en_data = json.loads(en_json.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [警告] 解析失败 {en_json}: {e}")
                continue

            # 已有 zh_cn → 比较 key 数量
            existing_keys = set()
            if zh_path:
                try:
                    zh_data = json.loads(zh_path.read_text(encoding="utf-8"))
                    existing_keys = set(zh_data.keys())
                except Exception:
                    pass

            missing = {k for k in en_data if k not in existing_keys}
            if zh_path and not missing:
                print(f"  [跳过] {modid}: zh_cn 已全覆盖 ({len(en_data)}/{len(en_data)} keys)")
                stats["skip_full_match"] += 1
                continue
            elif zh_path and missing:
                print(f"  [补充] {modid}: en_us {len(en_data)}, zh_cn {len(existing_keys)}, 缺 {len(missing)}")
                stats["mod_partial"] += 1
            else:
                print(f"  [提取] {modid}: {len(en_data)} 条")
                stats["mod_full"] += 1

            for k in (missing if zh_path else en_data):
                v = en_data[k]
                if isinstance(v, str) and v.strip():
                    add_entry(
                        f"_temp_extracted/{modid}/lang/en_us.json",
                        k, v
                    )

        # ── LANG 格式 ──
        lang_file = en_lang if en_lang.exists() else (en_us_lang if en_us_lang.exists() else None)
        if lang_file:
            try:
                lines = lang_file.read_text(encoding="utf-8").splitlines()
            except Exception as e:
                print(f"  [警告] 读取失败 {lang_file}: {e}")
                continue

            extracted = 0
            for line_no, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if v:
                        add_entry(
                            f"_temp_extracted/{modid}/lang/{lang_file.name}",
                            k, v, f"line: {line_no}"
                        )
                        extracted += 1
            if extracted:
                print(f"  [提取] {modid} (.lang): {extracted} 条")
                stats["mod_lang"] += 1


# ─── 2. FTB Quests (.snbt) ──────────────────────────────────

def extract_snbt():
    """提取 .snbt 中的 title/subtitle/description/text"""
    snbt_files = []
    config_dir = TARGET_DIR / "config"
    if config_dir.is_dir():
        snbt_files.extend(config_dir.rglob("*.snbt"))

    snbt_count = 0
    for fp in snbt_files:
        rel = str(fp.relative_to(TARGET_DIR)).replace("\\", "/")
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = text.splitlines()
        entries = 0

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 单行模式: title: "xxx", subtitle: "xxx", text: "xxx"
            m = re.match(r'(title|subtitle|name|text)\s*:\s*"(.+?)"', line)
            if m:
                field, value = m.group(1), m.group(2)
                if value.strip():
                    add_entry(rel, f"{field}:L{i+1}", value, f"line: {i+1}")
                    entries += 1
                i += 1
                continue

            # 多行数组模式: description: ["abc", "def"]
            m = re.match(r"description\s*:\s*\[", line)
            if m:
                # 收集直到 ]
                full = line
                j = i
                while "]" not in full and j + 1 < len(lines):
                    j += 1
                    full = "\n".join(lines[i:j+1])

                # 提取所有引号内字符串
                vals = re.findall(r'"(.+?)"', full)
                for idx, v in enumerate(vals):
                    if v.strip():
                        add_entry(rel, f"desc[{idx}]:L{i+1}", v, f"line: {i+1}")
                        entries += 1
                i = j + 1
                continue

            # 多行描述: description: [\n"Line 1"\n"Line 2"\n]
            m = re.match(r"description\s*:\s*\[\s*$", line)
            if m:
                j = i + 1
                vals = []
                while j < len(lines):
                    ln = lines[j].strip()
                    if ln == "]":
                        break
                    m2 = re.match(r'"(.+?)"\s*$', ln)
                    if m2:
                        vals.append(m2.group(1))
                    j += 1
                for idx, v in enumerate(vals):
                    if v.strip():
                        add_entry(rel, f"desc[{idx}]:L{i+1}", v, f"line: {i+1}")
                        entries += 1
                i = j + 1
                continue

            i += 1

        if entries:
            print(f"  [SNBT] {rel}: {entries} 条")
            snbt_count += 1

    if snbt_count:
        stats["snbt"] = snbt_count


# ─── 3. CraftTweaker (.zs) ──────────────────────────────────

def extract_zs():
    """提取 .zs 中 translate()/setName()/addTooltip() 的字符串参数"""
    zs_files = list(TARGET_DIR.rglob("*.zs"))

    zs_count = 0
    for fp in zs_files:
        # 跳过临时和备份目录
        if any(p.startswith("_") for p in fp.relative_to(TARGET_DIR).parts):
            continue
        rel = str(fp.relative_to(TARGET_DIR)).replace("\\", "/")
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = text.splitlines()
        entries = 0

        for line_no, line in enumerate(lines, 1):
            line = line.strip()

            # translate("...")
            for m in re.finditer(r'translate\s*\(\s*"(.+?)"', line):
                if m.group(1).strip():
                    add_entry(rel, f"translate:L{line_no}", m.group(1), f"line: {line_no}")
                    entries += 1

            # .setName("...")
            for m in re.finditer(r'\.setName\s*\(\s*"(.+?)"', line):
                if m.group(1).strip():
                    add_entry(rel, f"setName:L{line_no}", m.group(1), f"line: {line_no}")
                    entries += 1

            # .addTooltip("...")
            for m in re.finditer(r'\.addTooltip\s*\(\s*"(.+?)"', line):
                if m.group(1).strip():
                    add_entry(rel, f"tooltip:L{line_no}", m.group(1), f"line: {line_no}")
                    entries += 1

        if entries:
            print(f"  [ZS] {rel}: {entries} 条")
            zs_count += 1

    if zs_count:
        stats["zs"] = zs_count


# ─── 4. KubeJS (.js) ────────────────────────────────────────

def extract_js():
    """
    KubeJS .js 文件：提取所有字符串字面量。
    这会引入大量误提取（变量名、路径等），全部标记 source_type=js_auto，
    由模型在后续步骤中精筛。
    """
    js_files = list(TARGET_DIR.rglob("*.js"))

    js_count = 0
    for fp in js_files:
        if any(p.startswith("_") for p in fp.relative_to(TARGET_DIR).parts):
            continue
        rel = str(fp.relative_to(TARGET_DIR)).replace("\\", "/")
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = text.splitlines()
        entries = 0

        for line_no, line in enumerate(lines, 1):
            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue

            # 双引号字符串 (排除空串和纯数字)
            for m in re.finditer(r'"([^"]*)"', line):
                s = m.group(1)
                if is_likely_text(s):
                    add_entry(rel, f"str:L{line_no}", s, f"line: {line_no}")
                    entries += 1

            # 单引号字符串
            for m in re.finditer(r"'([^']*)'", line):
                s = m.group(1)
                if is_likely_text(s):
                    add_entry(rel, f"str:L{line_no}", s, f"line: {line_no}")
                    entries += 1

            # 模板字符串
            for m in re.finditer(r'`([^`]*)`', line):
                s = m.group(1)
                # 去掉模板插值 ${...}
                s = re.sub(r'\$\{[^}]*\}', '', s)
                if is_likely_text(s):
                    add_entry(rel, f"str:L{line_no}", s, f"line: {line_no}")
                    entries += 1

        if entries:
            print(f"  [JS] {rel}: {entries} 条（待模型精筛）")
            js_count += 1

    if js_count:
        stats["js_auto"] = js_count


def is_likely_text(s: str) -> bool:
    """粗筛：判断字符串是否像玩家可见文本（宁可多提）"""
    s = s.strip()
    if not s:
        return False
    if len(s) <= 1:
        return False
    # 纯数字/纯符号 → 不是文本
    if re.match(r'^[\d\s.+\-*/%=<>!&|^~,;:{}[\]()\\]+$', s):
        return False
    # 纯路径/ID 模式
    if re.match(r'^[a-z_][a-z0-9_.:/]*$', s) and "/" in s:
        return False
    # 明显是代码标识符（纯 snake_case 或 camelCase，无空格无标点）
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', s) and "_" in s and " " not in s:
        if len(s.split("_")) >= 2:
            return False
    # 包含至少一个英文字母
    if not re.search(r'[a-zA-Z]', s):
        return False
    return True


# ─── 5. 配置文件 (.toml / .cfg) ─────────────────────────────

def extract_config():
    """提取 .toml 和 .cfg 中的字符串值和注释"""
    cfg_files = list(TARGET_DIR.rglob("*.toml")) + list(TARGET_DIR.rglob("*.cfg"))

    cfg_count = 0
    for fp in cfg_files:
        if any(p.startswith("_") for p in fp.relative_to(TARGET_DIR).parts):
            continue
        rel = str(fp.relative_to(TARGET_DIR)).replace("\\", "/")

        # 跳过 FTB Quests 的 quests 子目录（已被 snbt 处理）
        if "ftbquests" in rel.lower() and not rel.endswith(".cfg"):
            continue

        try:
            lines = fp.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        entries = 0

        for line_no, line in enumerate(lines, 1):
            stripped = line.strip()

            # CFG 注释: # 或 ; 开头
            if stripped.startswith("#") or stripped.startswith(";"):
                comment = stripped[1:].strip()
                if len(comment) > 3 and re.search(r'[a-zA-Z]', comment):
                    add_entry(rel, f"comment:L{line_no}", comment, f"line: {line_no}")
                    entries += 1
                continue

            # TOML 格式: key = "value"
            m = re.match(r'(\w+)\s*=\s*"(.+?)"', stripped)
            if m:
                key, value = m.group(1), m.group(2)
                # 排除明显的非文本 key（如路径、布尔值别名）
                if key.lower() in ("path", "file", "url", "version"):
                    continue
                if value.strip() and re.search(r'[a-zA-Z]', value) and len(value) > 1:
                    add_entry(rel, key, value, f"line: {line_no}")
                    entries += 1

        if entries:
            print(f"  [配置] {rel}: {entries} 条")
            cfg_count += 1

    if cfg_count:
        stats["config"] = cfg_count


# ─── 主流程 ─────────────────────────────────────────────────

def main():
    if not TARGET_DIR.is_dir():
        print(f"错误: 目标目录不存在: {TARGET_DIR}")
        sys.exit(1)

    print(f"[粗提取] 目标: {TARGET_DIR}\n")

    # 清空旧 JSONL
    if JSONL_PATH.exists():
        backup = JSONL_PATH.with_suffix(".jsonl.bak")
        JSONL_PATH.rename(backup)
        print(f"[准备] 已备份旧 JSONL -> {backup.name}")

    files_before = 0

    # 1. 模组语言文件
    print("\n── 模组语言文件 ──")
    extract_lang_files()
    files_before = next_id - 1
    if files_before:
        print(f"  -> 小计: {files_before} 条\n")

    # 2. FTB Quests
    print("── FTB Quests (.snbt) ──")
    extract_snbt()
    snbt_count = next_id - 1 - files_before
    files_before = next_id - 1

    # 3. CraftTweaker
    print("── CraftTweaker (.zs) ──")
    extract_zs()

    # 4. KubeJS
    print("── KubeJS (.js) ──")
    extract_js()

    # 5. 配置文件
    print("── 配置文件 (.toml/.cfg) ──")
    extract_config()

    # ── 汇总 ──
    total = next_id - 1
    print(f"\n{'='*50}")
    print(f"[完成] 粗提取完毕，共 {total} 条待翻译条目")
    print(f"\n分布:")
    print(f"  模组全覆盖跳过: {stats.get('skip_full_match', 0)} 个")
    print(f"  模组全量提取:   {stats.get('mod_full', 0)} 个")
    print(f"  模组增量补充:   {stats.get('mod_partial', 0)} 个")
    print(f"  模组 .lang:     {stats.get('mod_lang', 0)} 个")
    print(f"  FTB Quests:     {stats.get('snbt', 0)} 个 .snbt")
    print(f"  CraftTweaker:   {stats.get('zs', 0)} 个 .zs")
    print(f"  KubeJS (粗提):  {stats.get('js_auto', 0)} 个 .js（待模型精筛）")
    print(f"  配置文件:       {stats.get('config', 0)} 个")
    print(f"\n输出文件: {JSONL_PATH}")
    print("下一步: 模型读取 JSONL，精筛后进入翻译流程")


if __name__ == "__main__":
    main()
