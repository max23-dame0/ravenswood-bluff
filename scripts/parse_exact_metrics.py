import os
import json
import glob

def get_exact_metrics():
    session_files = glob.glob('data/sessions/*_20260430_*.jsonl')
    
    print("=" * 85)
    print(f"{'Game ID':<36} | {'Status':<10} | {'Players':<7} | {'Actions':<7} | {'Tokens':<8} | {'Winner':<8}")
    print("=" * 85)
    
    for file_path in sorted(session_files):
        game_id = os.path.basename(file_path).split('_')[0]
        status = "Interrupted"
        players = 0
        total_tokens = 0
        total_actions = 0
        winner = "N/A"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    event_type = data.get("event_type")
                    
                    if event_type == "game_started":
                        players = len(data.get("payload", {}).get("roles", {}))
                    
                    payload = data.get("payload", {})
                    
                    if "winning_team" in data:
                        status = "Completed"
                        winner = data.get("winning_team")
                    elif "winning_team" in payload:
                        status = "Completed"
                        winner = payload.get("winning_team")
                    
                    # Accumulate Tokens
                    usage = data.get("usage") or payload.get("usage")
                    if usage and "total_tokens" in usage:
                        total_tokens += usage.get("total_tokens", 0)
                        total_actions += 1
                        
                except Exception:
                    pass
        
        # If tokens were not found directly in event
        if total_tokens == 0:
            last_records = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        payload = data.get("payload", {})
                        if "ai_action_records" in payload:
                            last_records = payload["ai_action_records"]
                        elif "ai_action_records" in data:
                            last_records = data["ai_action_records"]
                    except Exception:
                        pass
            
            if last_records:
                total_tokens = sum(r.get("total_tokens", 0) for r in last_records)
                total_actions = len(last_records)
                    
        print(f"{game_id:<36} | {status:<10} | {players:<7} | {total_actions:<7} | {total_tokens:<8} | {winner:<8}")

if __name__ == "__main__":
    get_exact_metrics()
