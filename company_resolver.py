"""
company_resolver.py
===================
Energy CVC Intelligence Platform — Company Registry & Resolution

단일 책임:
  - 회사명 정규화 (normalize_name)
  - Fuzzy matching (SEED 13개 + auto 등록 회사)
  - 신규 회사 자동 등록
  - Buyer / 전략 파트너 필터

사용처:
  generate-signals.py      → CompanyResolver().resolve(name, segment)
  build_company_profile.py → CompanyResolver().load_auto_from_profiles(profiles)

파일 I/O 없음.
"""

from __future__ import annotations
import difflib, re
from typing import Optional


# ── SEED 13개 ─────────────────────────────────────────────────────────────
SEED_COMPANIES: list[dict] = [
    {"id":"c_gridwiz",    "name":"그리드위즈",     "sector":"grid_sw",   "country":"KR",
     "stage":"First Commercial","source":"registered",
     "aliases":["gridwiz","grid wiz","그리드위즈"],"watchlist_default":True},
    {"id":"c_sixtyhertz", "name":"식스티헤르츠",   "sector":"grid_sw",   "country":"KR",
     "stage":"First Commercial","source":"registered",
     "aliases":["sixty hertz","60hz","sixtyhertz","식스티헤르츠"],"watchlist_default":True},
    {"id":"c_vincen",     "name":"빈센",           "sector":"marine_fc", "country":"KR",
     "stage":"Pilot",          "source":"registered",
     "aliases":["vincen","vinsen","빈센"],"watchlist_default":False},
    {"id":"c_standard_e", "name":"스탠다드에너지", "sector":"ess",       "country":"KR",
     "stage":"Demo",           "source":"registered",
     "aliases":["standard energy","스탠다드에너지"],"watchlist_default":True},
    {"id":"c_hylium",     "name":"하이리움산업",   "sector":"hydrogen",  "country":"KR",
     "stage":"Demo",           "source":"registered",
     "aliases":["hylium","하이리움","하이리움산업"],"watchlist_default":False},
    {"id":"c_cs_energy",  "name":"씨에스에너지",   "sector":"ess",       "country":"KR",
     "stage":"First Commercial","source":"registered",
     "aliases":["cs energy","씨에스에너지"],"watchlist_default":False},
    {"id":"c_form_energy","name":"Form Energy",     "sector":"ess",       "country":"US",
     "stage":"Scaling",        "source":"registered",
     "aliases":["form energy","formenergy"],"watchlist_default":True},
    {"id":"c_autogrid",   "name":"AutoGrid",        "sector":"grid_sw",   "country":"US",
     "stage":"Scaling",        "source":"registered",
     "aliases":["autogrid","auto grid"],"watchlist_default":True},
    {"id":"c_sunfire",    "name":"Sunfire",         "sector":"hydrogen",  "country":"DE",
     "stage":"First Commercial","source":"registered",
     "aliases":["sunfire"],"watchlist_default":False},
    {"id":"c_amogy",      "name":"Amogy",           "sector":"marine_fc", "country":"US",
     "stage":"Pilot",          "source":"registered",
     "aliases":["amogy"],"watchlist_default":False},
    {"id":"c_hysata",     "name":"Hysata",          "sector":"hydrogen",  "country":"AU",
     "stage":"Pilot",          "source":"registered",
     "aliases":["hysata"],"watchlist_default":False},
    {"id":"c_ceres",      "name":"Ceres Power",     "sector":"marine_fc", "country":"UK",
     "stage":"First Commercial","source":"registered",
     "aliases":["ceres power","ceres"],"watchlist_default":False},
    {"id":"c_invinity",   "name":"Invinity Energy", "sector":"ess",       "country":"UK",
     "stage":"First Commercial","source":"registered",
     "aliases":["invinity","invinity energy"],"watchlist_default":False},
]

# ── Buyer 스킵 목록 (빈 문자열 절대 포함 금지) ─────────────────────────────
_BUYER_TERMS: tuple[str, ...] = (
    "microsoft","google","alphabet","amazon","meta","apple",
    "shell","bp","chevron","exxon","exxonmobil","totalenergies","equinor","aramco",
    "kepco","georgia power","national grid","nationalgrid",
    "engie","e.on","edf","rwe","iberdrola","vattenfall",
    "xcel energy","great river energy","duke energy","dominion energy",
    "nextera","southern company","pacific gas","pge utility",
    "한국전력","kpx","ls electric","ls일렉트릭",
    "hd hyundai","hd한국조선해양","삼성중공업","sk에코플랜트",
    "samsung heavy","hyundai heavy",
    "siemens energy","siemens gamesa","siemens","ge vernova",
    "schneider electric","hitachi energy","vestas","orsted",
)
_EXACT_SKIP: frozenset[str] = frozenset({"unassigned","n/a","tbd","unknown",""})


