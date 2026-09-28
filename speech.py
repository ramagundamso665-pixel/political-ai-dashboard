"""Audio: decoding, transcription, and fingerprints for checking clips against the leader's own recordings.

Decoding uses the ffmpeg binary that ships inside the imageio-ffmpeg package, so no system install is
needed. Transcription uses OpenAI's speech models (Telugu, Urdu, Hindi, English and mixes).

The fingerprint is the landmark method Shazam made famous: find the loudest points in the sound's
spectrogram, pair nearby points, and hash each pair's two pitches and time gap. A clip cut from a
recording shares thousands of these hashes with it at one consistent time offset, even after WhatsApp
re-compresses it or a TV channel adds a logo. Re-recorded or synthetic speech shares almost none.
Checking the clip in short windows shows whether it is one continuous piece of a recording or pieces
of different moments joined together.
"""

import base64
import hashlib
import io
import json
import os
import subprocess
import tempfile
import zlib
from collections import Counter, defaultdict
from difflib import SequenceMatcher

import numpy as np

RATE = 8000               # fingerprints are taken at 8 kHz mono: speech lives below 4 kHz
FRAME, HOP = 1024, 256    # ~128 ms windows, 32 ms steps
PEAKS_PER_FRAME = 5
FAN_OUT = 6
MAX_DT = 64               # pair points up to ~2 s apart
WINDOW_S = 5              # clip windows checked separately for splices
MIN_SHARE = 0.2           # a matched window has at least this share of its hashes at one alignment
MIN_SPIKE = 3.0           # and that alignment beats the sixth-best by this factor
# measured on test clips: a cut from the recording scored 0.44-0.81 of its hashes in one sharp spike
# (8-14x the background), a re-recording of the same words and an unrelated clip at most 0.12, flat


def _ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def decode(data, rate=RATE):
    """Any audio or video file (bytes) -> mono float32 samples at `rate`."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as fh:
        fh.write(data)
        path = fh.name
    try:
        out = subprocess.run([_ffmpeg(), "-v", "error", "-i", path, "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                             capture_output=True, timeout=600)
        if out.returncode != 0 or not out.stdout:
            raise ValueError("could not read audio from this file: " + out.stderr.decode(errors="ignore")[-200:])
        return np.frombuffer(out.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        os.unlink(path)


def to_mp3(data, bitrate="32k"):
    """Compact mono MP3 for the transcription API (an hour is about 14 MB at 32 kbit/s)."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as fh:
        fh.write(data)
        path = fh.name
    try:
        out = subprocess.run([_ffmpeg(), "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-b:a", bitrate, "-f", "mp3", "-"],
                             capture_output=True, timeout=600)
        if out.returncode != 0:
            raise ValueError("could not convert audio")
        return out.stdout
    finally:
        os.unlink(path)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------------
# Transcription
# ----------------------------------------------------------------------
def pause_cuts(samples, rate=16000, target_s=12, min_s=5, max_s=25):
    """Cut points (in samples) at the quietest moment near every `target_s` seconds, so no word is split."""
    hop = int(0.03 * rate)
    n = len(samples) // hop
    if n == 0:
        return [0, len(samples)]
    rms = np.sqrt(np.mean(samples[: n * hop].reshape(n, hop) ** 2, axis=1))
    cuts, pos = [0], 0
    while (n - pos) * hop / rate > max_s:
        lo, hi = pos + int(min_s * rate / hop), min(n - 1, pos + int(max_s * rate / hop))
        centre = pos + int(target_s * rate / hop)
        window = rms[lo:hi]
        # prefer quiet, then closeness to the target length
        cost = window / (np.median(rms) + 1e-6) + np.abs(np.arange(lo, hi) - centre) / (rate / hop * 20)
        pos = lo + int(np.argmin(cost))
        cuts.append(pos * hop)
    cuts.append(len(samples))
    return cuts


PROMPT = "A political speech or press meet in Telangana, in Telugu, English, Urdu or Hindi, often mixed. Write Telugu in Telugu script."


