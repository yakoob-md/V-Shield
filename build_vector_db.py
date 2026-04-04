"""
build_vector_db.py
==================
Generates realistic anti-doping datasets, creates sentence embeddings,
and stores them in a FAISS index for RAG-based retrieval.

Run this ONCE before starting the backend:
    python build_vector_db.py
"""

import json
import pickle
import numpy as np

# ── Third-party ────────────────────────────────────────────────────────────────
try:
    import faiss
    from sentence_transformers import SentenceTransformer
except ImportError:
    raise SystemExit(
        "Please install dependencies first:\n"
        "  pip install faiss-cpu sentence-transformers"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1.  DATASET DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

# ── 1a. WADA Prohibited Substances ────────────────────────────────────────────
WADA_SUBSTANCES = [
    {"name": "Testosterone", "category": "Anabolic Agents", "banned": True,
     "notes": "Endogenous anabolic steroid; triggers positive if ratio >4:1."},
    {"name": "Nandrolone", "category": "Anabolic Agents", "banned": True,
     "notes": "Found in contaminated meat and some herbal supplements."},
    {"name": "Stanozolol", "category": "Anabolic Agents", "banned": True,
     "notes": "Common in counterfeit mass-gainer powders sold in rural markets."},
    {"name": "Clostebol", "category": "Anabolic Agents", "banned": True,
     "notes": "Present in some topical creams/ointments used for wound healing."},
    {"name": "Clenbuterol", "category": "Beta-2 Agonists", "banned": True,
     "notes": "Found in contaminated meat; also misused as a fat-burner."},
    {"name": "Salbutamol (Albuterol)", "category": "Beta-2 Agonists", "banned": False,
     "notes": "Permitted by inhalation up to 1600 mcg/day for asthma. Needs TUE for oral."},
    {"name": "EPO (Erythropoietin)", "category": "Peptide Hormones", "banned": True,
     "notes": "Blood-boosting agent; banned in all sports at all times."},
    {"name": "HGH (Human Growth Hormone)", "category": "Peptide Hormones", "banned": True,
     "notes": "Banned in-competition and out-of-competition."},
    {"name": "Methylhexaneamine (DMAA)", "category": "Stimulants", "banned": True,
     "notes": "Derived from geranium oil; found in pre-workouts and cosmetics."},
    {"name": "Ephedrine", "category": "Stimulants", "banned": True,
     "notes": "Present in traditional Chinese medicine and some cold remedies."},
    {"name": "Pseudoephedrine", "category": "Stimulants", "banned": True,
     "notes": "Common decongestant in over-the-counter cold medicines."},
    {"name": "Amphetamine", "category": "Stimulants", "banned": True,
     "notes": "Some ADHD medications contain amphetamine – TUE needed."},
    {"name": "Furosemide", "category": "Diuretics / Masking Agents", "banned": True,
     "notes": "Used medically for edema; banned in sport as a masking agent."},
    {"name": "Probenecid", "category": "Diuretics / Masking Agents", "banned": True,
     "notes": "Gout medicine that can mask steroid use – always banned."},
    {"name": "Prednisolone", "category": "Glucocorticoids", "banned": True,
     "notes": "Common anti-inflammatory; banned in-competition without TUE."},
    {"name": "Dexamethasone", "category": "Glucocorticoids", "banned": True,
     "notes": "Frequently prescribed by rural doctors; triggers positive test."},
    {"name": "Betamethasone", "category": "Glucocorticoids", "banned": True,
     "notes": "Topical and injectable steroid; banned in-competition."},
    {"name": "Cannabinoids (THC)", "category": "Cannabinoids", "banned": True,
     "notes": "Banned in-competition only. CBD is NOT prohibited."},
    {"name": "Insulin", "category": "Peptide Hormones", "banned": True,
     "notes": "Banned for non-diabetic athletes. Diabetic athletes need TUE."},
    {"name": "Ibuprofen", "category": "NSAIDs", "banned": False,
     "notes": "NOT banned. Safe for athletes to use as pain relief."},
    {"name": "Paracetamol (Acetaminophen)", "category": "Analgesics", "banned": False,
     "notes": "NOT banned. Safe to use for fever and pain."},
    {"name": "Creatine Monohydrate", "category": "Supplements", "banned": False,
     "notes": "NOT banned by WADA. Widely used and generally safe if certified."},
    {"name": "Caffeine", "category": "Stimulants", "banned": False,
     "notes": "NOT banned. Monitored substance – high doses flag for investigation."},
]

# ── 1b. Indian Medicine Dataset ────────────────────────────────────────────────
MEDICINES = [
    {"brand": "Becosules", "composition": "Vitamin B complex", "banned": False,
     "notes": "Multivitamin – safe for athletes."},
    {"brand": "Combiflam", "composition": "Ibuprofen + Paracetamol", "banned": False,
     "notes": "Pain relief – NOT banned."},
    {"brand": "Corex", "composition": "Codeine + Chlorpheniramine", "banned": True,
     "notes": "Contains Codeine (narcotic analgesic) – banned in-competition."},
    {"brand": "Vicks Action 500", "composition": "Paracetamol + Pseudoephedrine", "banned": True,
     "notes": "Contains Pseudoephedrine – BANNED stimulant. Avoid completely."},
    {"brand": "Allegra", "composition": "Fexofenadine", "banned": False,
     "notes": "Antihistamine – safe for athletes."},
    {"brand": "Betnovate Cream", "composition": "Betamethasone", "banned": True,
     "notes": "Contains glucocorticoid – banned in-competition."},
    {"brand": "Foracort Inhaler", "composition": "Budesonide + Formoterol", "banned": True,
     "notes": "Contains glucocorticoid and beta-2 agonist – TUE required."},
    {"brand": "Pan 40", "composition": "Pantoprazole", "banned": False,
     "notes": "Antacid – safe for athletes."},
    {"brand": "Taxim-O", "composition": "Cefixime", "banned": False,
     "notes": "Antibiotic – safe for athletes."},
    {"brand": "Disprin", "composition": "Aspirin", "banned": False,
     "notes": "NOT banned. Safe to use."},
    {"brand": "Benadryl Cough Syrup", "composition": "Diphenhydramine + Ammonium Chloride", "banned": False,
     "notes": "Safe – no banned substance. But check variant; some versions have codeine."},
    {"brand": "ORS (Electral)", "composition": "Sodium + Potassium + Glucose", "banned": False,
     "notes": "Rehydration solution – completely safe."},
    {"brand": "Decadron Injection", "composition": "Dexamethasone", "banned": True,
     "notes": "Glucocorticoid injection – banned in-competition without TUE."},
    {"brand": "Actifed", "composition": "Triprolidine + Pseudoephedrine", "banned": True,
     "notes": "BANNED – contains Pseudoephedrine stimulant."},
    {"brand": "Clotrimazole (Candid)", "composition": "Clotrimazole", "banned": False,
     "notes": "Antifungal – safe for athletes."},
]

# ── 1c. Indian Supplement Dataset ─────────────────────────────────────────────
SUPPLEMENTS = [
    {"name": "Ashwagandha", "type": "Ayurvedic", "certified": False,
     "risk": "HIGH",
     "notes": "Contains plant steroids (withanolides) that can trigger anabolic agent positives. Contamination risk very high."},
    {"name": "Tribulus Terrestris", "type": "Herbal", "certified": False,
     "risk": "HIGH",
     "notes": "Contains steroidal saponins; linked to testosterone positives. AVOID."},
    {"name": "Deer Antler Velvet", "type": "Herbal", "certified": False,
     "risk": "HIGH",
     "notes": "Contains IGF-1 (insulin-like growth factor) – banned peptide hormone. NEVER use."},
    {"name": "Shilajit", "type": "Ayurvedic", "certified": False,
     "risk": "HIGH",
     "notes": "Heavy metals found in many samples. May contain undeclared steroids."},
    {"name": "Kaunch Beej (Mucuna Pruriens)", "type": "Ayurvedic", "certified": False,
     "risk": "HIGH",
     "notes": "Contains L-DOPA; may affect dopamine and trigger positive for controlled substances."},
    {"name": "Whey Protein (local unbranded)", "type": "Protein Supplement", "certified": False,
     "risk": "HIGH",
     "notes": "Unbranded local whey frequently adulterated with anabolic steroids and cheap fillers."},
    {"name": "Mass Gainer (counterfeit)", "type": "Protein Supplement", "certified": False,
     "risk": "HIGH",
     "notes": "Counterfeit mass gainers often contain banned anabolic agents and diuretics."},
    {"name": "Optimum Nutrition Gold Standard Whey", "type": "Protein Supplement", "certified": True,
     "risk": "LOW",
     "notes": "Internationally certified brand. Relatively safe but buy from verified retailers only."},
    {"name": "MuscleBlaze Whey Protein (CoE-NSTS certified)", "type": "Protein Supplement", "certified": True,
     "risk": "LOW",
     "notes": "CoE-NSTS batch tested and certified. Safe for Indian athletes."},
    {"name": "Creatine Monohydrate (Bigmuscles / CoE-NSTS)", "type": "Performance", "certified": True,
     "risk": "LOW",
     "notes": "Creatine itself is not banned. CoE-NSTS certified batch – safe."},
    {"name": "Geranium Oil / Geranamine", "type": "Pre-workout ingredient", "certified": False,
     "risk": "HIGH",
     "notes": "Natural source of DMAA (Methylhexaneamine) – BANNED stimulant. Found in cosmetics too."},
    {"name": "Pre-workout (local unbranded)", "type": "Pre-workout", "certified": False,
     "risk": "HIGH",
     "notes": "Unverified pre-workouts frequently contain DMAA, ephedrine, or banned stimulants."},
    {"name": "Sarpagandha (Rauwolfia)", "type": "Ayurvedic", "certified": False,
     "risk": "HIGH",
     "notes": "Contains reserpine and yohimbine – potential stimulant flagging."},
    {"name": "Multivitamin (Revital H / CoE-NSTS)", "type": "Vitamins", "certified": True,
     "risk": "LOW",
     "notes": "Standard multivitamin – if CoE-NSTS certified batch, safe to use."},
    {"name": "Iron Supplements (Ferrous Sulphate)", "type": "Minerals", "certified": False,
     "risk": "LOW",
     "notes": "NOT banned. Safe for anemic athletes. Prefer pharmaceutical grade."},
    {"name": "Vitamin D3 (Calcirol)", "type": "Vitamins", "certified": False,
     "risk": "LOW",
     "notes": "NOT banned. Safe and commonly needed in India."},
]

# ── 1d. Educational Knowledge Chunks ──────────────────────────────────────────
KNOWLEDGE_TEXTS = [
    # Strict Liability
    ("WADA Strict Liability Rule",
     "WADA ka Strict Liability rule kehta hai: agar teri body mein koi banned substance mili, "
     "toh tu zimmedar hai – chahe tune jaanbujhkar liya ho ya nahi. Isiliye har cheez lene se pehle check karna zaroori hai. "
     "Rural athletes ko yeh rule sabse zyada affect karta hai kyunki unhe koi sports scientist ki madad nahi milti."),

    # Supplement Contamination
    ("Supplement Contamination in India",
     "India mein bechne wale bahut saare supplements unregulated hain. "
     "Local market ke protein powders aur mass gainers mein aksar steroids milaye jaate hain bina label pe likhe. "
     "Sirf CoE-NSTS (Centre of Excellence in Nutritional Supplements Testing) certified products use karo. "
     "Koi bhi uncertified supplement lena doping ka risk hai."),

    # Ayurvedic Risk
    ("Ayurvedic Supplements and Doping Risk",
     "Ashwagandha, Tribulus Terrestris, aur Shilajit jaise Ayurvedic products mein plant steroids hote hain "
     "jo doping test mein positive aa sakte hain. "
     "Yeh natural hai iska matlab safe nahi hai. "
     "WADA ne kai athletes ko sirf Ayurvedic supplements ki wajah se ban kiya hai."),

    # TUE Process
    ("Therapeutic Use Exemption (TUE) Process",
     "Agar tujhe koi banned medicine doctor ne di hai – jaise asthma ke liye inhaler ya koi steroid cream – "
     "toh competition se pehle NADA se TUE (Therapeutic Use Exemption) lena padega. "
     "TUE ke liye doctor ki prescription aur medical report chahiye. "
     "Bina TUE ke woh medicine lena automatic doping violation hai."),

    # Rural Doctor Warning
    ("Rural Doctors and Sports Pharmacology",
     "Gaon ke doctors aur government clinic ke nurses ko WADA Prohibited List ke baare mein aksar kuch pata nahi. "
     "Woh routine mein glucocorticoid injections ya pseudoephedrine wali cough syrup de sakte hain "
     "jo doping violation karti hain. "
     "Isliye doctor se medicine lene se pehle NADA KYM app ya is assistant se zaroor check karo."),

    # CoE-NSTS Certification
    ("CoE-NSTS Supplement Certification",
     "CoE-NSTS yaani Centre of Excellence in Nutritional Supplements Testing for Sportspersons "
     "ek government-backed certification hai jo supplements ko batch-test karta hai. "
     "Agar kisi supplement ka CoE-NSTS ya NFSU-NSTS Certified label hai, toh woh relatively safe hai. "
     "Har supplement ki certification status cnsts.nfsu.ac.in pe check karo."),

    # Clostebol Case (Manjeet Singh)
    ("Clostebol in Healing Creams - Manjeet Singh Case",
     "Ek famous case mein, Manjeet Singh naam ke athlete ko government nurse ne Clostebol wali healing cream lagayi "
     "jo ek anabolic steroid hai. "
     "Unhe pata nahi tha, phir bhi WADA ne unhe ban kar diya. "
     "Yeh dikhata hai ki topical creams aur ointments bhi check karne chahiye."),

    # Geranium Oil / DMAA
    ("DMAA and Geranium Oil Warning",
     "Methylhexaneamine (DMAA) ek banned stimulant hai jo geranium oil se naturally milta hai. "
     "Yeh kai pre-workout supplements aur yahan tak ki cosmetic products mein bhi hota hai. "
     "Agar koi product geranium oil, geranamine, ya 1,3-dimethylamylamine list karta hai, "
     "toh use bilkul mat lo – yeh banned hai."),

    # Meat Contamination
    ("Contaminated Meat and Clenbuterol",
     "Kuch deshon mein cattle ko Clenbuterol diya jaata hai growth ke liye. "
     "Agar tum wahan ka meat khao, toh teri body mein Clenbuterol aa sakta hai aur test positive ho sakta hai. "
     "International tournaments mein participate karne wale athletes ko yeh dhyan rakhna chahiye."),

    # Safe Supplements Summary
    ("Safe Supplements for Indian Athletes",
     "Indian athletes ke liye relatively safe supplements: "
     "Creatine Monohydrate (CoE-NSTS certified), Whey Protein (CoE-NSTS certified brands jaise MuscleBlaze), "
     "Vitamin D3, Iron supplements, aur Multivitamins. "
     "Hamesha certified batch lo aur local unbranded products se door raho."),

    # Whistleblowing / Doping Rings
    ("Reporting Doping in Rural Gyms",
     "Agar tera coach ya gym owner tujhe bina label ka powder ya injection de raha hai, "
     "toh yeh illegal hai aur tujhe ban karwa sakta hai. "
     "Tu anonymously NADA ke helpline pe report kar sakta hai. "
     "Apni career aur health ki raksha karo."),

    # India's Doping Problem
    ("India's Doping Statistics",
     "WADA 2024 report ke mutabiq, India globally sabse zyada doping violations wala desh hai – "
     "7113 samples mein se 260 Adverse Analytical Findings mile, jo 3.6% positivity rate hai. "
     "Athletics, weightlifting, aur wrestling mein 55% se zyada cases hain. "
     "98% cases inadvertent doping se hain – matlab athletes ko pata nahi tha ki substance banned hai."),

    # Out of Competition Testing
    ("Out-of-Competition Testing and ADAMS",
     "Elite athletes ko apni daily location ADAMS (Anti-Doping Administration and Management System) pe report karni hoti hai. "
     "Doping testers kabhi bhi ghar ya training camp aa sakte hain. "
     "Agar tum whereabouts report nahi karte ya 3 baar miss ho jata hai, toh yeh bhi violation hai."),
]


# ══════════════════════════════════════════════════════════════════════════════
# 2.  TEXT CHUNK GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def build_text_chunks() -> list[str]:
    """
    Converts all structured datasets into natural-language text chunks
    suitable for embedding and retrieval.
    """
    chunks = []

    # WADA substances
    for s in WADA_SUBSTANCES:
        status = "BANNED ❌" if s["banned"] else "ALLOWED ✅ (in sport)"
        text = (
            f"[WADA Substance] {s['name']} | Category: {s['category']} | "
            f"Status: {status} | Notes: {s['notes']}"
        )
        chunks.append(text)

    # Medicines
    for m in MEDICINES:
        status = "BANNED ❌" if m["banned"] else "SAFE ✅"
        text = (
            f"[Medicine] Brand: {m['brand']} | Composition: {m['composition']} | "
            f"Status: {status} | Notes: {m['notes']}"
        )
        chunks.append(text)

    # Supplements
    for s in SUPPLEMENTS:
        cert = "CoE-NSTS Certified ✅" if s["certified"] else "NOT Certified ⚠️"
        text = (
            f"[Supplement] Name: {s['name']} | Type: {s['type']} | "
            f"Risk: {s['risk']} | Certification: {cert} | Notes: {s['notes']}"
        )
        chunks.append(text)

    # Knowledge texts
    for title, body in KNOWLEDGE_TEXTS:
        chunks.append(f"[Knowledge: {title}] {body}")

    print(f"✅ Total text chunks generated: {len(chunks)}")
    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# 3.  EMBEDDING + FAISS INDEX
# ══════════════════════════════════════════════════════════════════════════════

def build_faiss_index(chunks: list[str]):
    """
    Embeds all chunks using SentenceTransformers and stores them in FAISS.
    Saves:
        faiss_index.bin   – FAISS index file
        chunks.pkl        – corresponding list of raw text chunks
    """
    print("⏳ Loading embedding model (paraphrase-multilingual-MiniLM-L12-v2)…")
    # Multilingual model supports Hindi text too
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    print("⏳ Generating embeddings…")
    embeddings = model.encode(chunks, show_progress_bar=True, convert_to_numpy=True)
    embeddings = embeddings.astype(np.float32)

    dimension = embeddings.shape[1]
    print(f"✅ Embedding dimension: {dimension}")

    # Build a flat L2 index (exact search – fine for small datasets)
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    print(f"✅ FAISS index built with {index.ntotal} vectors")

    # Persist
    faiss.write_index(index, "faiss_index.bin")
    print("💾 Saved → faiss_index.bin")

    with open("chunks.pkl", "wb") as f:
        pickle.dump(chunks, f)
    print("💾 Saved → chunks.pkl")

    # Save raw datasets as JSON for optional inspection
    datasets = {
        "wada_substances": WADA_SUBSTANCES,
        "medicines": MEDICINES,
        "supplements": SUPPLEMENTS,
    }
    with open("datasets.json", "w", encoding="utf-8") as f:
        json.dump(datasets, f, indent=2, ensure_ascii=False)
    print("💾 Saved → datasets.json")

    print("\n🎉 Vector DB build complete! Run `python main.py` to start the API.")


# ══════════════════════════════════════════════════════════════════════════════
# 4.  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Anti-Doping RAG – Vector DB Builder")
    print("=" * 60)
    chunks = build_text_chunks()
    build_faiss_index(chunks)