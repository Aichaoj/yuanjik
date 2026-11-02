# 元健康 AI 顾问 · 服务端骨架（v0）

> 建立日期：2026-10-06
> 定位：**不是完整后端**，而是把专家组审核发现的四类结构缺陷在代码层堵死的最小骨架。
> 依赖：Python 3.12 + 标准库（**不依赖 FastAPI / PostgreSQL / Redis 即可跑通与测试**）

---

## 一、为什么先写这个，而不是先写业务接口

专家组审核（`方案/17`）指出：**服务端接口契约为零**，两个后端工程师会各自发明一套 envelope、错误码和登录态，到前端接入时全部返工。而这四件事不依赖任何算法决策与外部前置条件，可以立刻做。

本骨架对应四条修复：

| 审核发现 | 对应实现 | 验证 |
|---|---|---|
| **A-5** param_hash 漏 baseline/self_scale（三层同源） | `app/envelope.py` | 7 项测试 |
| **A-8** 护栏不是结构性卡口 | `app/kernel_adapter.GuardedText` | 6 项测试 |
| **软件阻断-4** 个体基线闭环从未接入 | `app/baseline.py` + 《基线契约》 | 10 项测试 |
| **软件阻断-7** 接口/错误码/缓存键缺失 | `app/errors.py` + `envelope.cache_key` | 5 项测试 |

---

## 二、目录

```
服务端/
├── 基线契约.md            ★ 个体基线生命周期的唯一口径源（写代码前的前置件）
├── 接口契约v0.md          ★ C 端业务 API 契约（响应结构/鉴权/限流/幂等/分页/版本）
├── README.md
├── demo.py                端到端演示（python demo.py）
├── _verify_pg_redis.py    生产化验证脚本（连真库跑关键链路并打印证据）
├── app/
│   ├── __init__.py
│   ├── envelope.py        ★ 统一入参信封 → param_hash + cache_key
│   ├── errors.py          ★ 业务错误码分段表（唯一口径源）
│   ├── baseline.py        ★ BaselineService + 内存仓储
│   ├── kernel_adapter.py  ★ 内核适配层（可替换，为 FTO 留后路）+ GuardedText
│   ├── reading_service.py ★ 编排：信封 + 基线 + 内核 + 护栏 + 缓存
│   ├── auth.py            ★ 不透明令牌 + 服务端会话（撤销即时生效）+ 身份归一 + 账号合并
│   ├── ratelimit.py       ★ 令牌桶（契约 §3 表）+ 幂等键存储（契约 §4）
│   ├── http.py            ★ 框架无关路由 + 响应装配 + 游标分页
│   ├── api.py             ★ v1 接口处理函数（只吃 dict、只吐 dict）
│   ├── pg.py              生产：PostgreSQL 连接池 / 事务 / 环境变量 DSN + 脱敏
│   └── repos/             生产：仓储层（**刻意不导出到 app/__init__**；psycopg/redis 为可选依赖）
│       ├── pg_baseline.py       BaselineRepo 的 PostgreSQL 实现（rhythm.baseline）
│       ├── pg_idempotency.py    幂等键的 PG 持久兜底（ops.idempotency_key）
│       ├── redis_session.py     SessionStore 的 Redis 实现（sess:* 键布局）
│       ├── redis_idempotency.py IdempotencyStore 的 Redis 实现（idem:* 键布局）
│       └── wiring.py            build_production_stack()：可注入切换的唯一入口
└── tests/                 104 项测试（test_service + test_auth_infra + test_pg_baseline + test_redis_stores）
```

**★ `http.py` 与 `api.py` 不依赖任何 Web 框架**——入参是普通 dict，出参是普通 dict。
FastAPI / Flask / 云函数都只是薄包装。直接好处：**在没有 Web 框架的机器上也能跑全部接口测试**。

---

## 三、三条设计原则

### 3.1 参数摘要由单一来源产生

