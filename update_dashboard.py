#!/usr/bin/env python3
"""
Read prediction_monitor.log + prediction_tracking.json,
write signals.json, git commit + push to GitHub.
"""
import json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path
from datetime import datetime, timedelta

HOME = Path.home()
LOG_FILE = HOME / ".hermes" / "prediction_monitor.log"
TRACKING_FILE = HOME / ".hermes" / "prediction_tracking.json"
OUTPUT_FILE = Path(__file__).parent / "signals.json"
MAX_HISTORY = 1000

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
    trend_info = None
    for line in block:
        m = re.match(r".*(⏰Time|🏊Pool|📈Mom|💥Liq|💰FR):([🟢🔴⚪]?)\((\d+)\)\s*(.*)", line)
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
        m2 = re.search(r"⚠️Trend:\s*(.*)", line)
        if m2:
            trend_info = m2.group(1).strip()
    
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
        "trend": trend_info,
        "time": alert_time
    }


def parse_history():
    """Parse latest signal blocks from the log (from end)."""
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text().splitlines()
    history = []

    # Scan from end, collect signal blocks
    i = len(lines) - 1
    while i >= 0 and len(history) < MAX_HISTORY + 20:
        if "\U0001f95e Pancake Prediction Signal" not in lines[i] and "🥞 Prediction Signal" not in lines[i]:
            i -= 1
            continue
        block = lines[i:i + 20]
        text = "\n".join(block)

        m = re.search(r"Epoch:\s*(\d+)", text)
        if not m:
            i -= 1
            continue
        epoch = int(m.group(1))

        m = re.search(r"Signal:\s*(🟢|🔴|⚪)?(BULL|BEAR|SKIP)\s*\(信心:(\d+\.?\d*)\)", text)
        if not m:
            i -= 1
            continue
        direction = m.group(2)
        confidence = float(m.group(3))

        m = re.search(r"⏰\s*([\d:]+)\s*HKT", text)
        alert_time = m.group(1) if m else ""

        # Compute full datetime for 24h filtering
        time_full = None
        if alert_time:
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                alert_hour = int(alert_time.split(":")[0])
                current_hour = datetime.now().hour
                # Cross-midnight fix: if current hour is early (0-2) and alert is late (22-23), it's yesterday
                if current_hour < 3 and alert_hour >= 22:
                    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    time_full = f"{yesterday} {alert_time}"
                else:
                    time_full = f"{today} {alert_time}"
            except:
                pass

        trend_info = None
        m2 = re.search(r"⚠️Trend:\s*(.*)", text)
        if m2:
            trend_info = m2.group(1).strip()

        history.append({
            "epoch": epoch,
            "direction": direction,
            "confidence": confidence,
            "time": alert_time,
            "time_full": time_full,
            "trend": trend_info if trend_info else None,
            "outcome": None
        })
        i -= 1

    # Reverse so oldest first
    history.reverse()

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

    # On-chain fallback: fetch results for entries still missing result (limit to 50)
    try:
        sys.path.insert(0, str(HOME))
        from prediction_monitor import get_round
        checked = 0
        for h in history:
            if h.get("result") or checked >= 200:
                continue
            rd = get_round(h["epoch"])
            if not rd or rd.get("close_p", 0) == 0 or rd.get("lock_p", 0) == 0:
                continue
            winner = "BULL" if rd["close_p"] > rd["lock_p"] else "BEAR" if rd["close_p"] < rd["lock_p"] else "TIE"
            h["result"] = winner
            if winner == h["direction"]:
                h["outcome"] = "WIN"
            elif winner == "TIE":
                h["outcome"] = "TIE"
            else:
                h["outcome"] = "LOSS"
            checked += 1
    except Exception as e:
        print(f"On-chain check error: {e}")

    return history[-MAX_HISTORY:]

def compute_hourly_stats(history):
    """Compute current hour interval stats from history for the dashboard hourly-live section."""
    now = datetime.now()
    hkt_offset = timedelta(hours=8)
    hkt_now = now + hkt_offset
    current_hour = hkt_now.hour
    
    # Find the latest hour that has data (may be current or previous)
    latest_hour = None
    for h in reversed(history):
        t_str = h.get("time", "")
        if not t_str:
            continue
        try:
            hour = int(t_str.split(":")[0])
            # Verify same day
            t_full = h.get("time_full")
            if t_full:
                ts = datetime.fromisoformat(t_full)
                ts_hkt = ts + hkt_offset
                if ts_hkt.date() != hkt_now.date():
                    continue
            latest_hour = hour
            break
        except:
            continue
    
    if latest_hour is None:
        return {"hour": current_hour, "bull": 0, "bear": 0, "skip": 0, "total": 0}
    
    bull = 0
    bear = 0
    skip = 0
    total = 0
    
    for h in history:
        t_str = h.get("time", "")
        if not t_str:
            continue
        try:
            hour = int(t_str.split(":")[0])
            if hour != latest_hour:
                continue
        except:
            continue
        
        # Verify same day
        t_full = h.get("time_full")
        if t_full:
            try:
                ts = datetime.fromisoformat(t_full)
                ts_hkt = ts + hkt_offset
                if ts_hkt.date() != hkt_now.date():
                    continue
            except:
                continue
        
        total += 1
        direction = h.get("direction", "")
        if direction == "BULL":
            bull += 1
        elif direction == "BEAR":
            bear += 1
        elif direction == "SKIP":
            skip += 1
    
    return {
        "hour": latest_hour,
        "bull": bull,
        "bear": bear,
        "skip": skip,
        "total": total,
    }


