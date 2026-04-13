#!/usr/bin/env python3
"""
Read prediction_monitor.log + prediction_tracking.json,
write signals.json, git commit + push to GitHub.
"""
import json, os, re, subprocess, time
from pathlib import Path
from datetime import datetime

HOME = Path.home()
LOG_FILE = HOME / ".hermes" / "prediction_monitor.log"
TRACKING_FILE = HOME / ".hermes" / "prediction_tracking.json"
OUTPUT_FILE = Path(__file__).parent / "signals.json"
MAX_HISTORY = 50

def parse_latest_signal():
    """Parse the latest signal block from the log."""
    if not LOG_FILE.exists():
        return None
    lines = LOG_FILE.read_text().splitlines()
    
    # Find last "🥞 Prediction Signal" block
    block_start = None
    for i in range(len(lines) - 1, -1, -1):
        if "🥞 Prediction Signal" in lines[i]:
            block_start = i
            break
    if block_start is None:
        return None
    
    block = lines[block_start:block_start + 20]
    text = "\n".join(block)
    
    # Parse epoch
    m = re.search(r"Epoch:\s*(\d+)", text)
    epoch = int(m.group(1)) if m else 0
    
    # Parse direction + confidence
    m = re.search(r"Signal:\s*(🟢|🔴)?(BULL|BEAR|SKIP)\s*\(信心:(\d+\.?\d*)\)", text)
    if m:
        direction = m.group(2)
        confidence = float(m.group(3))
    else:
        direction = "SKIP"
        confidence = 0
    
    # Parse pool
    m = re.search(r"当前池:\s*([\d.]+)\s*BNB", text)
    pool_total = float(m.group(1)) if m else 0
    m = re.search(r"BULL:\s*([\d.]+)", text)
    pool_bull = float(m.group(1)) if m else 0
    m = re.search(r"BEAR:\s*([\d.]+)", text)
    pool_bear = float(m.group(1)) if m else 0
    
    # Parse individual signals
    signals = []
    for line in block:
        m = re.match(r".*(⏰Time|🏊Pool|📈Mom|💥Liq|💰FR):(🟢|🔴|⚪)?\((\d+)\)\s*(.*)", line)
        if m:
            name_map = {"⏰Time": "Time", "🏊Pool": "Pool", "📈Mom": "Mom", "💥Liq": "Liq", "💰FR": "FR"}
            emoji_dir = {"🟢": "BULL", "🔴": "BEAR", "⚪": None}
            raw_name = m.group(1)
            name = name_map.get(raw_name, raw_name)
            dot = m.group(2)
            direction_s = emoji_dir.get(dot, None)
            score = int(m.group(3))
            info = m.group(4).strip()
            signals.append({"name": name, "direction": direction_s, "score": score, "info": info})
    
    # Parse time
    m = re.search(r"⏰\s*([\d:]+)\s*HKT", text)
    alert_time = m.group(1) if m else ""
    
    return {
        "epoch": epoch,
        "direction": direction,
        "confidence": confidence,
        "pool_total": pool_total,
        "pool_bull": pool_bull,
        "pool_bear": pool_bear,
        "signals": signals,
        "time": alert_time
    }


def parse_history():
    """Parse all signal blocks from the log for history."""
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text().splitlines()
    history = []
    
    for i, line in enumerate(lines):
        if "🥞 Prediction Signal" not in line:
            continue
        block = lines[i:i + 20]
        text = "\n".join(block)
        
        m = re.search(r"Epoch:\s*(\d+)", text)
        if not m:
            continue
        epoch = int(m.group(1))
        
        m = re.search(r"Signal:\s*(🟢|🔴)?(BULL|BEAR)\s*\(信心:(\d+\.?\d*)\)", text)
        if not m:
            continue
        direction = m.group(2)
        confidence = float(m.group(3))
        
        m = re.search(r"⏰\s*([\d:]+)\s*HKT", text)
        alert_time = m.group(1) if m else ""
        
        history.append({
            "epoch": epoch,
            "direction": direction,
            "confidence": confidence,
            "time": alert_time,
            "outcome": None
        })
    
    # Deduplicate by epoch (keep last)
    seen = {}
    for h in history:
        seen[h["epoch"]] = h
    history = sorted(seen.values(), key=lambda x: x["epoch"])
    
    # Merge with tracking results
    try:
        tracking = json.loads(TRACKING_FILE.read_text())
        preds = tracking.get("predictions", {})
        for h in history:
            pred = preds.get(str(h["epoch"]), {})
            if pred.get("outcome"):
                h["outcome"] = pred["outcome"]
            if pred.get("result"):
                h["result"] = pred["result"]
    except:
        pass
    
    return history[-MAX_HISTORY:]


def load_tracking():
    """Load tracking stats."""
    try:
        t = json.loads(TRACKING_FILE.read_text())
        return {
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "time_wins": t.get("time_wins", 0),
            "time_losses": t.get("time_losses", 0),
        }
    except:
        return {"wins": 0, "losses": 0, "time_wins": 0, "time_losses": 0}


def git_push():
    """Commit and push to GitHub."""
    repo_dir = str(Path(__file__).parent)
    try:
        subprocess.run(["git", "-C", repo_dir, "add", "signals.json"],
                       capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "-C", repo_dir, "diff", "--cached", "--quiet", "signals.json"],
            capture_output=True, timeout=10
        )
        if result.returncode == 0:
            return  # No changes
        subprocess.run(
            ["git", "-C", repo_dir, "commit", "-m", f"signal {datetime.now().strftime('%H:%M:%S')}"],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", repo_dir, "push", "--quiet"],
            capture_output=True, timeout=30
        )
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Pushed to GitHub")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Git error: {e}")


def main():
    current = parse_latest_signal()
    history = parse_history()
    tracking = load_tracking()
    
    data = {
        "current": current or {"epoch": 0, "direction": "SKIP", "confidence": 0,
                                "pool_total": 0, "pool_bull": 0, "pool_bear": 0,
                                "signals": [], "time": "--"},
        "history": history,
        "tracking": tracking,
        "updated": datetime.now().isoformat(),
    }
    
    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    git_push()


if __name__ == "__main__":
    main()
