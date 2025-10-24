import os, re, statistics as stats, requests, datetime as dt

# === Secrets dari GitHub ===
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
GOLDAPI_KEY = os.environ.get("GOLDAPI_KEY", "")

# === Util Telegram ===
def send(msg: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload, timeout=20)
    try:
        r.raise_for_status()
    except Exception:
        # Tetap log sebagian respon biar gampang debug
        print("TELEGRAM_STATUS=", r.status_code, "RESP=", r.text[:200])
        raise

# === Sumber Data ===
def fetch_yahoo_closes():
    """Yahoo historis 15m buat SMA. Endpoint query2 + params (lebih stabil)."""
    url = "https://query2.finance.yahoo.com/v8/finance/chart/XAUUSD=X"
    params = {"range": "5d", "interval": "15m"}
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Connection": "keep-alive",
    }
    r = requests.get(url, params=params, headers=headers, timeout=25)
    r.raise_for_status()
    j = r.json()["chart"]["result"][0]
    closes = [x for x in j["indicators"]["quote"][0]["close"] if x]
    print("YAHOO_LEN=", len(closes))
    if len(closes) < 60:
        raise RuntimeError("Yahoo data kurang")
    return closes

def fetch_goldapi_price():
    """Harga spot dari GoldAPI (butuh key)."""
    r = requests.get(
        "https://www.goldapi.io/api/XAU/USD",
        headers={"x-access-token": GOLDAPI_KEY, "Accept": "application/json"},
        timeout=20,
    )
    r.raise_for_status()
    p = r.json().get("price")
    if not p:
        raise RuntimeError("GoldAPI: price kosong")
    return float(p)

def fetch_kitco_price():
    """Scrape ringan Kitco (eksperimental)."""
    url = "https://www.kitco.com/gold-price-today-usa/"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    html = r.text
    # beberapa variasi selector yang sering muncul
    m = re.search(r'id="sp-bid">([\d\.,]+)', html)
    if not m:
        m = re.search(r'"goldBid":\s*([\d\.]+)', html)
    if not m:
        raise RuntimeError("Kitco: selector tidak ditemukan")
    return float(m.group(1).replace(",", ""))

def fetch_metalsdaily_price():
    """Scrape ringan MetalsDaily (eksperimental)."""
    url = "https://www.metalsdaily.com/gold-price-today"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    html = r.text
    # Cari angka USD per oz yang paling besar (heuristik)
    nums = re.findall(r"\$?\s*([0-9]{3,5}\.?[0-9]{0,2})", html)
    candidates = [float(x) for x in nums if 900 <= float(x) <= 5000]
    if not candidates:
        raise RuntimeError("MetalsDaily: harga tak terbaca")
    # Ambil median biar robust
    return stats.median(candidates)

def safe_fetch(fn, name):
    try:
        v = fn()
        print(f"{name}=", v)
        return v
    except Exception as e:
        print(f"{name}_ERR=", e)
        return None

# === Analitik ===
def mean(arr): return sum(arr) / len(arr)

def atr_proxy(series, lookback=20):
    diffs = [abs(series[i] - series[i-1]) for i in range(1, len(series))]
    return mean(diffs[-lookback:])

def analyze_sma(closes):
    last = closes[-1]
    sma20 = mean(closes[-20:])
    sma50 = mean(closes[-50:])
    atr = atr_proxy(closes[-60:])
    # momentum: kemiringan sederhana
    sma20_prev = mean(closes[-21:-1])
    sma50_prev = mean(closes[-51:-1])

    side = "WAIT"
    tag_bos = ""
    entry = last

    if last > sma20 > sma50:
        side = "BUY"
        if (sma20 - sma20_prev) > 0 and (sma50 - sma50_prev) > 0:
            tag_bos = " (entry bos)"
        tp = entry + 2 * atr
        sl = entry - 1.5 * atr
    elif last < sma20 < sma50:
        side = "SELL"
        if (sma20 - sma20_prev) < 0 and (sma50 - sma50_prev) < 0:
            tag_bos = " (entry bos)"
        tp = entry - 2 * atr
        sl = entry + 1.5 * atr
    else:
        return {
            "mode": "WAIT",
            "msg": (
                f"⚖️ *WAIT*\n"
                f"Price : {last:,.2f}\n"
                f"SMA20 : {sma20:,.2f}\n"
                f"SMA50 : {sma50:,.2f}\n"
                f"ATR   : {atr:,.2f}"
            )
        }

    return {
        "mode": side,
        "entry": entry,
        "tp": tp,
        "sl": sl,
        "atr": atr,
        "tag": tag_bos,
        "last": last,
        "sma20": sma20,
        "sma50": sma50,
    }