def load_tracking(history=None):
    """Load tracking stats, enriched with 24h and hourly stats from history."""
    base = {"wins": 0, "losses": 0, "skips": 0,
            "time_wins": 0, "time_losses": 0,
            "win_rate_24h": 50.0, "total_24h": 0,
            "hourly_wins": {}, "hourly_losses": {},
            "tracking_win_rate_24h": 50.0, "tracking_total_24h": 0}
    try:
        t = json.loads(TRACKING_FILE.read_text())
        base.update({
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "skips": t.get("skips", 0),
            "time_wins": t.get("time_wins", 0),
            "time_losses": t.get("time_losses", 0),
        })
    except:
        pass

    # Compute 24h stats and hourly distribution from history
    if history:
        now = datetime.now()
        cutoff = now - timedelta(hours=24)
        wins_24h = 0
        losses_24h = 0
        hourly_wins = {}
        hourly_losses = {}
        for h in history:
            if not h.get("outcome"):
                continue
            # Hourly distribution (all time)
            t_str = h.get("time", "")
            if t_str:
                try:
                    hour = int(t_str.split(":")[0])
                    hour_key = str(hour)
                    if h["outcome"] == "WIN":
                        hourly_wins[hour_key] = hourly_wins.get(hour_key, 0) + 1
                    elif h["outcome"] == "LOSS":
                        hourly_losses[hour_key] = hourly_losses.get(hour_key, 0) + 1
                except:
                    pass
            # 24h stats
            t_full = h.get("time_full")
            if t_full:
                try:
                    ts = datetime.fromisoformat(t_full)
                    if ts >= cutoff:
                        if h["outcome"] == "WIN":
                            wins_24h += 1
                        elif h["outcome"] == "LOSS":
                            losses_24h += 1
                except:
                    pass
        total_24h = wins_24h + losses_24h
        base["win_rate_24h"] = round(wins_24h / total_24h * 100, 1) if total_24h > 0 else 50.0
        base["total_24h"] = total_24h
        base["hourly_wins"] = hourly_wins
        base["hourly_losses"] = hourly_losses

        # Tracking file 24h (for comparison)
        if total_24h > 0:
            base["tracking_win_rate_24h"] = base["win_rate_24h"]
            base["tracking_total_24h"] = total_24h

    return base


def update_tracking_results():
    """Check on-chain results for tracking predictions missing outcome, update tracking file."""
    try:
        t = json.loads(TRACKING_FILE.read_text())
    except:
        return
    
    preds = t.get("predictions", {})
    if not preds:
        return
    
    sys.path.insert(0, str(HOME))
    from prediction_monitor import get_round
    
    updated = False
    for epoch_str, pred in preds.items():
        if pred.get("result"):
            continue
        try:
            rd = get_round(int(epoch_str))
            if not rd or rd.get("close_p", 0) == 0 or rd.get("lock_p", 0) == 0:
                continue
            winner = "BULL" if rd["close_p"] > rd["lock_p"] else "BEAR" if rd["close_p"] < rd["lock_p"] else "TIE"
            pred["result"] = winner
            direction = pred.get("direction", "")
            if direction == "SKIP":
                # SKIP 不計入勝率，只標記結果
                pred["outcome"] = "SKIP"
            elif winner == direction:
                pred["outcome"] = "WIN"
            elif winner == "TIE":
                pred["outcome"] = "TIE"
            else:
                pred["outcome"] = "LOSS"
            updated = True
        except:
            continue
    
    if not updated:
        return
    
    # Recompute win/loss counts (exclude SKIP)
    wins = sum(1 for p in preds.values() if p.get("outcome") == "WIN")
    losses = sum(1 for p in preds.values() if p.get("outcome") == "LOSS")
    skips = sum(1 for p in preds.values() if p.get("outcome") == "SKIP")
    t["wins"] = wins
    t["losses"] = losses
    t["skips"] = skips
    
    TRACKING_FILE.write_text(json.dumps(t, ensure_ascii=False))
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Updated tracking: {wins}W/{losses}L")


