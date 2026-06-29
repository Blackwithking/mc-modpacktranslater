#!/usr/bin/env python3
"""
generate_assets.py - 动态回写与生成模块
读取 JSONL 任务清单，探测 KubeJS 环境，生成翻译资源或兜底资源包。
利用 context_hint 对代码文件进行安全字符串替换。
"""

import sys
import os
import json
import zipfile
import io
import re
from pathlib import Path
from collections import defaultdict

TARGET_DIR = Path(sys.argv[1]).resolve()


def check_kubejs(target: Path) -> bool:
    """探测是否为 KubeJS 模式：检测 kubejs/ 目录或 mods/kubejs-*.jar"""
    if (target / "kubejs").is_dir():
        print("  [探测] 发现 kubejs/ 目录 -> KubeJS 模式")
        return True
    mods_dir = target / "mods"
    if mods_dir.is_dir():
        for jar in mods_dir.glob("kubejs-*.jar"):
            print(f"  [探测] 发现 {jar.name} -> KubeJS 模式")
            return True
    print("  [探测] 未检测到 KubeJS -> 兜底资源包模式")
    return False


def extract_modid(source_file: str) -> str:
    """从语言文件路径中提取 modid"""
    # 匹配 assets/<modid>/lang/ 模式
    m = re.search(r"assets/([^/]+)/lang/", source_file)
    if m:
        return m.group(1)
    # 从 jar 解压路径提取
    m = re.search(r"_temp_extracted/([^/]+)/", source_file)
    if m:
        return m.group(1)
    return "unknown"


def has_existing_translation(target: Path, modid: str) -> bool:
    """检查目标模组是否已存在 zh_cn 翻译"""
    checks = [
        target / "kubejs" / "assets" / modid / "lang" / "zh_cn.json",
        target / "kubejs" / "assets" / modid / "lang" / "zh_CN.lang",
    ]
    # 也检查资源包路径下的已有翻译
    for p in checks:
        if p.exists():
            print(f"  [跳过] {modid} 已有翻译文件: {p}")
            return True
    return False


