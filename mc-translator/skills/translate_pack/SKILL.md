---
name: translate-pack
description: 智能提取并翻译 Minecraft 整合包，支持 KubeJS, CraftTweaker, FTBQuests 及各版本模组。
trigger: 当用户要求"翻译整合包"、"汉化"时触发。
---

# Minecraft 整合包智能翻译工作流

你是一个资深的 MC 整合包开发者兼本地化专家。你将通过调用插件自带的 Python 脚本，对用户当前打开的工作区（整合包目录）进行翻译。

## 路径定义

- **SCRIPTS_DIR**: 本插件脚本目录的绝对路径 
- **GLOSSARY_PATH**: 本插件 CSV 术语表的绝对路径 
- **TARGET_DIR**: 用户当前工作区的绝对路径。

## 步骤 1：物理准备与备份

执行以下命令生成 `file_tree.json` 并全量备份：

```powershell
python "{SCRIPTS_DIR}prepare.py" "{TARGET_DIR}"
```

等待脚本执行完成，确认生成了 `file_tree.json`、`file_summary.json`、`_lang_backup/` 目录及其中的 `backup_manifest.json`。

## 步骤 2：文件类型确认（防止遗漏）

**在开始提取之前，必须先读取 `{TARGET_DIR}/file_summary.json`**。该文件按扩展名分组统计了所有待翻译文件。

你将看到类似这样的内容：

```json
{
  ".json": {"count": 320, "samples": ["_temp_extracted/minecraft/lang/en_us.json", ...]},
  ".snbt": {"count": 45, "samples": ["config/ftbquests/quests/chapter1.snbt", ...]},
  ".js":   {"count": 12, "samples": ["kubejs/server_scripts/main.js", ...]},
  ".zs":   {"count": 3,  "samples": [...]},
  ".lang": {"count": 8,  "samples": [...]},
  ".cfg":  {"count": 2,  "samples": [...]},
  ".toml": {"count": 1,  "samples": [...]}
}
```

**逐类型确认规则**：

- `.json` / `.lang`（模组语言文件）→ 必须处理
- `.snbt`（FTB Quests 任务）→ **必须处理**，不可跳过
- `.js`（KubeJS 脚本）→ **必须处理**，不可跳过
- `.zs`（CraftTweaker 脚本）→ **必须处理**，不可跳过
- `.cfg` / `.toml`（配置文件）→ 检查后处理

**如果 file_summary 中某类型 count > 0，则对应的 JSONL 条目也必须 > 0。跳过 JS/SNBT 会导致任务文本、脚本提示、界面文字严重缺失，这是不可接受的。**

## 步骤 3：智能提取 (生成 JSONL)

根据 `file_summary.json` 确认所有文件类型后，逐类型读取文件内容并提取玩家可见文本。

### 代码文件安全说明（重要）

对于 `.js` / `.zs` / `.snbt` 这类代码文件，你可能会担心替换时破坏语法。请放心——整个安全链条有两道保险：

1. **你在提取时填入 `context_hint`**（如 `"line: 42"` 或前后文锚点）
2. **`generate_assets.py` 的 `safe_string_replace` 函数**优先使用行号定位，只替换指定行内的匹配文本；行号失效才回退到全局精确替换，且只替换**第一次出现**

因此，只要你准确填写了 `context_hint`（尤其是行号），回写就非常安全。**不要因为担心破坏代码而跳过 JS/SNBT 文件——这会导致大量玩家可见文本丢失。**

### 文件类型处理策略（下列每个都在 `{TARGET_DIR}` 中检查）

1. **模组语言文件** (路径包含 `assets/*/lang/` 的 `.json` 或 `.lang`)：
   - JSON 格式：提取所有 value
   - LANG 格式：提取 `key=value` 中的 value
   - 记录 `source_file` 为相对路径，`key` 为键名

2. **KubeJS 脚本** (`.js`)：
   - 读取每个 `.js` 文件，逐行检查字符串字面量（单引号或双引号内的文本）
   - 提取原则：**只要是人类能读懂的英文句子/短语，就提取**
   - 排除：纯变量名（如 `"player"`）、事件名（如 `"server.tick"`）、注册 ID（如 `"minecraft:stick"`）、单字符或纯数字字符串
   - `key` 填 `"line:N"`（N 为行号），`context_hint` 填 `"line: N"` 加前后各 10 个字符的原文片段
   - 示例：`Player.tell("Welcome to the server!")` → `original: "Welcome to the server!"`, `context_hint: "line: 42"`

3. **CraftTweaker 脚本** (`.zs`)：
   - 仅提取 `translate("...")` 调用的参数、`<language:...>` 内容
   - 排除 `import`, `val`, `var`, 函数参数名等语法结构

