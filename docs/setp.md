# 文档二：Minecraft 整合包智能本地化插件 - 项目实施步骤 v2.0 (Final)
## 阶段一：插件目录结构搭建
在 Codex 插件目录下创建项目，**注意整合包不要放在这里**。
```text
mc-translator/                  # 插件根目录
├── .codex-plugin/
│   └── plugin.json             # 插件入口配置
├── scripts/
│   ├── prepare.py              # 物理准备与备份
│   ├── glossary_lookup.py      # 术语查表 (读取 CSV)
│   ├── generate_assets.py      # 资源生成与回写 (读取 JSONL)
│   └── rollback.py             # 一键回滚
├── skills/
│   └── translate_pack/
│       └── SKILL.md            # 大模型工作流指令
└── glossary.csv                # 10 万行术语表 (保持 CSV 格式，EN→ZH 映射)
```
## 阶段二：Python 脚本开发要点
1. **路径参数化**：所有脚本第一行必须获取 `target_dir = sys.argv[1]`，后续所有文件操作均基于该路径拼接。所有文件读写统一使用 **UTF-8** 编码。
2. **`prepare.py`**：实现 JAR 只读解压；实现全量备份逻辑，特别是捕获 `kubejs/assets` 下已存在的将被合并的文件，在 `backup_manifest.json` 中单独记录已存在的 KubeJS 翻译文件清单，供回滚时区分新旧文件。
3. **`glossary_lookup.py`**：接收 `translation_tasks.jsonl` 文件路径和 ID 范围（如 `--ids 1-200`），脚本自行读取 JSONL 中对应行的 `original` 字段进行查表。使用 Python 内置 `csv` 模块读取术语表，构建 `defaultdict(list)` 索引并 `pickle` 缓存为 `glossary.csv.pkl` 存放在插件目录，避免每次重复读取。按 ID 逐条返回多义词 JSON 数组。
4. **`generate_assets.py`**：
   - **读取 JSONL**：使用 `for line in open(jsonl_path, encoding='utf-8'): data = json.loads(line)` 解析任务清单，读取 `source_file`、`key`、`translated`、`context_hint` 字段。
   - 实现 `check_kubejs(target_dir)` 探测逻辑：同时检测 `kubejs/` 目录是否存在以及 `mods/` 下是否存在 `kubejs-*.jar`，任一条件满足即为 KubeJS 模式。
   - **跳过已有翻译**：若目标模组已存在 `zh_cn.json` 或 `zh_CN.lang`，跳过该模组不覆盖。
   - 实现标准资源包 ZIP 打包逻辑（注意 `pack.mcmeta` 的 `pack_format` 兼容）。
   - 实现普通文件的精确字符串替换：利用 `context_hint` 中的锚点信息（行号、前后文特征）定位替换位置，避免误改变量名/函数名。
