"""
Curated prehospital first-aid / BLS-level protocol cards.

These summarise widely published first-aid and basic life support principles
(e.g. ILCOR/AHA/Red Cross-style guidance and Indian snakebite practice) for
DECISION SUPPORT ONLY. Medication lines are reference entries that a deployment
must replace with its own state 108 / medical-director protocol; the agent always
presents them as "per your protocol" and never as an order.
"""
from __future__ import annotations

import re

PROTOCOLS: list[dict] = [
    {
        "id": "cardiac_arrest", "title": "Cardiac arrest (adult)", "priority": "RED",
        "triggers": ["cardiac arrest", "no pulse", "pulseless", "not breathing", "collapsed and unresponsive", "arrest", "cpr"],
        "steps": [
            "Confirm scene is safe; check response and breathing for no more than 10 seconds.",
            "Start chest compressions immediately: centre of chest, 5-6 cm deep, 100-120 per minute, full recoil.",
            "Attach the AED/defibrillator as soon as available and follow its prompts; minimise pauses.",
            "Give 2 breaths after every 30 compressions with a bag-valve-mask if trained; otherwise continuous compressions.",
            "Swap compressor every 2 minutes; continue until ROSC, handover or a protocol termination decision.",
        ],
        "red_flags": ["Shockable rhythm on AED", "Return of spontaneous circulation - check pulse and breathing, recovery position if breathing"],
        "do_not": ["Do not delay compressions to look for a pulse repeatedly", "Do not stop CPR for transport unless protocol allows mechanical CPR"],
        "meds": [{"drug": "Adrenaline", "dose": "1 mg IV/IO every 3-5 min", "note": "ALS-trained crew, per protocol"},
                 {"drug": "Amiodarone", "dose": "300 mg IV/IO after 3rd shock", "note": "ALS-trained crew, per protocol"}],
        "log_hints": ["CPR start time", "each shock with joules", "each adrenaline dose", "ROSC time"],
    },
    {
        "id": "chest_pain", "title": "Chest pain / suspected heart attack", "priority": "RED",
        "triggers": ["chest pain", "chest tightness", "heart attack", "acs", "stemi", "pain radiating to left arm", "seene mein dard"],
        "steps": [
            "Sit the patient in a comfortable half-sitting position; keep them calm and still.",
            "Record time of onset, BP, pulse, SpO2; obtain a 12-lead ECG if available and transmit if possible.",
            "Ask about aspirin allergy, bleeding disorders and recent use of erectile-dysfunction drugs.",
            "Give oxygen only if SpO2 is below 94%.",
            "Pre-alert a PCI-capable hospital; be ready for cardiac arrest (AED nearby).",
        ],
        "red_flags": ["Systolic BP < 90", "New confusion or collapse", "ST elevation on ECG"],
        "do_not": ["Do not let the patient walk", "Do not give nitrates if systolic BP < 90 or PDE-5 inhibitor taken in last 24-48 h"],
        "meds": [{"drug": "Aspirin", "dose": "300 mg chewed, once", "note": "if no allergy / active bleeding"},
                 {"drug": "Isosorbide dinitrate", "dose": "5 mg sublingual", "note": "if SBP > 90, per protocol"}],
        "log_hints": ["onset time", "aspirin given + time", "ECG done", "pain score"],
    },
    {
        "id": "severe_bleeding", "title": "Severe bleeding / trauma", "priority": "RED",
        "triggers": ["bleeding", "haemorrhage", "hemorrhage", "cut", "laceration", "amputation", "stab", "gunshot", "rta", "road traffic accident", "accident", "bike accident"],
        "steps": [
            "Protect yourself (gloves); control catastrophic bleeding first: firm direct pressure with a dressing.",
            "For life-threatening limb bleeding not controlled by pressure, apply a tourniquet high and tight; note the time.",
            "Check airway with cervical-spine care if mechanism suggests spinal injury; apply collar per protocol.",
            "Keep the patient warm and lying flat; monitor pulse, BP and level of consciousness every 5 minutes.",
            "Rapid transport to a trauma-capable hospital; pre-alert with mechanism and injuries.",
        ],
        "red_flags": ["Pulse > 120 or SBP < 90 (shock)", "GCS falling", "Bleeding through dressings"],
        "do_not": ["Do not remove impaled objects", "Do not remove a tourniquet once applied", "Do not give food or drink"],
        "meds": [{"drug": "Tranexamic acid", "dose": "1 g IV over 10 min", "note": "within 3 h of injury, per protocol"},
                 {"drug": "Ringer lactate", "dose": "250 mL boluses to radial pulse", "note": "permissive hypotension, per protocol"}],
        "log_hints": ["tourniquet time", "dressing applied", "collar applied", "TXA time"],
    },
    {
        "id": "anaphylaxis", "title": "Anaphylaxis / severe allergic reaction", "priority": "RED",
        "triggers": ["anaphylaxis", "allergic reaction", "lip swelling", "tongue swelling", "throat swelling", "urticaria", "hives", "bee sting", "angioedema"],
        "steps": [
            "Remove the trigger if possible; call for ALS backup.",
            "Lie the patient flat with legs raised (sit up if breathing is difficult; left side if pregnant).",
            "Give intramuscular adrenaline into the outer thigh without delay (per protocol); note the time.",
            "High-flow oxygen; monitor airway, breathing, SpO2 and BP continuously.",
            "Repeat adrenaline after 5 minutes if no improvement, per protocol.",
        ],
        "red_flags": ["Stridor or hoarse voice", "Wheeze with falling SpO2", "SBP < 90 or collapse"],
        "do_not": ["Do not let the patient stand or walk", "Do not delay adrenaline for antihistamines"],
        "meds": [{"drug": "Adrenaline", "dose": "0.5 mg IM (1 mg/mL) adult; 0.01 mg/kg child", "note": "outer thigh, per protocol"},
                 {"drug": "Hydrocortisone", "dose": "200 mg IV", "note": "after adrenaline, per protocol"},
                 {"drug": "Pheniramine", "dose": "22.75-45.5 mg IV/IM", "note": "adjunct only, per protocol"}],
        "log_hints": ["adrenaline dose + time", "repeat dose", "BP after"],
    },
    {
        "id": "breathing", "title": "Breathlessness / asthma attack", "priority": "YELLOW",
        "triggers": ["breathless", "shortness of breath", "asthma", "wheeze", "wheezing", "difficulty breathing", "saans"],
        "steps": [
            "Sit the patient upright; loosen tight clothing; help them use their own inhaler if they have one.",
            "Measure SpO2, respiratory rate and ability to speak in sentences.",
            "Give oxygen to keep SpO2 94-98%.",
            "Nebulise bronchodilator per protocol; reassess after each nebulisation.",
        ],
        "red_flags": ["Unable to speak", "Silent chest", "SpO2 < 92% despite oxygen", "Exhaustion or confusion"],
        "do_not": ["Do not lie the patient flat"],
        "meds": [{"drug": "Salbutamol", "dose": "5 mg nebulised adult; 2.5 mg child", "note": "per protocol"},
                 {"drug": "Ipratropium", "dose": "500 mcg nebulised adult", "note": "severe attack, per protocol"},
                 {"drug": "Hydrocortisone", "dose": "100 mg IV", "note": "per protocol"}],
        "log_hints": ["SpO2 before/after", "nebulisation time", "RR"],
    },
    {
        "id": "hypoglycaemia", "title": "Low blood sugar (hypoglycaemia)", "priority": "YELLOW",
        "triggers": ["hypoglycemia", "hypoglycaemia", "low sugar", "sugar low", "diabetic unconscious", "sweating diabetic", "hypo"],
        "steps": [
            "Check blood glucose (GRBS).",
            "If conscious and able to swallow: give 15-20 g oral glucose or a sugary drink; recheck after 15 minutes.",
            "If drowsy/unable to swallow: nothing by mouth; recovery position; IV dextrose or IM glucagon per protocol.",
            "Recheck glucose and GCS; give a longer-acting carbohydrate once awake.",
        ],
        "red_flags": ["GCS < 13", "Seizure", "No response to treatment"],
        "do_not": ["Do not give anything by mouth to a drowsy patient"],
        "meds": [{"drug": "Dextrose", "dose": "D25 50-100 mL IV (or D10 per protocol)", "note": "if unable to swallow"},
                 {"drug": "Glucagon", "dose": "1 mg IM", "note": "if no IV access"}],
        "log_hints": ["GRBS before/after", "dextrose time"],
    },
    {
        "id": "seizure", "title": "Seizure / fits", "priority": "YELLOW",
        "triggers": ["seizure", "fits", "convulsion", "seizing", "mirgi", "epilepsy"],
        "steps": [
            "Note the start time; protect the head and move hard objects away.",
            "Do not restrain; put nothing in the mouth.",
            "Check glucose once safe; give oxygen if SpO2 low.",
            "After the seizure: recovery position, check airway and breathing, reassure.",
            "If seizure lasts more than 5 minutes or recurs without recovery: benzodiazepine per protocol.",
        ],
        "red_flags": ["Seizure > 5 minutes", "Repeated seizures", "Head injury", "Pregnancy"],
        "do_not": ["Do not put fingers or objects in the mouth", "Do not give water or food until fully alert"],
        "meds": [{"drug": "Midazolam", "dose": "10 mg buccal/IM adult; 0.2-0.3 mg/kg intranasal child", "note": "seizure > 5 min, per protocol"}],
        "log_hints": ["seizure start/stop", "benzodiazepine time", "GRBS"],
    },
    {
        "id": "stroke", "title": "Suspected stroke", "priority": "RED",
        "triggers": ["stroke", "facial droop", "slurred speech", "weakness of one side", "weakness of right", "weakness of left", "hemiparesis", "face drooping"],
        "steps": [
            "BE-FAST check: balance, eyes, face, arm, speech; record the exact time last known well.",
            "Check blood glucose to rule out hypoglycaemia.",
            "Keep nil by mouth; position head up 30 degrees if no spinal concern; oxygen only if SpO2 < 94%.",
            "Rapid transport to a stroke-ready (thrombolysis-capable) hospital with pre-alert.",
        ],
        "red_flags": ["GCS falling", "Seizure", "Very high BP with headache"],
        "do_not": ["Do not give anything by mouth", "Do not give aspirin before a brain scan"],
        "meds": [],
        "log_hints": ["last known well time", "GRBS", "BE-FAST findings"],
    },
    {
        "id": "snake_bite", "title": "Snake bite", "priority": "RED",
        "triggers": ["snake bite", "snakebite", "saanp", "bitten by snake", "cobra", "krait", "viper"],
        "steps": [
            "Reassure the patient and keep them still; immobilise the bitten limb with a splint at heart level.",
            "Remove rings, watches and tight clothing near the bite.",
            "Note the time of bite and watch for drooping eyelids, bleeding, swelling or breathing difficulty.",
            "Transport urgently to a hospital that stocks anti-snake venom (ASV).",
        ],
        "red_flags": ["Ptosis or difficulty breathing (neurotoxic)", "Bleeding from gums or wound (haemotoxic)", "Rapid swelling"],
        "do_not": ["Do not cut, suck or apply ice", "Do not apply a tight tourniquet", "Do not let the patient walk"],
        "meds": [],
        "log_hints": ["time of bite", "limb immobilised", "symptom progression"],
    },
    {
        "id": "burns", "title": "Burns", "priority": "YELLOW",
        "triggers": ["burn", "burns", "scald", "fire", "acid", "electrical burn"],
        "steps": [
            "Stop the burning process; ensure your own safety (electricity off, chemicals brushed off).",
            "Cool the burn with cool running water for 20 minutes; remove jewellery and loose clothing that is not stuck.",
            "Cover loosely with cling film or a clean non-fluffy dressing; keep the patient warm.",
            "Estimate the burned area; give analgesia and IV fluids per protocol for large burns.",
        ],
        "red_flags": ["Burns to face/airway or singed nasal hair", "Hoarse voice", "Large or circumferential burns", "Electrical burn"],
        "do_not": ["Do not use ice, toothpaste, oil or butter", "Do not burst blisters", "Do not peel off stuck clothing"],
        "meds": [{"drug": "Paracetamol", "dose": "1 g oral/IV adult", "note": "analgesia, per protocol"}],
        "log_hints": ["cooling duration", "% area estimate", "dressing applied"],
    },
    {
        "id": "fracture", "title": "Fracture / limb injury", "priority": "GREEN",
        "triggers": ["fracture", "broken", "deformity", "fall", "fell", "sprain", "dislocation"],
        "steps": [
            "Check circulation, sensation and movement beyond the injury.",
            "Support and immobilise in the position found with a splint; pad gaps.",
            "Cover open wounds with a sterile dressing; control bleeding without pressing on bone ends.",
            "Recheck circulation after splinting; give analgesia per protocol.",
        ],
        "red_flags": ["Cold or pulseless limb", "Open fracture", "Suspected femur or pelvic fracture (shock risk)"],
        "do_not": ["Do not try to straighten a deformed limb unless circulation is absent and you are trained"],
        "meds": [{"drug": "Diclofenac", "dose": "75 mg IM", "note": "analgesia, no NSAID allergy, per protocol"},
                 {"drug": "Paracetamol", "dose": "1 g", "note": "per protocol"}],
        "log_hints": ["splint applied", "distal pulse after", "pain score"],
    },
    {
        "id": "head_injury", "title": "Head injury", "priority": "YELLOW",
        "triggers": ["head injury", "hit head", "scalp bleeding", "unconscious after fall", "concussion"],
        "steps": [
            "Assume spinal injury if mechanism suggests it: manual in-line stabilisation, collar per protocol.",
            "Record GCS and pupils; repeat every 5-10 minutes.",
            "Control scalp bleeding with pressure; keep SpO2 >= 94%.",
            "Transport to a neuro-capable hospital if GCS < 15 or red flags.",
        ],
        "red_flags": ["GCS falling by 2 or more", "Unequal pupils", "Repeated vomiting", "Seizure", "Blood or fluid from ears/nose"],
        "do_not": ["Do not leave the patient alone", "Do not give food or drink"],
        "meds": [],
        "log_hints": ["GCS trend", "pupils", "collar applied"],
    },
    {
        "id": "choking", "title": "Choking (adult)", "priority": "RED",
        "triggers": ["choking", "choke", "food stuck", "cannot breathe after eating", "foreign body airway"],
        "steps": [
            "If they can cough, encourage coughing.",
            "If coughing is ineffective: up to 5 back blows between the shoulder blades.",
            "Then up to 5 abdominal thrusts; alternate 5 and 5.",
            "If they become unresponsive: start CPR and check the mouth before breaths.",
        ],
        "red_flags": ["Unresponsive", "Silent cough or cyanosis"],
        "do_not": ["Do not do blind finger sweeps"],
        "meds": [],
        "log_hints": ["manoeuvres used", "obstruction cleared time"],
    },
    {
        "id": "poisoning", "title": "Poisoning / overdose", "priority": "YELLOW",
        "triggers": ["poison", "poisoning", "overdose", "organophosphate", "pesticide", "consumed", "ingested", "kerosene"],
        "steps": [
            "Ensure your own safety; remove contaminated clothing and wash skin for pesticides (use gloves).",
            "Identify the substance, amount and time; bring the container.",
            "Monitor airway, breathing, pupils, heart rate and GCS; recovery position if drowsy.",
            "Contact poison information / medical direction; transport urgently.",
        ],
        "red_flags": ["Pinpoint pupils with secretions and slow pulse (organophosphate)", "Slow breathing (opioid)", "Seizure"],
        "do_not": ["Do not induce vomiting", "Do not give milk or oil"],
        "meds": [{"drug": "Naloxone", "dose": "0.4 mg IV/IM, repeat", "note": "suspected opioid, per protocol"},
                 {"drug": "Atropine", "dose": "per protocol titration", "note": "organophosphate, ALS/medical direction"}],
        "log_hints": ["substance + time", "decontamination", "pupils"],
    },
    {
        "id": "heat", "title": "Heat stroke", "priority": "RED",
        "triggers": ["heat stroke", "heatstroke", "sun stroke", "very hot skin", "collapsed in heat"],
        "steps": [
            "Move to shade or an air-conditioned ambulance; remove excess clothing.",
            "Cool rapidly: wet the skin and fan, cold packs to neck, armpits and groin.",
            "Check glucose and GCS; recovery position if drowsy.",
            "Oral fluids only if fully alert; otherwise IV fluids per protocol.",
        ],
        "red_flags": ["Confusion or seizure", "Temperature > 40 °C", "Stopped sweating"],
        "do_not": ["Do not give fluids by mouth to a confused patient"],
        "meds": [],
        "log_hints": ["cooling started", "temperature trend"],
    },
]

_BY_ID = {p["id"]: p for p in PROTOCOLS}


def match(text: str, limit: int = 3) -> list[dict]:
    t = " " + text.lower() + " "
    scored = []
    for p in PROTOCOLS:
        score = 0
        for trig in p["triggers"]:
            if re.search(r"(?<![a-z])" + re.escape(trig) + r"(?![a-z])", t):
                score += 3 if " " in trig else 2
        if score:
            scored.append((score, {"RED": 2, "YELLOW": 1}.get(p["priority"], 0), p))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [p for _, _, p in scored[:limit]]


def get(pid: str) -> dict | None:
    return _BY_ID.get(pid)


def catalogue() -> list[dict]:
    return [{"id": p["id"], "title": p["title"], "priority": p["priority"]} for p in PROTOCOLS]
