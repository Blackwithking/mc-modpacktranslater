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

提取分两步：**先跑脚本粗提取**（正则/结构化，宁可多提不漏），**再人工精筛**（删除误提取、补充遗漏）。

### 3.1 脚本粗提取

```powershell
python "{SCRIPTS_DIR}extract_texts.py" "{TARGET_DIR}"
```

该脚本自动提取以下内容，写入 `translation_tasks.jsonl`：

| 类型 | 提取方式 | 可靠性 |
|---|---|---|
| 模组语言文件 `.json` | 全量 value，与已有 `zh_cn.json` 比 key，只提缺失 | ✅ 高 |
| 模组语言文件 `.lang` | `key=value` 解析 | ✅ 高 |
| FTB Quests `.snbt` | `title/subtitle/description/text` 正则，含多行数组 | ✅ 高 |
| CraftTweaker `.zs` | `translate()/setName()/addTooltip()` 正则 | ✅ 高 |
| KubeJS `.js` | **所有**字符串字面量（双引号/单引号/模板） | ⚠️ 粗提含大量误提取 |
| 配置文件 `.toml/.cfg` | `key="value"` 和注释行 | ⚠️ 需筛 |

等待脚本完成，确认生成了 `translation_tasks.jsonl`。

### 3.2 模型精筛与补充

脚本跑完后，你需要对 JSONL 进行审查：

**删除误提取**（主要来自 JS 的粗提取）：
- 纯变量名（`"player"`, `"stick"`）
- 事件名（`"server.tick"`）
- 注册 ID（`"minecraft:diamond"`）
- 路径字符串（`"kubejs/assets/..."`）
- 纯数字/纯符号字符串
- 单字符字符串

**检查遗漏**（对照 `file_summary.json`）：
- `.snbt` 数量是否匹配
- `.zs` 数量是否匹配
- JS 文件中是否有脚本没提取到的玩家可见文本（如拼接字符串、动态生成的消息）
- 补充遗漏的条目到 JSONL

### 代码文件安全说明（重要）

对于 `.js` / `.zs` / `.snbt` 这类代码文件，你可能会担心替换时破坏语法。请放心——整个安全链条有两道保险：

1. **你在提取时填入 `context_hint`**（如 `"line: 42"` 或前后文锚点）
2. **`generate_assets.py` 的 `safe_string_replace` 函数**优先使用行号定位，只替换指定行内的匹配文本；行号失效才回退到全局精确替换，且只替换**第一次出现**

因此，只要你准确填写了 `context_hint`（尤其是行号），回写就非常安全。**不要因为担心破坏代码而跳过 JS/SNBT 文件——这会导致大量玩家可见文本丢失。**

### JSONL 字段规范

脚本已生成的条目格式：

```jsonl
{"id": 1, "source_file": "相对路径", "key": "键名", "original": "原文", "translated": "", "status": "pending", "context_hint": ""}
```

**字段规范**：
- `id`：从 1 开始递增的唯一整数（脚本已分配好）
- `source_file`：相对于整合包根目录的路径，使用正斜杠 `/`
- `key`：语言键名（语言文件中），或代码中该文本的定位标识（如 `"line:42"` 或 `"desc[0]:L15"`）
- `original`：原文内容
- `translated`：初始为空字符串
- `status`：初始为 `"pending"`
- `context_hint`：脚本已预填行号（如 `"line: 42"`），精筛时如需补充或修正可以直接修改

**精筛完毕后自检**：逐类型对比 `file_summary.json` 的 count，确认每类文件都有对应条目进入 JSONL。如果某类型遗漏了，必须回溯读取并补充。

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

#### 生造词与罕见词处理（存疑不翻）

MC 模组中大量存在作者生造的词语。遇到无法确定含义的原文，按以下策略处理，**宁可保留原文也不要瞎编**：

**1. 模组专有名词 / 社区已有共识译名**
- 如：`Zoglin`, `Ars Nouveau`, `Thaumcraft`, `Create`, `Mekanism`
- 策略：**保留原文**。这些是玩家社区的通用称呼，翻译反而造成混淆。

**2. 可拆解的生造合成词**
- 如：`Voidmetal` → `"虚空金属"`, `Thaumonomicon` → `"魔导手册"`, `Stormcrystal` → `"风暴水晶"`
- 策略：尝试拆解词根后意译。如果不确定拆解是否正确 → **保留原文**。

**3. 完全无法识别的罕见词 / 生造词**
- 如：某个自创法术名 `Euphonium`（可能是乐器名，也可能是编的）、无法判断来源的专有名词
- 策略：**保留原文**。此时 `translated` 填入与 `original` 完全相同的英文原文，`status` 仍然改为 `done`（表示已审视但决定不翻，和未处理的 `pending` 区分开）。

**核心原则：存疑不翻。玩家能认出英文原文，但认不出错误的翻译。**

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

## 步骤 5：翻译质量自检（信达雅）

所有条目翻译完成后、回写之前，对译文进行最终质量审查。

### 审查方法

1. **抽样检查**：从 `translation_tasks.jsonl` 中随机抽取 30-50 条已完成条目，逐条对照原文审查译文
2. **重点覆盖**：优先抽查代码文件（.js/.zs/.snbt）条目和术语表未匹配的条目，这两类最易出问题
3. **扫读 JSONL**：快速扫读全部已完成条目，发现明显异常的译文（如未替换的原文、乱码、格式符丢失）

### 审查标准（信达雅）

- **信（准确性）**：译文是否准确传达了原文含义？有无错译、漏译、过度发挥？
- **达（流畅性）**：中文是否通顺自然？有无翻译腔、语序倒错、生硬直译？
- **雅（游戏语境适配）**：
  - 物品名/技能名：简洁有力，符合中国玩家习惯（如 `"Iron Sword"` → `"铁剑"` 而非 `"铁制长剑"`）
  - 任务描述：口语化、有代入感（如 `"Craft a wooden pickaxe to get started"` → `"先做一把木镐吧"` 而非 `"制作一把木镐以开始"`）
  - UI 按钮/提示：短小精悍，不宜过长
  - 保留原文的条目（生造词/专有名词）：确认决策正确，不应翻的没被硬翻

### 修复

发现质量问题后，按步骤 4.3 的方法原地更新对应条目的 `translated` 字段。

确认质量满意后，继续执行步骤 6 回写。

## 步骤 6：安全回写与资源生成

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

## 步骤 7：报告与兜底提示

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
