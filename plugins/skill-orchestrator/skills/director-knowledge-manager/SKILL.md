---
name: director-knowledge-manager
description: 显式管理导演知识的索引、HTML/Markdown 转换、职责映射、用户审定和版本发布。用于维护用户指定工作目录中的导演资料及可追踪岗位知识包；不参与普通导演决策，不自动发布未经用户审定的资料。
metadata:
  tags: [knowledge-management, director, provenance, review]
  input_types: [html, markdown]
  output_types: [director_knowledge_catalog_v1, director_role_catalog_v1]
---

# 导演知识管理

只在用户显式调用时运行。中央源库保存转换后的纯文本 Markdown、原文件与转换哈希、职责候选、审定记录；岗位 Skill 只加载已发布的精炼规则和来源 ID。公开包中的 catalog 是空模板，`knowledge/published` 只包含通用方法规则，不代表已为当前用户审定外部资料。原始资料、转换结果与用户审定记录保存在仓库外的项目工作目录。

## 生命周期

`indexed → converted → review_pending → published/rejected`。

- 转换保留标题、正文层级、段落、列表、表格文本和来源信息；剔除图片、视频、脚本、样式、导航、表单和交互控件。
- 原目录仅作来源分类；专业职责映射独立记录，可跨岗位。
- 发布必须带用户审定记录。新增资料和已发布来源的新哈希都先进入 `review_pending`。
- 已发布来源变化时，岗位继续使用旧封存版本；新版不能影响结果。
- “提示词导演”资料必须保持 `isolated: true`，不得进入任何导演岗位包。只有用户审定记录同时声明 `isolated_prompt_only` 和明确的提示词编译器目标时，才能发布给该隔离编译器。
- 不复制许可不清的外部代码或长篇正文。

```bash
python3 scripts/knowledge_manager.py ingest /path/to/project-work/inbox /path/to/project-work/director-knowledge-catalog.json /path/to/project-work/converted
python3 scripts/knowledge_manager.py publish /path/to/project-work/director-knowledge-catalog.json /path/to/project-work/director-role-catalog.json --review /path/to/project-work/review.json
```

Schema 见 `references/schemas/`。发布前把待审定清单展示给用户，未经明确确认不得构造 review 文件或代替用户批准。
