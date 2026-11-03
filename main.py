Python

import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

TOKEN = os.environ.get("TELEGRAM_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}"

JUMIA_URLS = [
    "https://www.jumia.com.eg/catalog/?q=defacto+jacket",
    "https://www.jumia.com.eg/catalog/?q=defacto+women+jacket",
    "https://www.jumia.com.eg/catalog/?q=defacto+men+jacket",
    "https://www.jumia.com.eg/catalog/?q=defacto+kids+jacket"
]

def send_message(chat_id, message):
    requests.post(
        f"{API}/sendMessage",
        data={"chat_id": chat_id, "text": message},
        timeout=20
    )

def find_offers():
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for url in JUMIA_URLS:
        try:
            response = requests.get(
                url, headers=headers, timeout=20
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            for item in soup.select("article.prd"):
                name = item.select_one(".name")
                price = item.select_one(".prc")
                link = item.select_one("a.core")

                if not name or not price or not link:
                    continue

                title = name.get_text(" ", strip=True)

                if "defacto" not in title.lower():
                    continue

                product_url = urljoin(
                    "https://www.jumia.com.eg", link.get("href", "")
                )

                results.append(
                    f"{title}\nالسعر: {price.get_text(strip=True)}\n"
                    f"{product_url}"
                )

        except Exception as error:
            print("Jumia error:", error)

    return list(dict.fromkeys(results))

def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN is missing")

    offset = None
    while True:
        try:
            response = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 25},
                timeout=30
            ).json()

            for update in response.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                command = message.get("text", "")

                if not chat_id:
                    continue

                if command.startswith("/start"):
                    send_message(
                        chat_id,
                        "أهلاً بيكي ❤️ أنا صياد عروض DeFacto على جوميا!\n"
                        "اكتبي /check للبحث عن الجواكت."
                    )

                elif command.startswith("/check"):
                    send_message(chat_id, "بدور لك على العروض... 🔎")
                    offers = find_offers()

                    if offers:
                        for offer in offers[:20]:
                            send_message(chat_id, offer)
                    else:
                        send_message(
                            chat_id,
                            "ملقتش منتجات حاليًا أو جوميا لم يسمح بالبحث. "
                            "جربي مرة تانية."
                        )

        except Exception as error:
            print("Bot error:", error)
            time.sleep(5)

if __name__ == "__main__":
    main()