内核旧实现在 `engine._param_hash()` 里自己拼 payload，服务层若再拼一份，**两处都可能漏输入**。现改为：
`InputEnvelope` 产生摘要 → 传给内核 `read_day(param_hash=...)` → 内核直接采用 → 服务层自校验回传值是否一致。

任一方被改坏，**启动或首次调用即失败**，不会静默返回错误结果。

### 3.2 护栏是类型约束，不是纪律

内核 `DailyReading.to_dict()` 会导出 `focus` / `strategy_hints` 等**未过护栏**的字段。本骨架**不导出这些字段**——对外文本只能是 `GuardedText`，其唯一构造入口是 `KernelAdapter.guard()`。调用方拿不到未过护栏的字符串，绕过就从"默认行为"变成"做不到"。

### 3.3 基线未建立时降级输出

按《基线契约》§2.1：`observation_count < 7` 时只输出 Δ 与"基线建立中（n/7）"，**不出观察等级、不出关注通道、不出策略取向**。对应专利 2 权利要求 6。

---

## 四、运行

```bash
cd 服务端
python demo.py                                   # 端到端演示
python -m unittest discover -s tests -t .        # 104 项测试（63 项骨架 + 41 项生产实现）
python _verify_pg_redis.py                       # 连真库跑关键链路并打印证据（退出码 0=全过）
```

内核路径默认为 `../核心`，可用环境变量覆盖：

```bash
set TYH_KERNEL_ROOT=D:\path\to\核心
```

---

## 五、生产化待办（按依赖排序）

| # | 事项 | 依赖 | 状态 |
|---|---|---|---|
| 1 | `BaselineRepo` / `SessionStore` / `IdempotencyStore` 的 PostgreSQL + Redis 实现 | ✅ **前置已解除（2026-10-08）**：`调研/schema_v1.sql` 首次在真实 PostgreSQL 18.0 上执行成功（0 error；10 schema / 95 基表 + 15 分区父表 / 751 分区 / 845 索引 / 5 扩展），本地开发库 `aiyjk @ 127.0.0.1:15432` 可用。证据见 `变更记录/2026-10-08_建库脚本首次真机跑通.md` | ✅ **已完成（2026-10-08）**——见 §八。不改任何接口签名，只新增实现 + 可注入切换 |
| 2 | 微信 `code2session` 真实对接（当前为注入回调，便于测试） | 小程序 appid/secret（**须走 `vault:` 引用，不入代码/日志**） | 🔲 |
| 3 | FastAPI 薄包装（复用 `http.Router` 与 `api.ApiV1` 的处理函数） | 需 `pip install fastapi uvicorn` | 🔲 |
| 4 | 短信通道 + 双维度限流接线 | 通道选型（境内 + 数据处理协议，见 `方案/17` §2.2 重要-8） | 🔲 |
| 5 | 同意管理（5 份独立文书）与数据权利接口 | 需先出《个人信息处理同意架构》（`方案/17` §3.3 第 4 项） | 🔲 |

> **⚠️ 明确未做**：任何与抗量子/加密相关的实现。密码能力由关联方提供，本方只做适配层
> （见 `方案/11` §3 与 `方案/14` 的关联方口径）。本目录**不含**任何加密算法、密钥管理、信封格式代码。
> `auth.py` 里的令牌是**随机不透明串**，不是密码学构造，也不承担机密性职责。

---

## 六、跑通后立刻能验证的五件事

1. **参数摘要是真的覆盖全部输入**：改基线 → `param_hash` 与 `cache_key` 同时变（旧实现两者都不变，会命中错误缓存）
2. **冷启动不会输出无意义的等级**：新用户拿到的是"校准中（0/7）"，不是一套量纲不对的 L1–L4
3. **护栏堵得住实测过的四类绕过**：药物剂量、字符混淆、免责声明截断、组合式判读
4. **撤销即时生效**：撤回同意 → 该账号全部会话在**同一秒**失效（这是不用 JWT 的全部理由）
5. **幂等真的幂等**：同键同体重复请求，业务只执行一次；同键异体报 `10003`

