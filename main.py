Python

import os
import re
import time
import json
import base64
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

TOKEN = os.environ["TELEGRAM_TOKEN"]
API = f"https://api.telegram.org/bot{TOKEN}"
JUMIA = "https://www.jumia.com.eg"

MIN_DISCOUNT = 70
MAX_DEALS = 20

SEARCHES = [
    "DeFacto jacket men",
    "DeFacto jacket women",
    "DeFacto jacket kids",
    "Collins jacket men",
    "Collins jacket women",
    "Collins jacket kids",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
})

REPO = os.environ.get("GITHUB_REPOSITORY")
GH_TOKEN = os.environ.get("GITHUB_TOKEN")
STATE_FILE = "bot_state.json"


def load_state():
    default = {"subscribers": [], "seen": [], "offset": 0}

    if not REPO or not GH_TOKEN:
        return default

    url = f"https://api.github.com/repos/{REPO}/contents/{STATE_FILE}"
    headers = {"Authorization": f"Bearer {GH_TOKEN}"}

    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            state = json.loads(content)
            state["sha"] = data["sha"]
            return state
    except Exception as e:
        print("State loading error:", e)

    return default


def save_state(state):
    if not REPO or not GH_TOKEN:
        print("Warning: persistent storage unavailable")
        return

    url = f"https://api.github.com/repos/{REPO}/contents/{STATE_FILE}"
    headers = {"Authorization": f"Bearer {GH_TOKEN}"}

    data = {k: v for k, v in state.items() if k != "sha"}
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": "Update jacket deals bot state",
        "content": content
    }

    if state.get("sha"):
        payload["sha"] = state["sha"]

    r = requests.put(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()

    if r.status_code not in (200, 201):
        raise RuntimeError("Could not save bot state")


def send_message(chat_id, message):
    try:
        r = requests.post(
            API + "/sendMessage",
            data={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": False
            },
            timeout=25
        )
        r.raise_for_status()
        result = r.json()
        if not result.get("ok"):
            print("Telegram rejected message:", result)
    except Exception as e:
        print("Telegram error:", e)


def get_number(value):
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def search_jumia(query):
    url = JUMIA + "/catalog/?q=" + quote(query)
    products = []

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for item in soup.select("article.prd, .prd"):
            name_tag = item.select_one(".name")
            price_tag = item.select_one(".prc")
            old_tag = item.select_one(".old")
            link_tag = item.select_one("a.core")

            if not all([name_tag, price_tag, old_tag, link_tag]):
                continue

            name = name_tag.get_text(" ", strip=True)
            title = name.lower()

            if not any(word in title for word in [
                "jacket", "coat", "جاكيت", "جاكت"
            ]):
                continue

            if not any(brand in title for brand in [
                "defacto", "de facto", "collins"
            ]):
                continue

            current = get_number(price_tag.get_text())
            old = get_number(old_tag.get_text())

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

    except Exception as e:
        print("Jumia search error:", query, e)

    return products


def check_deals(chat_id, state):
    send_message(chat_id, "🔎 جاري البحث عن أقوى عروض الجواكت...")

    found = []

    for query in SEARCHES:
        found.extend(search_jumia(query))
        time.sleep(2)

    unique = {p["link"]: p for p in found}

    found = sorted(
        unique.values(),
        key=lambda p: p["discount"],
        reverse=True
    )

    seen = set(state.get("seen", []))
    new_deals = [p for p in found if p["link"] not in seen]

    if not new_deals:
        send_message(
            chat_id,
            "لم أجد عروضًا جديدة بخصم 70% أو أكثر حاليًا ❤️"
        )
        return

    for p in new_deals[:MAX_DEALS]:
        message = (
            f"🔥 خصم {p['discount']}%\n\n"
            f"🧥 {p['name']}\n\n"
            f"💰 السعر الحالي: {p['price']} جنيه\n"
            f"🏷️ السعر القديم: {p['old']} جنيه\n\n"
            f"🛒 رابط المنتج:\n{p['link']}"
        )

        send_message(chat_id, message)
        seen.add(p["link"])
        time.sleep(1)

    state["seen"] = list(seen)[-1000:]


def process_updates(state):
    offset = state.get("offset", 0)

    try:
        r = requests.get(
            API + "/getUpdates",
            params={"offset": offset, "timeout": 5},
            timeout=15
        )
        r.raise_for_status()

        updates = r.json()

        if not updates.get("ok"):
            return

        for update in updates.get("result", []):
            state["offset"] = update["update_id"] + 1

            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            command = message.get("text", "").strip().lower()

            if not chat_id:
                continue

            if command.startswith("/start"):
                if chat_id not in state["subscribers"]:
                    state["subscribers"].append(chat_id)

                send_message(
                    chat_id,
                    "أهلاً بيك ❤️\n"
                    "بوت صيد عروض الجواكت جاهز!\n\n"
                    "أبحث عن DeFacto وCollins.\n"
                    "رجالي وحريمي وأطفال.\n"
                    "خصومات من 70% إلى 90% وأكثر.\n\n"
                    "اكتب /check للبحث الآن."
                )

            elif command.startswith("/check"):
                if chat_id not in state["subscribers"]:
                    state["subscribers"].append(chat_id)

                check_deals(chat_id, state)

    except Exception as e:
        print("Update processing error:", e)


def main():
    print("Jacket Deals Tracker started")

    state = load_state()

    process_updates(state)

    for chat_id in list(state["subscribers"]):
        check_deals(chat_id, state)

    save_state(state)

    print("Jacket Deals Tracker finished successfully")


if __name__ == "__main__":
    main()
