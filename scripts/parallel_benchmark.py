import asyncio
import json
import os
import time
import re
from pathlib import Path

# 配置：8/9/10人局，各3局
PLAYER_COUNTS = [8, 9, 10]
GAMES_PER_COUNT = 3
CONCURRENCY_LIMIT = 3  # 同时运行的对局数，防止触发 API 频率限制

async def run_single_game(players, game_index):
    print(f"[START] Players={players}, Game {game_index+1}/3")
    cmd = [
        ".\\.venv\\Scripts\\python.exe", "simulate_game.py",
        "--player-count", str(players),
        "--backend", "live",
        "--stop-after", "game_over",
        "--timeout-seconds", "3600",  # 给足一小时，防止 10 人局超时
        "--audit-mode"
    ]
    
    start_time = time.time()
    # 使用 asyncio 创建子进程
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    duration = time.time() - start_time
    
    output = stdout.decode('utf-8', errors='ignore')
    err_output = stderr.decode('utf-8', errors='ignore')
    
    metrics = {
        "players": players,
        "game_index": game_index + 1,
        "duration": duration,
        "status": "success" if process.returncode == 0 else "failed",
        "action_count": 0,
        "total_tokens": 0,
        "fallback_count": 0,
        "winner": "unknown"
    }
    
    if process.returncode != 0:
        print(f"[FAILED] Players={players}, Game {game_index+1}. Error: {err_output[:200]}")
    
    # 解析输出
    game_id_match = re.search(r"- game_id: ([a-f0-9\-]+)", output)
    if game_id_match:
        metrics["game_id"] = game_id_match.group(1)
        
    actions_match = re.search(r"- ai_action_count: (\d+)", output)
    if actions_match:
        metrics["action_count"] = int(actions_match.group(1))
        
    tokens_match = re.search(r"- ai_total_tokens: (\d+)", output)
    if tokens_match:
        metrics["total_tokens"] = int(tokens_match.group(1))
        
    fallback_match = re.search(r"- ai_fallback_count: (\d+)", output)
    if fallback_match:
        metrics["fallback_count"] = int(fallback_match.group(1))
        
    winner_match = re.search(r"- winner: (\w+)", output)
    if winner_match:
        metrics["winner"] = winner_match.group(1)
        
    print(f"[DONE] Players={players}, Game {game_index+1}. Winner={metrics['winner']}, Duration={duration:.1f}s")
    return metrics

async def main():
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    
    async def sem_run(p, i):
        async with semaphore:
            return await run_single_game(p, i)
            
    tasks = []
    for p in PLAYER_COUNTS:
        for i in range(GAMES_PER_COUNT):
            tasks.append(sem_run(p, i))
            
    print(f"Starting parallel benchmark: {len(tasks)} total games, concurrency={CONCURRENCY_LIMIT}")
    results = await asyncio.gather(*tasks)
    
    # 汇总报表
    print("\n" + "="*60)
    print("ALPHA 1.0 PARALLEL BENCHMARK REPORT")
    print("="*60)
    
    header = "| Players | Index | Duration (s) | Actions | Tokens | Avg Token/Action | Fallbacks | Winner |"
    sep = "|---" * 8 + "|"
    print(header)
    print(sep)
    
    for r in sorted(results, key=lambda x: (x['players'], x['game_index'])):
        avg = r['total_tokens'] / max(1, r['action_count'])
        line = f"| {r['players']} | {r['game_index']} | {r['duration']:.1f} | {r['action_count']} | {r['total_tokens']} | {avg:.1f} | {r['fallback_count']} | {r['winner']} |"
        print(line)
        
    # 写入 Markdown
    with open("docs/alpha-1.0-parallel-benchmark.md", "w", encoding="utf-8") as f:
        f.write("# Alpha 1.0 并行压力测试报告 (8-10人局)\n\n")
        f.write(f"测试模型: Gemini 1.5 Flash (via Live Backend)\n\n")
        f.write(header + "\n")
        f.write(sep + "\n")
        for r in sorted(results, key=lambda x: (x['players'], x['game_index'])):
            avg = r['total_tokens'] / max(1, r['action_count'])
            line = f"| {r['players']} | {r['game_index']} | {r['duration']:.1f} | {r['action_count']} | {r['total_tokens']} | {avg:.1f} | {r['fallback_count']} | {r['winner']} |\n"
            f.write(line)
        f.write(f"\nGenerated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == "__main__":
    asyncio.run(main())
