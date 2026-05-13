#!/usr/bin/env python3
"""
OKX Market Data Integration
Provides real-time crypto market data for prediction signals and monitoring.
No auth required — public OKX V5 API.
"""

import requests
import json
from datetime import datetime
from typing import Optional

BASE_URL = "https://www.okx.com/api/v5"

# ── Ticker ──────────────────────────────────────────────────────────────
def get_ticker(inst_id: str) -> Optional[dict]:
    """Get real-time ticker for a single instrument."""
    try:
        resp = requests.get(f"{BASE_URL}/market/ticker", params={"instId": inst_id}, timeout=5)
        data = resp.json()
        if data["code"] != "0":
            return None
        t = data["data"][0]
        last = float(t["last"])
        open24h = float(t["open24h"])
        high24h = float(t["high24h"])
        low24h = float(t["low24h"])
        vol24h = float(t["vol24h"])
        volCcy24h = float(t["volCcy24h"])
        chg = (last / open24h - 1) * 100
        return {
            "instId": inst_id,
            "last": last,
            "open24h": open24h,
            "high24h": high24h,
            "low24h": low24h,
            "change24h": round(chg, 2),
            "vol24h": vol24h,
            "volCcy24h": volCcy24h,
            "ts": datetime.fromtimestamp(int(t["ts"]) / 1000).strftime("%H:%M:%S"),
        }
    except Exception as e:
        print(f"[okx-market] ticker error {inst_id}: {e}")
        return None


# ── Funding Rate ────────────────────────────────────────────────────────
def get_funding_rate(inst_id: str) -> Optional[dict]:
    """Get current funding rate for a perpetual swap."""
    try:
        resp = requests.get(f"{BASE_URL}/public/funding-rate", params={"instId": inst_id}, timeout=5)
        data = resp.json()
        if data["code"] != "0":
            return None
        d = data["data"][0]
        rate = float(d["fundingRate"])
        annual = rate * 3 * 365 * 100
        next_time = datetime.fromtimestamp(int(d["fundingTime"]) / 1000)
        return {
            "instId": inst_id,
            "fundingRate": rate,
            "fundingPct": round(rate * 100, 4),
            "annualized": round(annual, 2),
            "nextSettle": next_time.strftime("%H:%M"),
            "nextRate": float(d.get("nextFundingRate", 0) or 0),
        }
    except Exception as e:
        print(f"[okx-market] funding error {inst_id}: {e}")
        return None


# ── Open Interest ───────────────────────────────────────────────────────
def get_open_interest(inst_id: str) -> Optional[dict]:
    """Get open interest for a perpetual swap."""
    try:
        resp = requests.get(f"{BASE_URL}/public/open-interest", params={"instId": inst_id}, timeout=5)
        data = resp.json()
        if data["code"] != "0":
            return None
        d = data["data"][0]
        oi = float(d["oi"])
        oiCcy = float(d["oiCcy"])
        return {
            "instId": inst_id,
            "oi": oi,
            "oiCcy": oiCcy,
            "ts": datetime.fromtimestamp(int(d["ts"]) / 1000).strftime("%H:%M:%S"),
        }
    except Exception as e:
        print(f"[okx-market] oi error {inst_id}: {e}")
        return None


# ── Candles ─────────────────────────────────────────────────────────────
def get_candles(inst_id: str, bar: str = "5m", limit: int = 30) -> Optional[list]:
    """Get candlestick data. Returns list of {ts, o, h, l, c, vol}."""
    try:
        resp = requests.get(f"{BASE_URL}/market/candles", params={
            "instId": inst_id, "bar": bar, "limit": str(limit)
        }, timeout=5)
        data = resp.json()
        if data["code"] != "0":
            return None
        candles = []
        for c in reversed(data["data"]):  # oldest first
            candles.append({
                "ts": datetime.fromtimestamp(int(c[0]) / 1000).strftime("%Y-%m-%d %H:%M"),
                "o": float(c[1]),
                "h": float(c[2]),
                "l": float(c[3]),
                "c": float(c[4]),
                "vol": float(c[5]),
            })
        return candles
    except Exception as e:
        print(f"[okx-market] candles error {inst_id}: {e}")
        return None


