"""Определение страны автора по свободному полю location из профиля.

resolve_country("Houston, TX") -> "US"; неопределимое -> None.
Подход: нормализация строки, затем поиск по словарям (страны, штаты/провинции,
крупные города) от последнего сегмента к первому — в Twitter-профилях страна
обычно в конце ("Calgary, Alberta", "Dubai, United Arab Emirates").
"""
from __future__ import annotations

import re
import unicodedata

# --- Страны: имя -> ISO2 (английские, самоназвания, частые варианты) ---
COUNTRIES = {
    "united states": "US", "usa": "US", "us": "US", "u.s.": "US", "u.s.a.": "US",
    "united states of america": "US", "america": "US", "estados unidos": "US",
    "murica": "US", "دبي": "AE", "الامارات العربية المتحدة": "AE",
    "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "great britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB", "britain": "GB",
    "canada": "CA", "mexico": "MX", "méxico": "MX", "brazil": "BR", "brasil": "BR",
    "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE", "venezuela": "VE",
    "ecuador": "EC", "bolivia": "BO", "uruguay": "UY", "guyana": "GY", "trinidad and tobago": "TT",
    "france": "FR", "germany": "DE", "deutschland": "DE", "spain": "ES", "españa": "ES",
    "italy": "IT", "italia": "IT", "portugal": "PT", "netherlands": "NL", "the netherlands": "NL",
    "holland": "NL", "belgium": "BE", "switzerland": "CH", "schweiz": "CH", "suisse": "CH",
    "svizzera": "CH", "austria": "AT", "österreich": "AT", "ireland": "IE", "éire": "IE",
    "norway": "NO", "norge": "NO", "sweden": "SE", "sverige": "SE", "denmark": "DK",
    "danmark": "DK", "finland": "FI", "suomi": "FI", "iceland": "IS", "poland": "PL",
    "polska": "PL", "czech republic": "CZ", "czechia": "CZ", "slovakia": "SK", "hungary": "HU",
    "romania": "RO", "românia": "RO", "bulgaria": "BG", "greece": "GR", "cyprus": "CY",
    "malta": "MT", "croatia": "HR", "serbia": "RS", "slovenia": "SI", "ukraine": "UA",
    "україна": "UA", "украина": "UA", "russia": "RU", "россия": "RU", "russian federation": "RU",
    "belarus": "BY", "estonia": "EE", "latvia": "LV", "lithuania": "LT", "moldova": "MD",
    "georgia country": "GE", "armenia": "AM", "azerbaijan": "AZ", "kazakhstan": "KZ",
    "казахстан": "KZ", "uzbekistan": "UZ", "turkmenistan": "TM", "turkey": "TR",
    "türkiye": "TR", "turkiye": "TR",
    "china": "CN", "中国": "CN", "hong kong": "HK", "taiwan": "TW", "japan": "JP", "日本": "JP",
    "south korea": "KR", "korea": "KR", "대한민국": "KR", "north korea": "KP",
    "india": "IN", "bharat": "IN", "भारत": "IN", "pakistan": "PK", "bangladesh": "BD",
    "sri lanka": "LK", "nepal": "NP", "afghanistan": "AF",
    "indonesia": "ID", "malaysia": "MY", "singapore": "SG", "singapura": "SG",
    "thailand": "TH", "vietnam": "VN", "viet nam": "VN", "philippines": "PH", "myanmar": "MM",
    "cambodia": "KH", "laos": "LA", "brunei": "BN",
    "australia": "AU", "new zealand": "NZ", "aotearoa": "NZ", "fiji": "FJ",
    "papua new guinea": "PG",
    "united arab emirates": "AE", "uae": "AE", "u.a.e.": "AE", "emirates": "AE",
    "saudi arabia": "SA", "ksa": "SA", "السعودية": "SA", "qatar": "QA", "kuwait": "KW",
    "bahrain": "BH", "oman": "OM", "yemen": "YE", "iraq": "IQ", "iran": "IR", "israel": "IL",
    "palestine": "PS", "jordan": "JO", "lebanon": "LB", "syria": "SY",
    "egypt": "EG", "libya": "LY", "algeria": "DZ", "tunisia": "TN", "morocco": "MA",
    "sudan": "SD", "nigeria": "NG", "ghana": "GH", "kenya": "KE", "ethiopia": "ET",
    "tanzania": "TZ", "uganda": "UG", "angola": "AO", "mozambique": "MZ", "zambia": "ZM",
    "zimbabwe": "ZW", "botswana": "BW", "namibia": "NA", "south africa": "ZA",
    "senegal": "SN", "ivory coast": "CI", "cote d'ivoire": "CI", "cameroon": "CM",
    "gabon": "GA", "congo": "CG", "dr congo": "CD", "chad": "TD", "niger": "NE",
    "mali": "ML", "mauritania": "MR", "equatorial guinea": "GQ",
}

