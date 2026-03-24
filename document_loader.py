import re
from pathlib import Path


def load_document(path):
    """
    Load a document and return a list of subject-coherent text chunks.

    Each chunk is a meaningful unit of text for topic modelling.
    The full text is also returned as a single string.

    Returns:
        chunks   : list[str]
        full_text: str
    """
    path = Path(path)
    ext = path.suffix.lower()

    if ext == ".srt":
        chunks = _load_srt(path)
    elif ext == ".txt":
        chunks = _load_txt(path)
    else:
        raise ValueError(f"Unsupported file type: {ext!r}. Add a loader to document_loader.py.")

    chunks = [c.strip() for c in chunks if c.strip()]
    full_text = "\n".join(chunks)
    return chunks, full_text


# ---------------------------------------------------------------------------
# SRT
# ---------------------------------------------------------------------------

# Hard break: gap between entries longer than this is almost certainly a scene change.
_SRT_HARD_GAP_MS   = 3000   # 3 seconds

# Soft break: gap longer than this AND low vocabulary overlap → topic shift.
_SRT_SOFT_GAP_MS   = 1000   # 1 second
_SRT_OVERLAP_MIN   = 0.15   # Jaccard threshold below which we consider a topic shift

# Don't break unless the current chunk has accumulated at least this many words.
_SRT_MIN_CHUNK_WORDS = 20

# Rolling context window: how many recent entries to compare against for overlap.
_SRT_CONTEXT_WINDOW = 6


def _ts_to_ms(ts):
    """Convert SRT timestamp string to milliseconds."""
    ts = ts.replace(",", ".")
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms)


def _word_set(text):
    """Lowercase word set, ignoring very short tokens."""
    return {w for w in re.findall(r"[a-záéíóúüñçàèìòùâêîôûäëïöü\w]{3,}", text.lower())}


def _jaccard(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _parse_srt_entries(text):
    """Return list of (start_ms, end_ms, clean_text) for every subtitle entry."""
    entries = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.strip().splitlines()
        start_ms = end_ms = None
        text_lines = []
        for line in lines:
            if re.match(r"^\d+\s*$", line):
                continue
            m = re.match(r"(\d{2}:\d{2}:\d{2}[,\.]\d+)\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d+)", line)
            if m:
                start_ms = _ts_to_ms(m.group(1))
                end_ms   = _ts_to_ms(m.group(2))
                continue
            clean = re.sub(r"<[^>]+>", "", line).strip()
            if clean:
                text_lines.append(clean)
        if start_ms is not None and text_lines:
            entries.append((start_ms, end_ms, " ".join(text_lines)))
    return entries


def _load_srt(path):
    """
    Group subtitle entries into subject-coherent chunks using two signals:

    1. Time gap  — a gap longer than _SRT_HARD_GAP_MS is a hard scene break.
                   A gap longer than _SRT_SOFT_GAP_MS is a candidate soft break.
    2. Vocabulary drift — Jaccard similarity between the rolling context window
                          of recent entries and the incoming entry.  Low overlap
                          during a soft gap indicates a topic shift.

    Both thresholds are tunable via the module-level constants at the top of
    this file.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    entries = _parse_srt_entries(text)
    if not entries:
        return []

    chunks = []
    current = [entries[0][2]]
    current_words = len(entries[0][2].split())

    for i in range(1, len(entries)):
        prev_end   = entries[i - 1][1]
        curr_start = entries[i][0]
        curr_text  = entries[i][2]
        gap_ms     = curr_start - prev_end

        # Hard break — long silence, almost certainly a scene change
        if gap_ms >= _SRT_HARD_GAP_MS:
            chunks.append(" ".join(current))
            current = [curr_text]
            current_words = len(curr_text.split())
            continue

        # Soft break — moderate gap, check vocabulary drift
        if gap_ms >= _SRT_SOFT_GAP_MS and current_words >= _SRT_MIN_CHUNK_WORDS:
            context_entries = current[-_SRT_CONTEXT_WINDOW:]
            context_words   = _word_set(" ".join(context_entries))
            incoming_words  = _word_set(curr_text)
            if _jaccard(context_words, incoming_words) < _SRT_OVERLAP_MIN:
                chunks.append(" ".join(current))
                current = [curr_text]
                current_words = len(curr_text.split())
                continue

        current.append(curr_text)
        current_words += len(curr_text.split())

    if current:
        chunks.append(" ".join(current))

    return chunks


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------

def _load_txt(path):
    """Return one chunk per paragraph (blank-line separated)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [p.replace("\n", " ") for p in re.split(r"\n\s*\n", text)]
