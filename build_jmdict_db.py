"""
Build the JMdict SQLite lookup DB from the JMdict XML file.

JMdict is Jim Breen's Japanese-Multilingual Dictionary (~170k entries).
The XML file is freely available from the EDRDG project under a Creative
Commons Attribution Share-Alike licence.

Download
--------
    wget https://ftp.edrdg.org/pub/Nihongo/JMdict_e_examp.gz
    gunzip JMdict_e_examp.gz
    mv JMdict_e_examp resources/JMdict

Or for the full multilingual edition (larger, includes DE/FR/ES glosses):
    wget https://ftp.edrdg.org/pub/Nihongo/JMdict.gz
    gunzip JMdict.gz
    mv JMdict resources/JMdict

Run
---
    python build_jmdict_db.py                   # uses resources/JMdict
    python build_jmdict_db.py --src path/to/JMdict

Output
------
    resources/jmdict.db  (~50–80 MB)

Schema
------
    entries(
        id        INTEGER PRIMARY KEY,
        kanji     TEXT,       -- primary kanji form; '' for kana-only entries
        reading   TEXT,       -- primary hiragana/katakana reading
        pos       TEXT,       -- GF category: N | V | V2 | A | Adv
        sense_idx INTEGER,    -- 0-based index of this sense within the entry
        gloss_en  TEXT,       -- English gloss (first sense, single-word preferred)
        gloss_de  TEXT,       -- German gloss (NULL if not in source file)
        gloss_es  TEXT,       -- Spanish gloss (NULL if not in source file)
        gloss_fr  TEXT        -- French gloss (NULL if not in source file)
    )
"""

import argparse
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

JMDICT_PATH = "./resources/JMdict"
DB_PATH     = "./resources/jmdict.db"

# JMdict xml:lang attribute values → our ISO-639-1 codes
_LANG_MAP = {
    "eng": "en",
    "ger": "de",
    "spa": "es",
    "fre": "fr",
}

# JMdict POS entity names → GF category
# POS is stored as XML entity references like &n; &vt; &vi; &adj-i; etc.
# After parsing, ElementTree expands them using the DOCTYPE declarations.
_POS_TO_GF = {
    # Nouns
    "noun": "N",
    "noun (common) (futsuumeishi)": "N",
    "adverbial noun (fukushitekimeishi)": "Adv",
    "noun, used as a suffix": "N",
    "noun, used as a prefix": "N",
    "noun or verb acting prenominally": "N",
    "proper noun": "N",
    "place name": "N",
    "personal name": "N",
    # Verbs — transitive (→ V2) vs intransitive (→ V)
    "transitive verb": "V2",
    "intransitive verb": "V",
    "Ichidan verb": "V",
    "Ichidan verb - kureru special class": "V",
    "Nidan verb (upper class) with ku ending (archaic)": "V",
    # Godan verbs — default V (many are intransitive)
    "Godan verb with u ending": "V",
    "Godan verb with ku ending": "V",
    "Godan verb with gu ending": "V",
    "Godan verb with su ending": "V",
    "Godan verb with tsu ending": "V",
    "Godan verb with nu ending": "V",
    "Godan verb with bu ending": "V",
    "Godan verb with mu ending": "V",
    "Godan verb with ru ending": "V",
    "Godan verb with ru ending (irregular verb)": "V",
    "Godan verb - aru special class": "V",
    "Godan verb - iku/yuku special class": "V",
    # Suru verbs (usually transitive → V2)
    "suru verb - special class": "V2",
    "suru verb - included": "V2",
    "noun or participle which takes the aux. verb suru": "V2",
    # Adjectives
    "adjective (keiyoushi)": "A",
    "adjective (keiyoushi) - yoi/ii class": "A",
    "adjectival nouns or quasi-adjectives (keiyodoshi)": "A",
    "pre-noun adjectival (rentaishi)": "A",
    # Adverbs
    "adverb (fukushi)": "Adv",
    "adverb taking the `to' particle": "Adv",
}

_STOPWORDS = frozenset({"of", "the", "a", "an", "in", "at", "to", "and", "or",
                        "for", "with", "by", "from"})

_INFLECTION_PREFIXES = (
    "inflection of", "form of", "alternative form of", "used as",
    "see ", "esp.", "usu.", "abbr.", "arch.", "obs.", "dated",
)


def _clean_gloss(raw: str) -> str | None:
    """
    Extract a clean, short gloss from a JMdict gloss string.

    Returns None if the gloss looks like a grammatical description, a
    multi-word phrase, or a form reference rather than a usable translation.
    """
    raw = raw.strip()
    lower = raw.lower()

    # Skip grammatical descriptions
    if any(lower.startswith(p) for p in _INFLECTION_PREFIXES):
        return None

    # Strip parenthetical qualifiers: "battery (for a device)" → "battery"
    cleaned = re.sub(r'\s*\([^)]*\)', '', raw).strip()
    cleaned = re.sub(r'\s*\[[^\]]*\]', '', cleaned).strip()

    # Use the first comma-separated item if multiple synonyms listed
    cleaned = cleaned.split(",")[0].split(";")[0].strip()

    # Strip "to " prefix for verbs
    if cleaned.lower().startswith("to "):
        cleaned = cleaned[3:].strip()

    # Reject if still multi-word (>3 content words)
    words = [w for w in cleaned.split() if w.lower() not in _STOPWORDS]
    if len(words) > 3 or not words:
        return None

    return cleaned if cleaned else None


