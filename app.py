import os, requests, datetime as dt

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
GOLDAPI_KEY = os.environ["GOLDAPI_KEY"]

def fetch_xauusd():
    """Ambil data harga XAUUSD 15m.
    - Coba Yahoo (historical) supaya bisa hitung SMA
    - Kalau gagal, fallback ke GoldAPI (harga terkini saja)
    """
    # --- Coba Yahoo dulu (historical utk SMA) ---
    try:
        url = "https://query2.finance.yahoo.com/v8/finance/chart/XAUUSD=X"
        params = {"range": "3d", "interval": "15m"}  # cukup utk SMA50
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Connection": "keep-alive",
        }
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        data = [x for x in closes if x]
        print("YAHOO_LEN=", len(data))
        if len(data) >= 50:
            return data
    except Exception as e:
        print("YAHOO_ERR=", e)

    # --- Fallback: GoldAPI (harga terkini) ---
    g = requests.get(
        "https://www.goldapi.io/api/XAU/USD",
        headers={"x-access-token": GOLDAPI_KEY, "Accept": "application/json"},
        timeout=20,
    )
    g.raise_for_status()
    price = g.json().get("price")
    if not price:
        raise RuntimeError("GoldAPI: field 'price' kosong")
    print("FALLBACK_PRICE=", price)
    return [price]

def send_signal(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=20)
        print("TELEGRAM_STATUS=", r.status_code)
        print("TELEGRAM_RESP=", r.text[:200])
        r.raise_for_status()
    except Exception as e:
        print("TELEGRAM_ERR=", e)
        raise

def main():
    data = fetch_xauusd()
    print("LEN_DATA=", len(data))
    print("LAST_PRICE=", data[-1])

    # Jika data < 50 (fallback GoldAPI), kirim update harga saja
    if len(data) < 50:
        print("SOURCE=GoldAPI (fallback)")
        time = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        text = (
            f"🟡 *XAUUSD UPDATE*\n"
            f"Time: {time}\n"
            f"Price: {data[-1]:,.2f}\n"
            f"Source: GoldAPI (fallback)"
        )
        send_signal(text)
        return

    # Kalau historis cukup, hitung SMA dan kirim sinyal
    print("SOURCE=Yahoo (SMA)")
    sma20 = sum(data[-20:]) / 20
    sma50 = sum(data[-50:]) / 50
    last = data[-1]

    if last > sma20 > sma50:
        sig = "BUY ⚡️"
    elif last < sma20 < sma50:
        sig = "SELL 🔻"
    else:
        sig = "WAIT ⚖️"

    time = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    text = (
        f"🟡 *XAUUSD ALERT*\n"
        f"Time: {time}\n"
        f"Price: {last:,.2f}\n"
        f"Signal: {sig}"
    )
    send_signal(text)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        send_signal(f"⚠️ Error: {e}")
        print("MAIN_ERR=", e)
