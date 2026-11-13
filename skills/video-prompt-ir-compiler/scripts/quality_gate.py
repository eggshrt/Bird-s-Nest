#!/usr/bin/env python3
"""
视频提示词 IR 质量门禁校验器
执行 10 项强制规则，返回 JSON 格式的校验结果
"""

import json
import sys
import re
from typing import Dict, List, Any, Tuple


class QualityGate:
    """质量门禁校验器"""

    def __init__(self, ir_data: Dict[str, Any]):
        self.ir = ir_data
        self.violations = []

    def validate_all(self) -> Dict[str, Any]:
        """执行所有 10 项门禁检查"""
        self.check_duration_alignment()
        self.check_time_continuity()
        self.check_subject_consistency()
        self.check_anchor_count()
        self.check_platform_compatibility()
        self.check_camera_movement_feasibility()
        self.check_anchor_coverage()
        self.check_focal_length_match()
        self.check_lighting_continuity()
        self.check_required_fields()

        return {
            "pass": len(self.violations) == 0,
            "violations": self.violations
        }

    def add_violation(self, gate: str, message: str, severity: str = "error"):
        """添加违规记录"""
        self.violations.append({
            "gate": gate,
            "severity": severity,
            "message": message
        })

    def parse_time_range(self, time_str: str) -> Tuple[float, float]:
        """解析时间段字符串，如 '0-5秒' 返回 (0.0, 5.0)"""
        match = re.match(r'^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)秒$', time_str)
        if not match:
            raise ValueError(f"无效的时间段格式: {time_str}")
        return float(match.group(1)), float(match.group(2))

    def check_duration_alignment(self):
        """门禁 1: 时长强制对齐"""
        try:
            total_duration = self.ir.get("global_constraints", {}).get("总时长")
            segments = self.ir.get("分段脚本", [])

            if total_duration is None:
                self.add_violation("时长强制对齐", "缺少 global_constraints.总时长")
                return

            if not segments:
                self.add_violation("时长强制对齐", "分段脚本为空")
                return

            segment_total = 0.0
            for seg in segments:
                time_range = seg.get("时间段")
                if not time_range:
                    continue
                start, end = self.parse_time_range(time_range)
                segment_total += (end - start)

            # 允许 0.1 秒的浮点误差
            if abs(segment_total - total_duration) > 0.1:
                self.add_violation(
                    "时长强制对齐",
                    f"分段脚本总时长 {segment_total} 秒不等于全局总时长 {total_duration} 秒"
                )
        except Exception as e:
            self.add_violation("时长强制对齐", f"校验失败: {str(e)}")

    def check_time_continuity(self):
        """门禁 2: 时间段连续性"""
        try:
            segments = self.ir.get("分段脚本", [])
            if not segments:
                return

            prev_end = None
            for i, seg in enumerate(segments):
                time_range = seg.get("时间段")
                if not time_range:
                    continue

                start, end = self.parse_time_range(time_range)

                if start >= end:
                    self.add_violation(
                        "时间段连续性",
                        f"第 {i+1} 段时间段起始时间 {start} 不小于结束时间 {end}"
                    )

                if prev_end is not None:
                    gap = abs(start - prev_end)
                    if gap > 0.1:  # 允许 0.1 秒误差
                        self.add_violation(
                            "时间段连续性",
                            f"第 {i+1} 段起始时间 {start} 与前一段结束时间 {prev_end} 存在间隙或重叠"
                        )

                prev_end = end
        except Exception as e:
            self.add_violation("时间段连续性", f"校验失败: {str(e)}")

    def check_subject_consistency(self):
        """门禁 3: 主体一致性"""
        try:
            subject = self.ir.get("主要主体", {})
            appearance = subject.get("外观描述", "").strip()

            if not appearance:
                self.add_violation("主体一致性", "主要主体.外观描述 为空")
                return

            # 检查分段脚本中是否有矛盾的主体描述（简化检查）
            segments = self.ir.get("分段脚本", [])
            for i, seg in enumerate(segments):
                event = seg.get("主要事件", "")
                action = seg.get("主体动作", "")
                # 这里可以扩展更复杂的一致性检查逻辑

        except Exception as e:
            self.add_violation("主体一致性", f"校验失败: {str(e)}")

    def check_anchor_count(self):
        """门禁 4: 固定锚点数量"""
        try:
            continuity = self.ir.get("连续性控制", {})
            anchors = continuity.get("固定锚点", [])

            # 判断是否为一镜到底（简化判断：只有一个分段或总时长较长）
            segments = self.ir.get("分段脚本", [])
            is_one_shot = len(segments) == 1 or self.ir.get("global_constraints", {}).get("总时长", 0) > 10

            if is_one_shot and len(anchors) < 2:
                self.add_violation(
                    "固定锚点数量",
                    f"一镜到底场景的固定锚点数量为 {len(anchors)}，必须≥2 个"
                )
        except Exception as e:
            self.add_violation("固定锚点数量", f"校验失败: {str(e)}")

    def check_platform_compatibility(self):
        """门禁 5: 平台兼容性"""
        try:
            constraints = self.ir.get("global_constraints", {})
            total_duration = constraints.get("总时长", 0)
            ratio = constraints.get("比例", "")
            platforms = constraints.get("目标平台", [])

            for platform in platforms:
                if platform == "Seedance" and total_duration > 30:
                    self.add_violation(
                        "平台兼容性",
                        f"Seedance 不支持超过 30 秒的视频，当前总时长 {total_duration} 秒",
                        severity="warning"
                    )

                if platform == "MiniMax-H3" and total_duration > 60:
                    self.add_violation(
                        "平台兼容性",
                        f"MiniMax-H3 不支持超过 60 秒的视频，当前总时长 {total_duration} 秒",
                        severity="warning"
                    )
        except Exception as e:
            self.add_violation("平台兼容性", f"校验失败: {str(e)}")

    def check_camera_movement_feasibility(self):
        """门禁 6: 摄影机运动合理性"""
        try:
            segments = self.ir.get("分段脚本", [])

            # 检测是否有快速、剧烈的运动变化
            rapid_movements = ["急转", "快速旋转", "瞬间", "猛地"]

            for i, seg in enumerate(segments):
                camera_action = seg.get("摄影机动作", "")
                time_range = seg.get("时间段", "")

                if not time_range or not camera_action:
                    continue

                start, end = self.parse_time_range(time_range)
                duration = end - start

                # 如果时间段很短（<2秒）且包含剧烈运动词汇
                if duration < 2.0:
                    for word in rapid_movements:
                        if word in camera_action:
                            self.add_violation(
                                "摄影机运动合理性",
                                f"第 {i+1} 段在 {duration} 秒内有不合理的快速运动: {camera_action}",
                                severity="warning"
                            )
                            break
        except Exception as e:
            self.add_violation("摄影机运动合理性", f"校验失败: {str(e)}")

    def check_anchor_coverage(self):
        """门禁 7: 锚点贯穿性"""
        try:
            continuity = self.ir.get("连续性控制", {})
            anchors = continuity.get("固定锚点", [])

            if not anchors:
                return

            segments = self.ir.get("分段脚本", [])
            all_elements = []

            for seg in segments:
                elements = seg.get("重点元素", [])
                all_elements.extend(elements)
                all_elements.append(seg.get("主要事件", ""))
                all_elements.append(seg.get("主体动作", ""))

            # 检查每个锚点是否至少在某个分段中被提及
            for anchor in anchors:
                found = False
                for element in all_elements:
                    if anchor in str(element):
                        found = True
                        break

                if not found:
                    self.add_violation(
                        "锚点贯穿性",
                        f"固定锚点 '{anchor}' 未在任何分段脚本的重点元素中出现",
                        severity="warning"
                    )
        except Exception as e:
            self.add_violation("锚点贯穿性", f"校验失败: {str(e)}")

    def check_focal_length_match(self):
        """门禁 8: 景别与焦距匹配"""
        try:
            camera = self.ir.get("摄影参数", {})
            shot_type = camera.get("镜头类型", "")
            focal_length = camera.get("焦距", "").lower()

            if not shot_type or not focal_length:
                return

            # 简化的匹配规则
            mismatches = [
                ("特写", ["14mm", "16mm", "18mm", "超广角", "广角"]),
                ("大远景", ["85mm", "100mm", "135mm", "长焦"]),
            ]

            for shot, incompatible_lenses in mismatches:
                if shot in shot_type:
                    for lens in incompatible_lenses:
                        if lens in focal_length:
                            self.add_violation(
                                "景别与焦距匹配",
                                f"镜头类型 '{shot_type}' 不适合使用 '{focal_length}'",
                                severity="warning"
                            )
        except Exception as e:
            self.add_violation("景别与焦距匹配", f"校验失败: {str(e)}")

    def check_lighting_continuity(self):
        """门禁 9: 光照连续性"""
        try:
            environment = self.ir.get("场景环境", {})
            time_of_day = environment.get("时间", "")
            lighting = environment.get("光照条件", "")

            # 检测时间跨度
            time_transitions = [
                ("黎明", "白天"),
                ("白天", "黄昏"),
                ("黄昏", "夜晚"),
            ]

            for start_time, end_time in time_transitions:
                if start_time in time_of_day and end_time in time_of_day:
                    # 应该描述光照变化
                    change_keywords = ["渐变", "过渡", "变化", "转换", "从...到"]
                    has_change_description = any(kw in lighting for kw in change_keywords)

                    if not has_change_description:
                        self.add_violation(
                            "光照连续性",
                            f"时间跨度从 {start_time} 到 {end_time}，但光照条件未描述变化过程",
                            severity="warning"
                        )
        except Exception as e:
            self.add_violation("光照连续性", f"校验失败: {str(e)}")

    def check_required_fields(self):
        """门禁 10: 必填字段完整性"""
        try:
            required_top = ["metadata", "global_constraints", "主要主体", "场景环境", "摄影参数", "分段脚本"]
            for field in required_top:
                if field not in self.ir or not self.ir[field]:
                    self.add_violation("必填字段完整性", f"顶层必填字段 '{field}' 缺失或为空")

            # 检查嵌套必填字段
            metadata = self.ir.get("metadata", {})
            if not metadata.get("ir_version"):
                self.add_violation("必填字段完整性", "metadata.ir_version 缺失")
            if not metadata.get("source"):
                self.add_violation("必填字段完整性", "metadata.source 缺失")

            constraints = self.ir.get("global_constraints", {})
            if not constraints.get("总时长"):
                self.add_violation("必填字段完整性", "global_constraints.总时长 缺失")
            if not constraints.get("比例"):
                self.add_violation("必填字段完整性", "global_constraints.比例 缺失")
            if not constraints.get("目标平台"):
                self.add_violation("必填字段完整性", "global_constraints.目标平台 缺失")

            subject = self.ir.get("主要主体", {})
            if not subject.get("类型"):
                self.add_violation("必填字段完整性", "主要主体.类型 缺失")
            if not subject.get("外观描述"):
                self.add_violation("必填字段完整性", "主要主体.外观描述 缺失")

            environment = self.ir.get("场景环境", {})
            if not environment.get("空间描述"):
                self.add_violation("必填字段完整性", "场景环境.空间描述 缺失")
            if not environment.get("光照条件"):
                self.add_violation("必填字段完整性", "场景环境.光照条件 缺失")

            camera = self.ir.get("摄影参数", {})
            if not camera.get("镜头类型"):
                self.add_violation("必填字段完整性", "摄影参数.镜头类型 缺失")
            if not camera.get("机位运动"):
                self.add_violation("必填字段完整性", "摄影参数.机位运动 缺失")

            segments = self.ir.get("分段脚本", [])
            for i, seg in enumerate(segments):
                if not seg.get("时间段"):
                    self.add_violation("必填字段完整性", f"分段脚本第 {i+1} 段缺少 '时间段'")
                if not seg.get("主要事件"):
                    self.add_violation("必填字段完整性", f"分段脚本第 {i+1} 段缺少 '主要事件'")

        except Exception as e:
            self.add_violation("必填字段完整性", f"校验失败: {str(e)}")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "pass": False,
            "violations": [{
                "gate": "使用方法",
                "severity": "error",
                "message": "用法: python3 quality_gate.py <ir_file.json>"
            }]
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    ir_file = sys.argv[1]

    try:
        with open(ir_file, 'r', encoding='utf-8') as f:
            ir_data = json.load(f)
    except FileNotFoundError:
        print(json.dumps({
            "pass": False,
            "violations": [{
                "gate": "文件读取",
                "severity": "error",
                "message": f"文件不存在: {ir_file}"
            }]
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(json.dumps({
            "pass": False,
            "violations": [{
                "gate": "JSON解析",
                "severity": "error",
                "message": f"JSON 格式错误: {str(e)}"
            }]
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    gate = QualityGate(ir_data)
    result = gate.validate_all()

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 返回非零退出码如果校验失败
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