def consensus_boost(side, entry, atr, extras):
    """
    Tambah konfirmasi dari sumber lain.
    - BUY: hitung berapa sumber yang harga-nya >= entry + 0.25*ATR
    - SELL: hitung berapa sumber yang harga-nya <= entry - 0.25*ATR
    Kalau >=1 konfirmasi → tambahkan (entry bos) kalau belum ada.
    """
    if atr is None or atr == 0: return False
    tol = 0.25 * atr
    ok = 0
    for name, p in extras.items():
        if p is None: continue
        if side == "BUY" and (p >= entry + tol): ok += 1
        if side == "SELL" and (p <= entry - tol): ok += 1
    return ok >= 1

def format_levels(side, entry, tp, sl, atr, tag):
    arrow = "🟢" if side == "BUY" else "🔴"
    body = (
        f"{arrow} *{side}*{tag}\n"
        f"Entry : {entry:,.2f}\n"
        f"TP    : {tp:,.2f}\n"
        f"SL    : {sl:,.2f}\n"
        f"ATR   : {atr:,.2f}\n"
        f"RR    : ~1:1.33"
    )
    return body

# === Main ===
def main():
    tnow = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # 1) Coba Yahoo (utama)
    closes = None
    try:
        closes = fetch_yahoo_closes()
    except Exception as e:
        print("YAHOO_FAIL=", e)

    # 2) Ambil beberapa sumber realtime (opsional/eksperimental)
    p_goldapi = safe_fetch(fetch_goldapi_price, "GoldAPI") if GOLDAPI_KEY else None
    p_kitco = safe_fetch(fetch_kitco_price, "Kitco")
    p_metalsdaily = safe_fetch(fetch_metalsdaily_price, "MetalsDaily")

    # 3) Jika historis ada → hitung sinyal profesional
    if closes:
        res = analyze_sma(closes)
        if res["mode"] == "WAIT":
            header = "🟡 *XAUUSD STATUS*"
            text = f"{header}\nTime  : {tnow}\n{res['msg']}\nSource: Yahoo (SMA)"
            send(text)
            return

        # side dengan TP/SL
        side = res["mode"]
        entry, tp, sl = res["entry"], res["tp"], res["sl"]
        atr = res["atr"]
        tag = res["tag"]

        # 4) Konsensus sederhana: konfirmasi dari minimal 1 sumber realtime
        extras = {"GoldAPI": p_goldapi, "Kitco": p_kitco, "MetalsDaily": p_metalsdaily}
        if side in ("BUY", "SELL") and consensus_boost(side, entry, atr, extras):
            if "(entry bos)" not in tag:
                tag = (tag + " (entry bos)").strip()

        body = format_levels(side, entry, tp, sl, atr, tag)
        text = f"🟡 *XAUUSD ALERT*\nTime  : {tnow}\n{body}\nSource: Yahoo (SMA) + multi-source check"
        send(text)
        return

    # 5) Kalau historis gagal total → kirim update harga dari sumber yang tersedia
    prices = [p for p in [p_goldapi, p_kitco, p_metalsdaily] if p is not None]
    if prices:
        # tampilkan ringkas
        lines = []
        if p_goldapi is not None: lines.append(f"GoldAPI : {p_goldapi:,.2f}")
        if p_kitco is not None: lines.append(f"Kitco   : {p_kitco:,.2f}")
        if p_metalsdaily is not None: lines.append(f"MetalsD : {p_metalsdaily:,.2f}")
        joined = "\n".join(lines)
        send(
            "🟡 *XAUUSD UPDATE*\n"
            f"Time  : {tnow}\n"
            f"{joined}\n"
            "Signal: WAIT (butuh historis utk entry/TP/SL)\n"
            "Source: Multi-source fallback"
        )
        return

    # 6) Kalau semua sumber gagal
    send(f"⚠️ Semua sumber gagal diakses {tnow}. Coba lagi nanti.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        send(f"⚠️ Error: {e}")
        print("MAIN_ERR=", e)
