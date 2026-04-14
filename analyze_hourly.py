#!/usr/bin/env python3
"""Hourly bull/bear analysis using fast batched JSON-RPC."""
import json, time, requests
from collections import defaultdict

RPC = 'https://bsc-dataseed.binance.org/'
CONTRACT = '0x18B2A687610328590Bc8F2e5fEdDe3b582A49cdA'

session = requests.Session()
session.headers.update({'Content-Type': 'application/json'})

def get_rounds_batch(epochs):
    batch = [{"jsonrpc":"2.0","method":"eth_call",
              "params":[{"to":CONTRACT,"data":"0x8c65c81f"+hex(e)[2:].zfill(64)},"latest"],"id":i}
             for i,e in enumerate(epochs)]
    try:
        r = session.post(RPC, json=batch, timeout=60)
        results = r.json() if isinstance(r.json(), list) else [r.json()]
        out = []
        for item in results:
            res = item.get('result','')
            if not res or res=='0x': out.append(None); continue
            h = res[2:]; f = []
            for j in range(0, min(len(h),1920), 64):
                v = int(h[j:j+64],16)
                if v >= 2**255: v -= 2**256
                f.append(v)
            if len(f)<10: out.append(None); continue
            out.append({'start_ts':f[1],'lock_p':f[4]/1e8,'close_p':f[5]/1e8})
        return out
    except Exception as e:
        print(f"  Batch err: {e}", flush=True)
        return [None]*len(epochs)

def get_round(epoch):
    r = get_rounds_batch([epoch])
    return r[0] if r else None

# Binary search
print("Finding epoch range...", flush=True)
def find_epoch(target_ts, lo, hi):
    while hi - lo > 1:
        mid = (lo+hi)//2
        rd = get_round(mid)
        if rd and rd['start_ts'] < target_ts: lo = mid
        else: hi = mid
    return hi

start_epoch = find_epoch(1767196800, 440000, 472500)  # Jan 1 00:00 HKT
rd_s = get_round(start_epoch)
print(f"Start: epoch {start_epoch} = {time.strftime('%Y-%m-%d %H:%M HKT', time.gmtime(rd_s['start_ts']+28800))}", flush=True)

end_epoch = find_epoch(1776160800, start_epoch, 472500)  # Apr 14 11:00 HKT
rd_e = get_round(end_epoch)
print(f"End: epoch {end_epoch} = {time.strftime('%Y-%m-%d %H:%M HKT', time.gmtime(rd_e['start_ts']+28800))}", flush=True)
print(f"Total: {end_epoch - start_epoch} epochs", flush=True)

# Fetch all in batches of 50
hourly = defaultdict(lambda:{'bull':0,'bear':0,'total':0})
valid = 0
batch_size = 20
all_epochs = list(range(start_epoch, end_epoch+1))
t0 = time.time()

for bs in range(0, len(all_epochs), batch_size):
    batch = all_epochs[bs:bs+batch_size]
    rounds = get_rounds_batch(batch)
    for rd in rounds:
        if not rd or rd['close_p']==0 or rd['lock_p']==0: continue
        hkt = rd['start_ts'] + 28800
        hour = (hkt % 86400) // 3600
        if rd['close_p'] > rd['lock_p']: hourly[hour]['bull'] += 1
        elif rd['close_p'] < rd['lock_p']: hourly[hour]['bear'] += 1
        else: continue
        hourly[hour]['total'] += 1
        valid += 1
    done = min(bs+batch_size, len(all_epochs))
    if done % 500 == 0 or done == len(all_epochs):
        elapsed = time.time()-t0
        rate = done/elapsed
        print(f"  {done}/{len(all_epochs)} ({valid} valid) {rate:.0f}/s ETA:{(len(all_epochs)-done)/rate:.0f}s", flush=True)

elapsed = time.time()-t0
print(f"\nDone in {elapsed:.0f}s", flush=True)

# Results
print(f"\n{'='*65}", flush=True)
print(f"  BNB Prediction 每小时涨跌分布 (HKT)", flush=True)
print(f"  2026-01-01 ~ 2026-04-14 | 共 {valid} 轮", flush=True)
print(f"{'='*65}", flush=True)
print(f"{'时段':>8s} | {'涨🟢':>5s} | {'跌🔴':>5s} | {'总':>5s} | {'涨概率':>6s} | {'跌概率':>6s}", flush=True)
print(f"{'-'*65}", flush=True)
for h in range(24):
    d = hourly[h]; t = d['total']
    if t==0:
        print(f"  {h:02d}:00  |  --  |  --  |  --  |  --   |  --  ", flush=True); continue
    bp = d['bull']/t*100; rp = d['bear']/t*100
    e = '🟢' if bp>52 else '🔴' if rp>52 else '⚪'
    print(f"{e} {h:02d}:00  | {d['bull']:>5d} | {d['bear']:>5d} | {t:>5d} | {bp:>5.1f}% | {rp:>5.1f}%", flush=True)
print(f"{'-'*65}", flush=True)
tb=sum(d['bull'] for d in hourly.values()); tr=sum(d['bear'] for d in hourly.values()); tt=sum(d['total'] for d in hourly.values())
if tt > 0:
    print(f"📊 合计   | {tb:>5d} | {tr:>5d} | {tt:>5d} | {tb/tt*100:>5.1f}% | {tr/tt*100:>5.1f}%", flush=True)

json.dump({'total':valid,'range':'2026-01-01 ~ 2026-04-14','hourly':{str(h):dict(hourly[h]) for h in range(24)}},
    open('/home/cowbike/prediction-signals/hourly_analysis.json','w'), indent=2, ensure_ascii=False)
print("Saved hourly_analysis.json", flush=True)
