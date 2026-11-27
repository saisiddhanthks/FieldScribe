"""
Code-mixed Indian dictation: Hindi and Kannada, in their own scripts or typed/heard in Latin letters,
mixed with English clinical words (the way 108 crews actually speak).

Pipeline (runs before English normalisation and NER):
  1. Native digits → ASCII   (३०० / ೩೦೦ → 300)
  2. Devanagari / Kannada script → simple Latin   (सीने में दर्द → sine men dard, ಎದೆ ನೋವು → ede novu)
  3. Clinical phrases, numbers and grammar words → English   (sine men dard → chest pain, teen sau → 300,
     45 saal ka aadmi → 45 years male, ede novu → chest pain, munnooru → 300, kottiddini → given)

No network and no model: a lookup table that a clinician can read and extend.
"""
from __future__ import annotations

import re

# ----------------------------------------------------------------------------- 1. digits

_DIGITS = {**{chr(0x0966 + i): str(i) for i in range(10)}, **{chr(0x0CE6 + i): str(i) for i in range(10)}}

# ----------------------------------------------------------------------------- 2. script → Latin
# Kannada (U+0C80) and Devanagari (U+0900) share the ISCII layout, so Kannada is shifted onto
# Devanagari code points and one table romanises both.
_KN_SHIFT = 0x0C80 - 0x0900

_V = {  # independent vowels
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "ऎ": "e", "ऒ": "o", "ऍ": "e", "ऑ": "o",
}
_M = {  # dependent vowel signs (matras)
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ॆ": "e", "ॊ": "o", "ॅ": "e", "ॉ": "o",
}
_C = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l", "ऱ": "r", "ऴ": "l",
}
_NUKTA = {"ज": "z", "फ": "f", "ड": "r", "ढ": "rh", "क": "q", "ख": "kh", "ग": "g"}
_VIRAMA, _ANUSVARA, _CANDRA, _VISARGA, _NUKTA_SIGN = "्", "ं", "ँ", "ः", "़"


def has_indic(text: str) -> bool:
    return bool(re.search(r"[ऀ-ॿಀ-೿]", text))


def _shift(ch: str) -> str:
    o = ord(ch)
    return chr(o - _KN_SHIFT) if 0x0C80 <= o <= 0x0CFF else ch


def _word(chars: list[str], kannada: bool) -> str:
    # syllables: [consonant cluster, vowel, kind]  kind: "inh" inherent a, "exp" written vowel, "none" (virama / bare)
    syl: list[list[str]] = []
    pend = ""                      # consonants joined by virama (conjuncts)
    i = 0
    while i < len(chars):
        c = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if c in _C:
            cons = _C[c]
            if nxt == _NUKTA_SIGN:
                cons = _NUKTA.get(c, cons)
                i += 1
                nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt == _VIRAMA:
                pend += cons
                i += 2
                continue
            if nxt in _M:
                syl.append([pend + cons, _M[nxt], "exp"])
                i += 2
            else:
                syl.append([pend + cons, "a", "inh"])
                i += 1
            pend = ""
            continue
        if pend:
            syl.append([pend, "", "none"])
            pend = ""
        if c in _V:
            syl.append(["", _V[c], "exp"])
        elif c in _M:
            syl.append(["", _M[c], "exp"])
        elif c in (_ANUSVARA, _CANDRA):
            if syl:
                syl[-1][1] += "m" if nxt in ("प", "फ", "ब", "भ", "म") else "n"
                if syl[-1][2] == "inh":
                    syl[-1][2] = "exp"       # सं = san: the a is pronounced
        elif c == _VISARGA:
            syl.append(["", "h", "exp"])
        elif c in ("।", "॥"):
            syl.append(["", ".", "exp"])
        i += 1
    if pend:
        syl.append([pend, "", "none"])
    if not kannada and syl:
        # Hindi schwa deletion: final inherent a is silent (दर्द → dard), and so is a medial one between
        # two pronounced syllables (आदमी → admi, कमज़ोरी → kamzori)
        if syl[-1][2] == "inh" and len(syl) > 1:
            syl[-1][1] = ""
        for k in range(1, len(syl) - 1):
            if syl[k][2] == "inh" and syl[k + 1][2] == "exp" and syl[k - 1][1] and syl[k + 1][0]:
                syl[k][1] = ""
                break
    return "".join(c + v for c, v, _ in syl)


