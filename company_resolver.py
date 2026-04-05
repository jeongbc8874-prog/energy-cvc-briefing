"""
company_resolver.py
===================
Energy CVC Intelligence Platform — Company Registry & Resolution

단일 책임:
  - 회사명 정규화 (normalize_name)
  - Fuzzy matching (SEED 13개 + auto 등록 회사)
  - 신규 회사 자동 등록
  - Buyer / 전략 파트너 필터 (프로필 생성 제외)

사용처:
  generate-signals.py       → CompanyResolver().resolve(name, segment)
  build_company_profile.py  → CompanyResolver().load_auto_from_profiles(profiles)

파일 I/O 없음. 영속성은 build_company_profile.py가 담당.
"""

from __future__ import annotations

import difflib
import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────
# 등록 회사 시드 (generate-signals.py COMPANIES와 동기화)
# ─────────────────────────────────────────────────────────────────────────
SEED_COMPANIES: list[dict] = [
    # ── Korean ──────────────────────────────────────────────────────────
    {"id":"c_gridwiz",    "name":"그리드위즈",     "sector":"grid_sw",   "country":"KR",
     "stage":"First Commercial", "source":"registered",
     "aliases":["gridwiz","grid wiz","그리드위즈"],
     "watchlist_default":True,
     "description":"KPX-certified VPP/DR platform operator."},
    {"id":"c_sixtyhertz", "name":"식스티헤르츠",   "sector":"grid_sw",   "country":"KR",
     "stage":"First Commercial", "source":"registered",
     "aliases":["sixty hertz","60hz","sixtyhertz","식스티헤르츠"],
     "watchlist_default":True,
     "description":"AI-powered renewable energy forecasting."},
    {"id":"c_vincen",     "name":"빈센",           "sector":"marine_fc", "country":"KR",
     "stage":"Pilot",            "source":"registered",
     "aliases":["vincen","vinsen","빈센"],
     "watchlist_default":False,
     "description":"Marine hydrogen PEM fuel cell."},
    {"id":"c_standard_e", "name":"스탠다드에너지", "sector":"ess",       "country":"KR",
     "stage":"Demo",             "source":"registered",
     "aliases":["standard energy","스탠다드에너지"],
     "watchlist_default":True,
     "description":"Vanadium redox flow battery."},
    {"id":"c_hylium",     "name":"하이리움산업",   "sector":"hydrogen",  "country":"KR",
     "stage":"Demo",             "source":"registered",
     "aliases":["hylium","하이리움","하이리움산업"],
     "watchlist_default":False,
     "description":"Liquid hydrogen plant operator."},
    {"id":"c_cs_energy",  "name":"씨에스에너지",   "sector":"ess",       "country":"KR",
     "stage":"First Commercial", "source":"registered",
     "aliases":["cs energy","씨에스에너지"],
     "watchlist_default":False,
     "description":"ESS system integrator."},
    # ── Global ──────────────────────────────────────────────────────────
    {"id":"c_form_energy","name":"Form Energy",     "sector":"ess",       "country":"US",
     "stage":"Scaling",          "source":"registered",
     "aliases":["form energy","formenergy"],
     "watchlist_default":True,
     "description":"Iron-air 100h+ LDES."},
    {"id":"c_autogrid",   "name":"AutoGrid",        "sector":"grid_sw",   "country":"US",
     "stage":"Scaling",          "source":"registered",
     "aliases":["autogrid","auto grid"],
     "watchlist_default":True,
     "description":"VPP/Energy Intelligence Platform."},
    {"id":"c_sunfire",    "name":"Sunfire",         "sector":"hydrogen",  "country":"DE",
     "stage":"First Commercial", "source":"registered",
     "aliases":["sunfire"],
     "watchlist_default":False,
     "description":"SOEC electrolyzer."},
    {"id":"c_amogy",      "name":"Amogy",           "sector":"marine_fc", "country":"US",
     "stage":"Pilot",            "source":"registered",
     "aliases":["amogy"],
     "watchlist_default":False,
     "description":"Ammonia-to-power marine fuel cell."},
    {"id":"c_hysata",     "name":"Hysata",          "sector":"hydrogen",  "country":"AU",
     "stage":"Pilot",            "source":"registered",
     "aliases":["hysata"],
     "watchlist_default":False,
     "description":"Capillary-fed electrolyzer."},
    {"id":"c_ceres",      "name":"Ceres Power",     "sector":"marine_fc", "country":"UK",
     "stage":"First Commercial", "source":"registered",
     "aliases":["ceres power","ceres"],
     "watchlist_default":False,
     "description":"SOFC platform licensor."},
    {"id":"c_invinity",   "name":"Invinity Energy", "sector":"ess",       "country":"UK",
     "stage":"First Commercial", "source":"registered",
     "aliases":["invinity","invinity energy"],
     "watchlist_default":False,
     "description":"Vanadium flow battery manufacturer."},
]