---

## 七、本轮抓出并修掉的两个自身缺陷

写代码过程中由测试与 demo 各暴露一个，都值得记下来：

| # | 缺陷 | 暴露方式 | 教训 |
|---|---|---|---|
| 1 | 信封与内核**各算一份 param_hash**，永远不可能相等 | 服务层自校验一跑就炸 | 「两处各算一份」本身就是漂移源，必须收敛为单一来源 |
| 2 | 固定合规文本 `DISCLAIMER` **被自己送进护栏降级**（它含"诊断、治疗"） | `demo.py` 打印输出时肉眼发现 | 固定合规文本必须直接引用常量，不进护栏；否则每条响应都会把免责声明换成养生模板 |
| 3 | 账号合并的**主/从判定取反**，会把较早的 member_id 丢掉 | 单元测试 | 合并类逻辑必须测「哪个是主」而不只测「合没合」 |

---

## 八、生产化实现：PostgreSQL + Redis（2026-10-08）

**目标**：把内存版持久化换成生产实现，**不改任何既有接口签名 / 错误码 / 响应形状**。

### 8.1 切换方式（唯一入口）

```python
from app.repos.wiring import build_production_stack, compose_reading_service, compose_api
from app.kernel_adapter import KernelAdapter

stack = build_production_stack()      # 读 TYH_PG_DSN / TYH_REDIS_URL
stack.assert_ready()                  # 起服务前自检；任一依赖不可用即抛 90001，不静默降级
reading = compose_reading_service(stack, KernelAdapter())
ApiV1(router, **compose_api(stack, reading=reading))
```

内存版与生产版的接口完全同形——这就是《接口契约 v0》存在的意义。
单测仍可继续用 `InMemoryBaselineRepo` / `SessionStore` / `IdempotencyStore`。

### 8.2 环境变量（口令由 vault 注入到环境，不入代码/日志）

| 变量 | 必需 | 说明 |
|---|---|---|
| `TYH_PG_DSN` | 是 | PostgreSQL 连接串；缺失时 `PgConfigError` 给出清晰报错（含注入示例） |
| `TYH_PG_TENANT_ID` | 否 | 会话级 `app.tenant_id`（`core.member` 的 FORCE RLS 需要；超级用户可省） |
| `TYH_PG_POOL_MAX` / `TYH_PG_APP_NAME` / `TYH_PG_CONNECT_TIMEOUT` | 否 | 连接池参数，默认 8 / `tyh-service` / 5 s |
| `TYH_REDIS_URL` | 是 | Redis 连接串；缺失时 `RedisConfigError` 给出清晰报错 |
| `TYH_REDIS_TIMEOUT` | 否 | socket 超时，默认 3 s |

`PgDatabase.dsn_redacted` / `RedisSessionStore.url_redacted` 是 DSN 对外出现的**唯一形式**（口令替换为 `***`）。

### 8.3 与 `调研/schema_v1.sql` 的结构差异（**未改 schema**，在仓储层适配）

