---
name: screenplay-shot-prose-compiler
description: 将已封存的 SceneDirectionPackageV1 编译为一镜一段的中文导演分镜正文和无表格 DOCX。用于导演决定已经完成、需要把结构化镜头写成连续可拍文本的阶段；不得重新导演、改写剧本、生成视频提示词或处理未封存草案。
metadata:
  tags: [screenplay, shot-prose, storyboard, docx, directing]
  input_types: [scene_direction_package_v1]
  output_types: [shot_prose_record_collection_v1, document]
---

# 分镜正文编译器

把封存导演包翻译成导演、分镜师和现场执行人员可以顺读的“一镜一段”中文正文。它是导演组之后的表达层，不拥有新的导演权力。

## 硬门槛

1. 只接受 `status: sealed` 且规范哈希有效的 `SceneDirectionPackageV1`。
2. 镜号、场景、beat/evidence、对白、人物关系、接触、核心走位、道具状态和镜头结果以导演包为准。发现缺失或冲突时停止，不自行补写。
3. 技术性错字、景别、机位、构图和摄影逻辑应在导演包封存前定稿。正文不得保留“或中景”“也可以平拍”“什么的”等未裁决备选。
4. 本 Skill 不生成提示词、模型参数、负面提示词、图片引用语法、XLSX、分镜图或审计附录。
5. 第一次使用本写法或标准版本变化时，先提交建立镜、长对白镜、复合调度镜各一条校样。用户确认后才能物化全场 DOCX。

## 正文方法

开始编译前读取 [shot-prose-standard.md](references/shot-prose-standard.md)。每个场次只在标题出现一次 `E### S###`，随后用 `C###` 表示普通镜头；同一叙事节拍内的独立机位段落使用 `C###-1`、`C###-2`。

场次开头用一段导演基线说明导演意图、空间与轴线、天气光线、持续环境声和人物起始状态。镜头正文按自然发生顺序整合：

- 景别、角度、拍摄关系和必要运镜。
- 前中后景、人物位置、视线和空间关系。
- 动作、微表情、台词、对手反应与该镜新增或变化的声音。
- 镜头结束时的人物、动作和构图状态。

抽象情绪只有在同时给出可执行的呼吸、目光、面部、手部、姿态、重心或节奏时才可保留。持续环境声只写在场次基线；镜头段落只写变化和单点声音。

## 校验与物化

`schemas/shot-prose-records-v1.schema.json` 是交换契约。脚本还会校验封存哈希、场景顺序、主镜／子镜编号、证据引用、对白一致性、校样门和正文边界。

```bash
python3 scripts/shot_prose_compiler.py validate package.json shot-prose-records.json
python3 scripts/shot_prose_compiler.py materialize package.json shot-prose-records.json --output shots.docx
```

DOCX 只呈现场次标题、导演基线和镜头正文。决定日志、来源哈希、内部 scene/beat/evidence ID 继续留在 JSON，不进入正文。