def read_jsonl(jsonl_path: Path) -> list:
    """读取 JSONL 文件，返回所有条目"""
    entries = []
    if not jsonl_path.exists():
        print(f"错误: JSONL 文件不存在: {jsonl_path}")
        return entries

    with open(jsonl_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [警告] JSONL 解析失败: {e}")
    return entries


def safe_string_replace(content: str, old: str, new: str, context_hint: str = "") -> str:
    """
    安全字符串替换：利用 context_hint 中的锚点信息精确定位。
    优先使用行号锚点，否则使用精确字符串匹配。
    """
    if not old:
        return content

    # 尝试解析 context_hint 中的行号
    line_no = None
    if context_hint:
        m = re.search(r"line[:\s]*(\d+)", context_hint, re.IGNORECASE)
        if m:
            line_no = int(m.group(1))

    if line_no is not None:
        # 按行替换，仅替换指定行
        lines = content.split("\n")
        if 1 <= line_no <= len(lines):
            if old in lines[line_no - 1]:
                lines[line_no - 1] = lines[line_no - 1].replace(old, new, 1)
                return "\n".join(lines)
        # 行号无效或未匹配，回退到全局精确替换
        print(f"    [警告] 行号 {line_no} 未匹配，回退到全局精确替换")

    # 精确字符串替换 (只替换第一次出现)
    if old in content:
        return content.replace(old, new, 1)

    print(f"    [警告] 未找到原文: {old[:40]}...")
    return content


def process_lang_entries(entries: list, target: Path, is_kubejs: bool) -> dict:
    """
    处理语言文件条目，按 modid 分组生成翻译输出。
    返回资源包文件映射 {relative_path: content}
    """
    # 按 modid 分组
    modid_translations = defaultdict(dict)
    modid_source_map = {}  # modid -> first source_file for modid detection

    for entry in entries:
        source_file = entry.get("source_file", "")
        translated = entry.get("translated", "")
        key = entry.get("key", "")
        status = entry.get("status", "")

        if not translated or status != "done":
            continue

        # 只处理语言文件类型
        ext = Path(source_file).suffix.lower()
        if ext not in (".json", ".lang"):
            continue

        modid = extract_modid(source_file)
        if modid == "unknown":
            continue

        modid_translations[modid][key] = translated
        if modid not in modid_source_map:
            modid_source_map[modid] = source_file

    # 生成输出文件
    output_files = {}

    for modid, translations in modid_translations.items():
        # 跳过已有翻译的模组
        if has_existing_translation(target, modid):
            continue

        if not translations:
            continue

        if is_kubejs:
            # KubeJS 模式: 写入 kubejs/assets/<modid>/lang/zh_cn.json
            rel_path = f"kubejs/assets/{modid}/lang/zh_cn.json"
            content = json.dumps(translations, ensure_ascii=False, indent=2)
            output_files[rel_path] = content
            print(f"  [KubeJS] 生成 {rel_path} ({len(translations)} 条)")
        else:
            # 兜底模式: 构建资源包结构
            rel_path = f"assets/{modid}/lang/zh_cn.json"
            content = json.dumps(translations, ensure_ascii=False, indent=2)
            output_files[rel_path] = content
            print(f"  [资源包] 加入 {rel_path} ({len(translations)} 条)")

    return output_files


def process_code_entries(entries: list, target: Path):
    """
    处理代码文件条目 (.js, .zs, .snbt)：
    利用 context_hint 对原始文件进行精确字符串替换
    """
    # 按 source_file 分组
    file_entries = defaultdict(list)
    for entry in entries:
        source_file = entry.get("source_file", "")
        translated = entry.get("translated", "")
        status = entry.get("status", "")
        if not translated or status != "done":
            continue
        ext = Path(source_file).suffix.lower()
        if ext in (".js", ".zs", ".snbt"):
            file_entries[source_file].append(entry)

    for source_file, file_entries_list in file_entries.items():
        full_path = target / source_file
        if not full_path.exists():
            print(f"  [跳过] 文件不存在: {source_file}")
            continue

        print(f"  [回写] {source_file}")
        content = full_path.read_text(encoding="utf-8")
        modified = False

        for entry in file_entries_list:
            original = entry.get("original", "")
            translated = entry.get("translated", "")
            context_hint = entry.get("context_hint", "")
            old_content = content
            content = safe_string_replace(content, original, translated, context_hint)
            if content != old_content:
                modified = True
                print(f"    [替换] \"{original[:30]}...\" -> \"{translated[:30]}...\"")

        if modified:
            full_path.write_text(content, encoding="utf-8")
            print(f"    [已保存] {source_file}")


def write_output_files(output_files: dict, target: Path, is_kubejs: bool):
    """将输出文件写入磁盘或打包为 ZIP"""
    if is_kubejs:
        # 直接写入 kubejs/assets/ 目录
        for rel_path, content in output_files.items():
            full_path = target / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            print(f"  [写入] {rel_path}")
    else:
        # 打包为资源包 ZIP
        resourcepacks_dir = target / "resourcepacks"
        resourcepacks_dir.mkdir(exist_ok=True)

        zip_path = resourcepacks_dir / "Auto_Translation.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 写入 pack.mcmeta
            pack_mcmeta = {
                "pack": {
                    "pack_format": 15,
                    "description": "Auto-generated translation resource pack"
                }
            }
            zf.writestr("pack.mcmeta", json.dumps(pack_mcmeta, ensure_ascii=False, indent=2))

            # 写入语言文件
            for rel_path, content in output_files.items():
                zf.writestr(rel_path, content.encode("utf-8"))
                print(f"  [ZIP] 添加 {rel_path}")

        print(f"  [完成] 资源包已生成: {zip_path}")


def main():
    if not TARGET_DIR.is_dir():
        print(f"错误: 目标目录不存在: {TARGET_DIR}")
        sys.exit(1)

    jsonl_path = TARGET_DIR / "translation_tasks.jsonl"
    print(f"[生成] 目标目录: {TARGET_DIR}")
    print(f"[读取] JSONL: {jsonl_path}")

    # 1. 读取 JSONL
    entries = read_jsonl(jsonl_path)
    if not entries:
        print("错误: JSONL 文件为空或不存在")
        sys.exit(1)
    print(f"  -> 共读取 {len(entries)} 条任务")

    # 2. 探测 KubeJS
    is_kubejs = check_kubejs(TARGET_DIR)

    # 3. 处理语言文件条目 -> 生成翻译输出
    print("[语言文件] 处理模组翻译 ...")
    output_files = process_lang_entries(entries, TARGET_DIR, is_kubejs)

    # 4. 写入输出
    if output_files:
        print("[输出] 写入翻译文件 ...")
        write_output_files(output_files, TARGET_DIR, is_kubejs)
    else:
        print("[输出] 没有需要生成的翻译文件（所有模组已有翻译或未提取到条目）")

    # 5. 处理代码文件条目 -> 安全替换
    print("[代码文件] 安全回写 ...")
    process_code_entries(entries, TARGET_DIR)

    print("[完成] 资源生成与回写执行完毕")


if __name__ == "__main__":
    main()
