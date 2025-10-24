import os, requests, datetime as dt

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
GOLDAPI_KEY = os.environ["GOLDAPI_KEY"]

def fetch_xauusd():
    # Coba Yahoo dulu (historical utk SMA)
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?range=2d&interval=15m"
        headers = {"User-Agent": "Mozilla/5.0"}  # bantu kurangi 429
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        data = [x for x in data if x]
        if len(data) >= 50:
            return data
    except Exception:
        pass

    # Fallback: GoldAPI (harga terkini)
    g = requests.get(
        "https://www.goldapi.io/api/XAU/USD",
        headers={"x-access-token": GOLDAPI_KEY, "Accept": "application/json"},
        timeout=20,
    )
    g.raise_for_status()
    price = g.json().get("price")
    if not price:
        raise RuntimeError("GoldAPI: field 'price' kosong")
    return [price]

def send_signal(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=20)

def main():
    data = fetch_xauusd()
    last = data[-1]

    # Jika data kurang dari 50 (fallback), kirim update harga saja
    if len(data) < 50:
        time = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        text = f"🟡 *XAUUSD UPDATE*\nTime: {time}\nPrice: {last:,.2f}\nSource: GoldAPI (fallback)"
        send_signal(text)
        return

    # Hitung sinyal SMA
    sma20 = sum(data[-20:]) / 20
    sma50 = sum(data[-50:]) / 50

    if last > sma20 > sma50:
        sig = "BUY ⚡️"
    elif last < sma20 < sma50:
        sig = "SELL 🔻"
    else:
        sig = "WAIT ⚖️"

    time = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    text = f"🟡 *XAUUSD ALERT*\nTime: {time}\nPrice: {last:,.2f}\nSignal: {sig}"
    send_signal(text)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        send_signal(f"⚠️ Error: {e}")