def normalize_name(name: str) -> str:
    n = re.sub(
        r"(?i)\b(inc|corp|ltd|llc|gmbh|co|company|group|holding|holdings"
        r"|plc|se|ag|bv|sas|sarl|ab|as|oy|nv|spa|srl|asa)\b\.?", "", name)
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", "_", n.strip().lower())
    return re.sub(r"_+", "_", n).strip("_")


def is_buyer(name: str) -> bool:
    if not name or not name.strip():
        return True
    n = name.lower().strip()
    if n in _EXACT_SKIP:
        return True
    return any(term in n for term in _BUYER_TERMS)


class CompanyResolver:
    _FUZZY_THRESHOLD = 0.82

    def __init__(self) -> None:
        self._auto: list[dict] = []

    def resolve(self, name: str, segment: str = "") -> tuple[Optional[str], Optional[str], bool]:
        if is_buyer(name):
            return None, None, False
        cid, cname = self._fuzzy_match(name, SEED_COMPANIES)
        if cid:
            return cid, cname, False
        cid, cname = self._fuzzy_match(name, self._auto)
        if cid:
            return cid, cname, False
        return self._register(name, segment)

    def resolve_from_raw_text(self, raw_text: str) -> tuple[Optional[str], Optional[str]]:
        for co in SEED_COMPANIES:
            if any(a.lower() in raw_text for a in co.get("aliases", [])):
                return co["id"], co["name"]
        return None, None

    def all_companies(self) -> list[dict]:
        return SEED_COMPANIES + self._auto

    def auto_companies(self) -> list[dict]:
        return list(self._auto)

    def seed_ids(self) -> frozenset[str]:
        return frozenset(c["id"] for c in SEED_COMPANIES)

    def load_auto_from_profiles(self, profiles: dict) -> int:
        loaded = 0
        existing_ids = {c["id"] for c in self.all_companies()}
        for cid, prof in profiles.items():
            if not isinstance(prof, dict): continue
            if prof.get("source") != "auto": continue
            if cid in existing_ids: continue
            self._auto.append({
                "id": cid, "name": prof.get("name", cid),
                "sector": prof.get("sector", ""), "country": prof.get("country", ""),
                "stage": prof.get("stage", "Lab"), "source": "auto",
                "aliases": prof.get("aliases", [cid]),
                "watchlist_default": False,
                "description": prof.get("description", "Auto-registered."),
                "tags": prof.get("tags", ["auto-registered"]),
                "known_investors": prof.get("known_investors", []),
                "investor_type": prof.get("investor_type", "Unknown"),
                "founded": prof.get("founded"), "hq": prof.get("hq", ""),
            })
            existing_ids.add(cid)
            loaded += 1
        return loaded

    def _fuzzy_match(self, name: str, pool: list[dict]) -> tuple[Optional[str], Optional[str]]:
        if not pool: return None, None
        name_l = name.lower().strip()
        norm   = normalize_name(name)
        for co in pool:
            aliases = co.get("aliases", [])
            if name_l in aliases: return co["id"], co["name"]
            if norm and norm in [normalize_name(a) for a in aliases]: return co["id"], co["name"]
            if norm and normalize_name(co.get("name", "")) == norm: return co["id"], co["name"]
        best_id, best_name, best_score = None, None, 0.0
        for co in pool:
            norm_known = normalize_name(co.get("name", ""))
            if not norm_known: continue
            score = difflib.SequenceMatcher(None, norm, norm_known).ratio()
            short, long_ = sorted([norm, norm_known], key=len)
            if short and len(short) >= 4 and short in long_:
                score = max(score, 0.87)
            if score > best_score:
                best_score, best_id, best_name = score, co["id"], co["name"]
        if best_score >= self._FUZZY_THRESHOLD:
            return best_id, best_name
        return None, None

    def _register(self, name: str, segment: str) -> tuple[str, str, bool]:
        base_id = normalize_name(name)
        if not base_id: return None, None, False  # type: ignore
        existing_ids = {c["id"] for c in self.all_companies()}
        new_id, suffix = base_id, 2
        while new_id in existing_ids:
            for co in self.all_companies():
                if co["id"] == new_id: return new_id, co["name"], False
            new_id = f"{base_id}_{suffix}"; suffix += 1
        self._auto.append({
            "id": new_id, "name": name, "sector": segment or "other",
            "country": "", "stage": "Lab", "source": "auto",
            "aliases": [name.lower(), new_id], "watchlist_default": False,
            "description": "Auto-registered from signal. Analyst review recommended.",
            "tags": ["auto-registered"], "known_investors": [],
            "investor_type": "Unknown", "founded": None, "hq": "",
        })
        return new_id, name, True