def transcribe(data, api_key, timestamps=True, language=None, prompt=PROMPT):
    """{'ok', 'error', 'text', 'segments': [{start, end, text}], 'duration'}.
    With timestamps, the audio is cut at pauses into pieces of about 12 seconds and each piece is transcribed
    by gpt-4o-transcribe; the pieces' times are the timestamps. (whisper-1's own timestamps dropped the Telugu
    of a mixed Telugu-English test speech entirely, so it is not used.)"""
    from concurrent.futures import ThreadPoolExecutor

    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=300)
    try:
        samples = decode(data, 16000)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    duration = len(samples) / 16000
    cuts = pause_cuts(samples) if timestamps else [0, len(samples)]
    pieces = [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a > 1600]

    def one(ab):
        a, b = ab
        resp = client.audio.transcriptions.create(model="gpt-4o-transcribe", file=("audio.wav", _wav_bytes(samples[a:b], 16000)),
                                                  **({"language": language} if language else {}), **({"prompt": prompt} if prompt else {}))
        return {"start": round(a / 16000, 2), "end": round(b / 16000, 2), "text": resp.text.strip()}

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            segments = [s for s in pool.map(one, pieces) if s["text"]]
    except Exception as exc:
        return {"ok": False, "error": f"transcription failed ({type(exc).__name__}: {str(exc)[:160]})"}
    return {"ok": True, "error": None, "text": " ".join(s["text"] for s in segments), "segments": segments, "duration": round(duration, 1)}


def _wav_bytes(samples, rate):
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


# ----------------------------------------------------------------------
# Fingerprints
# ----------------------------------------------------------------------
def _spectrogram(samples):
    if len(samples) < FRAME:
        samples = np.pad(samples, (0, FRAME - len(samples)))
    n = 1 + (len(samples) - FRAME) // HOP
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    frames = samples[idx] * np.hanning(FRAME)[None, :]
    spec = np.abs(np.fft.rfft(frames, axis=1))
    return np.log1p(spec[:, 8:400])      # ~60 Hz to ~3.1 kHz


def peaks(samples):
    """(frame, bin) of the strongest local points: a few per frame, above the frame's own median."""
    spec = _spectrogram(samples)
    out = []
    for t, row in enumerate(spec):
        # a point must beat its neighbours along frequency and be well above this frame's median
        cand = np.argpartition(row, -PEAKS_PER_FRAME * 3)[-PEAKS_PER_FRAME * 3:]
        med = np.median(row)
        cand = [f for f in cand if row[f] > med + 1.0 and row[f] >= row[max(0, f - 3):f + 4].max()]
        cand = sorted(cand, key=lambda f: -row[f])[:PEAKS_PER_FRAME]
        out.extend((t, int(f)) for f in cand)
    return out


def hashes(samples):
    """[(hash, frame)] for landmark pairs."""
    pk = sorted(peaks(samples))
    out = []
    for i, (t1, f1) in enumerate(pk):
        n = 0
        for t2, f2 in pk[i + 1:]:
            dt = t2 - t1
            if dt == 0:
                continue
            if dt > MAX_DT:
                break
            out.append(((f1 << 16) | (f2 << 6) | dt, t1))
            n += 1
            if n >= FAN_OUT:
                break
    return out


def pack(hs):
    """Hashes as compact text for storage (int32 pairs, zlib): about 4 MB per hour of speech."""
    arr = np.array(hs, dtype=np.int64).reshape(-1, 2).astype(np.int32)
    return base64.b64encode(zlib.compress(arr.tobytes(), 9)).decode()


def unpack(text):
    return np.frombuffer(zlib.decompress(base64.b64decode(text)), dtype=np.int32).reshape(-1, 2)


class Index:
    """All archived recordings' hashes, looked up by hash value."""

    def __init__(self, archive):
        self.by_hash = defaultdict(list)
        self.titles = {}
        for rec in archive:
            if not rec.get("fingerprint"):
                continue
            self.titles[rec["id"]] = rec
            for h, t in unpack(rec["fingerprint"]):
                self.by_hash[int(h)].append((rec["id"], int(t)))

    def match(self, hs):
        """Best (recording id, offset in frames, share of hashes aligned there, spike over background)."""
        votes = Counter()
        for h, t in hs:
            for rid, rt in self.by_hash.get(h, ()):
                votes[(rid, rt - t)] += 1
        if not votes:
            return None, None, 0.0, 0.0
        ranked = votes.most_common(6)
        (rid, off), best = ranked[0]
        background = ranked[-1][1] if len(ranked) == 6 else 1
        return rid, off, best / max(1, len(hs)), best / max(1, background)


def frames_to_s(frames):
    return frames * HOP / RATE


