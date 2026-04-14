#!/usr/bin/env python3
"""
Analyze PancakeSwap BNB Prediction hourly BULL/BEAR distribution.
Jan 1 2026 00:00 HKT to Apr 14 2026 11:00 HKT.
Uses parallel curl for fast batch fetching.
"""
import json, subprocess, sys, os, time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

CONTRACT = "0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA"
RPC_SERVERS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.binance.org/",
    "https://bsc-dataseed2.binance.org/",
    "https://bsc-dataseed3.binance.org/",
]
HKT = timezone(timedelta(hours=8))
TARGET_TS = 1767196800  # Jan 1 2026 00:00 HKT
END_TS = int(datetime(2026, 4, 14, 11, 0, tzinfo=HKT).timestamp())

def log(msg):
    print(msg, flush=True)

def rpc_call(rpc_url, method, params):
    try:
        payload = json.dumps({"jsonrpc":"2.0","method":method,"params":params,"id":1})
        r = subprocess.run(['curl','-s','--max-time','10',
            '-H','Content-Type:application/json','-d',payload,rpc_url],
            capture_output=True, text=True, timeout=12)
        data = json.loads(r.stdout)
        if 'result' in data and data['result'] and data['result'] != '0x':
            return data['result']
    except:
        pass
    return None

def parse_round(result_hex, epoch):
    if not result_hex:
        return None
    h = result_hex[2:]
    f = []
    for i in range(0, min(len(h), 1920), 64):
        v = int(h[i:i+64], 16)
        if v >= 2**255:
            v -= 2**256
        f.append(v)
    if len(f) < 6:
        return None
    lock_ts = f[2]
    lock_p = f[4] / 1e8
    close_p = f[5] / 1e8
    if close_p > lock_p:
        winner = 'BULL'
    elif close_p < lock_p:
        winner = 'BEAR'
    else:
        winner = 'TIE'
    return {'epoch': epoch, 'lock_ts': lock_ts, 'lock_p': lock_p, 'close_p': close_p, 'winner': winner}

def get_epoch():
    result = rpc_call(RPC_SERVERS[0], "eth_call", [{"to":CONTRACT,"data":"0x76671808"},"latest"])
    if result:
        return int(result, 16)
    return None

def get_lock_ts(epoch, rpc_url):
    calldata = "0x8c65c81f" + hex(epoch)[2:].zfill(64)
    result = rpc_call(rpc_url, "eth_call", [{"to":CONTRACT,"data":calldata},"latest"])
    if result and len(result) >= 2 + 192:
        h = result[2:]
        v = int(h[128:192], 16)
        if v >= 2**255:
            v -= 2**256
        return v
    return None

def fetch_batch_parallel(epoch_batch, rpc_url):
    """Fetch a batch of epochs using parallel curl."""
    results = []
    
    # Build all requests as JSON-RPC calls
    requests = []
    for epoch in epoch_batch:
        calldata = "0x8c65c81f" + hex(epoch)[2:].zfill(64)
        req = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":CONTRACT,"data":calldata},"latest"],"id":epoch})
        requests.append((epoch, req))
    
    # Use xargs for parallel curl
    # Write all request payloads to a temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        for epoch, req in requests:
            f.write(f"{epoch}\t{req}\n")
        tmpfile = f.name
    
    # Use GNU parallel or xargs to send requests
    # Actually, let's just use ThreadPoolExecutor for parallel curl
    def do_curl(args):
        epoch, req = args
        try:
            r = subprocess.run(['curl','-s','--max-time','10',
                '-H','Content-Type:application/json','-d',req,rpc_url],
                capture_output=True, text=True, timeout=12)
            data = json.loads(r.stdout)
            if 'result' in data and data['result'] and data['result'] != '0x':
                return parse_round(data['result'], epoch)
        except:
            pass
        return None
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        for rd in executor.map(do_curl, requests):
            if rd:
                results.append(rd)
    
    os.unlink(tmpfile)
    return results