# --- Штаты/провинции/регионы -> страна ---
US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "washington dc", "washington d.c.", "district of columbia", "puerto rico",
}
US_STATE_ABBR = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
    "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
    "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
    "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}
CA_PROVINCES = {
    "alberta", "british columbia", "manitoba", "new brunswick", "newfoundland",
    "nova scotia", "ontario", "quebec", "québec", "saskatchewan", "yukon",
    "bc", "ab", "on", "qc", "sk", "mb", "ns", "nb",
}
UK_REGIONS = {"greater london", "yorkshire", "midlands", "cornwall", "essex", "kent", "surrey"}
AU_STATES = {"new south wales", "nsw", "victoria au", "queensland", "western australia", "tasmania"}

# --- Крупные города (и нефтяные хабы) -> страна ---
CITIES = {
    # Северная Америка
    "new york": "US", "nyc": "US", "los angeles": "US", "chicago": "US", "houston": "US",
    "dallas": "US", "austin": "US", "san antonio": "US", "midland": "US", "denver": "US",
    "boston": "US", "miami": "US", "seattle": "US", "san francisco": "US", "atlanta": "US",
    "philadelphia": "US", "phoenix": "US", "las vegas": "US", "oklahoma city": "US",
    "tulsa": "US", "new orleans": "US", "pittsburgh": "US", "detroit": "US",
    "minneapolis": "US", "charlotte": "US", "nashville": "US", "san diego": "US",
    "portland": "US", "anchorage": "US", "washington": "US",
    "toronto": "CA", "calgary": "CA", "vancouver": "CA", "montreal": "CA", "montréal": "CA",
    "ottawa": "CA", "edmonton": "CA", "victoria bc": "CA", "winnipeg": "CA",
    "mexico city": "MX", "ciudad de mexico": "MX", "monterrey": "MX",
    # Европа
    "london": "GB", "manchester": "GB", "birmingham": "GB", "edinburgh": "GB",
    "glasgow": "GB", "aberdeen": "GB", "leeds": "GB", "liverpool": "GB", "bristol": "GB",
    "paris": "FR", "lyon": "FR", "marseille": "FR", "berlin": "DE", "munich": "DE",
    "münchen": "DE", "hamburg": "DE", "frankfurt": "DE", "cologne": "DE", "düsseldorf": "DE",
    "madrid": "ES", "barcelona": "ES", "rome": "IT", "roma": "IT", "milan": "IT",
    "milano": "IT", "amsterdam": "NL", "rotterdam": "NL", "the hague": "NL",
    "brussels": "BE", "antwerp": "BE", "zurich": "CH", "zürich": "CH", "geneva": "CH",
    "genève": "CH", "basel": "CH", "zug": "CH", "vienna": "AT", "wien": "AT",
    "dublin": "IE", "oslo": "NO", "stavanger": "NO", "bergen": "NO", "stockholm": "SE",
    "copenhagen": "DK", "københavn": "DK", "helsinki": "FI", "reykjavik": "IS",
    "warsaw": "PL", "warszawa": "PL", "prague": "CZ", "praha": "CZ", "budapest": "HU",
    "bucharest": "RO", "bucurești": "RO", "sofia": "BG", "athens": "GR", "lisbon": "PT",
    "lisboa": "PT", "nicosia": "CY", "limassol": "CY", "kyiv": "UA", "kiev": "UA",
    "moscow": "RU", "москва": "RU", "saint petersburg": "RU", "санкт-петербург": "RU",
    "istanbul": "TR", "ankara": "TR",
    # Ближний Восток и Африка
    "dubai": "AE", "abu dhabi": "AE", "sharjah": "AE", "riyadh": "SA", "jeddah": "SA",
    "dhahran": "SA", "doha": "QA", "kuwait city": "KW", "manama": "BH", "muscat": "OM",
    "baghdad": "IQ", "basra": "IQ", "tehran": "IR", "tel aviv": "IL", "jerusalem": "IL",
    "amman": "JO", "beirut": "LB", "cairo": "EG", "tripoli": "LY", "algiers": "DZ",
    "casablanca": "MA", "lagos": "NG", "abuja": "NG", "port harcourt": "NG",
    "accra": "GH", "nairobi": "KE", "johannesburg": "ZA", "cape town": "ZA",
    "luanda": "AO",
    # Азия и Океания
    "tokyo": "JP", "osaka": "JP", "seoul": "KR", "busan": "KR", "beijing": "CN",
    "shanghai": "CN", "shenzhen": "CN", "guangzhou": "CN", "hong kong": "HK",
    "taipei": "TW", "mumbai": "IN", "delhi": "IN", "new delhi": "IN", "bangalore": "IN",
    "bengaluru": "IN", "chennai": "IN", "kolkata": "IN", "hyderabad": "IN", "pune": "IN",
    "karachi": "PK", "lahore": "PK", "islamabad": "PK", "dhaka": "BD", "colombo": "LK",
    "jakarta": "ID", "kuala lumpur": "MY", "bangkok": "TH", "chiangmai": "TH",
    "chiang mai": "TH", "hanoi": "VN",
    "ho chi minh": "VN", "manila": "PH", "sydney": "AU", "melbourne": "AU",
    "perth": "AU", "brisbane": "AU", "auckland": "NZ", "wellington": "NZ",
    # Латинская Америка
    "sao paulo": "BR", "são paulo": "BR", "rio de janeiro": "BR", "brasilia": "BR",
    "buenos aires": "AR", "santiago": "CL", "bogota": "CO", "bogotá": "CO",
    "lima": "PE", "caracas": "VE", "quito": "EC", "georgetown": "GY",
}

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u200d]+"
)