# ── Top Movers ──────────────────────────────────────────────────────────
def get_top_movers(inst_type: str = "SPOT", top_n: int = 5) -> list:
    """Get top gainers/losers by 24h change."""
    try:
        resp = requests.get(f"{BASE_URL}/market/tickers", params={"instType": inst_type}, timeout=10)
        data = resp.json()
        if data["code"] != "0":
            return []
        
        tickers = []
        for t in data["data"]:
            try:
                last = float(t["last"])
                open24h = float(t["open24h"])
                if open24h <= 0 or last <= 0:
                    continue
                chg = (last / open24h - 1) * 100
                vol = float(t.get("volCcy24h", 0))
                if vol < 1_000_000:  # skip low volume
                    continue
                tickers.append({
                    "instId": t["instId"],
                    "last": last,
                    "change24h": round(chg, 2),
                    "vol24h_usd": round(vol, 0),
                })
            except:
                continue
        
        tickers.sort(key=lambda x: x["change24h"], reverse=True)
        gainers = tickers[:top_n]
        losers = tickers[-top_n:]
        return {"gainers": gainers, "losers": losers}
    except Exception as e:
        print(f"[okx-market] top movers error: {e}")
        return []


# ── BNB Market Overview (for PancakeSwap Prediction) ────────────────────
def get_bnb_overview() -> dict:
    """Get comprehensive BNB market data for prediction signals."""
    result = {}
    
    # Spot price
    ticker = get_ticker("BNB-USDT")
    if ticker:
        result["spot"] = ticker
    
    # Perpetual swap
    swap = get_ticker("BNB-USDT-SWAP")
    if swap:
        result["swap"] = swap
    
    # Funding rate
    funding = get_funding_rate("BNB-USDT-SWAP")
    if funding:
        result["funding"] = funding
    
    # Open interest
    oi = get_open_interest("BNB-USDT-SWAP")
    if oi:
        result["openInterest"] = oi
    
    # 5m candles (last 12 = 1 hour)
    candles = get_candles("BNB-USDT", "5m", 12)
    if candles:
        result["candles_5m"] = candles
        # Calculate short-term trend
        if len(candles) >= 2:
            first_c = candles[0]["c"]
            last_c = candles[-1]["c"]
            result["trend_1h"] = round((last_c / first_c - 1) * 100, 3)
    
    # BTC correlation
    btc = get_ticker("BTC-USDT")
    if btc:
        result["btc"] = {"last": btc["last"], "change24h": btc["change24h"]}
    
    # ETH correlation
    eth = get_ticker("ETH-USDT")
    if eth:
        result["eth"] = {"last": eth["last"], "change24h": eth["change24h"]}
    
    result["ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return result


# ── Market Sentiment Summary ────────────────────────────────────────────
def get_market_sentiment() -> dict:
    """Get overall market sentiment indicators."""
    result = {}
    
    # BTC funding
    btc_fr = get_funding_rate("BTC-USDT-SWAP")
    if btc_fr:
        result["btc_funding"] = btc_fr
    
    # ETH funding
    eth_fr = get_funding_rate("ETH-USDT-SWAP")
    if eth_fr:
        result["eth_funding"] = eth_fr
    
    # BNB funding
    bnb_fr = get_funding_rate("BNB-USDT-SWAP")
    if bnb_fr:
        result["bnb_funding"] = bnb_fr
    
    # BTC OI
    btc_oi = get_open_interest("BTC-USDT-SWAP")
    if btc_oi:
        result["btc_oi"] = btc_oi
    
    # Price summary
    for sym in ["BTC-USDT", "ETH-USDT", "BNB-USDT", "SOL-USDT"]:
        t = get_ticker(sym)
        if t:
            result[sym.replace("-", "_").lower()] = {
                "price": t["last"],
                "change24h": t["change24h"],
            }
    
    # Sentiment interpretation
    if btc_fr:
        fr = btc_fr["fundingRate"]
        if fr > 0.001:
            result["sentiment"] = "🔴 极度贪婪 (资金费率过高)"
        elif fr > 0.0005:
            result["sentiment"] = "🟠 偏多 (正资金费率)"
        elif fr > -0.0005:
            result["sentiment"] = "🟡 中性"
        elif fr > -0.001:
            result["sentiment"] = "🟢 偏空 (负资金费率)"
        else:
            result["sentiment"] = "🔵 极度恐惧 (资金费率极负)"
    
    result["ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return result


# ── CLI ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 okx_market.py <command>")
        print("Commands: bnb, sentiment, ticker <instId>, funding <instId>, movers")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "bnb":
        data = get_bnb_overview()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif cmd == "sentiment":
        data = get_market_sentiment()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif cmd == "ticker":
        inst = sys.argv[2] if len(sys.argv) > 2 else "BTC-USDT"
        data = get_ticker(inst)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif cmd == "funding":
        inst = sys.argv[2] if len(sys.argv) > 2 else "BTC-USDT-SWAP"
        data = get_funding_rate(inst)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif cmd == "movers":
        data = get_top_movers()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Unknown command: {cmd}")
