# -*- coding: utf-8 -*-
"""
统一入参信封与缓存键（Canonical Input Envelope）
================================================
专家组审核发现的三层同源缺陷：
    ① 内核 `engine._param_hash` 漏 baseline / self_scale（已修）
    ② `方案/16:234` 的缓存键 `daily_plan:{rule_version}:{user_id}:{date}` **不含 param_hash**
    ③ `schema_v1.sql` 的 `moment_chart_cache` 主键 **不含 param_hash**

本模块把这三处收敛成**一个信封**：所有影响结果的输入进信封，信封出两个东西——
`param_hash`（可复现性凭据）与 `cache_key`（缓存键）。**调用方不得自行拼装缓存键。**
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field, asdict

ENGINE_VERSION = "TYH-ENGINE-0.1.0"
SERVICE_VERSION = "TYH-SVC-0.1.0"

# 规则版本：必须与 核心/tianyuanheng/rules.py 的 RULE_VERSION 一致。
# ★ 生产环境由 CI 断言二者相等；此处不 import 内核，保持服务层可独立部署。
#
# 版本历史：
#   TYH-RULES-1.1.0  2026-10-06  客主加临逆顺权重对调（Z-4）+ 补司天在泉与中运参数（Z-3/Z-6）
#   TYH-RULES-1.0.0  2026-10-06  首次冻结（44 条规则 / 六大分组）
#
# ★ 这条常量与服务层其它模块**不是**重复：它是"服务层声明的版本"，
#   KernelAdapter 构造时会与内核实际版本强校验，不一致直接失败（见 kernel_adapter.py）。
#   核心里三处字面量已消除（realtime/dimensions 回落 rules.RULE_VERSION），
#   服务层保留一份是刻意的——否则跨版本部署会静默出一致性问题。
RULE_VERSION = "TYH-RULES-1.3.0"

# 缓存分区前缀
NS_DAILY = "rhythm:daily"


def _round_map(m: dict | None) -> dict:
    """字典规范化：键排序 + 数值定精度（保证同内容必得同哈希）"""
    if not m:
        return {}
    return {str(k): round(float(v), 6) for k, v in sorted(m.items())}


@dataclass(frozen=True)
class InputEnvelope:
    """
    一次节律解读的**全部**输入。新增任何影响结果的输入，都必须加进本类，
    否则会重现"同哈希不同结果"的静默失效。

    ── 出生信息 ──
    birth_local     出生地民用时间，'YYYY-MM-DDTHH:MM'
    longitude       经度（东经为正）
    latitude        纬度
    late_zi_rolls_day  晚子时是否进位（CAL-006，争议项，默认 True）

    ── 目标时刻 ──
    target_date     目标日期，'YYYY-MM-DD'
    target_hour     目标小时（默认 12，日粒度参考点）
    target_minute   目标分钟

    ── 个体参数（★ 旧实现漏掉的两项）──
    baseline        个体基线 S_ref（12 通道）。None = 未建立
    self_scale      个体敏感度 A 的对角元。None = 全 1

    ── 基线状态 ──
    observation_count  已累计观测次数（按日聚合后）
    min_observations   基线建立所需次数（默认 7）

    ── 规则版本 ──
    rule_version / engine_version / service_version
    """
    birth_local: str
    longitude: float
    latitude: float
    target_date: str
    target_hour: int = 12
    target_minute: int = 0
    late_zi_rolls_day: bool = True
    baseline: dict = field(default_factory=dict)
    self_scale: dict = field(default_factory=dict)
    observation_count: int = 0
    min_observations: int = 7
    rule_version: str = RULE_VERSION
    engine_version: str = ENGINE_VERSION
    service_version: str = SERVICE_VERSION

    def canonical(self) -> dict:
        d = asdict(self)
        d['longitude'] = round(self.longitude, 6)
        d['latitude'] = round(self.latitude, 6)
        d['baseline'] = _round_map(self.baseline)
        d['self_scale'] = _round_map(self.self_scale)
        d['birth_local'] = self.birth_local.strip()
        d['target_date'] = self.target_date.strip()
        return d

    @property
    def param_hash(self) -> str:
        """可复现性凭据：覆盖全部输入。同输入 → 同哈希；任一输入变 → 哈希变。"""
        blob = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode('utf-8')).hexdigest()

    @property
    def param_hash_short(self) -> str:
        return self.param_hash[:32]

    def cache_key(self, member_id: str, ns: str = NS_DAILY) -> str:
        """
        缓存键。★ 必须含 param_hash 与 rule_version：
          - 含 rule_version：规则升级后旧键不再被读
          - 含 param_hash：基线/敏度变化后旧键不再被读（旧实现在这里漏了）
        """
        return "%s:%s:%s:%s" % (ns, self.rule_version, member_id, self.param_hash_short)

    def check_consistency(self, other: "InputEnvelope") -> bool:
        """同哈希必须同内容——用于内核返回后的自校验（防止静默失效）"""
        return self.param_hash == other.param_hash


def build(**kwargs) -> InputEnvelope:
    return InputEnvelope(**kwargs)


def assert_rule_version_matches(kernel_rule_version: str) -> None:
    """
    启动自检：服务层声明的规则版本必须与内核一致，否则拒绝启动。
    ★ 旧实现的版本号散落在三处（rules.py / realtime.py / dimensions.py），
      服务层再加一处就会漂移；改为启动时强校验，不一致直接失败。
    """
    if kernel_rule_version != RULE_VERSION:
        raise RuntimeError(
            "规则版本不一致：服务层声明 %s，内核实际 %s。"
            "请同步 app/envelope.py 的 RULE_VERSION 与 核心/tianyuanheng/rules.py。"
            % (RULE_VERSION, kernel_rule_version))