# Флаги-эмодзи: пара региональных индикаторов -> ISO2
def _flag_to_iso(text: str) -> str | None:
    inds = [c for c in text if 0x1F1E6 <= ord(c) <= 0x1F1FF]
    if len(inds) >= 2:
        return chr(ord(inds[0]) - 0x1F1E6 + 65) + chr(ord(inds[1]) - 0x1F1E6 + 65)
    return None


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).strip().lower()
    s = _EMOJI_RE.sub(" ", s)
    s = s.replace("#", " ").replace("|", ",").replace("/", ",").replace("•", ",")
    s = re.sub(r"\s+", " ", s)
    return s.strip(" ,.-")


def resolve_country(location: str) -> str | None:
    if not location or not location.strip():
        return None
    flag = _flag_to_iso(location)

    norm = _normalize(location)
    if not norm:
        return flag

    # Полная строка целиком
    if norm in COUNTRIES:
        return COUNTRIES[norm]
    if norm in CITIES:
        return CITIES[norm]

    # По сегментам с конца (страна обычно последняя)
    segments = [seg.strip(" .") for seg in norm.split(",") if seg.strip(" .")]
    for seg in reversed(segments):
        if seg in COUNTRIES:
            return COUNTRIES[seg]
        if seg in US_STATES or seg in US_STATE_ABBR:
            return "US"
        if seg in CA_PROVINCES:
            return "CA"
        if seg in UK_REGIONS:
            return "GB"
    for seg in segments:
        if seg in CITIES:
            return CITIES[seg]

    # Пословный проход (для "Victoria BC Canada", "East Norway")
    words = norm.replace(",", " ").split()
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i : i + n])
            if phrase in COUNTRIES:
                return COUNTRIES[phrase]
    for n in (3, 2):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i : i + n])
            if phrase in CITIES:
                return CITIES[phrase]
            if phrase in US_STATES:
                return "US"
            if phrase in CA_PROVINCES:
                return "CA"
    for w in words:
        if w in CITIES:
            return CITIES[w]
        if w in US_STATES:
            return "US"
        if w in CA_PROVINCES and len(w) > 2:
            return "CA"

    return flag
