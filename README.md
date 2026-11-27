# FieldScribe

**Offline voice-to-structured clinical record generator for first responders.**
Team RCB · Virtusa hackathon · Stage 2 working prototype

An EMT dictates on scene ("gave ecosprin 300 mg chewed at 10:42, RL 500 ml iv…"). FieldScribe transcribes it on the device, extracts every drug, dose, unit, route, time, procedure and vital, runs protocol safety checks, and lets the EMT confirm and sign. The record is appended to a hash-chained, Ed25519-signed audit ledger and exported as a FHIR R4 bundle and an ATMIST handover PDF, all with no network. When signal returns, the outbox syncs to the ED hub.

---

## 0. Install as a desktop app (Windows 10/11, one click)

There are two downloads. Both run the same app and keep every record signed, encrypted and offline-capable.

| | **FieldScribe Lite** | **FieldScribe Full** |
|---|---|---|
| For | older or 4–8 GB laptops, quick demos, slow internet | the complete experience |
| Speech (offline Whisper) | `base` (145 MB), clear English dictation | `large-v3-turbo` (1.6 GB), best for accents, Hindi and Kannada |
| Copilot | Gemini online, built-in protocol engine offline | + **local AI (Ollama)** that works fully offline |
| ED hub | built-in hub | + PostgreSQL driver |
| Download / installed | ~0.3 GB / ~0.6 GB | ~3–7 GB / ~5–8 GB |
| Source code, tests, Docker | not included | included |

Upgrade any time: run the Full installer over Lite, and records, keys and PINs are kept. Lite options: `Install FieldScribe.bat -Speech small` for better speech (480 MB), `-NoAI:$false` to add the local AI.

1. Extract `FieldScribe.zip` anywhere.
2. Double-click **`Install FieldScribe.bat`**.

The installer (`installer/install.ps1`) does everything, and it's safe to run again: it resumes, upgrades and never overwrites your records.

| Step | What it does |
|---|---|
| App | copies FieldScribe to `%LOCALAPPDATA%\Programs\FieldScribe`, keeping an existing setup's records, keys and models |
| Python | uses Python 3.11–3.13 if present, otherwise installs 3.11 for this user (no admin) |
| Packages | private environment with SQLCipher, faster-whisper and the PostgreSQL driver |
| Offline AI | installs **Ollama** and downloads a Qwen 2.5 model sized to the laptop: 7B at ≥14 GB RAM, 3B at ≥7 GB, 1.5B below that |
| Speech | Whisper `large-v3-turbo` at ≥8 GB RAM, `small` below that |
| Map | Bengaluru roads for offline routing |
| Shortcuts | **FieldScribe** on the Desktop and Start menu, plus tablet mode and Uninstall |

It downloads about 3–7 GB the first time. After that, everything (records, speech, Copilot AI, map) works with no internet. Options: `Install FieldScribe.bat -NoAI`, `-NoMap`, `-Speech small`, `-AIModel qwen2.5:1.5b`.

The **FieldScribe** icon starts the backend with no console window, shows a start-up screen, and opens FieldScribe in its own app window (Edge or Chrome app mode). Closing the window stops it. **Uninstall FieldScribe** (Start menu) first copies records and the encryption key to `Documents\FieldScribe backup`.

### Offline Copilot (Ollama)

