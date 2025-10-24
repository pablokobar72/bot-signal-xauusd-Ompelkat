import os, requests, datetime as dt
from statistics import mean

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
GOLDAPI_KEY = os.environ.get("GOLDAPI_KEY", "")

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?range=5d&interval=15m"

def fetch_yahoo_closes():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(YAHOO_URL, headers=headers, timeout=25)
    r.raise_for_status()
    j = r.json()
    q = j["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    closes = [x for x in q if x]  # buang None
    if len(closes) < 60:
        raise RuntimeError("Yahoo: data kurang")
    return closes

def fetch_goldapi_price():
    r = requests.get(
        "https://www.goldapi.io/api/XAU/USD",
        headers={"x-access-token": GOLDAPI_KEY, "Accept": "application/json"},
        timeout=20,
    )
    r.raise_for_status()
    p = r.json().get("price")
    if not p:
        raise RuntimeError("GoldAPI: field 'price' kosong")
    return float(p)

def quick_atr_proxy(series, lookback=20):
    """Proxy ATR dari perubahan absolut penutupan (bukan true range penuh)."""
    diffs = [abs(series[i] - series[i-1]) for i in range(1, len(series))]
    return mean(diffs[-lookback:])

def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=20)

def format_levels(side, entry, tp, sl):
    arrow = "🟢" if side == "BUY" else "🔴"
    return (
        f"{arrow} *{side}*\n"
        f"Entry : {entry:,.2f}\n"
        f"TP    : {tp:,.2f}\n"
        f"SL    : {sl:,.2f}"
    )

def analyze_with_yahoo(closes):
    last = closes[-1]
    sma20 = mean(closes[-20:])
    sma50 = mean(closes[-50:])
    atr = quick_atr_proxy(closes[-60:])  # cukup 60 titik terakhir

    # Momentum (kemiringan)
    sma20_prev = mean(closes[-21:-1])
    sma50_prev = mean(closes[-51:-1])

    side = "WAIT"
    tag_bos = ""
    entry = last

    if last > sma20 > sma50:
        side = "BUY"
        tp = entry + 2 * atr
        sl = entry - 1.5 * atr
        if (sma20 - sma20_prev) > 0 and (sma50 - sma50_prev) > 0:
            tag_bos = " (entry bos)"
    elif last < sma20 < sma50:
        side = "SELL"
        tp = entry - 2 * atr
        sl = entry + 1.5 * atr
        if (sma20 - sma20_prev) < 0 and (sma50 - sma50_prev) < 0:
            tag_bos = " (entry bos)"
    else:
        # WAIT – kasih konteks level referensi
        msg = (
            f"⚖️ *WAIT*\n"
            f"Price : {last:,.2f}\n"
            f"SMA20 : {sma20:,.2f}\n"
            f"SMA50 : {sma50:,.2f}\n"
            f"ATR   : {atr:,.2f}"
        )
        return ("WAIT", msg)

    msg = format_levels(side, entry, tp, sl)
    msg += f"\nATR   : {atr:,.2f}\nRR    : ~1:1.33{tag_bos}"
    return (side, msg)

def main():
    time_utc = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    try:
        closes = fetch_yahoo_closes()
        side, core = analyze_with_yahoo(closes)
        header = "🟡 *XAUUSD ALERT*" if side in ("BUY", "SELL") else "🟡 *XAUUSD STATUS*"
        text = f"{header}\nTime  : {time_utc}\n{core}\nSource: Yahoo (SMA)"
        send(text)
        return
    except Exception as e:
        # Kalau Yahoo gagal (rate-limit/dll), fallback ke GoldAPI
        try:
            price = fetch_goldapi_price()
            text = (
                "🟡 *XAUUSD UPDATE*\n"
                f"Time  : {time_utc}\n"
                f"Price : {price:,.2f}\n"
                "Signal: WAIT (butuh historis untuk entry/TP/SL)\n"
                "Source: GoldAPI (fallback)"
            )
            send(text)
        except Exception as e2:
            send(f"⚠️ Error: {e2}")

if __name__ == "__main__":
    main()