def _pos_to_gf(pos_list: list[str]) -> str:
    """Map a list of JMdict POS strings to a GF category."""
    for pos in pos_list:
        gf = _POS_TO_GF.get(pos)
        if gf:
            return gf
    return "N"   # default


def _parse_and_insert(xml_path: str, cur: sqlite3.Cursor) -> int:
    """Parse JMdict XML and insert rows; returns the row count."""
    print(f"  Parsing {xml_path} ...")

    # JMdict uses DOCTYPE entity declarations for POS tags.
    # xml.etree.ElementTree does not expand entities by default on all Python
    # versions, so we read the file, extract the entity-expanded text with a
    # regex, and replace &xxx; with their values so the parser sees plain text.
    raw_xml = Path(xml_path).read_text(encoding="utf-8", errors="replace")

    # Extract entity declarations from DOCTYPE and build a substitution map
    entity_map: dict[str, str] = {}
    for m in re.finditer(r'<!ENTITY\s+(\S+)\s+"([^"]*)"', raw_xml):
        entity_map[m.group(1)] = m.group(2)

    # Replace entity references (&n; → "noun") so ElementTree can parse them
    def _expand(text: str) -> str:
        return re.sub(
            r'&([a-zA-Z0-9_-]+);',
            lambda m: entity_map.get(m.group(1), m.group(0)),
            text,
        )

    expanded_xml = _expand(raw_xml)

    try:
        root = ET.fromstring(expanded_xml)
    except ET.ParseError as e:
        sys.exit(f"XML parse error: {e}")

    count = 0
    for entry in root.iter("entry"):
        # Kanji forms (may be absent for kana-only words)
        kanji_forms = [k.findtext("keb", "").strip()
                       for k in entry.findall("k_ele")]
        primary_kanji = kanji_forms[0] if kanji_forms else ""

        # Reading forms (hiragana/katakana)
        reading_forms = [r.findtext("reb", "").strip()
                         for r in entry.findall("r_ele")]
        primary_reading = reading_forms[0] if reading_forms else ""

        if not primary_reading:
            continue   # malformed entry

        # Process senses
        for sense_idx, sense in enumerate(entry.findall("sense")):
            pos_texts = [p.text or "" for p in sense.findall("pos")]
            gf_cat    = _pos_to_gf(pos_texts)

            glosses: dict[str, str] = {}
            for gloss_el in sense.findall("gloss"):
                lang_attr = gloss_el.get("{http://www.w3.org/XML/1998/namespace}lang", "eng")
                our_lang  = _LANG_MAP.get(lang_attr)
                if our_lang and our_lang not in glosses:
                    cleaned = _clean_gloss(gloss_el.text or "")
                    if cleaned:
                        glosses[our_lang] = cleaned

            # Skip senses with no usable English gloss
            if "en" not in glosses:
                continue

            cur.execute(
                "INSERT INTO entries "
                "(kanji, reading, pos, sense_idx, gloss_en, gloss_de, gloss_es, gloss_fr) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    primary_kanji,
                    primary_reading,
                    gf_cat,
                    sense_idx,
                    glosses.get("en"),
                    glosses.get("de"),
                    glosses.get("es"),
                    glosses.get("fr"),
                ),
            )
            count += 1

    return count


def build_db(xml_path: str = JMDICT_PATH, db_path: str = DB_PATH) -> None:
    if not Path(xml_path).exists():
        sys.exit(
            f"JMdict XML not found at {xml_path}.\n"
            f"Download it with:\n"
            f"  wget --no-check-certificate https://ftp.edrdg.org/pub/Nihongo/JMdict.gz\n"
            f"  gunzip JMdict.gz && mv JMdict {xml_path}"
        )

    Path(db_path).unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    cur.executescript("""
        CREATE TABLE entries (
            id        INTEGER PRIMARY KEY,
            kanji     TEXT    NOT NULL DEFAULT '',
            reading   TEXT    NOT NULL,
            pos       TEXT    NOT NULL,
            sense_idx INTEGER NOT NULL DEFAULT 0,
            gloss_en  TEXT,
            gloss_de  TEXT,
            gloss_es  TEXT,
            gloss_fr  TEXT
        );
        CREATE INDEX idx_kanji   ON entries(kanji);
        CREATE INDEX idx_reading ON entries(reading);
    """)

    count = _parse_and_insert(xml_path, cur)
    conn.commit()
    conn.close()

    size_mb = Path(db_path).stat().st_size / 1_048_576
    print(f"  Wrote {count:,} rows → {db_path}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build JMdict SQLite DB")
    parser.add_argument("--src", default=JMDICT_PATH,
                        help=f"Path to JMdict XML file (default: {JMDICT_PATH})")
    parser.add_argument("--db",  default=DB_PATH,
                        help=f"Output DB path (default: {DB_PATH})")
    args = parser.parse_args()
    build_db(args.src, args.db)
