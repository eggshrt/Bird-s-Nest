# 技术来源与本Skill的转译范围

本Skill借鉴NVIDIA对DLSS 5的公开说明：以游戏引擎已有渲染帧为基础，使用帧颜色和运动向量，定向增强光照与材质并保留身份、场景/光照语义和摄影构图。开发者控制包括Structure Intensity、Tone Intensity、语义及引擎层蒙版。更丰富的输入光照信息会影响增强结果。

官方依据（2026-11-11查阅）：
- [NVIDIA DLSS 5：3D-Guided Neural Rendering](https://www.nvidia.com/en-us/geforce/news/dlss-5-3d-guided-neural-rendering/)
- [NVIDIA开发者说明：控制与集成](https://developer.nvidia.com/blog/whats-new-for-game-developers-dlss-5-with-3d-guided-neural-rendering-nvidia-ace-updates-and-new-rtx-kit-capabilities/)

本Skill实际能做的是解释既有设计、组织增强范围、提出光源/材质/介质/动态关系，并编译成提示词。它不包含NVIDIA SDK、模型权重、GPU调用、像素级蒙版推理、真实帧重建、超分或补帧；也不从一句提示词就取得运动向量。不能把方法借鉴称为已经启用DLSS 5渲染，不能承诺实时性、确定性或画质效果。

项目用法参考用户指定聊天“优化飞船宇宙光影提示词”：把PBR与光源试值转为能看见的材料差异、局部回光与真实运动反馈。聊天中的色温、粗糙度、光源角尺寸、转速、玻璃内景和运镜变化均属该项目当时的设计选择，不是技术事实或本Skill默认。未把该聊天全文、用户参考图或私有剧本随包复制。

当前0.8.1为本地试用更新。按用户要求没有执行样例、模型调用、图像/视频生成或效果测试；安装文件与版本核对不证明能力或审美验收通过。
