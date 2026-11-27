"""
Clinical lexicon for Indian prehospital care.

Drugs map generic name -> codes, aliases (incl. Indian brands and ASR
mis-hearings), default route/unit, and a *demo* reference range for adult
single doses used only to raise review flags. These ranges are NOT clinical
guidance; each deployment must load its own state 108 / medical-director
protocol (see /api/lexicon and data/protocol_overrides.json).

RxNorm codes are ingredient-level RXCUIs. Entries marked `rxnorm: None`
must be verified against the NLM RxNorm browser before production use.
"""
from __future__ import annotations

DRUGS: dict[str, dict] = {
    "Aspirin": {
        "rxnorm": "1191", "class": "Antiplatelet",
        "aliases": ["aspirin", "asprin", "aspirine", "ecosprin", "disprin", "loprin", "asa", "aspirin tablet"],
        "default_route": "PO", "default_unit": "mg", "range": [75, 325],
        "contra_allergy": ["aspirin", "nsaid", "salicylate"],
    },
    "Clopidogrel": {
        "rxnorm": "32968", "class": "Antiplatelet",
        "aliases": ["clopidogrel", "clopilet", "plavix", "deplatt", "clopi"],
        "default_route": "PO", "default_unit": "mg", "range": [75, 600],
    },
    "Nitroglycerin": {
        "rxnorm": "4917", "class": "Nitrate",
        "aliases": ["nitroglycerin", "nitroglycerine", "ntg", "gtn", "angised", "nitro"],
        "default_route": "SL", "default_unit": "mg", "range": [0.3, 0.8],
    },
    "Isosorbide dinitrate": {
        "rxnorm": "6058", "class": "Nitrate",
        "aliases": ["isosorbide dinitrate", "isosorbide", "sorbitrate", "isordil", "isdn"],
        "default_route": "SL", "default_unit": "mg", "range": [5, 10],
    },
    "Paracetamol": {
        "rxnorm": "161", "class": "Analgesic / antipyretic",
        "aliases": ["paracetamol", "acetaminophen", "pcm", "crocin", "dolo", "calpol", "p500", "paracitamol"],
        "default_route": "PO", "default_unit": "mg", "range": [325, 1000],
    },
    "Ondansetron": {
        "rxnorm": "26225", "class": "Antiemetic",
        "aliases": ["ondansetron", "emeset", "ondem", "vomikind", "zofran", "ondansetrone"],
        "default_route": "IV", "default_unit": "mg", "range": [2, 8],
    },
    "Pheniramine": {
        "rxnorm": None, "class": "Antihistamine",
        "aliases": ["pheniramine", "avil", "aveel", "phenyramine"],
        "default_route": "IM", "default_unit": "mg", "range": [22.75, 45.5],
    },
    "Chlorpheniramine": {
        "rxnorm": "2400", "class": "Antihistamine",
        "aliases": ["chlorpheniramine", "cpm", "piriton"],
        "default_route": "IV", "default_unit": "mg", "range": [4, 10],
    },
    "Salbutamol": {
        "rxnorm": "435", "class": "Bronchodilator",
        "aliases": ["salbutamol", "albuterol", "asthalin", "salbu", "ventolin", "salbutamole"],
        "default_route": "NEB", "default_unit": "mg", "range": [2.5, 5],
    },
    "Ipratropium": {
        "rxnorm": "7213", "class": "Bronchodilator",
        "aliases": ["ipratropium", "ipravent", "duolin", "atrovent"],
        "default_route": "NEB", "default_unit": "mcg", "range": [250, 500],
    },
    "Adrenaline": {
        "rxnorm": "3992", "class": "Sympathomimetic",
        "aliases": ["adrenaline", "epinephrine", "adrenalin", "adrenaline injection", "epi", "adrenalin injection", "adrenline"],
        "default_route": "IM", "default_unit": "mg", "range": [0.01, 1],
        "high_alert": True,
    },
    "Atropine": {
        "rxnorm": "1223", "class": "Anticholinergic",
        "aliases": ["atropine", "atropin", "atropine sulphate"],
        "default_route": "IV", "default_unit": "mg", "range": [0.5, 3],
        "high_alert": True,
    },
    "Amiodarone": {
        "rxnorm": "703", "class": "Antiarrhythmic",
        "aliases": ["amiodarone", "cordarone", "eptoin amio"],
        "default_route": "IV", "default_unit": "mg", "range": [150, 300],
        "high_alert": True,
    },
    "Adenosine": {
        "rxnorm": "296", "class": "Antiarrhythmic",
        "aliases": ["adenosine", "adenocor"],
        "default_route": "IV", "default_unit": "mg", "range": [6, 12],
        "high_alert": True,
    },
    "Morphine": {
        "rxnorm": "7052", "class": "Opioid analgesic",
        "aliases": ["morphine", "morfin", "morphin"],
        "default_route": "IV", "default_unit": "mg", "range": [2, 10],
        "high_alert": True, "controlled": True,
    },
    "Fentanyl": {
        "rxnorm": "4337", "class": "Opioid analgesic",
        "aliases": ["fentanyl", "fentanil", "fentanyl citrate"],
        "default_route": "IV", "default_unit": "mcg", "range": [25, 100],
        "high_alert": True, "controlled": True,
    },
    "Tramadol": {
        "rxnorm": "10689", "class": "Opioid analgesic",
        "aliases": ["tramadol", "contramal", "ultracet", "tramazac"],
        "default_route": "IV", "default_unit": "mg", "range": [50, 100],
    },
    "Diclofenac": {
        "rxnorm": "3355", "class": "NSAID",
        "aliases": ["diclofenac", "voveran", "voveran injection", "dynapar", "diclo"],
        "default_route": "IM", "default_unit": "mg", "range": [50, 75],
        "contra_allergy": ["nsaid", "diclofenac"],
    },
    "Ketamine": {
        "rxnorm": "6130", "class": "Anaesthetic",
        "aliases": ["ketamine", "ketamin", "ketalar"],
        "default_route": "IV", "default_unit": "mg", "range": [10, 200],
        "high_alert": True, "controlled": True,
    },
    "Midazolam": {
        "rxnorm": "6960", "class": "Benzodiazepine",
        "aliases": ["midazolam", "mezolam", "fulsed", "midaz"],
        "default_route": "IV", "default_unit": "mg", "range": [1, 10],
        "high_alert": True, "controlled": True,
    },
    "Diazepam": {
        "rxnorm": "3322", "class": "Benzodiazepine",
        "aliases": ["diazepam", "calmpose", "valium"],
        "default_route": "IV", "default_unit": "mg", "range": [2, 10],
        "high_alert": True, "controlled": True,
    },
    "Naloxone": {
        "rxnorm": "7242", "class": "Opioid antagonist",
        "aliases": ["naloxone", "narcan", "naloxon"],
        "default_route": "IV", "default_unit": "mg", "range": [0.04, 2],
    },
    "Dextrose": {
        "rxnorm": "4850", "class": "Carbohydrate",
        "aliases": ["dextrose", "d25", "d50", "d10", "glucose", "dextrose 25", "25 percent dextrose"],
        "default_route": "IV", "default_unit": "mL", "range": [10, 250],
    },
    "Glucagon": {
        "rxnorm": "4832", "class": "Hormone",
        "aliases": ["glucagon", "glucagen"],
        "default_route": "IM", "default_unit": "mg", "range": [0.5, 1],
    },
    "Hydrocortisone": {
        "rxnorm": "5492", "class": "Corticosteroid",
        "aliases": ["hydrocortisone", "efcorlin", "solu-cortef", "hydrocort", "hc"],
        "default_route": "IV", "default_unit": "mg", "range": [100, 200],
    },
    "Dexamethasone": {
        "rxnorm": "3264", "class": "Corticosteroid",
        "aliases": ["dexamethasone", "decadron", "dexona", "dexa"],
        "default_route": "IV", "default_unit": "mg", "range": [4, 16],
    },
    "Furosemide": {
        "rxnorm": "4603", "class": "Diuretic",
        "aliases": ["furosemide", "frusemide", "lasix"],
        "default_route": "IV", "default_unit": "mg", "range": [20, 80],
    },
    "Tranexamic acid": {
        "rxnorm": "10691", "class": "Antifibrinolytic",
        "aliases": ["tranexamic acid", "tranexamic", "txa", "pause", "trenaxa", "tranexa"],
        "default_route": "IV", "default_unit": "mg", "range": [1000, 1000],
    },
    "Magnesium sulfate": {
        "rxnorm": "6585", "class": "Electrolyte",
        "aliases": ["magnesium sulfate", "magnesium sulphate", "mgso4", "mag sulph", "magsulf"],
        "default_route": "IV", "default_unit": "g", "range": [1, 4],
        "high_alert": True,
    },
    "Normal saline": {
        "rxnorm": "9863", "class": "IV fluid",
        "aliases": ["normal saline", "ns", "saline", "sodium chloride", "0.9 saline", "nacl"],
        "default_route": "IV", "default_unit": "mL", "range": [100, 2000],
    },
    "Ringer lactate": {
        "rxnorm": None, "class": "IV fluid",
        "aliases": ["ringer lactate", "ringers lactate", "rl", "lactated ringer", "hartmann", "ringer's lactate"],
        "default_route": "IV", "default_unit": "mL", "range": [100, 2000],
    },
    "Oxygen": {
        "rxnorm": "7806", "class": "Medical gas",
        "aliases": ["oxygen", "o2", "o two", "oxigen"],
        "default_route": "INH", "default_unit": "L/min", "range": [1, 15],
    },
    "Pantoprazole": {
        "rxnorm": "40790", "class": "PPI",
        "aliases": ["pantoprazole", "pan 40", "pantop", "pantocid"],
        "default_route": "IV", "default_unit": "mg", "range": [40, 80],
    },
    "Metoclopramide": {
        "rxnorm": "6915", "class": "Antiemetic",
        "aliases": ["metoclopramide", "perinorm", "reglan"],
        "default_route": "IV", "default_unit": "mg", "range": [10, 10],
    },
    "Ceftriaxone": {
        "rxnorm": "2193", "class": "Antibiotic",
        "aliases": ["ceftriaxone", "monocef", "cefaxone", "rocephin"],
        "default_route": "IV", "default_unit": "g", "range": [1, 2],
    },
    "Tetanus toxoid": {
        "rxnorm": None, "class": "Vaccine",
        "aliases": ["tetanus toxoid", "tt injection", "tt", "tetanus"],
        "default_route": "IM", "default_unit": "mL", "range": [0.5, 0.5],
    },
}