# ----------------------------------------------------------------------
# Checking a clip
# ----------------------------------------------------------------------
def _norm(text):
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def text_similarity(a, b):
    """How much of clip text `a` appears, in order, inside master text `b` (0-1). Containment, not equality:
    the master's timestamped piece is usually longer than the clip."""
    a, b = _norm(a), _norm(b)
    if not a:
        return 0.0
    blocks = SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return sum(bl.size for bl in blocks) / len(a)


def transcript_between(rec, start, end, pad=0.0):
    segs = rec.get("segments") or []
    if isinstance(segs, str):
        segs = json.loads(segs)
    return " ".join(s["text"] for s in segs if s["end"] >= start - pad and s["start"] <= end + pad)


def best_text_match(archive, clip_text):
    """Where in any archived transcript the clip's words appear most closely: (record, start, end, score)."""
    best = (None, None, None, 0.0)
    target = _norm(clip_text)
    if not target:
        return best
    n_words = max(3, len(target.split()))
    for rec in archive:
        segs = rec.get("segments") or []
        if isinstance(segs, str):
            segs = json.loads(segs)
        for i in range(len(segs)):
            words, j = [], i
            while j < len(segs) and len(" ".join(words).split()) < n_words * 1.3:
                words.append(segs[j]["text"])
                j += 1
            score = text_similarity(target, " ".join(words))
            if score > best[3]:
                best = (rec, segs[i]["start"], segs[j - 1]["end"], score)
    return best


def check_clip(samples, clip_text, archive):
    """Verdict for a clip against the archive. Returns a dict with 'verdict', 'why', the matched recording,
    where in it, the words said there, and a per-window table showing continuity."""
    index = Index(archive)
    dur = len(samples) / RATE
    win = int(WINDOW_S * RATE)
    windows = []
    for s in range(0, max(1, len(samples) - win // 2), win):
        piece = samples[s:s + win]
        if len(piece) < RATE:
            continue
        rid, off, share, spike = index.match(hashes(piece))
        matched = share >= MIN_SHARE and spike >= MIN_SPIKE
        windows.append({"clip_from_s": round(s / RATE, 1), "recording": index.titles[rid]["title"] if matched else None, "rid": rid if matched else None,
                        "at_s": round(frames_to_s(off), 1) if matched else None, "match": f"{share * 100:.0f}%"})
    matched = [w for w in windows if w["rid"]]
    result = {"duration": round(dur, 1), "windows": windows, "recording": None, "at_s": None, "master_text": "", "context_text": ""}

    if matched:
        # continuity: every matched window should sit at the same place relative to the clip start
        starts = [(w["rid"], round(w["at_s"] - w["clip_from_s"])) for w in matched]
        main, main_n = Counter(starts).most_common(1)[0]
        rec = index.titles[main[0]]
        begin = main[1]
        result.update(recording=rec, at_s=begin, master_text=transcript_between(rec, begin, begin + dur),
                      context_text=transcript_between(rec, begin, begin + dur, pad=60))
        coverage = len(matched) / max(1, len(windows))
        consistent = main_n / len(matched)
        similarity = text_similarity(clip_text, result["master_text"]) if clip_text else None
        result["text_similarity"] = similarity
        if consistent < 0.8 or len({r for r, _ in starts}) > 1:
            result.update(verdict="Edited", why="Parts of this clip come from different moments or recordings joined together.")
        elif coverage < 0.7:
            result.update(verdict="Partly altered", why=f"Only {coverage * 100:.0f}% of the clip matches the recording; the rest does not come from it.")
        elif similarity is not None and similarity < 0.5:
            result.update(verdict="Check words", why="The sound matches the recording but the transcripts differ; listen to both.")
        else:
            result.update(verdict="Genuine", why="The whole clip is one continuous piece of this recording.")
        return result

    # no sound match: are the words anywhere in the archive?
    rec, start, end, score = best_text_match(archive, clip_text) if clip_text else (None, None, None, 0)
    if rec is not None and score >= 0.65:
        result.update(verdict="Words match, sound does not", recording=rec, at_s=start, master_text=transcript_between(rec, start, end),
                      context_text=transcript_between(rec, start, end, pad=60), text_similarity=score,
                      why="The same words were said in this recording, but this clip's audio is not taken from it: a different camera or phone, "
                          "a re-recording, or a synthetic voice. Compare them side by side.")
    else:
        result.update(verdict="Not in any recording", text_similarity=score,
                      why="Neither the sound nor the words match any recording in the archive. That is not proof of a fake: the archive only "
                          "knows what the team recorded.")
    return result
