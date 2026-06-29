#!/usr/bin/env python3
"""
rollback.py - 灾备回滚模块
读取 backup_manifest.json，还原所有备份文件，清理翻译过程中生成的新文件。
"""

import sys
import os
import json
import shutil
from pathlib import Path

TARGET_DIR = Path(sys.argv[1]).resolve()
LANG_BACKUP = TARGET_DIR / "_lang_backup"
BACKUP_MANIFEST = LANG_BACKUP / "backup_manifest.json"


def load_manifest(manifest_path: Path) -> dict:
    """加载备份清单"""
    if not manifest_path.exists():
        print(f"错误: 备份清单不存在: {manifest_path}")
        print("提示: 请确保已在目标目录执行过翻译流程")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def restore_backups(manifest: dict):
    """还原备份文件到原始路径"""
    restored_count = 0
    for file_entry in manifest.get("files", []):
        original_path = TARGET_DIR / file_entry["original_path"]
        backup_path = LANG_BACKUP / file_entry["backup_path"]

        if not backup_path.exists():
            print(f"  [跳过] 备份文件缺失: {file_entry['backup_path']}")
            continue

        # 确保目标目录存在
        original_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, original_path)
        restored_count += 1
        print(f"  [还原] {file_entry['original_path']}")

    return restored_count


def clean_generated_files(manifest: dict):
    """清理翻译过程中新生成的文件"""
    kubejs_existing = set(manifest.get("kubejs_existing", []))
    cleaned_count = 0

    # 1. 清理不在备份清单中的 KubeJS 翻译文件
    kubejs_assets_dir = TARGET_DIR / "kubejs" / "assets"
    if kubejs_assets_dir.is_dir():
        for lang_file in kubejs_assets_dir.rglob("*"):
            if lang_file.is_file():
                rel = str(lang_file.relative_to(TARGET_DIR)).replace("\\", "/")
                # 只处理 zh_cn 文件
                if not (rel.endswith("zh_cn.json") or rel.endswith("zh_CN.lang")):
                    continue
                # 如果不是备份前就存在的，删除
                if rel not in kubejs_existing:
                    lang_file.unlink()
                    cleaned_count += 1
                    print(f"  [清理] 新生成文件: {rel}")

        # 清理空目录
        for dirpath, dirnames, filenames in os.walk(kubejs_assets_dir, topdown=False):
            if not dirnames and not filenames and dirpath != str(kubejs_assets_dir):
                os.rmdir(dirpath)
                print(f"  [清理] 空目录: {Path(dirpath).relative_to(TARGET_DIR)}")

    # 2. 清理 Auto_Translation.zip
    zip_path = TARGET_DIR / "resourcepacks" / "Auto_Translation.zip"
    if zip_path.exists():
        zip_path.unlink()
        cleaned_count += 1
        print(f"  [清理] {zip_path.relative_to(TARGET_DIR)}")

        # 清理 resourcepacks 空目录
        rp_dir = TARGET_DIR / "resourcepacks"
        if rp_dir.exists() and not list(rp_dir.iterdir()):
            rp_dir.rmdir()
            print(f"  [清理] 空目录: resourcepacks/")

    # 3. 清理 _temp_extracted/
    temp_dir = TARGET_DIR / "_temp_extracted"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        print(f"  [清理] _temp_extracted/")

    # 4. 清理 translation_tasks.jsonl
    jsonl_path = TARGET_DIR / "translation_tasks.jsonl"
    if jsonl_path.exists():
        jsonl_path.unlink()
        cleaned_count += 1
        print(f"  [清理] translation_tasks.jsonl")

    # 5. 清理 file_tree.json
    file_tree_path = TARGET_DIR / "file_tree.json"
    if file_tree_path.exists():
        file_tree_path.unlink()
        cleaned_count += 1
        print(f"  [清理] file_tree.json")

    return cleaned_count


def main():
    if not TARGET_DIR.is_dir():
        print(f"错误: 目标目录不存在: {TARGET_DIR}")
        sys.exit(1)

    print(f"[回滚] 目标目录: {TARGET_DIR}")

    # 1. 加载备份清单
    print("[加载] 读取备份清单 ...")
    manifest = load_manifest(BACKUP_MANIFEST)
    print(f"  -> 备份清单中共 {len(manifest.get('files', []))} 个文件")

    # 2. 还原备份文件
    print("[还原] 还原备份文件 ...")
    restored = restore_backups(manifest)
    print(f"  -> 已还原 {restored} 个文件")

    # 3. 清理新生成的文件
    print("[清理] 清理翻译过程中生成的文件 ...")
    cleaned = clean_generated_files(manifest)
    print(f"  -> 已清理 {cleaned} 个文件/目录")

    # 4. 清理备份目录自身
    if LANG_BACKUP.exists():
        shutil.rmtree(LANG_BACKUP)
        print(f"  [清理] _lang_backup/")

    print("[完成] 回滚执行完毕，目标目录已恢复至翻译前状态")


if __name__ == "__main__":
    main()
