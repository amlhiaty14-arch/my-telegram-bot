Python

import os
import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN")

API = f"https://api.telegram.org/bot{TOKEN}"
JUMIA = "https://www.jumia.com.eg"

# الفئات والعلامات التجارية المطلوبة
SEARCHES = [
    "DeFacto jacket men",
    "DeFacto jacket women",
    "DeFacto jacket kids",
    "Collins jacket men",
    "Collins jacket women",
    "Collins jacket kids",
]

MIN_DISCOUNT = 70
CHECK_INTERVAL = 6 * 60 * 60

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"
})

subscribers = set()
seen = set()


def send_message(chat_id, message):
    try:
        requests.post(
            API + "/sendMessage",
            data={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": False
            },
            timeout=20
        )
    except Exception as e:
        print("Telegram error:", e)


def get_number(price):
    if not price:
        return None
    digits = re.sub(r"[^\d]", "", price)
    return int(digits) if digits else None


def search_jumia(query):
    url = JUMIA + "/catalog/?q=" + quote(query)

    try:
        response = session.get(url, timeout=25)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        products = []

        for item in soup.select("article.prd, .prd"):
            name_tag = item.select_one(".name")
            price_tag = item.select_one(".prc")
            old_tag = item.select_one(".old")
            link_tag = item.select_one("a.core")

            if not name_tag or not price_tag or not link_tag:
                continue

            name = name_tag.get_text(" ", strip=True)
            title = name.lower()

            if "jacket" not in title and "جاكيت" not in title:
                continue

            if not any(brand in title for brand in ["defacto", "de facto", "collins"]):
                continue

            current = get_number(price_tag.get_text())
            old = get_number(old_tag.get_text()) if old_tag else None

            if not current or not old or old <= current:
                continue

            discount = round((old - current) / old * 100)

            if discount < MIN_DISCOUNT:
                continue

            link = link_tag.get("href", "")
            if link.startswith("/"):
                link = JUMIA + link

            if not link.startswith("https://"):
                continue

            products.append({
                "name": name,
                "price": current,
                "old": old,
                "discount": discount,
                "link": link
            })

        return products

    except Exception as e:
        print("Jumia error:", query, e)
        return []


def check_deals(chat_id):
    send_message(chat_id, "🔎 جاري البحث عن أقوى عروض الجواكت على جوميا...")

    found = []

    for query in SEARCHES:
        found.extend(search_jumia(query))
        time.sleep(2)

    # إزالة المنتجات المكررة
    unique = {}
    for product in found:
        unique[product["link"]] = product

    found = sorted(
        unique.values(),
        key=lambda x: x["discount"],
        reverse=True
    )

    new_deals = [p for p in found if p["link"] not in seen]

    if not new_deals:
        send_message(
            chat_id,
            "لم أجد عروضًا جديدة مؤكدة بخصم 70% أو أكثر حاليًا. سأبحث مرة أخرى لاحقًا ❤️"
        )
        return

    for p in new_deals[:20]:
        message = (
            f"🔥 خصم {p['discount']}%\n\n"
            f"🧥 {p['name']}\n"
            f"💰 السعر الحالي: {p['price']} جنيه\n"
            f"السعر القديم: {p['old']} جنيه\n\n"
            f"🛒 رابط المنتج:\n{p['link']}"
        )
        send_message(chat_id, message)
        seen.add(p["link"])
        time.sleep(1)


def main():
    print("Telegram jacket deals bot started")

    offset = None
    last_check = 0

    while True:
        try:
            response = requests.get(
                API + "/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            ).json()

            if response.get("ok"):
                for update in response.get("result", []):
                    offset = update["update_id"] + 1

                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    chat_id = chat.get("id")
                    command = message.get("text", "").strip().lower()

                    if not chat_id:
                        continue

                    if command.startswith("/start"):
                        subscribers.add(chat_id)
                        send_message(
                            chat_id,
                            "أهلاً بيك ❤️\n"
                            "بوت صيد عروض الجواكت جاهز!\n\n"
                            "أبحث عن DeFacto وCollins للرجالي والحريمي والأطفال.\n"
                            "أقبل الخصومات من 70% إلى 90% وأكثر.\n\n"
                            "اكتب /check لبدء البحث الآن."
                        )

                    elif command.startswith("/check"):
                        subscribers.add(chat_id)
                        check_deals(chat_id)

            if time.time() - last_check >= CHECK_INTERVAL:
                for chat_id in list(subscribers):
                    check_deals(chat_id)
                last_check = time.time()

        except Exception as e:
            print("Main loop error:", e)
            time.sleep(10)


if __name__ == "__main__":
    main()