# Brand/abbreviation aliases that are genuinely ambiguous. When matched, the
# engine lists candidates and FORCES human review rather than choosing.
AMBIGUOUS: dict[str, list[str]] = {
    "pause": ["Tranexamic acid"],          # brand "Pause" vs the English word
    "hc": ["Hydrocortisone"],
    "tt": ["Tetanus toxoid"],
    "epi": ["Adrenaline"],
    "ns": ["Normal saline"],
    "nitro": ["Nitroglycerin"],
    "dexa": ["Dexamethasone"],
}

ROUTES: dict[str, list[str]] = {
    "IV": ["iv", "intravenous", "intravenously", "i.v.", "i v", "by vein", "iv push", "iv bolus", "nas mein", "drip"],
    "IM": ["im", "intramuscular", "intramuscularly", "i.m.", "i m", "into the thigh", "thigh mein", "deltoid"],
    "PO": ["oral", "orally", "po", "by mouth", "per oral", "chewed", "chew", "muh se", "swallowed", "tablet"],
    "SL": ["sublingual", "sublingually", "under the tongue", "sl", "zuban ke neeche"],
    "SC": ["subcutaneous", "subcut", "sc", "s.c.", "subcutaneously"],
    "IO": ["intraosseous", "io", "i.o."],
    "NEB": ["nebulised", "nebulized", "nebulisation", "nebulization", "neb", "nebuliser", "nebulizer"],
    "INH": ["inhaled", "inhalation", "by mask", "via mask", "face mask", "nasal cannula", "nrbm", "non rebreather", "nrb"],
    "IN": ["intranasal", "nasal spray", "in the nose"],
    "PR": ["rectal", "per rectal", "pr", "rectally"],
    "TOP": ["topical", "applied", "dressing applied"],
}