def romanise(text: str) -> str:
    """Devanagari / Kannada → plain lowercase Latin (long vowels written single, for matching English drug names)."""
    text = "".join(_DIGITS.get(c, c) for c in text)
    out: list[str] = []
    for word in re.split(r"([^\u0900-\u097F\u0C80-\u0CFF]+)", text):
        if not word or not has_indic(word):
            out.append(word)
            continue
        kannada = bool(re.search(r"[\u0C80-\u0CFF]", word))
        out.append(_word([_shift(c) for c in word], kannada))
    return "".join(out)


# ----------------------------------------------------------------------------- 3. phrases → English
# Keys are lowercase Latin: both how crews type Hinglish/Kanglish and how romanise() spells the scripts.
# Longer keys are applied first.

PHRASES_HI: dict[str, str] = {
    # ---- Hindi: complaints
    "seene mein dard": "chest pain", "sine men dard": "chest pain", "seene me dard": "chest pain", "chhati mein dard": "chest pain",
    "chhati men dard": "chest pain", "chhati me dard": "chest pain", "chhaati mein dard": "chest pain", "dil mein dard": "chest pain",
    "saans lene mein takleef": "shortness of breath", "saans lene mein dikkat": "shortness of breath", "sans lene men taklif": "shortness of breath",
    "sans lene men dikkat": "shortness of breath", "saans phool rahi": "shortness of breath", "saans phoolna": "shortness of breath",
    "saans nahi le raha": "not breathing", "sans nahin le raha": "not breathing", "saans nahi": "not breathing", "saans": "breathing",
    "behosh": "unconscious", "behos": "unconscious", "hosh mein nahi": "unconscious", "hosh men nahin": "unconscious", "hosh mein": "conscious", "hosh men": "conscious", "hosh men ai": "conscious", "hosh mein aayi": "conscious",
    "chakkar aa raha": "dizziness", "chakkar": "dizziness", "ulti": "vomiting", "ultee": "vomiting", "dast": "diarrhoea",
    "khoon beh raha": "bleeding", "khun bah raha": "bleeding", "khoon": "bleeding", "khun": "bleeding",
    "bukhar": "fever", "bukhaar": "fever", "daura pada": "seizure", "daura": "seizure", "mirgi": "seizure", "jhatke": "seizure",
    "sugar kam": "low sugar", "sugar low": "low sugar", "sar pe chot": "head injury", "sir pe chot": "head injury", "sar mein chot": "head injury",
    "sir men chot": "head injury", "chot": "injury", "haddi tooti": "fracture", "haddi tut gayi": "fracture", "haddi": "bone",
    "jal gaya": "burns", "jal gayi": "burns", "jalna": "burns", "zeher kha liya": "poisoning", "zahar kha liya": "poisoning",
    "keetnashak": "insecticide", "kitnashak": "insecticide", "pet mein dard": "abdominal pain", "pet men dard": "abdominal pain",
    "sar dard": "headache", "sir dard": "headache", "dard": "pain", "kamzori": "weakness", "lakwa": "stroke", "laqwa": "stroke",
    "muh tedha": "facial droop", "munh tedha": "facial droop", "haath kamzor": "arm weakness", "bolne mein dikkat": "slurred speech",
    "sujan": "swelling", "soojan": "swelling", "honth suj gaye": "lip swelling", "kida kaat liya": "bite", "saanp ne kaata": "snake bite",
    "saamp ne kata": "snake bite", "kutte ne kaata": "dog bite", "girne se": "fall", "gir gaya": "fall", "gir gayi": "fall",
    "upar se gira": "fall from height", "accident hua": "accident", "gaadi ne takkar mari": "road traffic accident", "takkar": "collision",
    "garbhvati": "pregnant", "pregnant hai": "pregnant", "dard shuru": "labour pain",
    # ---- Hindi: people, age
    "saal ka": "years", "saal ki": "years", "sal ka": "years", "sal ki": "years", "saal": "years", "sal": "years", "mahine ka": "months",
    "aadmi": "male", "admi": "male", "purush": "male", "ladka": "boy", "aurat": "female", "auarat": "female", "mahila": "female",
    "ladki": "girl", "baccha": "child", "bachcha": "child", "bachche": "child", "buzurg": "elderly", "marij": "patient", "mareez": "patient",
    # ---- Hindi: routes, forms, actions
    "muh se": "oral", "munh se": "oral", "muh men": "oral", "jeebh ke neeche": "sublingual", "jibh ke niche": "sublingual",
    "zuban ke neeche": "sublingual", "nas mein": "iv", "nas men": "iv", "nas se": "iv", "injection diya": "injection given",
    "goli": "tablet", "goliyan": "tablets", "dawai": "medicine", "dava": "medicine", "bottle chadhayi": "infusion started",
    "drip lagayi": "drip started", "oxygen lagaya": "oxygen started", "oxygen chalu": "oxygen started", "patti bandhi": "dressing applied",
    "patti": "dressing", "dabaav diya": "pressure applied", "daba ke rakha": "pressure applied",
    "de diya": "given", "de di": "given", "diya gaya": "given", "diya": "given", "diyaa": "given", "di gayi": "given", "di": "given",
    "nahi diya": "not given", "nahin diya": "not given", "mana kar diya": "refused", "mana kiya": "refused",
    "patti lagayi": "dressing applied", "patti lagaya": "dressing applied",
    "mask se lagaya": "by mask", "mask se lagayi": "by mask", "shugar kam": "low sugar", "gira": "fall", "giri": "fall",
    "lagaya": "applied", "lagayi": "applied", "chadhaya": "infused", "chalu kiya": "started", "shuru kiya": "started",
    # ---- Hindi: time & glue
    "minute baad": "minutes later", "minat bad": "minutes later", "minute pehle": "minutes ago", "abhi": "now", "phir se": "again",
    "baje": "hrs", "bje": "hrs", "phir": "then", "aur": "and", "lekin": "but", "haan": "yes", "nahi": "not", "nahin": "not",
    "mein": "", "men": "", "ko": "", "ka": "", "ki": "", "ke": "", "hai": "", "he": "", "tha": "", "thi": "", "hua": "", "hui": "", "gaya": "",
    "gayi": "", "raha": "", "rahi": "", "se": "", "par": "", "pe": "", "bhi": "", "ne": "",
    # units heard/written in Devanagari
    "miligram": "mg", "miligrem": "mg", "emji": "mg", "em ji": "mg", "mi.gra.": "mg", "mililitar": "ml", "mililitre": "ml", "emel": "ml",
    "em el": "ml", "litar": "litres", "litre prati minat": "litres per minute", "maikrogram": "mcg",
    "chaba ke": "chewed", "chabake": "chewed", "chaba": "chewed", "chabakar": "chewed",
    "adami": "male", "aadami": "male", "larka": "boy", "larki": "girl", "kamazori": "weakness", "behosha": "unconscious",
}