5. **`rollback.py`**：读取 `backup_manifest.json` 还原备份文件。清理新生成文件时，对照清单中记录的已存在 KubeJS 翻译文件列表，仅删除翻译过程中新生成的文件，保留翻译前就存在的文件。同时清理 `Auto_Translation.zip`、`_temp_extracted/` 等临时资源。
## 阶段三：Codex 技能提示词编写 (`SKILL.md`)
这是让模型理解"插件在哪，目标在哪"以及"如何处理 JSONL"的关键。
```markdown
---
name: translate-pack
description: 智能提取并翻译 Minecraft 整合包，支持 KubeJS, CraftTweaker, FTBQuests 及各版本模组。
trigger: 当用户要求"翻译整合包"、"汉化"时触发。
---
# Minecraft 整合包智能翻译工作流
你是一个资深的 MC 整合包开发者兼本地化专家。你将通过调用插件自带的 Python 脚本，对用户当前打开的工作区（整合包目录）进行翻译。
## 路径定义
- **SCRIPTS_DIR**: 本插件脚本目录的绝对路径 (如 ~/.codex/plugins/mc-translator/scripts/)
- **GLOSSARY_PATH**: 本插件 CSV 术语表的绝对路径 (如 ~/.codex/plugins/mc-translator/glossary.csv)
- **TARGET_DIR**: 用户当前工作区的绝对路径。
## 步骤 1：物理准备与备份
执行：`python {SCRIPTS_DIR}/prepare.py "{TARGET_DIR}"`
生成 `file_tree.json` 并全量备份文件至 `_lang_backup/`。
## 步骤 2：智能提取 (生成 JSONL)
读取 `{TARGET_DIR}/file_tree.json`。按类型读取内容提取玩家可见文本。
**极其重要**：在 `{TARGET_DIR}/` 下生成 `translation_tasks.jsonl` 文件。
每行必须是一个严格的 JSON 对象，格式如下，不要输出多余的逗号或破坏 JSON 结构：
`{"id": 1, "source_file": "相对路径", "key": "键名", "original": "原文", "translated": "", "status": "pending", "context_hint": "上下文提示"}`
其中 `context_hint` 用于代码文件（.js/.zs/.snbt）记录行号或前后文锚点，帮助回写脚本精准定位，避免误改变量名/函数名。
## 步骤 3：逐批翻译
每次从 `translation_tasks.jsonl` 读取至少 200 行（后期稳定后可全量处理）：
1. 调用查表脚本获取 CSV 术语表中的匹配项：
   `python {SCRIPTS_DIR}/glossary_lookup.py "{TARGET_DIR}/translation_tasks.jsonl" --ids <起始ID>-<结束ID>`
2. 根据返回的术语（含一词多义列表），结合语境翻译，保留 %s, §a 等代码。
3. **安全更新**：根据 ID 原地更新 `translation_tasks.jsonl` 中对应行的 `translated` 字段，`status` 改为 `done`。确保每一行都是合法的 JSON。
## 步骤 4：安全回写与资源生成
执行：`python {SCRIPTS_DIR}/generate_assets.py "{TARGET_DIR}"`
脚本会读取 JSONL 文件，利用 `context_hint` 安全替换代码文件，自动探测 KubeJS 生成覆盖文件（跳过已有 zh_cn.json 的模组），或生成兜底资源包 ZIP。
## 步骤 5：报告与兜底提示
向用户报告完成。并提示：
"翻译已应用。如果进游戏发现报错，可随时对我说'执行回滚'，或手动运行 `python {SCRIPTS_DIR}/rollback.py "{TARGET_DIR}"` 恢复原状。"
```
## 阶段四：沙盒测试与调优
1. **构建测试沙盒**：在非插件目录处创建测试整合包（含 `mods/` 放空 JAR 和 `kubejs-1.0.jar`、`kubejs/server_scripts/test.js`、已有 `zh_cn.json` 的模组目录、`config/ftbquests/main.snbt`）。
2. **验证提取与备份**：运行流程，检查是否正确生成了 JSONL（含 `source_file`、`key`、`context_hint` 字段），且 `_lang_backup` 中是否完整备份了原文件，`backup_manifest.json` 是否正确记录了已存在的 KubeJS 翻译文件。
3. **JSONL 鲁棒性测试**：故意在测试包的 SNBT 或 JS 中放入带双引号、换行符的复杂文本（如 `desc: "Line1\nLine2, with comma."`），检查 JSONL 是否结构完好。
4. **验证回写逻辑**：
   - *场景 A*：在 `mods` 放入 `kubejs-1.0.jar` 且存在 `kubejs/` 目录，检查是否生成了 `kubejs/assets/` 下的翻译文件，且已有 `zh_cn.json` 的模组被跳过。
   - *场景 B*：移除 `kubejs.jar` 和 `kubejs/` 目录，检查是否生成了 `resourcepacks/Auto_Translation.zip`。
   - *代码安全验证*：检查 `test.js` 中利用 `context_hint` 锚点替换后，英文字符串被准确替换，但代码括号语法和变量名完好。
5. **验证回滚机制**：执行 `rollback.py`，检查测试包是否完全恢复原貌（包括已有的 KubeJS 翻译文件未被误删），生成的 ZIP 和临时文件被清理。
## 阶段五：生产环境部署
1. 将 `mc-translator` 文件夹放入 Codex 插件目录。
2. 用 VS Code 打开真实的 Minecraft 整合包根目录，唤出 Codex。
3. 输入："帮我翻译这个整合包"。
4. 观察模型调度脚本执行，事后启动游戏校验模组物品、任务文本汉化情况及脚本是否报错。
