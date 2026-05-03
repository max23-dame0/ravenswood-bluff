import subprocess
import json
import os
import time
from pathlib import Path

# 配置要测试的人数 (使用真实 Live 后端)
CONFIGS = [
    {"players": 5, "backend": "live", "stop_after": "game_over"},   # 5人完整局
    {"players": 7, "backend": "live", "stop_after": "game_over"},   # 7人完整局
    {"players": 9, "backend": "live", "stop_after": "day_1"},      # 9人首日压力测试
    # 12 和 15 人局建议仅在必要时开启
    # {"players": 12, "backend": "live", "stop_after": "day_1"},
]

# 如果有 Live 秘钥，可以加一个 Live 测试
# CONFIGS.append({"players": 5, "backend": "live", "stop_after": "first_execution"})

def run_simulation(players, backend, stop_after):
    print(f"\n>>> Running simulation: {players} players, backend={backend}, stop_after={stop_after}")
    cmd = [
        ".\\.venv\\Scripts\\python.exe", "simulate_game.py",
        "--player-count", str(players),
        "--backend", backend,
        "--stop-after", stop_after,
        "--timeout-seconds", "1200",
        "--audit-mode"
    ]
    
    start_time = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    duration = time.time() - start_time
    
    if result.returncode != 0:
        print(f"Error running simulation: {result.stderr}")
        return None
        
    # 从输出中提取审计摘要
    import re
    metrics = {
        "players": players,
        "backend": backend,
        "duration": duration,
        "action_count": 0,
        "total_tokens": 0,
        "fallback_count": 0,
        "winner": "unknown",
        "avg_token_per_action": 0.0
    }
    
    # 提取 game_id
    game_id_match = re.search(r"- game_id: ([a-f0-9\-]+)", result.stdout)
    if game_id_match:
        metrics["game_id"] = game_id_match.group(1)
        
    # 提取其他指标
    actions_match = re.search(r"- ai_action_count: (\d+)", result.stdout)
    if actions_match:
        metrics["action_count"] = int(actions_match.group(1))
        
    tokens_match = re.search(r"- ai_total_tokens: (\d+)", result.stdout)
    if tokens_match:
        metrics["total_tokens"] = int(tokens_match.group(1))
        
    fallback_match = re.search(r"- ai_fallback_count: (\d+)", result.stdout)
    if fallback_match:
        metrics["fallback_count"] = int(fallback_match.group(1))
        
    winner_match = re.search(r"- winner: (\w+)", result.stdout)
    if winner_match:
        metrics["winner"] = winner_match.group(1)
        
    if metrics["action_count"] > 0:
        metrics["avg_token_per_action"] = metrics["total_tokens"] / metrics["action_count"]
    
    return metrics

def main():
    results = []
    for cfg in CONFIGS:
        res = run_simulation(cfg["players"], cfg["backend"], cfg["stop_after"])
        if res:
            results.append(res)
            
    # 输出报表
    print("\n" + "="*50)
    print("ALPHA 1.0 PERFORMANCE BENCHMARK REPORT")
    print("="*50)
    
    header = "| Players | Backend | Duration (s) | Actions | Tokens | Avg Token/Action | Fallbacks | Winner |"
    sep = "|---" * 8 + "|"
    print(header)
    print(sep)
    
    for r in results:
        line = f"| {r['players']} | {r['backend']} | {r['duration']:.1f} | {r.get('action_count', 0)} | {r.get('total_tokens', 0)} | {r.get('avg_token_per_action', 0):.1f} | {r.get('fallback_count', 0)} | {r.get('winner', 'N/A')} |"
        print(line)
        
    # 写入文件
    with open("docs/alpha-1.0-benchmark-results.md", "w", encoding="utf-8") as f:
        f.write("# Alpha 1.0 多人数配置基准测试报告\n\n")
        f.write(header + "\n")
        f.write(sep + "\n")
        for r in results:
            line = f"| {r['players']} | {r['backend']} | {r['duration']:.1f} | {r.get('action_count', 0)} | {r.get('total_tokens', 0)} | {r.get('avg_token_per_action', 0):.1f} | {r.get('fallback_count', 0)} | {r.get('winner', 'N/A')} |\n"
            f.write(line)
        f.write(f"\nGenerated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == "__main__":
    main()