# ─────────────────────────────────────────────────────────────────────────
# Buyer 스킵 목록 — 회사 프로필 생성 제외
# ※ 빈 문자열 절대 포함 금지 (any('' in s) 는 항상 True)
# ─────────────────────────────────────────────────────────────────────────
_BUYER_TERMS: tuple[str, ...] = (
    # Hyperscalers
    "microsoft", "google", "alphabet", "amazon", "meta", "apple",
    # Oil Majors
    "shell", "bp", "chevron", "exxon", "exxonmobil",
    "totalenergies", "equinor", "aramco",
    # Utilities
    "kepco", "georgia power", "national grid", "nationalgrid",
    "engie", "e.on", "edf", "rwe", "iberdrola", "vattenfall",
    "xcel energy", "great river energy", "duke energy",
    "dominion energy", "nextera", "southern company",
    "pacific gas", "pge utility",
    # Korean industrials / buyers
    "한국전력", "kpx", "ls electric", "ls일렉트릭",
    "hd hyundai", "hd한국조선해양", "삼성중공업",
    "sk에코플랜트", "sk ecoplant",
    "samsung heavy", "hyundai heavy",
    # OEMs / EPCs
    "siemens energy", "siemens gamesa", "siemens",
    "ge vernova", "schneider electric", "hitachi energy",
    "vestas", "orsted",
)

# 전체 단어가 "unassigned"이거나 빈 이름인 경우도 제외
_EXACT_SKIP: frozenset[str] = frozenset({"unassigned", "n/a", "tbd", "unknown"})


def normalize_name(name: str) -> str:
    """
    'Form Energy Inc.'  → 'form_energy'
    'H2 Green Steel AB' → 'h2_green_steel'
    'E.ON SE'           → 'e_on'
    """
    # 법인 접미사 제거
    n = re.sub(
        r"(?i)\b(inc|corp|ltd|llc|gmbh|co|company|group"
        r"|holding|holdings|plc|se|ag|bv|sas|sarl"
        r"|ab|as|oy|nv|spa|srl|asa)\b\.?",
        "", name,
    )
    n = re.sub(r"[^\w\s]", " ", n)          # 특수문자 → 공백
    n = re.sub(r"\s+", "_", n.strip().lower())
    return re.sub(r"_+", "_", n).strip("_")


def is_buyer(name: str) -> bool:
    """
    True 이면 회사 프로필 생성 제외.
    - 이름이 없거나 'unassigned' 등
    - 알려진 buyer / 전략 파트너
    """
    if not name or not name.strip():
        return True
    n = name.lower().strip()
    if n in _EXACT_SKIP:
        return True
    # 부분 포함 매칭 (단어 단위로 확인)
    return any(term in n for term in _BUYER_TERMS)


# ─────────────────────────────────────────────────────────────────────────
# CompanyResolver
# ─────────────────────────────────────────────────────────────────────────