PHRASES_KN: dict[str, str] = {
    # ---- Kannada: complaints
    "ede novu": "chest pain", "edenovu": "chest pain", "ede nov": "chest pain", "edeyalli novu": "chest pain",
    "usiraata tondare": "shortness of breath", "usiratada tondare": "shortness of breath", "usirata tondare": "shortness of breath",
    "usiru kashta": "shortness of breath", "usirata kashta": "shortness of breath", "usiraadta illa": "not breathing", "usiru illa": "not breathing",
    "usiru": "breathing", "prajne illa": "unconscious", "prajne illade": "unconscious", "prajna illa": "unconscious", "prajnahina": "unconscious",
    "prajne ide": "conscious", "tale suttu": "dizziness", "talesuttu": "dizziness", "vanti": "vomiting", "bedhi": "diarrhoea",
    "rakta baruttide": "bleeding", "rakta hogtide": "bleeding", "raktasrava": "bleeding", "rakta": "bleeding", "jvara": "fever", "jwara": "fever",
    "fits bantu": "seizure", "fits banthu": "seizure", "murchhe": "seizure", "sakkare kammi": "low sugar", "sugar kammi": "low sugar",
    "talege pettu": "head injury", "tale ge pettu": "head injury", "talege etu": "head injury", "pettu": "injury", "etu": "injury",
    "mule muridide": "fracture", "mule": "bone", "suttide": "burns", "sutta gaya": "burns", "visha kudididdare": "poisoning",
    "visha": "poison", "kritinashaka": "insecticide", "hotte novu": "abdominal pain", "tale novu": "headache", "novu": "pain",
    "pakshavata": "stroke", "bayi sotte": "facial droop", "maatu todaru": "slurred speech", "bavu": "swelling", "haavu kachchide": "snake bite",
    "havu kachide": "snake bite", "nayi kachide": "dog bite", "biddu": "fall", "melinda biddu": "fall from height", "apaghata": "accident",
    "apaghaata": "accident", "garbhini": "pregnant", "heriga novu": "labour pain",
    # ---- Kannada: people, age
    "varshada": "years", "varsha": "years", "varsa": "years", "vayassu": "age", "tingala": "months",
    "gandasu": "male", "gandsu": "male", "purusha": "male", "huduga": "boy", "hengasu": "female", "hengsu": "female", "mahile": "female",
    "hudugi": "girl", "magu": "child", "maguvige": "child", "hiriyaru": "elderly", "rogi": "patient", "rogige": "patient",
    # ---- Kannada: routes, actions
    "bayalli": "oral", "baayalli": "oral", "bayi mulaka": "oral", "nalige kelage": "sublingual", "naalige kelage": "sublingual",
    "nara ge": "iv", "naralli": "iv", "injekshan kottiddini": "injection given", "matre": "tablet", "maatre": "tablet", "oushadha": "medicine",
    "kottiddini": "given", "kottidini": "given", "kottiddeve": "given", "kottidivi": "given", "kottide": "given", "kotte": "given",
    "kottu": "given", "kodalaagide": "given", "kodalagide": "given", "kodu": "given", "kottilla": "not given", "kodalilla": "not given",
    "patti haakiddini": "dressing applied", "bandage haakiddini": "dressing applied",
    "mask mulaka haakiddini": "by mask", "maskalli haakiddini": "by mask",
    "haakiddini": "applied", "haakide": "applied", "haaki": "applied", "hakide": "applied", "shuru maadide": "started", "shuru madide": "started",
    "maadiddini": "done", "maadide": "done", "madide": "done", "beda andru": "refused", "nirakarisidaru": "refused",
    # ---- Kannada: time & glue
    "nimisha nantara": "minutes later", "nimisha": "minutes", "gante": "hrs", "ganta": "hrs", "mattu": "and", "aadare": "but", "haudu": "yes",
    "illa": "not", "ide": "", "ige": "", "alli": "", "inda": "", "ge": "", "u": "",
}

