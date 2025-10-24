import os, requests, datetime as dt

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

def fetch_xauusd():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?range=2d&interval=15m"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    return [x for x in data if x]

def send_signal(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=20)

def main():
    data = fetch_xauusd()
    if len(data) < 50:
        send_signal("⚠️ Data tidak cukup untuk analisis XAUUSD.")
        return

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
    text = f"🟡 *XAUUSD ALERT*\nTime: {time}\nPrice: {last:,.2f}\nSignal: {sig}"
    send_signal(text)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        send_signal(f"⚠️ Error: {e}")
