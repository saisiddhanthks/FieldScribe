"""Hindi and Kannada (both scripts and Latin letters) mixed with English clinical words."""
from app.nlp import indic
from app.nlp.ner import extract
from app import evaluation


def meds(text):
    r = extract(text, use_model=False)
    return [(e["fields"]["drug"]["value"], (e["fields"].get("dose") or {}).get("value"), (e["fields"].get("route") or {}).get("value"))
            for e in r["entities"] if e["kind"] == "medication" and not e["negated"]], r


def test_romanise_scripts():
    assert indic.romanise("सीने में दर्द") == "sine men dard"
    assert indic.romanise("आदमी") == "admi"                       # Hindi schwa deletion
    assert indic.romanise("ಎದೆ ನೋವು") == "ede novu"
    assert indic.romanise("ಮುನ್ನೂರು ३००") == "munnuru 300"


def test_plain_english_untouched():
    for t in ["Patient sat up, so we gave aspirin 300 mg oral", "gave adrenaline 0.5 mg IM, he is better", "do not give morphine"]:
        assert indic.to_english(t)["mixed"] is False


def test_hindi_devanagari_case():
    m, r = meds("सीने में दर्द, 45 साल का आदमी, एस्पिरिन ३०० मिलीग्राम मुँह से दिया")
    assert m == [("Aspirin", 300.0, "PO")]
    assert r["patient"]["age"] == 45 and r["patient"]["sex"] == "male"
    assert r["language"]["language"] == "hindi" and r["language"]["script"] == "devanagari"


def test_kannada_script_case():
    m, r = meds("ಎದೆ ನೋವು, 60 ವರ್ಷದ ಗಂಡಸು, ಸಾರ್ಬಿಟ್ರೇಟ್ 5 mg ನಾಲಿಗೆ ಕೆಳಗೆ ಕೊಟ್ಟಿದ್ದೀನಿ")
    assert m == [("Isosorbide dinitrate", 5.0, "SL")]
    assert r["language"]["language"] == "kannada"


def test_hinglish_numbers_and_negation():
    m, _ = meds("58 saal ka aadmi, seene mein dard, ecosprin teen sau mg chaba ke diya")
    assert m == [("Aspirin", 300.0, "PO")]
    m, _ = meds("aspirin nahi diya, allergy hai, chest pain")
    assert m == []


def test_kanglish_numbers():
    m, _ = meds("paracetamol munnooru mg bayalli kottiddini")
    assert m == [("Paracetamol", 300.0, "PO")]


def test_oxygen_is_never_topical():
    m, _ = meds("oxygen 6 litre per minute haakiddini")
    assert m[0][0] == "Oxygen" and m[0][2] == "INH"


def test_codemix_benchmark_beats_english_only():
    dev = evaluation.codemix(use_model=False)
    held = evaluation.codemix(use_model=False, heldout=True)
    assert dev["with_indic"]["overall"]["f1"] >= 0.95
    assert held["with_indic"]["overall"]["f1"] >= 0.85
    assert held["with_indic"]["overall"]["f1"] > held["without_indic"]["overall"]["f1"] + 0.15