UNITS: dict[str, list[str]] = {
    "mg": ["mg", "milligram", "milligrams", "mgs", "milli gram", "mili gram"],
    "mcg": ["mcg", "microgram", "micrograms", "ug", "µg", "micro gram"],
    "g": ["g", "gram", "grams", "gm", "gms"],
    "mL": ["ml", "millilitre", "milliliter", "millilitres", "milliliters", "cc", "mls", "mili litre"],
    "L": ["l", "litre", "liter", "litres", "liters"],
    "L/min": ["l/min", "lpm", "litres per minute", "liters per minute", "litre per minute", "litres a minute", "litres/min"],
    "units": ["units", "unit", "iu"],
    "puffs": ["puff", "puffs"],
    "tab": ["tab", "tabs", "tablet", "tablets"],
    "mEq": ["meq", "milliequivalent"],
}

DEVICES: dict[str, list[str]] = {
    "face mask": ["face mask", "simple mask", "by mask", "via mask", "mask"],
    "non-rebreather mask": ["non rebreather", "nrbm", "nrb", "non-rebreather"],
    "nasal cannula": ["nasal cannula", "nasal prongs", "cannula prongs"],
    "bag-valve-mask": ["bvm", "bag valve mask", "ambu bag", "ambu"],
    "nebuliser": ["nebuliser", "nebulizer", "neb mask"],
    "18G cannula": ["18g", "18 gauge", "green cannula"],
    "20G cannula": ["20g", "20 gauge", "pink cannula"],
    "22G cannula": ["22g", "22 gauge", "blue cannula"],
    "cervical collar": ["c collar", "cervical collar", "neck collar", "c-collar"],
    "AED": ["aed", "defibrillator", "defib"],
    "tourniquet": ["tourniquet", "cat tourniquet"],
}

