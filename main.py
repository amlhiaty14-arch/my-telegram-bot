"Python"

import os
import re
import time
import json
import base64
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin

# =========================
# SETTINGS
# =========================

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""

JUMIA = "https://www.jumia.com.eg"
MIN_DISCOUNT = 70
MAX_DEALS = 20

REPO = os.environ.get("GITHUB_REPOSITORY", "")
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
STATE_FILE = "bot_state.json"

SEARCHES = [
    "DeFacto jacket men",
    "DeFacto jacket women",
    "DeFacto jacket kids",
    "Collins jacket men",
    "Collins jacket women",
    "Collins jacket kids",
]

session = requests.Session()
python
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})


# =========================
# STATE STORAGE
# =========================

def load_state():
    default = {
        "subscribers": [],
        "seen": [],
        "offset": 0
    }

    if not REPO or not GH_TOKEN:
        print("Warning: GitHub storage is not configured")
        return default

    url = f"https://api.github.com/repos/{REPO}/contents/{STATE_FILE}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)

        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(
                data["content"]
            ).decode("utf-8")

            state = json.loads(content)
            state["sha"] = data["sha"]

            state.setdefault("subscribers", [])
            state.setdefault("seen", [])
            state.setdefault("offset", 0)

            return state

        if response.status_code != 404:
            print("State loading error:", response.text)

    except Exception as error:
        print("State loading error:", error)

    return default


def save_state(state):
    if not REPO or not GH_TOKEN:
        print("Warning: State was not saved")
        return

    url = f"https://api.github.com/repos/{REPO}/contents/{STATE_FILE}"

    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    data = {
        "subscribers": state.get("subscribers", []),
        "seen": state.get("seen", []),
        "offset": state.get("offset", 0)
    }

    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": "Update jacket deals bot state",
        "content": content
    }

    if state.get("sha"):
        payload["sha"] = state["sha"]

    response = requests.put(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    print("Bot state saved successfully")


# =========================
# TELEGRAM
# =========================

def send_message(chat_id, message):
    try:
        response = requests.post(
            API + "/sendMessage",
            data={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": False
            },
            timeout=25
        )

        response.raise_for_status()
        result = response.json()

        if result.get("ok"):
            return True

        print("Telegram error:", result)

    except Exception as error:
        print("Telegram sending error:", error)

    return False


# =========================
# PRICE AND PRODUCT SEARCH
# =========================

def get_number(value):
    if not value:
        return None

    digits = re.sub(r"[^\d]", "", str(value))

    return int(digits) if digits else None


def search_jumia(query):
    url = JUMIA + "/catalog/?q=" + quote(query)
    products = []

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        cards = soup.select("article.prd")

        if not cards:
            cards = soup.select(".prd")

        for item in cards:
            name_tag = item.select_one(".name")
            price_tag = item.select_one(".prc")
            old_tag = item.select_one(".old")
            link_tag = item.select_one("a.core")

            if not link_tag:
                link_tag = item.select_one("a[href]")

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

            discount = round(
                ((old - current) / old) * 100
            )

            if discount < MIN_DISCOUNT:
                continue

            link = urljoin(
                JUMIA,
                link_tag.get("href", "")
            )

            if not link.startswith("https://"):
                continue

            products.append({
                "name": name,
                "price": current,
                "old": old,
                "discount": discount,
                "link": link
            })

        print(
            f"Search: {query} | Found: {len(products)}"
        )

    except Exception as error:
        print("Jumia search error:", query, error)

    return products


# =========================
# DEALS TRACKER
# =========================

def check_deals(chat_id, state, manual=False):

    if manual:
        send_message(
            chat_id,
            "🔎 جاري البحث عن أقوى عروض الجواكت..."
        )

    found = []

    for query in SEARCHES:
        found.extend(search_jumia(query))
        time.sleep(2)

    unique = {
        product["link"]: product
        for product in found
    }

    found = sorted(
        unique.values(),
        key=lambda product: product["discount"],
        reverse=True
    )

    seen = set(state.get("seen", []))

    new_deals = [
        product for product in found
        if product["link"] not in seen
    ]

    if not new_deals:
        if manual:
            send_message(
                chat_id,
                "لم أجد عروضًا جديدة بخصم 70% أو أكثر حاليًا ❤️"
            )
        return

    sent = 0

    for product in new_deals[:MAX_DEALS]:

        message = (
            f"🔥 خصم {product['discount']}%\n\n"
            f"🧥 {product['name']}\n\n"
            f"💰 السعر الحالي: {product['price']} جنيه\n"
            f"🏷️ السعر القديم: {product['old']} جنيه\n\n"
            f"🛒 رابط المنتج:\n{product['link']}"
        )

        if send_message(chat_id, message):
            seen.add(product["link"])
            sent += 1

        time.sleep(1)

    state["seen"] = list(seen)[-1000:]

    print(
        f"Deals sent to {chat_id}: {sent}"
    )


# =========================
# TELEGRAM COMMANDS
# =========================

def process_updates(state):

    offset = state.get("offset", 0)
    manually_checked = set()

    try:
        response = requests.get(
            API + "/getUpdates",
            params={
                "offset": offset,
                "timeout": 5
            },
            timeout=15
        )

        response.raise_for_status()
        updates = response.json()

        if not updates.get("ok"):
            print("Telegram update error:", updates)
            return manually_checked

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
                    "أهلاً بيك ❤️\n\n"
                    "بوت صيد عروض الجواكت جاهز!\n\n"
                    "🔹 DeFacto\n"
                    "🔹 Collins\n"
                    "🔹 رجالي وحريمي وأطفال\n"
                    "🔹 خصومات 70% و80% و90% وأكثر\n\n"
                    "اكتب /check للبحث الآن.\n"
                    "اكتب /stop لإيقاف الاشتراك."
                )

            elif command.startswith("/check"):

                if chat_id not in state["subscribers"]:
                    state["subscribers"].append(chat_id)

                check_deals(chat_id, state, manual=True)
                manually_checked.add(chat_id)

            elif command.startswith("/stop"):

                if chat_id in state["subscribers"]:
                    state["subscribers"].remove(chat_id)

                send_message(
                    chat_id,
                    "تم إيقاف اشتراكك في تنبيهات العروض ❤️"
                )

            elif command.startswith("/help"):

                send_message(
                    chat_id,
                    "أوامر البوت:\n\n"
                    "/start - الاشتراك\n"
                    "/check - البحث عن العروض\n"
                    "/stop - إيقاف الاشتراك\n"
                    "/help - المساعدة"
                )

    except Exception as error:
        print("Update processing error:", error)

    return manually_checked


# =========================
# MAIN
# =========================

def main():

    if not TOKEN:
        raise RuntimeError(
            "Missing TELEGRAM_TOKEN secret"
        )

    print("Jacket Deals Tracker started")

    state = load_state()

    manually_checked = process_updates(state)

    for chat_id in list(state["subscribers"]):

        if chat_id in manually_checked:
            continue

        check_deals(chat_id, state)

    save_state(state)

    print("Jacket Deals Tracker finished")


if __name__ == "__main__":
    main()