# number words (both languages); the existing English number parser takes over after this
NUM_HI: dict[str, float] = {
    # Hindi
    "ek": 1, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6, "saat": 7, "sat": 7, "aath": 8,
    "ath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15, "bees": 20, "bis": 20, "pachchees": 25, "tees": 30, "chalis": 40,
    "chaalis": 40, "pachas": 50, "pachaas": 50, "assi": 80, "nabbe": 90, "dedh": 1.5, "dhai": 2.5, "aadha": 0.5, "adha": 0.5,
}
NUM_KN: dict[str, float] = {
    # Kannada
    "ondu": 1, "eradu": 2, "mooru": 3, "muru": 3, "naalku": 4, "nalku": 4, "aidu": 5, "aaru": 6, "elu": 7, "eelu": 7, "entu": 8,
    "ombattu": 9, "hattu": 10, "hadinaidu": 15, "ippattu": 20, "moovattu": 30, "muvattu": 30, "nalavattu": 40, "aivattu": 50,
    "aravattu": 60, "eppattu": 70, "embattu": 80, "tombattu": 90, "nooru": 100, "nuru": 100, "innooru": 200, "innuru": 200,
    "munnooru": 300, "munnuru": 300, "naanooru": 400, "nanuru": 400, "ainooru": 500, "ainuru": 500, "saavira": 1000, "savira": 1000,
    "ardha": 0.5,
}
# English clinical words as Whisper spells them in Devanagari or Kannada script (after romanise)
LOANWORDS: dict[str, str] = {
    "nebyulaiseshan": "nebulisation", "nebulaizeshan": "nebulisation", "nebulaijeshan": "nebulisation", "nebulaiser": "nebuliser",
    "nebyulaizeshan": "nebulisation", "injekshan": "injection", "injekshn": "injection", "injakshan": "injection", "injeshan": "injection",
    "aksijan": "oxygen", "oksijan": "oxygen", "aksijana": "oxygen", "oksijana": "oxygen", "salain": "saline", "selain": "saline",
    "shugar": "sugar", "bi pi": "bp", "bipi": "bp", "pals": "pulse", "es pi o tu": "spo2", "spo tu": "spo2", "sirap": "syrup",
    "tebalet": "tablet", "tabalet": "tablet", "teblet": "tablet", "glukoj": "glucose", "glukoz": "glucose", "glukos": "glucose",
    "dekstroj": "dextrose", "dekstros": "dextrose", "edrinalin": "adrenaline", "adrinalin": "adrenaline", "edrenalin": "adrenaline",
    "adrenalin": "adrenaline", "paresitamol": "paracetamol", "parasitamol": "paracetamol", "perasitamol": "paracetamol",
    "ondansetran": "ondansetron", "ekosprin": "ecosprin", "ikosprin": "ecosprin", "salbutamal": "salbutamol", "salbyutamol": "salbutamol",
    "esprin": "aspirin", "espirin": "aspirin", "aspirin": "aspirin", "aiwi": "iv", "ai vi": "iv", "ai em": "im", "isiji": "ecg",
    "i si ji": "ecg", "ji si es": "gcs", "jisies": "gcs", "ambyulens": "ambulance", "ambulens": "ambulance", "mililitar": "ml",
    "nayitroglisarin": "nitroglycerin", "naitroglisarin": "nitroglycerin", "sorbitret": "sorbitrate", "avil": "avil",
    "midajolam": "midazolam", "midazolam": "midazolam", "dayajepam": "diazepam", "dayazepam": "diazepam", "lorajepam": "lorazepam",
    "hidrokortison": "hydrocortisone", "haidrokortison": "hydrocortisone", "trenejamik": "tranexamic", "tranejamik": "tranexamic",
    "ringar": "ringer", "ringar lektet": "ringer lactate", "ar el": "rl", "noraml salain": "normal saline", "naurmal salain": "normal saline",
    "normal salain": "normal saline", "si pi ar": "cpr", "sipiar": "cpr",
    "dekstroz": "dextrose", "pratishat": "percent", "pratishata": "percent", "emael": "ml", "emal": "ml", "mariz": "patient",
    "tieksae": "txa", "tiekse": "txa", "ti eks e": "txa", "tiexae": "txa", "gram": "g", "graam": "g",
    "mask se": "by mask", "maskalli": "by mask", "mask nalli": "by mask", "mask mulaka": "by mask",
}

