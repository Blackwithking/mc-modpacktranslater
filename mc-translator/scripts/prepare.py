#!/usr/bin/env python3
"""
prepare.py - 物理准备与备份模块 (Phase 1)
接收目标整合包路径作为参数，执行：
1. 目录扫描，生成 file_tree.json
2. JAR 只读解包，提取 en_us.json / en_US.lang
3. 全量安全备份至 _lang_backup/
"""

import sys
import os
import json
import zipfile
import shutil
import hashlib
from pathlib import Path

TARGET_DIR = Path(sys.argv[1]).resolve()
TEMP_EXTRACTED = TARGET_DIR / "_temp_extracted"
LANG_BACKUP = TARGET_DIR / "_lang_backup"

# 需要备份的文件扩展名
BACKUP_EXTENSIONS = {".json", ".lang", ".snbt", ".zs", ".js", ".cfg", ".toml"}

# JAR 中需要提取的语言文件
LANG_FILES_IN_JAR = {"en_us.json", "en_US.lang", "en_us.lang"}


def scan_directory(target: Path) -> list:
    """遍历目标目录，生成文件树清单"""
    file_tree = []
    for root, dirs, files in os.walk(target):
        # 跳过临时目录和备份目录
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in files:
            full_path = Path(root) / f
            rel_path = full_path.relative_to(target)
            file_tree.append({
                "path": str(rel_path).replace("\\", "/"),
                "size": full_path.stat().st_size,
                "ext": full_path.suffix.lower(),
            })
    return file_tree


def extract_jar_lang_files(jar_path: Path):
    """从 JAR 包中只读提取语言文件到 _temp_extracted/"""
    output_dir = TEMP_EXTRACTED / modid / "lang"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            for name in zf.namelist():
                # 匹配 assets/<modid>/lang/en_us.json 或 en_US.lang
                parts = Path(name).parts
                if len(parts) >= 4 and parts[0] == "assets" and parts[2] == "lang":
                    if Path(name).name in LANG_FILES_IN_JAR:
                        lang_data = zf.read(name).decode("utf-8", errors="replace")
                        out_file = output_dir / Path(name).name
                        out_file.write_text(lang_data, encoding="utf-8")
                        print(f"  [提取] {name} -> {out_file}")
    except Exception as e:
        print(f"  [警告] 读取 {jar_path.name} 时出错: {e}")


def find_and_extract_jars(target: Path):
    """查找并提取所有 .jar 模组的语言文件"""
    mods_dir = target / "mods"
    if not mods_dir.is_dir():
        print("  [跳过] 未找到 mods/ 目录")
        return

    for jar_file in mods_dir.glob("*.jar"):
        print(f"  [解包] {jar_file.name}")
        # 尝试从文件名或 JAR 内获取 modid
        modid = jar_file.stem.split("-")[0].split("_")[0].lower()
        extract_jar_lang_files(jar_file, modid)


def backup_files(target: Path) -> dict:
    """全量安全备份将要修改的文件"""
    backup_manifest = {
        "target_dir": str(target),
        "backup_dir": str(LANG_BACKUP),
        "files": [],          # 所有备份的文件
        "kubejs_existing": [],  # 已存在的 KubeJS 翻译文件
        "created_at": None,
    }

    if LANG_BACKUP.exists():
        shutil.rmtree(LANG_BACKUP)
    LANG_BACKUP.mkdir(parents=True, exist_ok=True)

    for root, dirs, files in os.walk(target):
        # 跳过临时/备份目录
        dirs[:] = [d for d in dirs if not d.startswith("_") and d != "_lang_backup"]
        for f in files:
            full_path = Path(root) / f
            ext = full_path.suffix.lower()
            if ext not in BACKUP_EXTENSIONS:
                continue

            rel_path = full_path.relative_to(target)
            backup_path = LANG_BACKUP / rel_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(full_path, backup_path)

            entry = {
                "original_path": str(rel_path).replace("\\", "/"),
                "backup_path": str(backup_path.relative_to(LANG_BACKUP)).replace("\\", "/"),
            }
            backup_manifest["files"].append(entry)

            # 记录已存在的 KubeJS 翻译文件
            rel_str = str(rel_path).replace("\\", "/")
            if rel_str.startswith("kubejs/assets/") and (
                rel_str.endswith("/lang/zh_cn.json") or rel_str.endswith("/lang/zh_CN.lang")
            ):
                backup_manifest["kubejs_existing"].append(rel_str)
                print(f"  [KubeJS已有] {rel_str}")

            print(f"  [备份] {rel_str}")

    return backup_manifest


def main():
    if not TARGET_DIR.is_dir():
        print(f"错误: 目标目录不存在: {TARGET_DIR}")
        sys.exit(1)

    print(f"[准备] 目标目录: {TARGET_DIR}")

    # 1. 目录扫描
    print("[扫描] 生成 file_tree.json ...")
    file_tree = scan_directory(TARGET_DIR)
    file_tree_path = TARGET_DIR / "file_tree.json"
    with open(file_tree_path, "w", encoding="utf-8") as f:
        json.dump(file_tree, f, ensure_ascii=False, indent=2)
    print(f"  -> 共扫描 {len(file_tree)} 个文件, 已保存至 {file_tree_path}")

    # 2. JAR 只读解包
    print("[解包] 提取 JAR 中的语言文件 ...")
    if TEMP_EXTRACTED.exists():
        shutil.rmtree(TEMP_EXTRACTED)
    TEMP_EXTRACTED.mkdir(parents=True, exist_ok=True)
    find_and_extract_jars(TARGET_DIR)

    # 3. 全量备份
    print("[备份] 全量安全备份 ...")
    backup_manifest = backup_files(TARGET_DIR)
    backup_manifest["created_at"] = str(Path())

    manifest_path = LANG_BACKUP / "backup_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(backup_manifest, f, ensure_ascii=False, indent=2)
    print(f"  -> 备份清单已保存至 {manifest_path}")
    print(f"  -> 共备份 {len(backup_manifest['files'])} 个文件")
    print(f"  -> 已存在的 KubeJS 翻译: {len(backup_manifest['kubejs_existing'])} 个")

    print("[完成] 准备阶段执行完毕")


if __name__ == "__main__":
    main()
