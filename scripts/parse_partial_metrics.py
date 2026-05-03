import os
import json
import glob
from collections import defaultdict
from datetime import datetime

def parse_sessions():
    session_files = glob.glob('data/sessions/*_20260430_*.jsonl')
    
    print(f"找到了 {len(session_files)} 个在今天 (4/30) 运行的测试对局文件。")
    print("-" * 75)
    print(f"{'Game ID':<36} | {'Status':<10} | {'Players':<7} | {'Tokens':<8} | {'Actions':<7} | {'Fallbacks':<9}")
    print("-" * 75)
    
    total_tokens = 0
    total_actions = 0
    total_fallbacks = 0
    total_games = 0
    
    for file_path in sorted(session_files):
        players = 0
        actions = 0
        tokens = 0
        fallbacks = 0
        game_id = os.path.basename(file_path).split('_')[0]
        max_day = 0
        status = "Interrupted"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get("event_type") == "game_started":
                        players = len(data.get("payload", {}).get("roles", {}))
                    if data.get("event_type") == "game_over":
                        status = "Completed"
                    
                    if data.get("day_number"):
                        max_day = max(max_day, data.get("day_number"))
                        
                    # Some session structures store token metrics in ai_action_metrics format
                    if "payload" in data and "usage" in data["payload"]:
                        # Might be mixed
                        pass
                except Exception:
                    pass
        
        # In our implementation, usage metrics are not directly saved to jsonl event_type
        # But we can estimate tokens based on file size if needed, OR 
        # since we just terminated the parallel benchmark, the `simulate_game.py` outputs
        # were not cleanly captured. However, the orchestrator_run.log has the records!
        
        size_kb = os.path.getsize(file_path) / 1024
        
        # Estimate: A typical 5 player game is 60k tokens and 264KB. 
        # Token to KB ratio: 60000 / 264 = ~227 tokens per KB
        # This is a rough estimation for uncompleted games
        est_tokens = int(size_kb * 227)
        total_tokens += est_tokens
        total_games += 1
        
        print(f"{game_id:<36} | {status:<10} | {players:<7} | {est_tokens:<8} | {'N/A':<7} | {'N/A':<9}")

    print("-" * 75)
    print(f"Total Games: {total_games}")
    print(f"Total Estimated Tokens: ~{total_tokens:,}")

if __name__ == "__main__":
    parse_sessions()
