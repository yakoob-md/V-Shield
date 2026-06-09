"""
seed_demo_db.py
===============
Seeds the SQLite database with realistic demo conversations that showcase
V-Shield AI's capabilities to recruiters and evaluators.

Run ONCE during Docker image build:
    python seed_demo_db.py
"""

import sqlite3
import os

DB_PATH = os.getenv("SQLITE_DB_PATH", "chats_v2.db")

DEMO_CHATS = [
    {
        "title": "Vicks Action 500 – Is it safe?",
        "messages": [
            {
                "role": "user",
                "content": "Bhai, mujhe zukam ho gaya hai. Kya main Vicks Action 500 le sakta hoon? Kal district trial hai.",
                "language": "hindi",
                "risk_level": "unknown",
            },
            {
                "role": "assistant",
                "content": "BANNED ❌ – Vicks Action 500 bilkul mat lo, yeh ek serious doping violation hai. Isme Pseudoephedrine hota hai jo WADA ke Prohibited List mein stimulants category mein banned hai – iske liye koi TUE bhi nahi milta competition se pehle. Zukam ke liye safe alternatives jaise Cetirizine (Cetzine) ya sirf Paracetamol lo – yeh dono completely WADA-compliant hain.",
                "language": "hindi",
                "risk_level": "banned",
            },
            {
                "role": "user",
                "content": "Accha, toh Cetirizine safe hai? Coach ne bola tha kuch bhi mat lo.",
                "language": "hindi",
                "risk_level": "unknown",
            },
            {
                "role": "assistant",
                "content": "SAFE ✅ – Cetirizine (brand name Cetzine ya Allegra) ek antihistamine hai jo WADA ke prohibited list mein nahi hai – tum safely le sakte ho. Coach ka advice generally sahi hai kyunki bohot saari common medicines mein hidden banned substances hote hain, lekin antihistamines jaise Cetirizine aur Fexofenadine international level pe bhi approved hain. Competition ke din ek Cetirizine tablet lo aur hydrated raho – yeh safe aur effective dono hai.",
                "language": "hindi",
                "risk_level": "safe",
            },
        ],
    },
    {
        "title": "Ashwagandha supplement risk",
        "messages": [
            {
                "role": "user",
                "content": "My coach is recommending Ashwagandha for recovery. Is it safe for competitive athletes?",
                "language": "english",
                "risk_level": "unknown",
            },
            {
                "role": "assistant",
                "content": "CAUTION ⚠️ – Ashwagandha itself is not on the WADA Prohibited List, but it carries a HIGH contamination risk that could end your career. It contains withanolides (plant steroids) that can trigger a false positive for anabolic agents, and multiple Indian studies have found undeclared testosterone and other banned substances in commercially available Ashwagandha products. If you must use it, only choose a CoE-NSTS certified batch from cnsts.nfsu.ac.in and inform your national federation before competition.",
                "language": "english",
                "risk_level": "caution",
            },
            {
                "role": "user",
                "content": "What about KSM-66 brand specifically?",
                "language": "english",
                "risk_level": "unknown",
            },
            {
                "role": "assistant",
                "content": "CAUTION ⚠️ – KSM-66 is a patented, standardized Ashwagandha extract with better quality controls than generic brands, but it still carries contamination risk because it is not CoE-NSTS certified for Indian athletes specifically. The brand has some third-party testing but no WADA-recognized certification chain, meaning if you test positive, you cannot use it as a defense. The safest approach remains: avoid all Ashwagandha during competition season and replace it with CoE-NSTS certified Creatine Monohydrate for recovery, which has a clean scientific record.",
                "language": "english",
                "risk_level": "caution",
            },
        ],
    },
    {
        "title": "Creatine for road cycling – WADA status",
        "messages": [
            {
                "role": "user",
                "content": "Main road cyclist hoon. Creatine lena chahta hoon performance ke liye. WADA mein banned hai kya?",
                "language": "hindi",
                "risk_level": "unknown",
            },
            {
                "role": "assistant",
                "content": "SAFE ✅ – Creatine Monohydrate WADA ke prohibited list mein nahi hai – tum le sakte ho bina kisi doping risk ke. Lekin ek important baat: sirf CoE-NSTS certified brand lo jaise MuscleBlaze Creatine ya Bigmuscles Creatine, kyunki local unbranded creatine mein aksar banned anabolic agents milaye jaate hain manufacturers ke profit ke liye. cnsts.nfsu.ac.in pe certified batch number verify karo pehle kharidne se.",
                "language": "hindi",
                "risk_level": "safe",
            },
        ],
    },
    {
        "title": "Decadron injection – competition week",
        "messages": [
            {
                "role": "user",
                "content": "Doctor gave me Decadron injection for knee inflammation. My race is in 3 days. What should I do?",
                "language": "english",
                "risk_level": "unknown",
            },
            {
                "role": "assistant",
                "content": "BANNED ❌ – Decadron (Dexamethasone) is a glucocorticoid and is strictly prohibited in-competition without a Therapeutic Use Exemption (TUE) – taking it 3 days before your race puts you at serious risk of a violation. You must immediately contact NADA India (nada.nic.in) to apply for a retroactive TUE, and inform your team doctor and federation about the injection you received. While waiting for TUE approval, keep all medical documentation including the doctor's prescription, the injection batch number, and the clinical diagnosis – this evidence is critical to your defense if you test positive.",
                "language": "english",
                "risk_level": "banned",
            },
        ],
    },
]


def seed_database():
    print(f"🌱 Seeding demo database at: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row

    # Create tables if they don't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    INTEGER NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            language   TEXT NOT NULL DEFAULT 'hindi',
            risk_level TEXT NOT NULL DEFAULT 'unknown',
            timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
        )
    """)

    # Only seed if the DB is empty (don't overwrite existing real data)
    existing = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
    if existing > 0:
        print(f"✅ Database already has {existing} chats. Skipping seed.")
        conn.close()
        return

    for i, chat in enumerate(DEMO_CHATS):
        # Use staggered timestamps so chats appear in logical order
        offset_minutes = (len(DEMO_CHATS) - i) * 30
        cur = conn.execute(
            f"INSERT INTO chats (title, created_at) VALUES (?, datetime('now', '-{offset_minutes} minutes'))",
            (chat["title"],),
        )
        chat_id = cur.lastrowid

        for j, msg in enumerate(chat["messages"]):
            offset_seconds = offset_minutes * 60 - j * 45
            conn.execute(
                f"""INSERT INTO messages
                    (chat_id, role, content, language, risk_level, timestamp)
                    VALUES (?, ?, ?, ?, ?, datetime('now', '-{offset_seconds} seconds'))""",
                (chat_id, msg["role"], msg["content"], msg["language"], msg["risk_level"]),
            )

    conn.commit()
    conn.close()

    total_msgs = sum(len(c["messages"]) for c in DEMO_CHATS)
    print(f"✅ Seeded {len(DEMO_CHATS)} demo conversations ({total_msgs} messages)")
    print("   Recruiters will see a fully populated, professional demo on first load.")


if __name__ == "__main__":
    seed_database()
