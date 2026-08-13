"""PLN-039 T6：解析最新 llm.jsonl，统计缓存命中率与各类别分布。

用法：python scripts/debug/analyze_llm_cache.py [llm.jsonl 路径]
默认读取 runtime_game_logs/recent_1/llm.jsonl。
"""

import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"runtime_game_logs\recent_1\llm.jsonl"
rows = []
with open(path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

reqs = {r["request_id"]: r for r in rows if r.get("type") == "request"}
resps = [r for r in rows if r.get("type") == "response"]

total_hit = 0
total_miss = 0
total_prompt = 0
total_completion = 0
total_total = 0
total_reasoning = 0
by_category = {}  # category -> {hit, miss, count, total}


def classify(req) -> str:
    if not req:
        return "unknown"
    sysp = req.get("system_prompt", "")
    msgs = req.get("messages", [])
    user = "".join(m.get("content", "") for m in msgs if m.get("role") == "user")
    # 先判定辅助类（其 system 也前置了全局静态层，需在 act/draft 之前检测）
    if "说书人" in sysp and "当前核心局势" in user:
        return "storyteller"
    if "邪恶频道" in sysp or "你的队友名字" in sysp:
        return "evil_coord"
    if "局势总体印象" in user or "深入思考" in sysp or "极简的内心独白" in user:
        return "reflect"
    if "阶段归纳" in sysp or "逻辑严密的血染钟楼玩家" in sysp:
        return "archive"
    if "【玩家名单】" in sysp or "【可用行动工具】" in sysp:
        if "请只返回一个 speak 动作的 JSON 决策" in user:
            return "draft"
        return "act"
    if "内心独白" in user:
        return "think"
    return "other"


for r in resps:
    req = reqs.get(r.get("request_id"))
    usage = r.get("usage") or {}
    hit = usage.get("prompt_cache_hit_tokens", 0) or 0
    miss = usage.get("prompt_cache_miss_tokens", 0) or 0
    prompt = usage.get("prompt_tokens", 0) or 0
    completion = usage.get("completion_tokens", 0) or 0
    total = usage.get("total_tokens", 0) or 0
    reasoning = usage.get("reasoning_tokens", 0) or 0
    total_hit += hit
    total_miss += miss
    total_prompt += prompt
    total_completion += completion
    total_total += total
    total_reasoning += reasoning
    cat = classify(req)
    c = by_category.setdefault(cat, {"hit": 0, "miss": 0, "count": 0, "total": 0})
    c["hit"] += hit
    c["miss"] += miss
    c["count"] += 1
    c["total"] += total

print(f"=== 对局 {path} ===")
print(f"总请求数: {len(resps)}")
denom = total_hit + total_miss
print(f"全量命中率: {total_hit}/{denom} = {total_hit / denom * 100:.2f}%")
print(f"prompt 总 token: {total_prompt} (hit={total_hit}, miss={total_miss})")
print(f"completion 总 token: {total_completion}")
print(f"真实总 token: {total_total}")
print(f"reasoning_tokens 总和: {total_reasoning}")
print(f"计费当量(input, hit 按 0.1 计): {total_miss + 0.1 * total_hit:.0f}")
print(f"响应 error 数: {sum(1 for r in resps if r.get('error'))}")
print()
print("=== 分类明细 ===")
for cat, c in sorted(by_category.items(), key=lambda kv: -kv[1]["count"]):
    rate = c["hit"] / (c["hit"] + c["miss"]) * 100 if c["hit"] + c["miss"] else 0
    print(
        f"{cat:12s} count={c['count']:4d} hit={c['hit']:7d} miss={c['miss']:7d} "
        f"命中率={rate:6.2f}% total_tokens={c['total']}"
    )

# T2.1 验证：同一玩家不同动作的 tools 参数完全一致
print()
print("=== T2.1 验证：act 调用 tools 参数恒等（按玩家分组去重） ===")
tools_by_player = {}
for r in resps:
    req = reqs.get(r.get("request_id"))
    if not req or classify(req) != "act":
        continue
    sysp = req.get("system_prompt", "")
    player = ""
    for seg in sysp.split("\n"):
        if "【你的身份】" in seg:
            player = seg
            break
    tools = json.dumps(req.get("parameters", {}).get("tools", []), sort_keys=True)
    tools_by_player.setdefault(player, set()).add(tools)
for player, toolset in sorted(tools_by_player.items()):
    print(f"player={player[:40]!r} 不同tools组合数={len(toolset)}")

# T3.1 验证：草稿 system 与同 agent act system 前缀一致
print()
print("=== T3.1 验证：同一 Agent 的 draft vs act system 逐 token 一致（REV-008 R3） ===")
import re as _re

draft_by_player: dict[str, set[str]] = {}
act_by_player: dict[str, set[str]] = {}
for r in resps:
    req = reqs.get(r.get("request_id"))
    if not req:
        continue
    cat = classify(req)
    if cat not in {"draft", "act"}:
        continue
    sysp = req.get("system_prompt", "")
    m = _re.search(r"【你的身份】你的名字是 ([^，,。\n]+)", sysp)
    player = m.group(1).strip() if m else "(unknown)"
    bucket = draft_by_player if cat == "draft" else act_by_player
    bucket.setdefault(player, set()).add(sysp)
print(f"draft 覆盖 player 数={len(draft_by_player)}, act 覆盖 player 数={len(act_by_player)}")
all_ok = True
for player in sorted(set(draft_by_player) | set(act_by_player)):
    d_var = len(draft_by_player.get(player, set()))
    a_var = len(act_by_player.get(player, set()))
    if d_var and a_var:
        d = next(iter(draft_by_player[player]))
        a = next(iter(act_by_player[player]))
        ok = d == a
        all_ok = all_ok and ok
        print(
            f"player={player!r}: draft变体={d_var} act变体={a_var} "
            f"draft==act完全一致={ok} (syslen={len(d)})"
        )
    else:
        print(
            f"player={player!r}: draft变体={d_var} act变体={a_var} "
            f"（缺 {('draft' if d_var == 0 else 'act')}，无法同 agent 比对）"
        )
print(
    f"T3.1 判定（同 agent draft==act 完全一致）: {'PASS' if all_ok else 'FAIL（有同 agent 不一致）'}"
)
# 全局静态层共享验证（任意一个 system 即可）
sample = next((s for bucket in (draft_by_player, act_by_player) for s in bucket.values() if s), "")
if sample:
    first = next(iter(sample))
    layer = first[: first.index("【玩家名单】")] if "【玩家名单】" in first else ""
    print(f"全局静态层长度(截取到【玩家名单】前): {len(layer)}")