4. **SNBT/配置文件** (`.snbt`, `.toml`, `.cfg`)：
   - 提取 `title`, `description`, `name`, `subtitle`, `text`, `tooltip` 等字段的字符串值
   - **FTB Quests (.snbt)**：必须检查 `config/ftbquests/` 下所有 `.snbt` 文件，提取 `title:"..."` 和 `description:["..."]` 中的文本
   - 使用 `context_hint` 记录行号

5. **其他**：
   - 只提取明显是玩家可见的字符串

### JSONL 输出

在 `{TARGET_DIR}/` 下生成 `translation_tasks.jsonl` 文件。

每行必须是一个严格的 JSON 对象，格式如下，**不要输出多余的逗号或破坏 JSON 结构**：

```jsonl
{"id": 1, "source_file": "相对路径", "key": "键名", "original": "原文", "translated": "", "status": "pending", "context_hint": "上下文提示"}
```

**字段规范**：
- `id`：从 1 开始递增的唯一整数
- `source_file`：相对于整合包根目录的路径，使用正斜杠 `/`
- `key`：语言键名（语言文件中），或代码中该文本的定位标识（如 `"line:42"`）
- `original`：原文内容
- `translated`：初始为空字符串
- `status`：初始为 `"pending"`
- `context_hint`：**极其重要**。对于代码文件（`.js`/`.zs`/`.snbt`），必须记录行号，格式如 `"line: 42"`。对语言文件可为空字符串。

**提取完毕后自检**：逐类型对比 `file_summary.json` 的 count，确认每类文件都有对应条目进入 JSONL。如果某类型遗漏了，必须回溯读取并补充。

## 步骤 4：逐批翻译

每次从 `translation_tasks.jsonl` 读取至少 **200 行**，按以下流程处理：

### 4.1 调用查表脚本

```powershell
python "{SCRIPTS_DIR}glossary_lookup.py" "{TARGET_DIR}/translation_tasks.jsonl" --ids <起始ID>-<结束ID>
```

脚本会返回每条的术语匹配结果（JSON Lines 格式），每条包含一个多义词数组：

```jsonl
{"id": 1, "translations": ["石头", "石"]}
{"id": 2, "translations": []}
```

### 4.2 结合语境翻译

- 对于有术语匹配的条目，根据完整语境选择最合适的释义
- 对于无匹配的条目，根据语境自行翻译
- **严格保留所有占位符和格式化代码**：
  - `%s`, `%1$s`, `%d`, `%f` 等占位符
  - `§a`, `§b`, `§c`, `§l`, `§o` 等颜色/格式代码
  - `&a`, `&b`, `&l` 等 Bukkit/原版格式代码
  - `\n`, `\t` 等转义序列
  - HTML/XML 标签
- 保持原始大小写风格（标题大写、全部小写等）
- 模组物品名、专有名词保持原样或使用社区通用译名

### 4.3 安全更新 JSONL

根据 ID **原地更新** `translation_tasks.jsonl` 中对应行的 `translated` 字段，`status` 改为 `"done"`。

**必须确保每一行都是合法的 JSON**，不能有多余的逗号、换行符破坏结构。

**更新方法**：
- 读取整个 JSONL 文件到列表
- 找到对应 ID 的任务
- 更新 `translated` 和 `status` 字段
- 重新写回整个文件

```python
# 示例：原地更新 JSONL
entries = []
with open(jsonl_path, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            entries.append(json.loads(line))

for entry in entries:
    if entry["id"] == target_id:
        entry["translated"] = translation_text
        entry["status"] = "done"

with open(jsonl_path, "w", encoding="utf-8") as f:
    for entry in entries:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

重复此步骤直到所有条目状态为 `"done"`。

## 步骤 5：安全回写与资源生成

执行回写脚本：

```powershell
python "{SCRIPTS_DIR}generate_assets.py" "{TARGET_DIR}"
```

该脚本会：
1. 读取 `translation_tasks.jsonl`
2. 自动探测 KubeJS 环境
3. 对语言文件：生成 `kubejs/assets/<modid>/lang/zh_cn.json`（KubeJS 模式）或打包为 `resourcepacks/Auto_Translation.zip`（兜底模式）
4. 跳过已有 `zh_cn.json`/`zh_CN.lang` 的模组
5. 对代码文件：利用 `context_hint` 锚点进行精确字符串替换，不破坏代码语法

## 步骤 6：报告与兜底提示

向用户报告完成情况。**报告必须包含以下各项，缺一不可**：

```
翻译完成！

概览：
- 语言文件翻译：X 个模组，Y 条
- 代码文件替换：.js X 个文件，.snbt X 个文件，.zs X 个文件（必须逐类列出）
- 资源输出：KubeJS 模式 / 兜底资源包模式

提示：翻译已应用。如果进游戏发现报错，可随时对我说"执行回滚"，
或手动运行以下命令恢复原状（不推荐）：
python {SCRIPTS_DIR}rollback.py "{TARGET_DIR}"
```

**如果某类代码文件（.js / .snbt / .zs）的替换数为 0，必须说明原因。**
