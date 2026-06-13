"""2GIS dan Uzbekiston bizneslari scraping, lead navbati va avtomatik outreach."""
import asyncio
import logging
import random
import re

import aiohttp

import config
import database as db

log = logging.getLogger(__name__)

# ─── Kategoriyalar va shaharlar ───────────────────────────────────────────────

CATEGORIES = [
    "klinika", "stomatologiya", "restoran", "kafe",
    "dorixona", "go'zallik salon", "fitness markaz",
    "ta'lim markaz", "mehmonxona", "optika", "bolalar bog'chasi",
]

CITIES = [
    "Toshkent", "Samarqand", "Buxoro", "Namangan",
    "Andijon", "Farg'ona", "Qarshi", "Nukus",
    "Jizzax", "Termiz", "Guliston", "Navoiy",
    "Chirchiq", "Olmaliq", "Bekobod",
]


# ─── Moslashtirilgan xabarlar ─────────────────────────────────────────────────

def outreach_message(name: str, category: str) -> str:
    """Kategoriyaga qarab moslashtirilgan birinchi xabar."""
    cat = (category or "").lower()

    if any(k in cat for k in ["klinika", "shifokor", "tibbiy", "poliklinika"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Klinikalar uchun Telegram bot qilamiz — bemorlar telefon qilmasdan navbat oladi, "
            f"eslatmalar avtomatik ketadi. Operator kerak emas.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    if any(k in cat for k in ["stomatolog", "dental", "tish"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Stomatologiya klinikalar uchun navbat boti qilamiz — "
            f"bemorlar bot orqali vaqt tanlaydi, siz admin panelda barchasini ko'rasiz.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    if any(k in cat for k in ["restoran", "oshxona", "milliy taom"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Restoran uchun Telegram bot qilamiz — mijozlar menyudan tanlab buyurtma beradi, "
            f"siz darhol xabar olasiz. Telefon operator kerak emas.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    if any(k in cat for k in ["kafe", "coffee", "qahva", "tea"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Kafe uchun pre-order bot qilamiz — mijozlar kelishdan oldin buyurtma beradi, "
            f"navbat bo'lmaydi. Savdo 20-30% oshadi.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    if any(k in cat for k in ["dorixona", "apteka", "farmatsiya"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Dorixona uchun Telegram bot qilamiz — mijozlar dori borligini so'raydi, "
            f"buyurtma beradi, telefon band bo'lmaydi.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    if any(k in cat for k in ["go'zallik", "beauty", "sartarosh", "salon", "nail", "kosmetik"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Salon uchun navbat boti qilamiz — mijozlar bot orqali vaqt tanlaydi, "
            f"sizga xabar keladi. Telefon kerak emas.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    if any(k in cat for k in ["fitness", "sport", "gym", "trening"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Sport markaz uchun bot qilamiz — a'zolik, dars jadvali, "
            f"to'lov barchasi Telegram orqali. Admin yuki kamayadi.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    if any(k in cat for k in ["ta'lim", "kurs", "maktab", "o'quv", "repetitor"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"O'quv markaz uchun bot qilamiz — o'quvchilar ro'yxatga olindi, "
            f"dars eslatmalari avtomatik boradi, to'lov nazorat qilinadi.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    if any(k in cat for k in ["mehmonxona", "hotel", "hostel"]):
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Mehmonxona uchun Telegram bot qilamiz — xona bron qilish, "
            f"tasdiq va eslatmalar avtomatik. Telefon qo'ng'irog'i kamayadi.\n\n"
            f"Qiziqsangiz, gaplashib ko'ramizmi?"
        )
    # Umumiy holat
    return (
        f"Assalomu alaykum, {name}!\n\n"
        f"Biznesingiz uchun Telegram bot qilamiz — mijozlar bilan ishlash "
        f"to'liq avtomatik bo'ladi, operatorsiz.\n\n"
        f"Qiziqsangiz, gaplashib ko'ramizmi?"
    )


# ─── Telefon yordamchi funksiyalar ───────────────────────────────────────────

# Faqat O'zbek mobil prefikslar — landline (71,72...) va qisqa raqamlar istisno
_UZ_MOBILE_PREFIXES = {"33", "55", "77", "88", "90", "91", "93", "94", "95", "97", "98", "99"}


def _normalize_phone(raw: str) -> str:
    phone = re.sub(r'[\s\-\(\)]', '', raw.strip())
    if not phone.startswith('+'):
        if phone.startswith('998'):
            phone = '+' + phone
        elif len(phone) == 9:
            phone = '+998' + phone
    return phone


def _is_mobile_uz(phone: str) -> bool:
    """Faqat O'zbek mobil raqamlarni o'tkazib beradi (+99890..., +99891... va h.k.)."""
    return (
        phone.startswith("+998")
        and len(phone) == 13
        and phone[4:6] in _UZ_MOBILE_PREFIXES
    )


def _extract_mobile_phone(raw: str) -> str:
    """Semicolon bilan ajratilgan raqamlar orasidan birinchi mobil raqamni qaytaradi."""
    for part in raw.split(";"):
        phone = _normalize_phone(part.strip())
        if _is_mobile_uz(phone):
            return phone
    return ""


def _extract_phone(item: dict) -> str:
    """2GIS contact_groups dan mobil raqam oladi."""
    for cg in item.get("contact_groups", []):
        for c in cg.get("contacts", []):
            if c.get("type") == "phone":
                val = c.get("value", "").strip()
                if val:
                    phone = _normalize_phone(val)
                    if _is_mobile_uz(phone):
                        return phone
    return ""


# Yandex Search uchun shahar markazlari (lon, lat)
_CITY_LL = {
    "Toshkent":  (69.2401, 41.2995),
    "Samarqand": (66.9597, 39.6547),
    "Buxoro":    (64.4286, 39.7747),
    "Namangan":  (71.6725, 40.9983),
    "Andijon":   (72.3438, 40.7829),
    "Farg'ona":  (71.7864, 40.3842),
    "Qarshi":    (65.7908, 38.8610),
    "Nukus":     (59.6106, 42.4600),
    "Jizzax":    (67.8422, 40.1158),
    "Termiz":    (67.2783, 37.2242),
    "Guliston":  (68.7864, 40.4897),
    "Navoiy":    (65.3792, 40.0842),
    "Chirchiq":  (69.5836, 41.4686),
    "Olmaliq":   (69.5997, 40.8481),
    "Bekobod":   (69.2614, 40.2214),
}

# Yandex Search uchun kategoriya so'rovlari (rus tilida — Yandex uchun yaxshiroq)
_YANDEX_QUERY = {
    "klinika":          "клиника медицинский центр",
    "stomatologiya":    "стоматология зубной врач",
    "restoran":         "ресторан",
    "kafe":             "кафе",
    "dorixona":         "аптека",
    "go'zallik salon":  "салон красоты парикмахерская",
    "fitness markaz":   "фитнес спортзал",
    "ta'lim markaz":    "учебный центр курсы",
    "mehmonxona":       "гостиница отель",
    "optika":           "оптика очки",
    "bolalar bog'chasi":"детский сад",
}

# Shaharlar uchun taxminiy koordinatalar (lat_min, lon_min, lat_max, lon_max)
_CITY_BBOX = {
    "Toshkent":   (41.20, 69.10, 41.42, 69.45),
    "Samarqand":  (39.58, 66.82, 39.75, 67.08),
    "Buxoro":     (39.72, 64.36, 39.83, 64.52),
    "Namangan":   (40.95, 71.55, 41.05, 71.75),
    "Andijon":    (40.72, 72.28, 40.82, 72.42),
    "Farg'ona":   (40.35, 71.70, 40.45, 71.85),
    "Qarshi":     (38.83, 65.75, 38.93, 65.90),
    "Nukus":      (42.43, 59.55, 42.53, 59.70),
    "Jizzax":     (40.08, 67.78, 40.18, 67.95),
    "Termiz":     (37.20, 67.22, 37.30, 67.38),
    "Guliston":   (40.47, 68.74, 40.55, 68.85),
    "Navoiy":     (40.07, 65.33, 40.17, 65.43),
    "Chirchiq":   (41.44, 69.54, 41.52, 69.66),
    "Olmaliq":    (40.83, 69.55, 40.92, 69.65),
    "Bekobod":    (40.20, 69.20, 40.28, 69.30),
}

# OpenStreetMap amenity teglari
_AMENITY_MAP = {
    "klinika":          ["clinic", "hospital"],
    "stomatologiya":    ["dentist"],
    "restoran":         ["restaurant"],
    "kafe":             ["cafe", "fast_food"],
    "dorixona":         ["pharmacy"],
    "go'zallik salon":  ["beauty", "hairdresser"],
    "fitness markaz":   ["fitness_centre", "sports_centre"],
    "ta'lim markaz":    ["school", "college", "language_school"],
    "mehmonxona":       ["hotel", "hostel", "guest_house"],
    "optika":           ["optician"],
    "bolalar bog'chasi":["kindergarten"],
}


async def fetch_from_overpass(category: str, city: str, count: int = 20) -> list[dict]:
    """OpenStreetMap Overpass API dan bepul leads yuklaydi. Kalit shart emas."""
    bbox = _CITY_BBOX.get(city)
    if not bbox:
        return []
    amenities = _AMENITY_MAP.get(category.lower(), [])
    if not amenities:
        return []

    amenity_filter = "|".join(amenities)
    lat_min, lon_min, lat_max, lon_max = bbox
    bbox_str = f"{lat_min},{lon_min},{lat_max},{lon_max}"

    query = f"""
[out:json][timeout:25];
(
  node["amenity"~"^({amenity_filter})$"]["phone"]({bbox_str});
  way["amenity"~"^({amenity_filter})$"]["phone"]({bbox_str});
);
out center {count * 2};
"""
    url = "https://overpass-api.de/api/interpreter"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, data={"data": query},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    log.warning("Overpass %d (%s, %s)", resp.status, category, city)
                    return []
                data = await resp.json()
    except Exception as e:
        log.warning("Overpass xatosi (%s, %s): %s", category, city, e)
        return []

    results = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = (tags.get("name") or tags.get("name:uz") or tags.get("name:ru") or "").strip()
        phone = _extract_mobile_phone(tags.get("phone", "") or tags.get("contact:phone", ""))
        address = tags.get("addr:street", "") or tags.get("addr:full", "")
        if name and phone:
            results.append({
                "name": name,
                "phone": phone,
                "category": category,
                "city": city,
                "address": address,
            })
        if len(results) >= count:
            break

    log.info("Overpass (%s, %s): %d ta lead topildi", category, city, len(results))
    return results


async def fetch_from_2gis(category: str, city: str, count: int = 20) -> list[dict]:
    """2GIS API dan leads yuklaydi (subscription bo'lsa telefon ham oladi)."""
    if not config.TWOGIS_API_KEY:
        return []

    url = "https://catalog.api.2gis.com/3.0/items"
    params = {
        "q": f"{category} {city}",
        "page_size": min(count, 50),
        "fields": "items.contact_groups,items.address,items.name_ex",
        "key": config.TWOGIS_API_KEY,
        "type": "branch",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception as e:
        log.warning("2GIS xatosi (%s, %s): %s", category, city, e)
        return []

    results = []
    for item in data.get("result", {}).get("items", []):
        name = item.get("name", "").strip()
        phone = _extract_phone(item)
        address = item.get("address_name", "")
        if name and phone:
            results.append({
                "name": name,
                "phone": phone,
                "category": category,
                "city": city,
                "address": address,
            })
    log.info("2GIS (%s, %s): %d ta lead topildi", category, city, len(results))
    return results


async def fetch_from_yandex(category: str, city: str, count: int = 20) -> list[dict]:
    """Yandex Maps Search API dan leads yuklaydi. Telefon raqamlari bor."""
    if not config.YANDEX_API_KEY:
        return []
    ll = _CITY_LL.get(city)
    if not ll:
        return []
    query = _YANDEX_QUERY.get(category.lower(), category)

    url = "https://search-maps.yandex.ru/v1/"
    params = {
        "text":    f"{query} {city}",
        "lang":    "ru_RU",
        "ll":      f"{ll[0]},{ll[1]}",
        "spn":     "0.3,0.3",
        "results": min(count * 2, 50),
        "type":    "biz",
        "apikey":  config.YANDEX_API_KEY,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    log.warning("Yandex %d (%s, %s)", resp.status, category, city)
                    return []
                data = await resp.json()
    except Exception as e:
        log.warning("Yandex xatosi (%s, %s): %s", category, city, e)
        return []

    results = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        name = props.get("name", "").strip()
        meta = props.get("CompanyMetaData", {})
        address = meta.get("address", "")

        # Telefon raqamlarni olish
        phone = ""
        for ph in meta.get("Phones", []):
            raw = ph.get("formatted", "") or ph.get("number", "")
            candidate = _extract_mobile_phone(raw)
            if candidate:
                phone = candidate
                break

        if name and phone:
            results.append({
                "name":     name,
                "phone":    phone,
                "category": category,
                "city":     city,
                "address":  address,
            })
        if len(results) >= count:
            break

    log.info("Yandex (%s, %s): %d ta lead topildi", category, city, len(results))
    return results


async def fetch_leads(category: str, city: str, count: int = 20) -> list[dict]:
    """Manbalar tartibi: Yandex → Overpass → 2GIS."""
    if config.YANDEX_API_KEY:
        results = await fetch_from_yandex(category, city, count)
        if results:
            return results
    results = await fetch_from_overpass(category, city, count)
    if not results and config.TWOGIS_API_KEY:
        results = await fetch_from_2gis(category, city, count)
    return results


async def replenish(target: int = 100, categories: list = None) -> int:
    """DB dagi yangi leadlar target dan kam bo'lsa to'ldiradi."""
    current = db.count_new_leads(categories=categories)
    if current >= target:
        return 0

    needed = target - current
    added = 0

    cats = (categories or CATEGORIES).copy()
    cities = CITIES.copy()
    random.shuffle(cats)
    random.shuffle(cities)

    for cat in cats:
        if added >= needed:
            break
        for city in cities:
            if added >= needed:
                break
            items = await fetch_leads(cat, city, count=20)
            for item in items:
                if db.add_lead(**item):
                    added += 1
            await asyncio.sleep(1.5)

    log.info("Lead to'ldirildi: +%d ta (jami yangi: %d)", added, db.count_new_leads())
    return added


# ─── Batch yuborish ───────────────────────────────────────────────────────────

async def send_batch(limit: int = 10, categories: list = None) -> tuple[int, int]:
    """limit ta yangi leadga xabar yuboradi.

    categories — None bo'lsa barcha kategoriyalar, berilsa faqat o'shalar.
    Qaytaradi: (yuborildi, xato)
    Xabarlar orasida 2-5 daqiqa kutadi (flood himoyasi).
    """
    import userbot

    if not userbot.is_running():
        log.warning("Userbot ishlamayapti — outreach o'tkazildi")
        return 0, 0

    # Leadlar yetarli bo'lmasa avval to'ldiradi
    if db.count_new_leads(categories=categories) < limit:
        cats_to_fill = categories or CATEGORIES
        await replenish(target=max(limit * 3, 60), categories=cats_to_fill)

    leads = db.get_new_leads(limit, categories=categories)
    if not leads:
        log.info("Yangi lead yo'q")
        return 0, 0

    sent = 0
    failed = 0

    for i, lead in enumerate(leads):
        phone = lead["phone"]
        name = lead["name"]
        category = lead["category"] or ""
        message = outreach_message(name, category)

        result, tg_chat_id = await userbot.start_conversation(phone, message, contact_name=name)

        if result.startswith("✅"):
            db.mark_lead_sent(lead["id"], telegram_chat_id=tg_chat_id)
            sent += 1
            log.info("Lead [%d/%d] yuborildi: %s (%s)", i + 1, len(leads), name, phone)
        else:
            db.mark_lead_failed(lead["id"])
            failed += 1
            log.warning("Lead [%d/%d] xato: %s — %s", i + 1, len(leads), phone, result)

        # Oxirgi xabardan keyin kutish shart emas
        if i < len(leads) - 1:
            delay = random.uniform(120, 300)  # 2–5 daqiqa
            log.info("Keyingi leadga %.0fs kutilmoqda...", delay)
            await asyncio.sleep(delay)

    log.info("Batch yakunlandi: yuborildi=%d, xato=%d", sent, failed)
    return sent, failed