PHRASES: dict[str, str] = {**LOANWORDS, **PHRASES_HI, **PHRASES_KN}
NUMBERS: dict[str, float] = {**NUM_HI, **NUM_KN}
KANNADA_KEYS = set(PHRASES_KN) | set(NUM_KN)

SCALES = {"sau": 100, "so": 100, "hazaar": 1000, "hazar": 1000, "nooru": 100, "nuru": 100}

# "do" (2) is also an English word: only a number when a unit or 'sau' follows
_DO = re.compile(r"\bdo(?=\s+(?:sau|so|hazaar|mg|ml|mcg|g|litre|litres|liter|tablet|tablets|goli|minute|minutes|saal|years|puff|puffs|units?)\b)")

# Words that are also English (or too short to trust): they only count once other evidence says the text is code-mixed.
AMBIGUOUS = {"he", "se", "pe", "di", "par", "ne", "u", "ge", "ide", "ige", "alli", "inda", "ka", "ki", "ke", "ko", "men", "mein", "sat", "tin",
             "so", "das", "bis", "ath", "char", "elu", "tha", "thi", "hai", "hui", "hua", "raha", "rahi", "gaya", "gayi", "abhi", "teen", "sal",
             "aur", "phir", "dard", "etu", "mule", "visha", "kodu", "kottu", "haaki", "khun", "dava", "patti", "sujan", "nimisha", "chot",
             "biddu", "magu", "ek", "nau", "sugar low", "admi", "ardha", "dast", "bavu", "gante", "ganta", "illa", "u"}
_STRONG = re.compile(r"(?<![a-z])(" + "|".join(re.escape(k) for k in sorted(
    [k for k in list(PHRASES_HI) + list(PHRASES_KN) + list(NUM_HI) + list(NUM_KN) + ["sau", "hazaar"] if k not in AMBIGUOUS and len(k) >= 3], key=len, reverse=True)) + r")(?![a-z])")


def looks_mixed(text: str) -> bool:
    """Latin-script text with at least one unambiguous Hindi or Kannada word."""
    return has_indic(text) or bool(_STRONG.search(text.lower()))


_KEYS = sorted(PHRASES, key=len, reverse=True)
_RX = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(k) for k in _KEYS) + r")(?![a-z0-9])")