**Settings → Offline AI** shows the engine and memory, recommends a model, downloads it with a progress bar, and runs a test question. FieldScribe starts Ollama itself when it opens and keeps the model loaded (30 min) so replies are quick. Copilot uses Ollama's native chat API with an 8k context window, so the protocol tools and instructions aren't cut off, and it calls the same tools as Gemini: find protocol, check medication, log care (always held for the crew's confirmation), handover draft, audit check.

Provider order: Gemini when online → **local AI** in dead zones → the built-in protocol engine. Switch on *Always use the local AI* and patient details never leave the laptop for AI, even with signal. CPU speed varies: on a typical 8 GB laptop with the 3B model, expect replies in roughly 5–20 s. The 1.5B model is faster with simpler answers.

## 1. Run it (Windows, simplest)

You need **Python 3.10–3.12** ([python.org](https://www.python.org/downloads/), tick *Add Python to PATH*). Node is **not** needed because the dashboard is pre-built in `frontend/dist`.

1. Unzip `FieldScribe.zip` anywhere, e.g. `C:\Users\<you>\Desktop\FieldScribe`.
2. Double-click **`run_windows.bat`**.
   The first run creates `.venv` and installs dependencies (2–4 min). Later runs start in seconds.
3. Your browser opens **http://127.0.0.1:8000**. API docs: http://127.0.0.1:8000/docs

The demo data (9 synthetic Bengaluru incidents) seeds itself on first start.

### Manual steps (any OS)

```bash
cd FieldScribe
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r backend/requirements.txt          # includes SQLCipher encryption
pip install -r backend/requirements-asr.txt     # offline speech recognition
pip install -r backend/requirements-hub.txt     # optional: PostgreSQL hub driver
python run.py
```

macOS/Linux shortcut: `./run_mac_linux.sh`

### Offline voice (Whisper)

Typing works out of the box. For voice:

```bash
pip install -r backend/requirements-asr.txt
cd backend
python fetch_model.py small     # one-time ~480 MB download; use "base" (~145 MB) on slower laptops
cd ..
python run.py                   # picks up backend/models/small automatically
```

**Most accurate option (recommended if the laptop has 8 GB RAM or more):** `python fetch_model.py large-v3-turbo` (~1.6 GB). It handles Indian-accented English and drug names noticeably better than `small`. If several models are downloaded, `run.py` picks the most accurate one automatically.

After that one download, the machine can stay in airplane mode. On the **Capture** page choose **Voice → Start dictation**, allow the microphone, speak, and press **Stop**. The first transcription loads the model (10–30 s). After that it runs at roughly real time on a laptop CPU.

### Hindi and Kannada dictation

108 crews in Karnataka hand over in a mix of Kannada, Hindi and English ("ede novu, 60 varshada gandasu, aspirin 300 mg kottiddini"). On **Capture**, choose what Whisper listens for: **English**, **हिंदी + English**, **ಕನ್ನಡ + English** or **Detect** (also under Settings → Preferences). Hindi and Kannada modes give Whisper a prompt written the way crews speak, so drug names and numbers usually stay in English letters.

Before extraction, an on-device language layer (`backend/app/nlp/indic.py`, no model, no network):

1. reads Devanagari and Kannada script, including native digits, and writes it in plain Latin letters (with Hindi schwa rules, so आदमी → *admi*),
2. matches drug names Whisper spelled in Indian scripts to the lexicon by consonant skeleton (ಪ್ಯಾರಸಿಟಮಾಲ್ → *pyarasitamal* → paracetamol),
3. maps about 330 clinical phrases, numbers and grammar words to clinical English (*seene mein dard* → chest pain, *teen sau* → 300, *munnooru* → 300, *kottiddini* → given, *nas mein* → IV, *nalige kelage* → sublingual).

Plain English passes through untouched. A text only counts as Hindi or Kannada when it has at least one unambiguous Hindi or Kannada word. Capture shows which phrases were mapped. **Model lab → Hindi and Kannada dictation** measures it on 40 development sentences and **24 held-out sentences written after the layer was finished**. On the held-out set, medication F1 is **92% vs 65%** for the English-only engine, and age and sex detection is **92% vs 4%**. The misses are shown sentence by sentence. These are hand-written test sentences, so real accuracy has to be measured on recorded crew audio.

### Login, roles and encryption

FieldScribe opens on a **sign-in screen**. Pick your name and enter your PIN. Demo PINs: **crew 1080**, **ED doctors 2020**, **supervisor 9090** (change them before any real use).

| Role | Can do |
|---|---|
| Ambulance crew (EMT) | Capture, sign, amend, Copilot logging, sync |
| ED doctor | Read everything, acknowledge handover, ask Copilot (read-only) |
| Supervisor | Everything, including the tamper drill and demo reset |

Every signed record, amendment and handover carries the **logged-in user's name**, taken from the session and not from what's typed. Five wrong PINs lock that user for 60 s. The screen **auto-locks after 5 minutes idle**, or press the lock icon.

The device database is **encrypted with SQLCipher (AES-256)** when `sqlcipher3-wheels` is installed (it's in `requirements.txt`). On first start the key is generated and saved in `backend/.env`, and an existing unencrypted database is converted automatically. **Back up `backend/.env`**: without the key the data cannot be read.

### Clinical tools

- **Clinical clock:** timers from what's logged. Vitals recheck (every 5/10/15 min for red/yellow/green), adrenaline repeat window, pain reassessment after analgesia, airway watch after benzodiazepines, glucose recheck after dextrose, tourniquet time (warns at 60 min, critical at 120), CPR 2-minute cycles, and the golden hour for time-critical patients. The bell in the top bar beeps and shows a toast when a timer falls due.
- **Handover readiness:** a score and checklist of what the ED needs (age and sex, allergies, triage, vitals, GCS, doses and routes…) plus condition-specific items, e.g. *time last known well* for stroke, *ECG and aspirin* for chest pain, *glucose before and after* for hypoglycaemia. It's shown on the incident page and to the ED before they accept.
- **Amendments:** on an incident, every entry has **Amend** and **Void**. A reason is required. The original is never deleted: it's marked superseded or voided, the correction is a new `ENTRY_AMENDED` / `ENTRY_VOIDED` block in the audit chain, and the history is shown under the care timeline.
- **Spoken read-back:** turn on the speaker icon in the top bar. Before signing, the record is read aloud ("Aspirin, 300 milligrams, oral, at 10:42 …"), and you say **"confirm"** (or *yes / haan*) to sign, or **"cancel"**. Copilot reads its answers aloud and asks for voice confirmation of held items. It uses Windows' built-in offline voices and the on-device Whisper.

### Field features for real 108 work

- **Right hospital, not nearest hospital** (incident page): works out what the patient needs (stroke unit, cath lab, trauma centre, neurosurgery, burns, children, obstetrics, poisoning, ICU) from the complaint and record, then ranks hospitals by capability and road time. It warns when the nearest hospital can't treat the condition. **Go here** sets the destination and ETA the ED sees. The directory is `backend/hospitals.json`. The capabilities shipped there are a sample, so replace them with your control room's verified list.
- **Medico-legal case (MLC):** road accidents, assault, burns, poisoning, falls from height, hanging, drowning and electrocution are flagged automatically. Record the police station, the time police were informed, the officer, the GD/FIR number, who brought the patient, and belongings handed over. It's sealed in the audit ledger and printed on the handover PDF.
- **ABHA (ABDM) identity:** link a 14-digit ABHA number or an ABHA address (`name@abdm`). The format is checked on the device. It goes into the FHIR `Patient.identifier` and the PDF, marked *linked, not yet verified*, because verification needs ABDM gateway credentials at the hospital. The ledger stores only the last 4 digits.
- **Refusal of care (LAMA):** records what was refused, the reason, capacity or representative, the advice given, a witness, and a finger or stylus signature. The signature's SHA-256 hash is sealed in the ledger, and the image prints on the PDF.
- **Mass casualty mode** (sidebar → Mass casualty, or `G X`): declare an incident, then triage each casualty with **START** (walking? breathing after opening the airway? breathing over 30? radial pulse or capillary refill? follows commands?). Each casualty gets a tag (T-01, T-02 …) and a live board of Red, Yellow, Green and Black counts with one-tap re-triage. Every casualty is a full incident record.
- **Who viewed this record:** every view, PDF download and FHIR export is logged per person, with role and time (DPDP Act 2023 accountability). Each person's views are logged at most once every 10 minutes, so the live auto-refresh doesn't flood the log.

### ED / state hub on PostgreSQL (optional)

Ambulances sync to a hub. By default it's simulated inside the device database. For a real hub:

1. Install PostgreSQL for Windows from https://www.postgresql.org/download/windows/ (EDB installer). Keep port 5432, set a password for the `postgres` user, and skip Stack Builder.
2. Open **SQL Shell (psql)** from the Start menu, press Enter through the prompts, type your password, then run: `CREATE DATABASE fieldscribe_hub;`
3. Install the driver: `.\.venv\Scripts\pip install -r backend\requirements-hub.txt`
4. In `backend\.env` add: `FIELDSCRIBE_HUB_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/fieldscribe_hub`
5. Restart. **Sync & device** shows *PostgreSQL · Connected*, and *Sync now* writes every queued item into `hub_items` (idempotent) and `hub_incidents` (versioned, with conflict detection).

If PostgreSQL is unreachable, sync reports it and the items simply stay queued on the device.

### Offline street map and road routing

The Command centre map can show real Bengaluru streets, lakes, parks and area names with **no internet**. Download the map data once:

```bash
cd backend
..\.venv\Scripts\python fetch_map.py          # Windows   (macOS/Linux: ../.venv/bin/python fetch_map.py)
#   adds ~10-25 MB: main roads, lakes, parks, area names from OpenStreetMap
#   python fetch_map.py --full   also includes every residential street (much larger)
```

It saves `backend/maps/bengaluru.json`. The map then switches automatically:

| Connection | Map | Routes and ETAs |
|---|---|---|
| Online | Live map with a **Dark / Streets / Satellite** switcher (OpenStreetMap with a night filter, OpenStreetMap, Esri imagery) | Live road routing (OSRM), saved after first use |
| Internet drops, the device is set to Offline, or tiles stop loading | **Offline street map** drawn from the downloaded file | **Computed on the laptop** over the real road network |
| Offline and no map file downloaded | True-to-scale offline plot | Saved routes, else labelled straight-line estimates |

It switches back to the live map as soon as the connection returns (checked every 20 s). The ED handover countdown and the "On the road" cards use the same road ETA. Ambulances may use either direction of one-way roads. Map data © OpenStreetMap contributors (ODbL).

### DistilBERT clinical NER (hybrid engine)

FieldScribe ships with a rule + lexicon + fuzzy extractor. Training the DistilBERT model turns on the **hybrid** engine. DistilBERT confirms rule hits and catches drug mentions the rules miss (unseen brands, badly mis-heard names). The rules still own codes, doses and safety checks, and anything found only by DistilBERT is flagged for EMT review.

```bash
pip install -r backend/requirements-ml.txt     # torch + transformers (CPU is fine)
cd backend
python train_ner.py                           # downloads distilbert-base-uncased once, ~10-25 min on CPU
#   quicker:  python train_ner.py --epochs 2 --train-n 4000
#   1-minute pipeline check, no download:  python train_ner.py --tiny
```

The model is saved to `backend/models/ner-distilbert/`. Restart FieldScribe and **Model lab** shows a held-out three-way comparison (rules vs DistilBERT vs hybrid) plus the model card. On Windows you can double-click `train_distilbert_windows.bat` instead.

Training data is synthetic, BIO-labelled dictations (DRUG, DOSE, UNIT, ROUTE, TIME, PROC, NEG) generated from the lexicon, random ASR-style corruptions and invented brand names in drug position, so the model learns context and not just spelling. The test split uses a different seed, heavier corruption and **real Indian brands that appear in neither the lexicon nor the training data**.

### AI Copilot (agent)

The **Copilot** page is a tool-calling agent. Describe a patient and it opens the matching first-aid protocol card. Tell it what you have done ("gave ecosprin 300 mg chewed, collar applied, bp 140/90") and it writes that into the signed record. Items with a critical safety flag (allergy conflict, ~10× dose) are held until the EMT presses **Checked, log it**. It never logs its own suggestions.

It works without any key using the built-in offline protocol engine. For the full conversational agent, add a free key:

1. Go to https://aistudio.google.com/apikey and create a Gemini API key (free tier; your ChatGPT subscription is not an API key).
2. Copy `backend/.env.example` to `backend/.env`. The Windows launcher does this for you on first run.
3. Paste the key after `GEMINI_API_KEY=` and restart. The Copilot header shows *Google Gemini*. New keys start with `AQ.` (older ones with `AIza`); both work.

Models: `GEMINI_MODEL=gemini-3.8-flash` (best answers) or `gemini-3.5-flash-lite` (fastest). If the main model is slow, busy or over quota, FieldScribe retries once on `GEMINI_FALLBACK_MODEL` (default `gemini-3.5-flash-lite`) before moving to the next provider. Gemini 2.5 models are not available to new keys.

**Fully offline Copilot (no internet at all):** install [Ollama](https://ollama.com), then run `ollama pull qwen2.5:7b` (~4.7 GB, needs 8 GB RAM; on 16 GB RAM `qwen2.5:14b` is better). Leave Ollama running and the Copilot uses it whenever the device is offline.

Optional backups, tried in this order: `GROQ_API_KEY` (free, https://console.groq.com/keys), `OPENAI_API_KEY`, then a local model via [Ollama](https://ollama.com) (`ollama pull qwen2.5:7b`), then the offline engine. When the device is set to **Offline**, cloud providers are skipped automatically. Cloud models only receive de-identified clinical fields (no place, vehicle or crew names). Keys stay in `backend/.env` and are never returned by the API. Do not share that file or commit it.

### Navigating the app

- **Ctrl K** (or `/`) opens the command bar: search incidents by dispatch ID or complaint, jump to any page, go offline, sync, lock, sign out.
- **?** shows every shortcut. **G then a letter** jumps to a page (G C Capture, G A Copilot, G E ED handover, G P Settings …). **N** starts a new incident.
- A short guided tour runs the first time each person signs in on a device. Replay it from the command bar or Settings.

### Settings

- **My account:** see what your role can do, and change your PIN.
- **Users** (supervisor only): add people, reset a PIN (also unlocks and signs them out everywhere), disable or re-enable accounts. The login screen stops showing the demo PIN hint once every account has its own PIN.
- **Readiness check:** every component (dashboard, encryption, PINs, Whisper, DistilBERT, cloud and offline Copilot, map, hub) shows green, amber or red, with the exact command to fix it.
- **Preferences & app:** spoken read-back, install as an app, shortcuts, tablet access.

### Install as an app

In Chrome or Edge, open FieldScribe and click the install icon in the address bar (or **Settings → Preferences & app → Install FieldScribe**). You get a desktop icon and FieldScribe opens in its own window. The app's screens are stored on the device, so it opens with no network.

### Phones and tablets (laptop does the work, phones are the screens)

The laptop in the ambulance runs FieldScribe. Crew phones and the ED tablet use it over the ambulance Wi-Fi or the laptop's **mobile hotspot** (Windows Settings → Network → Mobile hotspot), with no internet needed.

1. Start **FieldScribe (tablet mode)** from the Start menu (or `start_tablet_mode.bat`). The window shows a QR code, and so does **Settings → Preferences & app**. Allow *Private networks* if Windows asks about the firewall.
2. On the phone, scan the QR code. It opens `http://<laptop-ip>:8000/phone`, a set-up page that walks through three steps:
   - **Download the laptop's certificate.** FieldScribe creates its own certificate authority on the laptop the first time. Only the public certificate is ever served; the private key stays in `backend/data/certs`.
   - **Trust it** (the page shows the exact Android or iPhone steps).
   - **Open FieldScribe securely** at `https://<laptop-ip>:8443`, sign in with your PIN, and add it to the home screen.

Over HTTPS the phone can **dictate** (browsers only allow the microphone on secure pages) and install FieldScribe as an app icon that opens full-screen. Speech recognition, the AI and the records all stay on the laptop. The phone is just the screen and microphone. The certificate covers the laptop's current Wi-Fi addresses and renews itself if the address changes. Phones then reuse the same trusted authority, so they only set up once.

### Docker (app + PostgreSQL hub in one command)

```bash
docker compose up --build        # http://localhost:8000
```

This starts two containers: FieldScribe and a PostgreSQL 17 hub that it syncs to. The encrypted device database and its key live in the `fieldscribe-data` volume. For cloud Copilot, create a `.env` file next to `docker-compose.yml` with `GEMINI_API_KEY=...`. Set `HUB_DB_PASSWORD` there too for anything beyond a demo. A local Ollama on the host is reached automatically.

### Developing the dashboard

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173 (proxies /api to :8000; keep run.py running)
npm run build                     # rebuild frontend/dist
```

### Tests

```bash
pip install -r backend/requirements-dev.txt
cd backend && python -m pytest -q
```

---

## 2. Five-minute judge demo

| # | Screen | What to do | What it proves |
|---|---|---|---|
| 1 | Command centre | Point at the fleet plot, live units and their monitor traces | Situational view; the trace speed follows each patient's recorded HR |
| 2 | Top bar | Click **Online** to go **Offline** | Dead-zone mode; everything below still works |
| 3 | Capture | Click the **Noisy ASR + traps** sample | Misspellings auto-corrected *and flagged*; allergy conflict; 10× adrenaline dose caught; "no morphine" recorded as withheld; duplicate aspirin caught |
| 4 | Capture | Edit a dose, open **Why these values**, tick the critical acknowledgements, **Confirm and sign** | Human in the loop, explainable extraction, signed block |
| 5 | Capture | Try **Hinglish trauma** or dictate by voice | Code-mixed speech ("RL 500 ml iv chadhaya", "c collar lagaya") |
| 6 | Incident | Open the incident: 108 timeline, vitals trend, care timeline, **FHIR bundle**, **Handover PDF** | Interoperable output (MedicationAdministration, Procedure, Observation, Provenance) |
| 7 | Sync & device | **Simulate ED edit**, then go back **Online** | Outbox sync with conflict resolution |
| 8 | ED handover | Countdown board, ATMIST summary, **Acknowledge handover** | ED receives the record before the patient arrives |
| 9 | Audit ledger | **Tamper with a dose**: chain turns red at the exact block. **Restore original** | Tamper-evidence; the PDF footer and QR carry the ledger head |
| 10 | Copilot | Click the bleeding quick prompt, then type "allergic to diclofenac. tourniquet applied at 10:05, txa 1 g iv given, collar applied, voveran 75 mg im" | Protocol card with checklist; safe items signed instantly; Voveran held for confirmation |
| 11 | Model lab | Noise-robustness curve, slice F1, silent-error rate, live probe | Honest evaluation, including where it breaks |

---

## 3. Architecture

```
 Mic / keyboard ─► Offline ASR ─► Normaliser ─► Hybrid clinical NER ─► Safety engine ─► EMT review & sign
                  faster-whisper  Hinglish,      lexicon + fuzzy         allergy, range,       │
                  int8 + clinical  spoken nums,  (rapidfuzz) + clause    duplicate, high-alert, ▼
                  vocab prompt     times         attachment + negation   paediatric, units   SQLite (WAL)
                                                                                                │
             ┌──────────────────────────┬───────────────────────┬─────────────────────────────┤
             ▼                          ▼                       ▼                             ▼
   SHA-256 hash chain +         FHIR R4 Bundle            ATMIST PDF + QR             Outbox ─► ED hub sync
   Ed25519 device signature     (RxNorm, SNOMED,          (reportlab)                 (append-only merge,
   verify / tamper drill        LOINC, UCUM)                                          conflict log)
```

| Layer | Tech |
|---|---|
| ASR | faster-whisper (CTranslate2) Whisper-small int8, VAD filter, clinical vocabulary prompt |
| NER | Rule + lexicon + fuzzy engine (36 drugs / 160+ aliases incl. Indian brands, 16 procedures, code-mixed verbs) merged with a fine-tuned **DistilBERT** token classifier (BIO: DRUG, DOSE, UNIT, ROUTE, TIME, PROC, NEG); per-field confidence + evidence trail |
| Safety | Demo reference ranges, ×10 unit errors, allergy conflicts, duplicates across the incident, high-alert/controlled, paediatric, ambiguous brands never auto-resolved |
| Records | FastAPI + SQLite, FHIR R4 (MedicationAdministration, Procedure, Observation, AllergyIntolerance, Encounter, Provenance) |
| Audit | Canonical-JSON SHA-256 chain, Ed25519 signatures (`cryptography`), full replay verification |
| Map & routing | Offline OpenStreetMap extract (roads, lakes, parks, places) drawn with Leaflet on canvas; on-device Dijkstra routing over the road graph; OSRM and tile fallback online |
| Agent | Tool-calling Copilot (Gemini → Groq → OpenAI → Ollama → offline engine), 9 tools incl. protocol lookup, medication check, care logging with confirmation hold |
| UI | React 18 + TypeScript + Vite + Tailwind + Recharts + Framer Motion, fonts bundled (fully offline) |

## 4. API (selected)

`POST /api/extract` · `POST /api/asr` · `GET/POST /api/incidents` · `POST /api/incidents/{id}/records` (sign) · `GET /api/incidents/{id}/fhir` · `GET /api/incidents/{id}/pdf` · `POST /api/incidents/{id}/handover` · `GET /api/ledger/verify` · `POST /api/ledger/tamper|restore` · `GET /api/sync` · `POST /api/settings/online` · `GET /api/eval` · `GET /api/lexicon` · `POST /api/agent/chat` · `POST /api/agent/confirm` · `GET /api/agent/status`. Full interactive docs at `/docs`.

## 5. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `FIELDSCRIBE_ASR_MODEL` | `small` | `tiny`/`base`/`small`/`medium` or a local model folder |
| `FIELDSCRIBE_ASR_COMPUTE` | `int8` | CTranslate2 compute type |
| `FIELDSCRIBE_DATA` | `backend/data` | SQLite DB and device key location |
| `FIELDSCRIBE_AUTOSEED` | `1` | Seed demo incidents on an empty DB |
| `PORT` / `HOST` | `8000` / `127.0.0.1` | Server bind (use `HOST=0.0.0.0` to open it from a phone on the same Wi-Fi) |

Reset the demo any time from **Sync & device → Reset demo data**.

## 6. Honest limits

- All data is synthetic. No real PHI is used.
- Dose reference ranges are demo values that raise review flags only. They are not clinical guidance; a deployment loads its state 108 / medical-director protocol.
- RxNorm codes are ingredient-level RXCUIs. Entries shown as *verify* and local `FS-PROC` codes must be mapped by a terminology service before production.
- DistilBERT is trained on synthetic dictations. In the sandbox the full pipeline was verified with a tiny locally built DistilBERT (held-out hybrid F1 0.95 vs 0.82 for rules alone). Numbers for `distilbert-base-uncased` come from your own training run and appear in Model lab.
- The templated benchmark is a regression floor. The noise-robustness curve and field WER from EMT-corrected transcripts are the more realistic signals. Pilot validation on recorded 108 dictations is the next step.
