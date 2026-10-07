"""Extract Planck's First Lecture from the Project Gutenberg LaTeX source.

Produces ``data/lecture1_text.json``: Planck's words, made speakable
(LaTeX removed, equations written out as words), split into sentences.
Planck's wording is never changed; only notation is turned into speech.

Usage::

    python scripts/extract_lecture.py

Standard library only. The Gutenberg source is downloaded once into
``data/source/`` (git-ignored).
"""

import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "data" / "source"
OUTPUT = ROOT / "data" / "lecture1_text.json"
SOURCE_URL = "https://www.gutenberg.org/files/39017/39017-t.zip"
TEX_NAME = "39017-t/39017-t.tex"

START_MARKER = r"\Chapter{First Lecture.}"
END_MARKER = r"\Chapter{SECOND LECTURE.}"

# The five displayed equations of Lecture One, keyed by a fragment of their
# LaTeX, and how each should be read aloud.
SPOKEN_EQUATIONS = {
    r"\frac{T_{1} - T_{2}}{T_{1}}": (
        "Q times, T one minus T two, divided by T one; "
        "or, Q times, T one minus T two, divided by T two."
    ),
    r"-\frac{Q}{T_{1}} + \frac{Q}{T_{2}} > 0": (
        "minus Q over T one, plus Q over T two, is greater than zero."
    ),
    r"\tsum Q = A": "the sum of all the Q equals A.",
    r"\tsum \frac{Q}{T} \leq 0": (
        "the sum of all the Q over T is less than or equal to zero."
    ),
    r"\tsum Q \leq 0": (
        "the sum of all the Q is less than or equal to zero; "
        "hence, A is less than or equal to zero."
    ),
}

# Inline maths, e.g. "$T_{1}$" -> "T one".
SPOKEN_INLINE = {
    "Q/T": "Q over T",
    "T_{1}": "T one",
    "T_{2}": "T two",
}


def load_tex() -> str:
    """Return the Gutenberg LaTeX source, downloading it on first use."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    tex_path = SOURCE_DIR / "39017-t.tex"
    if not tex_path.exists():
        print(f"Downloading {SOURCE_URL} ...")
        with urllib.request.urlopen(SOURCE_URL) as resp:
            archive = zipfile.ZipFile(io.BytesIO(resp.read()))
        tex_path.write_bytes(archive.read(TEX_NAME))
    return tex_path.read_text(encoding="latin-1").replace("\r", "")


def speak_display_math(match: re.Match) -> str:
    body = match.group(1)
    for fragment, spoken in SPOKEN_EQUATIONS.items():
        if fragment in body:
            return f" {spoken} "
    raise ValueError(f"No spoken form for equation: {body!r}")


def speak_inline_math(match: re.Match) -> str:
    body = match.group(1)
    return SPOKEN_INLINE.get(body, body)


def to_speakable(tex: str) -> str:
    """Turn the lecture's LaTeX into plain text suitable for speech."""
    lines = [ln for ln in tex.split("\n") if not ln.lstrip().startswith("%")]
    text = "\n".join(lines)

    text = re.sub(r"\\\[(.*?)\\\]", speak_display_math, text, flags=re.S)
    text = re.sub(r"\$(.*?)\$", speak_inline_math, text)

    text = re.sub(r"\\label\{[^}]*\}", "", text)
    text = re.sub(r"\\pagestyle\{[^}]*\}", "", text)
    text = re.sub(r"\\(?:emph|First)\{([^}]*)\}", r"\1", text)
    # Latin abbreviations, written out the way a reader says them aloud.
    text = text.replace(r"\eg", "for example").replace(r"\ie", "that is")
    text = text.replace(r"cf.\ ", "compare ")
    text = text.replace("``", "\u201c").replace("''", "\u201d")
    text = text.replace("---", "\u2014").replace("--", "\u2013")
    text = text.replace("~", " ").replace(r"\-", "").replace("\\ ", " ")

    leftover = re.findall(r"\\[A-Za-z ]|[{}$]", text)
    if leftover:
        raise ValueError(f"Unconverted LaTeX left over: {sorted(set(leftover))}")
    return text


# A full stop after an initial ("R. Clausius") doesn't end a sentence.
INITIAL = re.compile(r"(?:^|\s)[A-Z]\.$")


def split_sentences(paragraph: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[\u201cA-Z])", paragraph)
    sentences: list[str] = []
    for part in parts:
        if sentences and INITIAL.search(sentences[-1]):
            sentences[-1] += " " + part
        else:
            sentences.append(part)
    return sentences


def main() -> None:
    tex = load_tex()
    start = tex.index(START_MARKER)
    end = tex.index(END_MARKER)
    lecture = tex[start:end]

    # Title block: \Chapter{First Lecture.}\n{Introduction: ...}
    title_match = re.match(r"\\Chapter\{([^}]*)\}\s*\{([^}]*)\}", lecture)
    assert title_match, "Lecture title not found"
    title = f"{title_match.group(1)} {title_match.group(2)}"
    body = to_speakable(lecture[title_match.end():])

    paragraphs = [
        " ".join(p.split()) for p in re.split(r"\n\s*\n", body) if p.strip()
    ]

    segments = [{"id": 0, "paragraph": 0, "kind": "title", "text": title}]
    for p_index, paragraph in enumerate(paragraphs, start=1):
        for sentence in split_sentences(paragraph):
            segments.append(
                {
                    "id": len(segments),
                    "paragraph": p_index,
                    "kind": "planck",
                    "text": sentence,
                }
            )

    OUTPUT.write_text(
        json.dumps(
            {
                "source": "Max Planck, Eight Lectures on Theoretical Physics "
                "(Columbia University, 1909), trans. A. P. Wills. "
                "Project Gutenberg eBook #39017. Public domain.",
                "segments": segments,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    words = sum(len(s["text"].split()) for s in segments)
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)}: {len(paragraphs)} paragraphs, "
        f"{len(segments)} segments, {words} words."
    )


if __name__ == "__main__":
    main()