def _numbers(t: str) -> str:
    t = _DO.sub("2", t)
    words = {**NUMBERS}
    toks = re.split(r"(\s+)", t)
    out: list[str] = []
    i = 0
    while i < len(toks):
        w = toks[i]
        if w in words or w in SCALES:
            total, cur, j, used = 0.0, 0.0, i, False
            while j < len(toks):
                x = toks[j]
                if x.isspace():
                    j += 1
                    continue
                if x in SCALES and (used or x in ("sau", "hazaar", "hazar")):
                    cur = (cur or 1) * SCALES[x]
                    if SCALES[x] >= 1000:
                        total += cur
                        cur = 0
                elif x in words:
                    if used and words[x] >= 100 and cur:          # "ondu nooru"
                        cur *= words[x]
                    else:
                        cur += words[x]
                elif x.isdigit() and not used:
                    cur += int(x)
                else:
                    break
                used = True
                j += 1
                k = j
            if used:
                v = total + cur
                out.append(str(int(v)) if float(v).is_integer() else f"{v:g}")
                trailing = [s for s in toks[i:j] if s.isspace()]
                out.append(" " if trailing and j < len(toks) else "")
                while j < len(toks) and toks[j].isspace():
                    j += 1
                i = j
                continue
        out.append(w)
        i += 1
    return "".join(out)


def _skeleton(w: str) -> str:
    w = w.lower().replace("ph", "f").replace("x", "ks").replace("c", "s").replace("q", "k").replace("j", "z").replace("v", "w")
    w = re.sub(r"[aeiouyh]", "", w)
    return re.sub(r"(.)\1+", r"\1", w)


_DRUG_SKEL: dict[str, str] | None = None


def _drug_skeletons() -> dict[str, str]:
    global _DRUG_SKEL
    if _DRUG_SKEL is None:
        from . import lexicon as L
        m: dict[str, str] = {}
        for name, d in L.DRUGS.items():
            for a in [name] + list(d.get("aliases", [])):
                a = a.lower()
                if " " in a or len(a) < 5:
                    continue
                k = _skeleton(a)
                if len(k) >= 4:
                    m.setdefault(k, a)
        _DRUG_SKEL = m
    return _DRUG_SKEL


def _fix_drug_words(t: str) -> tuple[str, list[tuple[str, str]]]:
    """Drug names Whisper wrote in Devanagari/Kannada come back as e.g. 'pyarasitamal': match them to the
    lexicon by consonant skeleton (paracetamol and pyarasitamal both reduce to p-r-s-t-m-l)."""
    skel = _drug_skeletons()
    fixed: list[tuple[str, str]] = []

    def rep(m: re.Match) -> str:
        w = m.group(0)
        if w in PHRASES or len(w) < 5:
            return w
        hit = skel.get(_skeleton(w))
        if hit and hit != w:
            fixed.append((w, hit))
            return hit
        return w
    return re.sub(r"[a-z]{5,}", rep, t), fixed


def to_english(text: str) -> dict:
    """Return {'text': English-ish text for NER, 'script': ..., 'replaced': [(from, to)], 'mixed': bool}."""
    script = "devanagari" if re.search(r"[ऀ-ॿ]", text) else "kannada" if re.search(r"[ಀ-೿]", text) else "latin"
    if not looks_mixed(text):
        return {"text": text, "script": "latin", "replaced": [], "mixed": False, "language": None}
    t = romanise(text) if script != "latin" else text
    t = t.lower()
    drug_fixes: list[tuple[str, str]] = []
    if script != "latin":
        t, drug_fixes = _fix_drug_words(t)
    # "300 ka/ke" etc. leave numbers alone; digits glued to Indic units: "300mg" stays
    t = re.sub(r"(\d)\s*(?:मि\.?ग्रा\.?)", r"\1 mg", t)
    t = _numbers(t)
    replaced: list[tuple[str, str]] = []

    def sub(m: re.Match) -> str:
        k = m.group(1)
        v = PHRASES[k]
        if k != v:
            replaced.append((k, v))
        return v

    # numbers + "years": "45 years male" reads fine for the age parser; collapse double spaces after removals
    t = _RX.sub(sub, t)
    t = re.sub(r"(\d+)\s+years\s+(male|female|boy|girl|child|elderly)", r"\1 years old \2", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    t = re.sub(r"\s+([,.])", r"\1", t)
    meaningful = drug_fixes + [r for r in replaced if r[1]]
    kn = sum(1 for k, _ in replaced if k in KANNADA_KEYS)
    hi = sum(1 for k, _ in replaced if k in PHRASES_HI)
    lang = "kannada" if script == "kannada" or (script == "latin" and kn > hi) else "hindi"
    return {"text": t, "script": script, "replaced": meaningful, "mixed": True, "language": lang}
