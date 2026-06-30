# MC Modpack Translater — Minecraft 整合包智能本地化插件

一款基于 **混合架构**（Python 脚本 + 大语言模型）的 [Codex](https://codex.so) 插件，用于自动化翻译 Minecraft 整合包。脚本负责物理操作，大模型负责语义理解，实现安全、智能、低成本的本地化工作流。

---

## 特性

- **混合架构** — Python 脚本处理解包、备份、术语查表、安全回写；大模型识别代码中的玩家可见文本并翻译
- **格式全支持** — 兼容 `.json`（1.13+）、`.lang`（1.12-）、`.js`（KubeJS）、`.zs`（CraftTweaker）、`.snbt`（FTB Quests）、`.toml` / `.cfg` 等
- **零侵入** — 绝不修改原始 `.jar` 模组文件，所有输出均为外部覆盖
- **动态输出** — 自动检测 KubeJS 环境，生成 `kubejs/assets/` 覆盖文件，或兜底打包为标准资源包 `Auto_Translation.zip`
- **10 万级术语表** — CSV 格式本地索引，零 Token 消耗，一词多义由大模型根据语境选择
- **安全中间体** — 采用 JSONL（JSON Lines）格式承载翻译任务，彻底解决换行符、引号导致的格式炸裂
- **全量备份 & 一键回滚** — 翻译前全量备份目标文件，生成 `backup_manifest.json`，支持一键恢复原状

## 目录结构

```
mc-translator/                  # 插件根目录 (Codex 插件目录)
├── .codex-plugin/
│   └── plugin.json             # 插件入口配置
├── scripts/
│   ├── prepare.py              # 物理准备与备份 (解包 JAR、全量备份)
│   ├── glossary_lookup.py      # 术语查表 (读取 CSV → 多义词 JSON)
│   ├── generate_assets.py      # 资源生成与回写 (读取 JSONL，动态输出)
│   └── rollback.py             # 一键回滚 (还原备份、清理临时文件)
├── skills/
│   └── translate_pack/
│       └── SKILL.md            # Codex 大模型工作流指令
├── glossary.csv                # 术语表 (EN→ZH，CSV 格式，人工可维护)
├── Dict.json / Dict-Mini.json  # 扩展词典 (按需补充)
├── .gitignore
└── README.md
```

## 快速开始

### 前置要求

- [Codex](https://developers.openai.ac.cn/codex) 
- Python 3.10+
- 一个 Minecraft 整合包目录（建议先备份）

### 安装

1. 将 `mc-translator/` 放入 Codex 插件目录：
   - **Codex**: `~/.codx/plugins/`


2. 在 VS Code 中打开目标整合包根目录

3. 唤出 Codex，输入：
   > 帮我翻译这个整合包

### 工作流程

| 步骤 | 执行者 | 说明 |
|------|--------|------|
| 准备与备份 | `prepare.py` | 扫描目录、解包 JAR、生成 `file_tree.json`、全量备份 |
| 智能提取 | 大模型 | 读取文件，识别玩家可见文本，生成 `translation_tasks.jsonl` |
| 术语查询 | `glossary_lookup.py` | 本地查表，返回多义词 JSON，零 Token 消耗 |
| 语境翻译 | 大模型 | 结合术语表与语境逐批翻译，保留占位符和颜色代码 |
| 资源生成 | `generate_assets.py` | 检测 KubeJS 环境，生成翻译文件或兜底资源包 ZIP |
| 回滚 | `rollback.py` | 根据 `backup_manifest.json` 还原备份，清理新生成文件 |

## 脚本说明

| 脚本 | 用途 | 命令示例 |
|------|------|----------|
| `prepare.py` | 扫描目标目录，解包 JAR 中的语言文件，全量备份 | `python prepare.py "D:\Minecraft\MyModpack"` |
| `glossary_lookup.py` | 读取 JSONL 中的原文，在术语表中查询多义词 | `python glossary_lookup.py "path/translation_tasks.jsonl" --ids 1-200` |
| `generate_assets.py` | 读取 JSONL，动态生成 KubeJS 覆盖或标准资源包 | `python generate_assets.py "D:\Minecraft\MyModpack"` |
| `rollback.py` | 一键回滚至翻译前的原始状态 | `python rollback.py "D:\Minecraft\MyModpack"` |

## 兼容性

- **Minecraft 版本**: 1.12 ~ 1.20+（通过 `.lang` / `.json` 自动适配）
- **模组加载器**: Forge、Fabric、NeoForge
- **联动模组**: KubeJS、CraftTweaker、FTB Quests、PneumaticCraft 等

## 开发指引

### 术语表（感谢CFPA - [i18n-dict](https://github.com/CFPATools/i18n-dict)）

`glossary.csv` 为 EN→ZH 映射的 CSV 文件，可用 Excel / WPS / VS Code 直接编辑：

```csv
en,zh
Stone,石头
Iron Ingot,铁锭
Diamond Sword,钻石剑
```

> **注意**: CSV 首行为表头 `en,zh`，后续每行一对映射。脚本首次运行会自动生成 Pickle 缓存加速查询。

### 构建测试沙盒

参见 [`docs/setp.md`](docs/setp.md) 阶段四，了解如何搭建测试用整合包目录及验证各项功能。

## 技术细节

- **JSONL 字段定义**: `{"id": 1, "source_file": "相对路径", "key": "键名", "original": "原文", "translated": "", "status": "pending", "context_hint": "上下文提示"}`
- **编码**: 全部文件使用 UTF-8 读写
- **备份清单**: 目标目录下的 `_lang_backup/backup_manifest.json` 记录了所有备份文件及已存在的 KubeJS 翻译文件清单
- **兜底机制**: 无 KubeJS 环境时自动生成 `resourcepacks/Auto_Translation.zip`，含 `pack.mcmeta`，用户可在游戏中手动加载

## 项目文档

| 文档 | 说明 |
|------|------|
| [`docs/PRD.md`](docs/PRD.md) | 产品需求文档 v2.1 |
| [`docs/setp.md`](docs/setp.md) | 项目实施步骤 v2.0 |
| [`docs/需求.md`](docs/需求.md) | 核心需求要点总结 |

## 许可

本项目基于 [MIT 协议](LICENSE) 开源。

---

*Made with ❤️ for the Minecraft modding community.*
