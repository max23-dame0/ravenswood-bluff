"""PLN-039 后续：分析缓存命中率剩余提升空间。

对最新 llm.jsonl 逐请求分析：
1. system / user1 / user2 三段长度（静态段占比 = 理论上限命中率）
2. 同一 Agent 的请求间 system 完全一致的比例（判断 system 是否已稳定）
3. 同 Agent 请求间 user1 一致比例（user1 是否已稳定）
4. 分类对比：命中率 vs 静态段占比（gap = 可提升空间）
"""
import json
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else r"runtime_game_logs\recent_3\llm.jsonl"
rows = []
with open(path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

reqs = {r["request_id"]: r for r in rows if r.get("type") == "request"}
resps = [r for r in rows if r.get("type") == "response"]


def classify(req) -> str:
    if not req:
        return "unknown"
    sysp = req.get("system_prompt", "")
    msgs = req.get("messages", [])
    user = "".join(m.get("content", "") for m in msgs if m.get("role") == "user")
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


def extract_player(sysp: str) -> str:
    """从 system 提取 player_id（层2 身份段）。"""
    for line in sysp.split("\n"):
        if "【你的身份】" in line:
            # 名字格式：你的名字是 Player X / Alice
            seg = line.split("，")[0] if "，" in line else line
            return seg
    return ""


cat_reqs = defaultdict(list)  # cat -> [req]
for r in resps:
    req = reqs.get(r.get("request_id"))
    if req:
        cat_reqs[classify(req)].append(req)

# 1) 静态段占比：system / (system + user1) 相对 prompt 理论上限
print("=== 1) 各分类静态段占比（system / system+user1 占请求比例）===")
print(f"{'cat':12s} {'n':>4s} {'avg_prompt':>10s} {'avg_sys':>9s} {'avg_u1':>8s} "
      f"{'static%':>8s} {'命中率%':>8s} {'gap%':>7s}")
for cat in sorted(cat_reqs, key=lambda c: -len(cat_reqs[c])):
    req_list = cat_reqs[cat]
    total_p = total_s = total_u1 = 0
    for req in req_list:
        sysp = req.get("system_prompt", "")
        msgs = req.get("messages", [])
        u1 = msgs[0].get("content", "") if msgs else ""
        total_p += len(sysp) + sum(len(m.get("content", "")) for m in msgs)
        total_s += len(sysp)
        total_u1 += len(u1)
    n = len(req_list)
    static_pct = (total_s + total_u1) / total_p * 100 if total_p else 0
    # 命中率（用该分类响应 usage 汇总）
    hit = miss = 0
    for r in resps:
        req = reqs.get(r.get("request_id"))
        if req and classify(req) == cat:
            usage = r.get("usage") or {}
            hit += usage.get("prompt_cache_hit_tokens", 0) or 0
            miss += usage.get("prompt_cache_miss_tokens", 0) or 0
    hit_rate = hit / (hit + miss) * 100 if hit + miss else 0
    print(f"{cat:12s} {n:4d} {total_p/n:10.0f} {total_s/n:9.0f} {total_u1/n:8.0f} "
          f"{static_pct:7.1f}% {hit_rate:7.1f}% {max(0, static_pct - hit_rate):6.1f}%")

# 2) 同 Agent 请求间 system 一致性（act/draft/reflect/archive）
print()
print("=== 2) 同 player 请求间 system 完全一致比例（act/draft/archive/reflect）===")
player_sys = defaultdict(set)
for cat in ("act", "draft", "archive", "reflect"):
    for req in cat_reqs.get(cat, []):
        pid = extract_player(req.get("system_prompt", ""))
        if pid:
            player_sys[(cat, pid)].add(req.get("system_prompt", ""))
for key in sorted(player_sys):
    cat, pid = key
    n_variants = len(player_sys[key])
    print(f"  {cat:8s} {pid[:36]:38s} system 变体数={n_variants}")

# 3) 同 player 请求间 user1 一致比例
print()
print("=== 3) 同 player 请求间 user1（首条 user）一致比例 ===")
player_u1 = defaultdict(set)
for cat in ("act", "draft"):
    for req in cat_reqs.get(cat, []):
        pid = extract_player(req.get("system_prompt", ""))
        if pid:
            msgs = req.get("messages", [])
            u1 = msgs[0].get("content", "") if msgs else ""
            player_u1[(cat, pid)].add(u1)
for key in sorted(player_u1):
    cat, pid = key
    n_variants = len(player_u1[key])
    print(f"  {cat:8s} {pid[:36]:38s} user1 变体数={n_variants}")

# 4) 草稿 vs act system 逐 token 前缀（T3 验证 + 可优化提示）
print()
print("=== 4) draft vs act system 共同前缀 ===")
draft_sys = [req.get("system_prompt", "") for req in cat_reqs.get("draft", [])]
act_sys = [req.get("system_prompt", "") for req in cat_reqs.get("act", [])]
if draft_sys and act_sys:
    d, a = draft_sys[0], act_sys[0]
    common = 0
    for x, y in zip(d, a, strict=False):
        if x == y:
            common += 1
        else:
            break
    print(f"  draft len={len(d)} act len={len(a)} 共同前缀={common} 完全一致={d == a}")