class CompanyResolver:
    """
    회사명 → company_id 변환 + 자동 등록 싱글 레지스트리.

    패턴:
        resolver = CompanyResolver()
        resolver.load_auto_from_profiles(profiles_dict)   # 기존 auto 복원
        co_id, co_name, is_new = resolver.resolve("Northvolt", "ess")
        all_cos = resolver.all_companies()                 # SEED + auto

    파일 I/O 없음.
    """

    _FUZZY_THRESHOLD = 0.82

    def __init__(self) -> None:
        self._auto: list[dict] = []

    # ── 공개 인터페이스 ───────────────────────────────────────────────────

    def resolve(
        self,
        name: str,
        segment: str = "",
    ) -> tuple[Optional[str], Optional[str], bool]:
        """
        Returns (co_id, co_name, is_new).
        is_new=True  : 이 호출에서 처음 등록됨
        (None,None,False) : buyer skip 또는 빈 이름
        """
        if is_buyer(name):
            return None, None, False

        # 1. SEED
        cid, cname = self._fuzzy_match(name, SEED_COMPANIES)
        if cid:
            return cid, cname, False

        # 2. auto 레지스트리
        cid, cname = self._fuzzy_match(name, self._auto)
        if cid:
            return cid, cname, False

        # 3. 신규 등록
        return self._register(name, segment)

    def resolve_from_raw_text(
        self,
        raw_text: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        raw_text에서 SEED alias 직접 탐색 (generate-signals.py match_company 대체).
        Returns (co_id, co_name) or (None, None).
        """
        for co in SEED_COMPANIES:
            if any(a.lower() in raw_text for a in co.get("aliases", [])):
                return co["id"], co["name"]
        return None, None

    def all_companies(self) -> list[dict]:
        """SEED + auto 전체."""
        return SEED_COMPANIES + self._auto

    def auto_companies(self) -> list[dict]:
        """auto 등록 회사만."""
        return list(self._auto)

    def seed_ids(self) -> frozenset[str]:
        return frozenset(c["id"] for c in SEED_COMPANIES)

    def load_auto_from_profiles(self, profiles: dict) -> int:
        """
        company_profiles.json 내용에서 source='auto' 항목을 _auto에 복원.
        build_company_profile.py가 파일을 읽은 후 이 메서드를 호출한다.
        Returns 복원된 회사 수.
        """
        loaded = 0
        existing_ids = {c["id"] for c in self.all_companies()}
        for cid, prof in profiles.items():
            if not isinstance(prof, dict):
                continue
            if prof.get("source") != "auto":
                continue
            if cid in existing_ids:
                continue
            self._auto.append({
                "id":              cid,
                "name":            prof.get("name", cid),
                "sector":          prof.get("sector", ""),
                "country":         prof.get("country", ""),
                "stage":           prof.get("stage", "Lab"),
                "source":          "auto",
                "aliases":         prof.get("aliases", [cid]),
                "watchlist_default": False,
                "description":     prof.get("description", "Auto-registered."),
                "tags":            prof.get("tags", ["auto-registered"]),
                "known_investors": prof.get("known_investors", []),
                "investor_type":   prof.get("investor_type", "Unknown"),
                "founded":         prof.get("founded"),
                "hq":              prof.get("hq", ""),
            })
            existing_ids.add(cid)
            loaded += 1
        return loaded

    # ── 내부 ─────────────────────────────────────────────────────────────

    def _fuzzy_match(
        self,
        name: str,
        pool: list[dict],
    ) -> tuple[Optional[str], Optional[str]]:
        """pool에서 fuzzy match. (co_id, co_name) or (None, None)."""
        if not pool:
            return None, None

        name_l = name.lower().strip()
        norm   = normalize_name(name)

        # 정확 매칭 (alias / 이름)
        for co in pool:
            aliases = co.get("aliases", [])
            # alias 직접 포함
            if name_l in aliases:
                return co["id"], co["name"]
            # normalize된 alias 포함
            if norm and norm in [normalize_name(a) for a in aliases]:
                return co["id"], co["name"]
            # normalize된 이름 일치
            if norm and normalize_name(co.get("name", "")) == norm:
                return co["id"], co["name"]

        # difflib ratio 기반 fuzzy
        best_id: Optional[str] = None
        best_name: Optional[str] = None
        best_score = 0.0
        for co in pool:
            norm_known = normalize_name(co.get("name", ""))
            if not norm_known:
                continue
            score = difflib.SequenceMatcher(None, norm, norm_known).ratio()
            # 짧은 쪽이 긴 쪽에 포함되면 보너스
            short, long_ = sorted([norm, norm_known], key=len)
            if short and len(short) >= 4 and short in long_:
                score = max(score, 0.87)
            if score > best_score:
                best_score = score
                best_id    = co["id"]
                best_name  = co["name"]

        if best_score >= self._FUZZY_THRESHOLD:
            return best_id, best_name
        return None, None

    def _register(
        self,
        name: str,
        segment: str,
    ) -> tuple[str, str, bool]:
        """신규 auto 회사 등록. Returns (co_id, co_name, is_new=True)."""
        base_id = normalize_name(name)
        if not base_id:
            return None, None, False  # type: ignore[return-value]

        existing_ids = {c["id"] for c in self.all_companies()}

        # 충돌 없으면 그대로, 있으면 suffix
        new_id = base_id
        suffix = 2
        while new_id in existing_ids:
            # 같은 이름의 기존 항목이면 그냥 반환
            for co in self.all_companies():
                if co["id"] == new_id:
                    return new_id, co["name"], False
            new_id = f"{base_id}_{suffix}"
            suffix += 1

        new_co: dict = {
            "id":              new_id,
            "name":            name,
            "sector":          segment or "other",
            "country":         "",
            "stage":           "Lab",
            "source":          "auto",
            "aliases":         [name.lower(), new_id],
            "watchlist_default": False,
            "description":     "Auto-registered from signal. Analyst review recommended.",
            "tags":            ["auto-registered"],
            "known_investors": [],
            "investor_type":   "Unknown",
            "founded":         None,
            "hq":              "",
        }
        self._auto.append(new_co)
        return new_id, name, True