def fetch_bnb_price():
    """Fetch BNB/USDT price from Binance."""
    try:
        req = urllib.request.Request(
            'https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT',
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return round(float(data['price']), 2)
    except:
        return None


def fetch_bnb_kline():
    """Fetch on-chain-derived kline from cache, fallback to Binance API."""
    # Try chain-derived kline first (PCSP-time-aligned)
    try:
        cache_file = HOME / ".hermes" / "kline_cache.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            if data and len(data) > 0:
                return data  # [{timestamp, open, high, low, close}, ...]
    except Exception as e:
        print(f"Kline cache read error: {e}")

    # Fallback: Binance 5m candles (for initial display before daemon has cache)
    try:
        url = 'https://api.binance.com/api/v3/klines?symbol=BNBUSDT&interval=5m&limit=60'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read())
        return [{'timestamp': k[0] / 1000, 'open': float(k[1]), 'high': float(k[2]),
                 'low': float(k[3]), 'close': float(k[4])} for k in raw]
    except Exception as e:
        print(f"Failed to fetch kline: {e}")
        return None


def git_push():
    """Commit and push to GitHub."""
    repo_dir = str(Path(__file__).parent)
    try:
        # Pull latest first to avoid non-fast-forward rejection
        subprocess.run(["git", "-C", repo_dir, "pull", "--rebase", "--quiet"],
                       capture_output=True, timeout=30)
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


def backfill_history_odds():
    """Fill win_odds for history entries that don't have it yet (one-time backfill)."""
    if not OUTPUT_FILE.exists():
        return
    try:
        data = json.loads(OUTPUT_FILE.read_text())
        hist = data.get("history", [])
        missing = [h for h in hist if h.get("result") and h.get("result") != "TIE" and "win_odds" not in h]
        if not missing:
            return
        sys.path.insert(0, str(HOME))
        from prediction_monitor import get_round
        filled = 0
        for h in missing:
            try:
                rd = get_round(h["epoch"])
                if not rd or rd.get("total", 0) == 0:
                    continue
                winner = h["result"]
                if winner == "BULL" and rd.get("bull", 0) > 0:
                    h["win_odds"] = round(rd["total"] * 0.97 / rd["bull"], 1)
                    filled += 1
                elif winner == "BEAR" and rd.get("bear", 0) > 0:
                    h["win_odds"] = round(rd["total"] * 0.97 / rd["bear"], 1)
                    filled += 1
            except:
                pass
        if filled > 0:
            data["history"] = hist
            OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Backfilled win_odds for {filled}/{len(missing)} history entries")
    except Exception as e:
        print(f"backfill_history_odds error: {e}")


def main():
    # First update tracking results from on-chain
    update_tracking_results()

    # Backfill win_odds for existing history entries
    backfill_history_odds()

    current = parse_latest_signal()
    history = parse_history()
    tracking = load_tracking(history)

    # Fetch on-chain round data for lock_ts
    lock_ts = 0
    current_epoch = 0
    if current and current.get("epoch"):
        current_epoch = current["epoch"]
        try:
            sys.path.insert(0, str(HOME))
            from prediction_monitor import get_round
            rd = get_round(current_epoch)
            if rd:
                lock_ts = rd.get("lock_ts", 0)
        except Exception as e:
            print(f" lock_ts fetch error: {e}")

    # Compute hourly stats from history
    hourly_stats = compute_hourly_stats(history)

    # Don't overwrite daemon's live signal if it's newer
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text())
            existing_epoch = existing.get("current", {}).get("epoch", 0)
            new_epoch = (current or {}).get("epoch", 0)
            if existing_epoch > new_epoch:
                # Daemon has newer signal — keep it, only update tracking/history
                existing["history"] = history
                existing["tracking"] = tracking
                existing["bnb_price"] = fetch_bnb_price()
                existing["kline"] = fetch_bnb_kline()
                existing["hourly_stats"] = hourly_stats
                existing["updated"] = datetime.now().isoformat()
                OUTPUT_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
                print(f" Kept daemon signal E{existing_epoch} (cron had E{new_epoch})")
                git_push()
                return
        except:
            pass

    data = {
        "current": current or {"epoch": 0, "direction": "SKIP", "confidence": 0,
                               "pool_total": 0, "pool_bull": 0, "pool_bear": 0,
                               "signals": [], "time": "--"},
        "lock_ts": lock_ts,
        "current_ts": int(time.time()),
        "history": history,
        "tracking": tracking,
        "hourly_stats": hourly_stats,
        "bnb_price": fetch_bnb_price(),
        "kline": fetch_bnb_kline(),
        "updated": datetime.now().isoformat(),
    }

    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    git_push()


if __name__ == "__main__":
    main()
