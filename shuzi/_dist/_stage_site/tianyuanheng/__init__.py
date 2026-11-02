# -*- coding: utf-8 -*-
"""
天元衡（TianYuanHeng）· 个人健康节律预测内核
=============================================
四步模型：编码 → 场谱 → 偏移 → 对冲

设计原则：
  · 只使用公有领域知识（《黄帝内经·素问》运气学说、干支历法、藏象学说、子午流注）
  · 不包含、不参考任何第三方未公开算法、映射表或命名体系
  · 完全确定性、可被第三方独立复现
  · 所有输出携带规则依据链（规则ID + 古典出处）

⚠️ 合规声明：本内核为健康管理辅助工具，不属于医疗器械，
   不用于疾病的诊断、治疗或预防，不替代专业医疗意见。
"""
from .engine import (ENGINE_VERSION, DailyReading, batch_daily, engine_info,
                     read_day, summarize_windows, CHANNEL_WUXING, COUNTER_STRATEGY)
from .calendar_layer import (BirthChart, Pillar, build_birth_chart,
                             julian_day_number, sexagenary_index_of_jdn,
                             solar_term_table, true_solar_time_offset_minutes)
from .yunqi_layer import (YunqiBoard, YunqiStep, board_of_year, build_board,
                          kezhu_relation)
from .zangfu_layer import (CHANNELS, ChannelEffect, FieldSpectrum,
                           build_field_spectrum)
from .offset_layer import (ChannelState, OffsetResult, compute_offset,
                           update_baseline, scan_windows, classify)
from .realtime import (EVENT_PROFILE, SCORE_CALIBER, SCORE_NAMESPACE,
                       BehaviorEvent, RealtimeEngine, RealtimeSnapshot,
                       curve_stats, event_delta, events_delta, shichen_weight)
from .intake import (DANGER_SIGNALS, QUESTION_BANK, SELF_HARM_SIGNALS,
                     ElicitationEngine, ElicitationPlan, ElicitationQuestion,
                     IntakeResult, daily_budget, parse_intake, parse_voice)
from .dimensions import (BAGANG, CALIBRATION_TARGETS, DIM_META, DIM_WEIGHTS,
                         LITERATURE, RELATION_FACTORS, WORK_FACTORS,
                         BaGangState, ConstitutionProfile, CouplingProfile,
                         MultiDimVector, apply_coupling, bagang_of,
                         build_multidim_vector, constitution_of,
                         liujing_state, yujie_active, yujie_hours)
from .rules import (ALL_RULES, RULE_VERSION, Rule, get_rule, lineage,
                    registry_summary)
from . import guardrail

__version__ = ENGINE_VERSION
__all__ = [
    "read_day", "batch_daily", "summarize_windows", "engine_info",
    "build_birth_chart", "solar_term_table", "true_solar_time_offset_minutes",
    "julian_day_number", "sexagenary_index_of_jdn",
    "build_board", "board_of_year", "kezhu_relation",
    "build_field_spectrum", "compute_offset", "update_baseline", "scan_windows",
    "classify", "get_rule", "lineage", "registry_summary", "guardrail",
    "RealtimeEngine", "RealtimeSnapshot", "BehaviorEvent", "event_delta",
    "events_delta", "shichen_weight", "curve_stats",
    "EVENT_PROFILE", "SCORE_CALIBER", "SCORE_NAMESPACE",
    # 录入层
    "parse_intake", "parse_voice", "IntakeResult", "DANGER_SIGNALS",
    "SELF_HARM_SIGNALS", "ElicitationEngine", "ElicitationPlan",
    "ElicitationQuestion", "QUESTION_BANK", "daily_budget",
    # 多维层
    "MultiDimVector", "CouplingProfile", "ConstitutionProfile", "BaGangState",
    "build_multidim_vector", "constitution_of", "liujing_state", "bagang_of",
    "yujie_active", "yujie_hours", "apply_coupling",
    "DIM_META", "DIM_WEIGHTS", "CALIBRATION_TARGETS", "LITERATURE",
    "RELATION_FACTORS", "WORK_FACTORS", "BAGANG",
    # 基础
    "BirthChart", "Pillar", "YunqiBoard", "YunqiStep", "FieldSpectrum",
    "ChannelEffect", "ChannelState", "OffsetResult", "DailyReading", "Rule",
    "CHANNELS", "CHANNEL_WUXING", "COUNTER_STRATEGY", "ALL_RULES", "RULE_VERSION",
]