| # | 契约/代码的写法 | `schema_v1.sql` 的实际列 | 适配方式 |
|---|---|---|---|
| 1 | §3「一行一会员，`s_ref` 为 jsonb」 | `rhythm.baseline` 是 **一行一(会员×通道×规则版本)**，`s_ref` 为 `numeric(7,4)` 标量 | 12 通道 = 12 行同事务写入，读回重组为 12 键字典 |
| 2 | `observation_count` / `last_observed_on` 两列 | 无此二列 | `sample_days` ≡ `observation_count`；`window_end` ≡ `last_observed_on`；`window_start` 记首次观测日 |
| 3 | `established` 列 | 无（且不该有，是派生量） | 由 `sample_days >= 7` 派生，不入库 |
| 4 | 服务层 `s_ref` 保留 6 位小数 | `numeric(7,4)` 只到 **4 位** | 写库前统一舍入到 4 位，保证"读回来的就是库里那一份"（8 次 EWMA 后与内存版最大偏差实测 7.10e-05） |
| 5 | `auth.py` 的会员号形如 `mbr_1a2b…` | `member_id uuid` 且外键到 `core.member(id)` | `member_uuid()` 对非 UUID 串做**确定性 uuid5** 映射（命名空间可注入），既有会员号可直接落库 |
| 6 | — | `core.member` 是 **FORCE ROW LEVEL SECURITY**，策略读会话变量 `app.tenant_id` | `PgDatabase` 建连时写 `app.tenant_id`；非超级用户角色必须提供 `TYH_PG_TENANT_ID` |

> **未提改动建议**：以上 6 条都能在仓储层无损适配，**没有发现必须改 schema 的硬缺陷**。
> 唯一建议（非必须）：`s_ref numeric(7,4)` 若要与服务层 6 位小数对齐，可考虑放宽到 `numeric(9,6)`。

### 8.4 两处生产实现的关键取舍

- **`sess:access:*` 的 TTL 取 refresh 剩余寿命（而非 15 分钟）**
  `AuthService.authenticate()` 自己判断 `access_expires_at` 返回 20001；若让键在 15 分钟时消失，
  过期令牌会被误判为"未知令牌"返回 20000，**错误码形状就变了**。
- **`sess:acct:{account_id}` 用 LIST 而非 SET**
  `active_of()` 要按 `issued_at` 排序判"最早登录的设备"，而 Windows 上 `time.time()` 分辨率约 15.6 ms，
  连续登录的会话 `issued_at` 可能完全相同；无序 SET 排序不稳定会**踢错设备**，插入序 LIST 则结果确定。

### 8.5 运行与验证

```bash
python -m unittest discover -s tests -t .   # 104 项（63 骨架 + 20 Redis + 21 PG）
python _verify_pg_redis.py                  # 连真库跑关键链路，打印证据，退出码 0=全过
```

**实测数字**（2026-10-08，PostgreSQL 18.0 @ 127.0.0.1:15432 / aiyjk）：

| 环节 | 实测 |
|---|---|
| 一次 `record` 落库 | `rhythm.baseline` 12 行；`sample_days=1`、`method=ewma`、`half_life_days=7` |
| α 平滑（0.2 → 1.0 → 0.5） | 库内 12 通道值依次 `0.2000 → 0.2800 → 0.3020` |
| 规则升级（v1 n=3 → v2） | v1 仍 `0.3020`/`sample_days=3`/12 行；v2 记 `0.3518`/`sample_days=4`/12 行（共 24 行） |
| 撤回同意 → 旧令牌 | `code=20002`（HTTP 401），时延 **0.0000–0.0011 秒** |
| 幂等同键异体 | `code=10003`（HTTP 409）；同键同体 handler 只执行 1 次 |
| 6 线程同日并发写基线 | `sample_days=1`、12 行（advisory lock 生效，无重复计数） |

### 8.6 明确未做 / 未验证

1. **本机未安装 redis-server**：Redis 适配层的测试与验证跑在 `fakeredis` 上，
   **真实 Redis 实例未验证**（键布局与命令按 redis-py 语义书写；设 `TYH_REDIS_URL` 后重跑 `_verify_pg_redis.py` 会自动切真实实例）。
2. **未做并发压测**（仅 6 线程同日并发写基线一条用例）。
3. `TYH_PG_DSN` / `TYH_REDIS_URL` 在生产如何注入（vault → 环境）未在本机验证。
4. 未实现 `BaselineRepo` 的"多实例高可用/主从切换"逻辑（连接池会丢弃坏连接并重建，但没有重试策略）。

---

*本目录与服务端骨架为工程实现，不构成法律意见或医疗意见。*