# SNOMED CT concept ids where well-established; otherwise a local FS code
# that the deployment's terminology service should map.
PROCEDURES: dict[str, dict] = {
    "IV cannulation": {"snomed": "FS-PROC-001", "aliases": ["iv cannulation", "iv access", "iv line", "cannulated", "cannula inserted", "started iv", "iv started", "secured iv", "line secured", "cannula lagaya", "iv established", "cannula", "cannulation", "venflon"]},
    "Oxygen therapy": {"snomed": "57485005", "aliases": ["oxygen therapy", "started oxygen", "oxygen started", "o2 started", "put on oxygen", "oxygen diya"]},
    "Cardiopulmonary resuscitation": {"snomed": "89666000", "aliases": ["cpr", "chest compressions", "cardiopulmonary resuscitation", "started cpr", "cpr started", "resuscitation"]},
    "Defibrillation": {"snomed": "FS-PROC-002", "aliases": ["defibrillation", "shocked", "shock delivered", "defibrillated", "shock given", "joules"]},
    "Electrocardiogram": {"snomed": "29303009", "aliases": ["ecg", "ekg", "12 lead", "twelve lead", "electrocardiogram", "ecg done", "ecg taken"]},
    "Endotracheal intubation": {"snomed": "112798008", "aliases": ["intubated", "intubation", "et tube", "endotracheal", "ett placed"]},
    "Supraglottic airway": {"snomed": "FS-PROC-003", "aliases": ["igel", "i-gel", "lma", "laryngeal mask", "supraglottic"]},
    "Bag-valve-mask ventilation": {"snomed": "FS-PROC-004", "aliases": ["bvm ventilation", "bagging", "bagged", "ambu bagging", "assisted ventilation"]},
    "Suctioning": {"snomed": "FS-PROC-005", "aliases": ["suction", "suctioned", "suctioning", "airway suction"]},
    "Spinal immobilisation": {"snomed": "FS-PROC-006", "aliases": ["c collar applied", "spinal immobilisation", "spinal immobilization", "spine board", "c-spine", "cervical collar applied", "log roll", "collar applied", "neck collar applied", "collar put", "collar lagaya"]},
    "Splinting": {"snomed": "FS-PROC-007", "aliases": ["splint", "splinted", "splinting", "traction splint", "sam splint"]},
    "Wound dressing": {"snomed": "FS-PROC-008", "aliases": ["dressing", "dressed the wound", "wound dressing", "pressure dressing", "bandage", "bandaged", "patti"]},
    "Haemorrhage control": {"snomed": "FS-PROC-009", "aliases": ["tourniquet", "direct pressure", "bleeding controlled", "haemorrhage control", "hemorrhage control"]},
    "Blood glucose measurement": {"snomed": "FS-PROC-010", "aliases": ["grbs", "cbg", "glucometer", "sugar checked", "blood sugar checked", "rbs checked"]},
    "Nebulisation": {"snomed": "FS-PROC-011", "aliases": ["nebulisation", "nebulization", "nebulised", "nebulized", "neb given"]},
    "Recovery position": {"snomed": "FS-PROC-012", "aliases": ["recovery position", "left lateral", "lateral position"]},
}

ALLERGY_TERMS = {
    "aspirin": "aspirin", "nsaid": "nsaid", "nsaids": "nsaid", "penicillin": "penicillin",
    "sulfa": "sulfa", "diclofenac": "diclofenac", "morphine": "morphine", "latex": "latex",
    "paracetamol": "paracetamol", "ibuprofen": "nsaid",
}

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "half": 0.5,
    # Hindi numerals often heard in code-mixed dictation
    "ek": 1, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "bees": 20, "pachas": 50, "sau": 100,
}
SCALE_WORDS = {"hundred": 100, "thousand": 1000, "sau": 100, "hazaar": 1000}

# Code-mixed (Hinglish / Kanglish) action verbs and fillers normalised to English.
CODE_MIX = {
    "diya": "given", "de diya": "given", "dia": "given", "diye": "given", "lagaya": "applied",
    "lagayi": "applied", "chadhaya": "infused", "chalu kiya": "started", "shuru kiya": "started",
    "kiya": "done", "ko": "", "aur": "and", "phir": "then", "baad mein": "later", "bje": "hrs",
    "baje": "hrs", "nahi": "not", "nahin": "not", "mana kiya": "refused", "kodu": "given",
    "kottidini": "given", "haaki": "applied", "maadide": "done",
}

NEGATION_CUES = [
    "no ", "not ", "denied", "refused", "withheld", "held", "declined", "without", "did not give",
    "didn't give", "not given", "avoid", "contraindicated", "deferred", "nahi diya", "mana kiya",
]
