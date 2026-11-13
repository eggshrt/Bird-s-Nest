# 输出契约

权威源是封存的 `scene-direction-package.json`。默认可见交付由 `$screenplay-shot-prose-compiler` 从同一封存包生成。

默认 DOCX：每场只出现一次 `E### S### 场名` 标题；随后是一段导演基线和逐镜正文。每镜一个自然段，镜号与正文同行；主镜显示 `C###`，子镜显示 `C###-#`。正文不包含表格、提示词、模型参数、决定日志、来源字段或内部 evidence ID。

内部 JSON：保留完整决定日志、scene/beat/evidence、来源哈希、连续性与执行风险。它是审计与后续派生的唯一权威源。

显式兼容 XLSX：仅在旧调用明确要求时生成每场镜头表、决定日志和来源追踪工作表；不再是默认交付。

DOCX/XLSX 由 Python 标准库 OOXML/ZIP 生成；可选用 `python-docx`、`openpyxl` 做附加打开验证，但不得成为跨电脑运行依赖。
