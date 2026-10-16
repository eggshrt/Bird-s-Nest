---
name: seedance-shot-prompt-compiler
description: 将已封存的 SceneDirectionPackageV1 镜头编译为中文 Seedance 2.0 文生视频提示词，并按用户提供的中文镜头表模板生成校样或完整 XLSX。仅在用户明确要求 Seedance 视频提示词或镜头表提示词列时使用；不得用于重新导演、剧本改写、图生视频或未封存草案。
metadata:
  tags: [seedance, video-prompt, shot-list, t2v, spreadsheet]
  input_types: [scene_direction_package_v1, spreadsheet]
  output_types: [seedance_shot_prompt_record_v1, spreadsheet]
---

# Seedance 镜头提示词编译器

把封存导演包翻译成逐镜、可独立使用的中文 Seedance 2.0 文生视频提示词。它是执行层，不是新的导演岗位。

## 硬门槛

1. 只接受 `status: sealed` 且规范哈希有效的 `SceneDirectionPackageV1`；一次仍限同一剧本的 1–2 场。
2. 以镜号、剧本证据、用户决定和导演包为事实边界。不得新增剧情、对白、触碰、人物关系、走位、道具状态或镜头事件。
3. 固定输出中文 Seedance 2.0 T2V。除非用户另行重开需求，不得生成 I2V/R2V、图片提示词、参考图语法或模型调用参数。
4. 默认先做代表镜头校样。校样未确认时，未选镜头的提示词格必须保持空白，不得假称完成全量编译。
5. 角色姓名可以作为唯一身份标签，但必须记录无外貌锚点导致的跨镜漂移风险。
6. 可依据已发布的表演与动作知识补充非剧情性的微表情、呼吸、手部小动作、衣料反应和拟音；不得借此改变接触、核心走位、道具、人物关系、剧情事实或镜头结果。

## 编译方法

开始写提示词前读取 [prompt-rules.md](references/prompt-rules.md)；需要补充表演节拍或动作链时再读取 [performance-action-rules.md](references/performance-action-rules.md)。每镜从导演包投影：

- 表演调度：动作力度、姿态、停顿、呼吸、目光与可见微表情。
- 摄影分镜：景别、角度、机位、焦段、一个主要运镜及结束构图。
- 连续性：轴线、视线、首尾状态、人物区域、手部和道具状态。
- 条件部门：只加入当前镜头需要的动作、光色、声音或特效信息。

`画面演绎` 只陈述客观可见的构图、人物位置、动作过程与结束画面。台词和声音分别保留在独立列作为结构化事实源，同时在视频提示词的实际发生位置完整嵌入。提示词不得带通用画质前缀、审计式尾注或尚未绑定素材的图片引用语法。

V2 记录把表演节拍、三层声音和机位段落分开保存。`schemas/shot-prompt-records-v2.schema.json` 是可移植交换契约，运行时还会校验封存导演包与提示词内容。长对白可在同一主镜号内按真实节拍多次切换机位；每次切换都必须有新的信息、表演或反应，并保持既定轴线和人物位置。不得为装饰性变化增加切镜。

## 确定性校验与渲染

```bash
python3 scripts/seedance_shot_prompt_compiler.py validate package.json prompt-records.json
python3 scripts/seedance_shot_prompt_compiler.py materialize package.json prompt-records.json \
  --reference reference.xlsx --output review.xlsx
```

渲染需要工作区提供的 `openpyxl`。输出只派生 XLSX，不改写或重封导演包。