def main():
    start_time = time.time()
    
    # STEP 1: Get current epoch
    log("[STEP 1] Getting current epoch...")
    current = get_epoch()
    log(f"  Current epoch: {current}")
    
    # Get reference round
    rd_ref = None
    for offset in range(1, 10):
        calldata = "0x8c65c81f" + hex(current - offset)[2:].zfill(64)
        result = rpc_call(RPC_SERVERS[0], "eth_call", [{"to":CONTRACT,"data":calldata},"latest"])
        if result:
            rd_ref = parse_round(result, current - offset)
            if rd_ref:
                break
    
    log(f"  Reference: epoch {rd_ref['epoch']}, lock_ts={rd_ref['lock_ts']} ({datetime.fromtimestamp(rd_ref['lock_ts'], tz=HKT).strftime('%Y-%m-%d %H:%M HKT')})")
    
    # Binary search for start epoch
    est_epoch = rd_ref['epoch'] - (rd_ref['lock_ts'] - TARGET_TS) // 300
    log(f"  Estimated start epoch: {est_epoch}")
    
    rpc_url = RPC_SERVERS[0]
    lo, hi = max(1, est_epoch - 300), min(current, est_epoch + 300)
    
    # Widen if needed
    lock_lo = get_lock_ts(lo, rpc_url)
    if lock_lo and lock_lo > TARGET_TS:
        while lock_lo and lock_lo > TARGET_TS and lo > 1000:
            lo = max(1, lo - 500)
            lock_lo = get_lock_ts(lo, rpc_url)
    
    best_epoch = est_epoch
    best_diff = float('inf')
    
    for _ in range(50):
        mid = (lo + hi) // 2
        lock_mid = get_lock_ts(mid, rpc_url)
        if lock_mid is None:
            for off in [1, -1, 2, -2]:
                lock_mid = get_lock_ts(mid + off, rpc_url)
                if lock_mid:
                    mid = mid + off
                    break
            if lock_mid is None:
                break
        
        diff = abs(lock_mid - TARGET_TS)
        if diff < best_diff:
            best_diff = diff
            best_epoch = mid
        
        if lock_mid < TARGET_TS:
            lo = mid + 1
        else:
            hi = mid - 1
        if lo > hi:
            break
    
    for off in range(-10, 11):
        c = best_epoch + off
        if c < 1 or c > current:
            continue
        lc = get_lock_ts(c, rpc_url)
        if lc:
            d = abs(lc - TARGET_TS)
            if d < best_diff:
                best_diff = d
                best_epoch = c
    
    start_epoch = best_epoch
    log(f"  Start epoch: {start_epoch}, lock_ts={get_lock_ts(start_epoch, rpc_url)} ({datetime.fromtimestamp(get_lock_ts(start_epoch, rpc_url), tz=HKT).strftime('%Y-%m-%d %H:%M HKT')})")
    
    # Binary search for end epoch
    lo, hi = start_epoch, current
    end_epoch = start_epoch
    
    for _ in range(50):
        mid = (lo + hi) // 2
        lock_mid = get_lock_ts(mid, rpc_url)
        if lock_mid is None:
            break
        if lock_mid <= END_TS:
            lo = mid + 1
        else:
            hi = mid - 1
        if lo > hi:
            break
    
    end_epoch = hi
    for off in range(-10, 11):
        c = end_epoch + off
        if c < start_epoch or c > current:
            continue
        lc = get_lock_ts(c, rpc_url)
        if lc and lc <= END_TS:
            end_epoch = c
    
    log(f"  End epoch: {end_epoch}, lock_ts={get_lock_ts(end_epoch, rpc_url)} ({datetime.fromtimestamp(get_lock_ts(end_epoch, rpc_url), tz=HKT).strftime('%Y-%m-%d %H:%M HKT')})")
    
    total_epochs = end_epoch - start_epoch + 1
    log(f"\n[STEP 2] Fetching {total_epochs} rounds...")
    
    epoch_list = list(range(start_epoch, end_epoch + 1))
    
    # Split into batches and distribute across RPC servers with parallel curl
    batch_size = 50
    num_parallel = 32  # parallel curl requests per batch
    
    all_rounds = []
    total_batches = (len(epoch_list) + batch_size - 1) // batch_size
    
    log(f"  {total_batches} batches of {batch_size}, {num_parallel} parallel curls")
    
    def fetch_single(args):
        epoch, rpc = args
        calldata = "0x8c65c81f" + hex(epoch)[2:].zfill(64)
        try:
            payload = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":CONTRACT,"data":calldata},"latest"],"id":1})
            r = subprocess.run(['curl','-s','--max-time','12',
                '-H','Content-Type:application/json','-d',payload,rpc],
                capture_output=True, text=True, timeout=15)
            data = json.loads(r.stdout)
            if 'result' in data and data['result'] and data['result'] != '0x':
                return parse_round(data['result'], epoch)
        except:
            pass
        return None
    
    # Build all (epoch, rpc) pairs
    tasks = []
    for i, ep in enumerate(epoch_list):
        rpc = RPC_SERVERS[i % len(RPC_SERVERS)]
        tasks.append((ep, rpc))
    
    completed = 0
    with ThreadPoolExecutor(max_workers=num_parallel) as executor:
        futures = {executor.submit(fetch_single, t): t[0] for t in tasks}
        for future in as_completed(futures):
            rd = future.result()
            if rd:
                all_rounds.append(rd)
            completed += 1
            if completed % 500 == 0 or completed == len(tasks):
                pct = completed / len(tasks) * 100
                log(f"  Progress: {completed}/{len(tasks)} ({pct:.1f}%) - {len(all_rounds)} valid rounds")
    
    # Sort and filter
    all_rounds.sort(key=lambda x: x['epoch'])
    
    valid_rounds = []
    for rd in all_rounds:
        if rd['lock_ts'] < TARGET_TS or rd['lock_ts'] > END_TS:
            continue
        if rd['winner'] == 'TIE':
            continue
        valid_rounds.append(rd)
    
    log(f"\n[STEP 3] Valid rounds: {len(valid_rounds)} (excl. TIEs)")
    
    # Group by HKT hour
    hourly = {h: {'bull': 0, 'bear': 0} for h in range(24)}
    
    for rd in valid_rounds:
        hour = datetime.fromtimestamp(rd['lock_ts'], tz=HKT).hour
        if rd['winner'] == 'BULL':
            hourly[hour]['bull'] += 1
        else:
            hourly[hour]['bear'] += 1
    
    total_bull = sum(h['bull'] for h in hourly.values())
    total_bear = sum(h['bear'] for h in hourly.values())
    total_all = total_bull + total_bear
    overall_bull_pct = total_bull / total_all * 100 if total_all > 0 else 0
    overall_bear_pct = total_bear / total_all * 100 if total_all > 0 else 0
    
    # Print table
    log(f"\n{'='*70}")
    log(f"  PancakeSwap BNB Prediction - Hourly BULL/BEAR Distribution")
    log(f"  Period: Jan 1 2026 00:00 HKT to Apr 14 2026 11:00 HKT")
    log(f"  Total rounds: {total_all}")
    log(f"{'='*70}")
    log(f"  {'Hour':>4}  {'BULL':>6}  {'BEAR':>6}  {'BULL%':>7}  {'BEAR%':>7}")
    log(f"  {'-'*4}  {'-'*6}  {'-'*6}  {'-'*7}  {'-'*7}")
    
    hourly_output = []
    for h in range(24):
        b = hourly[h]['bull']
        r = hourly[h]['bear']
        t = b + r
        bp = b / t * 100 if t > 0 else 0
        rp = r / t * 100 if t > 0 else 0
        log(f"  {h:>4}  {b:>6}  {r:>6}  {bp:>6.1f}%  {rp:>6.1f}%")
        hourly_output.append({
            "hour": h, "bull": b, "bear": r,
            "bull_pct": round(bp, 1), "bear_pct": round(rp, 1)
        })
    
    log(f"  {'-'*4}  {'-'*6}  {'-'*6}  {'-'*7}  {'-'*7}")
    log(f"  {'ALL':>4}  {total_bull:>6}  {total_bear:>6}  {overall_bull_pct:>6.1f}%  {overall_bear_pct:>6.1f}%")
    log(f"{'='*70}")
    
    # Save JSON
    start_lock = get_lock_ts(start_epoch, RPC_SERVERS[0])
    end_lock = get_lock_ts(end_epoch, RPC_SERVERS[0])
    start_dt = datetime.fromtimestamp(start_lock if start_lock else TARGET_TS, tz=HKT)
    end_dt = datetime.fromtimestamp(end_lock if end_lock else END_TS, tz=HKT)
    
    output = {
        "period": {
            "start": start_dt.strftime("%Y-%m-%d %H:%M HKT"),
            "end": end_dt.strftime("%Y-%m-%d %H:%M HKT")
        },
        "total_rounds": total_all,
        "overall": {
            "bull_pct": round(overall_bull_pct, 1),
            "bear_pct": round(overall_bear_pct, 1)
        },
        "hourly": hourly_output
    }
    
    os.makedirs("/home/cowbike/prediction-signals", exist_ok=True)
    out_path = "/home/cowbike/prediction-signals/hourly_analysis.json"
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    elapsed = time.time() - start_time
    log(f"\nSaved to {out_path}")
    log(f"Completed in {elapsed:.1f}s")

if __name__ == "__main__":
    main()
