"""
Google Docs integration.

Reading resume:
  - Uses the Docs API with credentials (most reliable — no need to make doc public).
  - Falls back to public export URL, then config/cv.md.

Creating tailored docs:
  - Copies the base resume GDoc — ALL fonts, layout, and formatting preserved.
  - Applies exact text replacements (replaceAllText) for summary, bullets, skills.
  - Re-bolds key phrases within replaced bullets (metrics, JD-anchor terms).
  - Fixes skills section: only category headings bold (Domain:, Product:, Technical & AI:).
  - Highlights changed paragraphs in light yellow for easy review and approval.
  - Grants "anyone with link can edit" access.
"""
import asyncio
import os
import aiohttp

_RESUME_DOC_ID = os.environ.get("RESUME_GDOC_ID", "")
if not _RESUME_DOC_ID:
    raise RuntimeError(
        "RESUME_GDOC_ID is not set in .env — add the Google Doc ID of your base resume."
    )
_FALLBACK_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "cv.md")

_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# Yellow highlight for changed paragraphs (easy review)
_HIGHLIGHT_COLOR = {"red": 1.0, "green": 0.976, "blue": 0.647}

# Light blue highlight for the "move this bullet to top" suggestion
_REORDER_COLOR = {"red": 0.678, "green": 0.847, "blue": 1.0}

# Skills headings that should remain bold; everything after colon is un-bolded
_SKILL_HEADINGS = ["Domain:", "Product:", "Technical & AI:", "Tools:", "Languages:"]


# ── Credential helpers ────────────────────────────────────────────────────────

def _resolve(env_key: str, default_rel: str) -> str:
    raw = os.environ.get(env_key, default_rel)
    if not os.path.isabs(raw):
        raw = os.path.join(_PROJECT_ROOT, raw)
    return os.path.normpath(raw)


def _load_creds():
    """OAuth token first, service account fallback."""
    token_path = _resolve("GOOGLE_TOKEN_PATH", "config/google_token.json")
    if os.path.exists(token_path):
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            creds = Credentials.from_authorized_user_file(token_path, _SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
            if creds.valid:
                return creds
        except Exception:
            pass

    sa_path = _resolve("GOOGLE_SERVICE_ACCOUNT_JSON", "config/google_service_account.json")
    if os.path.exists(sa_path):
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_file(sa_path, scopes=_SCOPES)
    return None


# ── Public: read resume ───────────────────────────────────────────────────────

async def read_resume_from_gdoc() -> str:
    """Read base resume. Tries Docs API → public export → local cv.md."""
    creds = _load_creds()
    if creds is not None:
        try:
            text = await asyncio.to_thread(_read_doc_via_api, creds)
            if text:
                print(f"  Resume loaded via Docs API ({len(text)} chars)")
                return text
        except Exception as e:
            print(f"  Docs API read failed ({e}), trying export URL...")

    export_url = f"https://docs.google.com/document/d/{_RESUME_DOC_ID}/export?format=txt"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(export_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    print(f"  Resume loaded from export URL ({len(text)} chars)")
                    return text
    except Exception as e:
        print(f"  Export URL failed ({e}), falling back to config/cv.md")

    if os.path.exists(_FALLBACK_PATH):
        with open(_FALLBACK_PATH) as f:
            text = f.read()
        print(f"  Resume loaded from config/cv.md ({len(text)} chars)")
        return text
    return ""


def _read_doc_via_api(creds) -> str:
    from googleapiclient.discovery import build
    docs = build("docs", "v1", credentials=creds)
    doc = docs.documents().get(documentId=_RESUME_DOC_ID).execute()
    lines = []
    for elem in doc.get("body", {}).get("content", []):
        para = elem.get("paragraph")
        if not para:
            continue
        text_parts = []
        for run in para.get("elements", []):
            t = run.get("textRun", {}).get("content", "")
            text_parts.append(t)
        lines.append("".join(text_parts))
    return "".join(lines).strip()


# ── Public: create tailored doc ───────────────────────────────────────────────

async def create_tailored_doc(replacements: dict, job=None, resume_text: str = "") -> str:
    creds = _load_creds()
    if creds is None:
        print("  [gdocs] skipped — no credentials (run scripts/authorize_google.py)")
        return ""
    return await asyncio.to_thread(_create_doc_sync, replacements, job, creds)


# ── Internal: document creation + formatting ─────────────────────────────────

def _create_doc_sync(replacements: dict, job, creds) -> str:
    try:
        from googleapiclient.discovery import build
        drive = build("drive", "v3", credentials=creds)
        docs  = build("docs",  "v1", credentials=creds)

        # 1. Title
        title = (
            f"Resume — {(job.company or 'Unknown').strip()} — {(job.title or 'PM').strip()}"
            if job else "Resume — Tailored Copy"
        )

        # 2. Copy base resume (preserves all fonts + layout)
        folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        copy_body = {"name": title}
        if folder_id:
            copy_body["parents"] = [folder_id]

        doc_id = drive.files().copy(
            fileId=_RESUME_DOC_ID,
            body=copy_body,
            fields="id",
            supportsAllDrives=True,
        ).execute()["id"]

        # 3. Apply text replacements
        if "_fallback_brief" in replacements:
            _append_brief(docs, doc_id, replacements["_fallback_brief"])
        else:
            replace_requests = _build_replace_requests(replacements)
            if replace_requests:
                docs.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": replace_requests},
                ).execute()
                print(f"    [gdocs] applied {len(replace_requests)} text replacements")

            # 4. Re-read doc and apply formatting passes
            doc = docs.documents().get(documentId=doc_id).execute()
            body = doc.get("body", {}).get("content", [])

            fmt_requests = []

            # 4a. Re-bold key phrases in replaced bullets
            fmt_requests += _bold_phrases_requests(body, replacements)

            # 4b. Fix skills section: only headings bold
            fmt_requests += _fix_skills_requests(body)

            # 4c. Yellow highlight on every replaced paragraph for review
            fmt_requests += _highlight_changed_requests(body, replacements)

            # 4d. Light blue highlight on the "move to top" suggestion bullet
            reorder = replacements.get("reorder_suggestion") or {}
            fmt_requests += _reorder_highlight_requests(body, reorder)
            if reorder.get("bullet_fragment"):
                print(f"    [gdocs] 💡 Move to top: \"{reorder['bullet_fragment']}...\"")
                if reorder.get("reason"):
                    print(f"           Reason: {reorder['reason']}")

            if fmt_requests:
                # Batch in chunks of 50 to stay under API limits
                for i in range(0, len(fmt_requests), 50):
                    docs.documents().batchUpdate(
                        documentId=doc_id,
                        body={"requests": fmt_requests[i:i+50]},
                    ).execute()
                print(f"    [gdocs] applied {len(fmt_requests)} formatting requests")

        # 5. Anyone with link can edit
        drive.permissions().create(
            fileId=doc_id,
            body={"type": "anyone", "role": "writer"},
        ).execute()

        url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"  GDoc created: {title}")
        print(f"    → {url}")
        return url

    except Exception as e:
        print(f"  [gdocs] creation failed: {e}")
        return ""


# ── Helpers: text replacement ─────────────────────────────────────────────────

def _build_replace_requests(replacements: dict) -> list:
    requests = []

    def _add(original: str, replacement: str) -> None:
        orig = (original or "").strip()
        repl = (replacement or "").strip()
        if orig and repl and orig != repl:
            requests.append({
                "replaceAllText": {
                    "containsText": {"text": orig, "matchCase": True},
                    "replaceText": repl,
                }
            })

    summary = replacements.get("summary") or {}
    if isinstance(summary, dict):
        _add(summary.get("original", ""), summary.get("replacement", ""))

    for b in (replacements.get("bullets") or []):
        if isinstance(b, dict):
            _add(b.get("original", ""), b.get("replacement", ""))

    for key in ("skills_core", "skills_domain"):
        entry = replacements.get(key) or {}
        if isinstance(entry, dict):
            _add(entry.get("original", ""), entry.get("replacement", ""))

    return requests


# ── Helpers: find text positions in document ──────────────────────────────────

def _find_phrase_ranges(body_content: list, phrase: str) -> list:
    """
    Return list of (startIndex, endIndex) for all occurrences of phrase.
    Handles text that spans paragraph elements by building a char→docIndex map.
    """
    results = []
    for elem in body_content:
        para = elem.get("paragraph")
        if not para:
            continue
        para_text = ""
        char_doc_index = []  # maps para_text[i] → document index
        for run in para.get("elements", []):
            tr = run.get("textRun", {})
            content = tr.get("content", "")
            start = run.get("startIndex", 0)
            for i, ch in enumerate(content):
                para_text += ch
                char_doc_index.append(start + i)

        idx = 0
        while True:
            pos = para_text.find(phrase, idx)
            if pos == -1:
                break
            end_pos = pos + len(phrase)
            if end_pos <= len(char_doc_index):
                results.append((char_doc_index[pos], char_doc_index[end_pos - 1] + 1))
            idx = pos + 1
    return results


def _para_range(para_elements: list) -> tuple:
    """Return (startIndex, endIndex) of a paragraph, excluding trailing newline."""
    if not para_elements:
        return (0, 0)
    start = para_elements[0].get("startIndex", 0)
    last_run = para_elements[-1]
    end = last_run.get("endIndex", start)
    # Back off one to exclude the trailing \n
    return (start, max(start, end - 1))


# ── Helpers: formatting requests ──────────────────────────────────────────────

def _bold_requests_for_range(start: int, end: int, bold: bool) -> dict:
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"bold": bold},
            "fields": "bold",
        }
    }


def _highlight_request_for_range(start: int, end: int) -> dict:
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {
                "backgroundColor": {
                    "color": {"rgbColor": _HIGHLIGHT_COLOR}
                }
            },
            "fields": "backgroundColor",
        }
    }


def _bold_phrases_requests(body_content: list, replacements: dict) -> list:
    """
    For each bullet, bold the phrases listed in bold_phrases within the replacement text.
    """
    requests = []
    for b in (replacements.get("bullets") or []):
        if not isinstance(b, dict):
            continue
        for phrase in (b.get("bold_phrases") or []):
            phrase = phrase.strip()
            if not phrase:
                continue
            for start, end in _find_phrase_ranges(body_content, phrase):
                requests.append(_bold_requests_for_range(start, end, True))
    return requests


def _fix_skills_requests(body_content: list) -> list:
    """
    For skill lines (Domain:, Product:, Technical & AI:, etc.):
      - Bold only the heading label (up to and including the colon)
      - Un-bold everything after the colon
    """
    requests = []
    for elem in body_content:
        para = elem.get("paragraph")
        if not para:
            continue
        runs = para.get("elements", [])
        para_text = "".join(r.get("textRun", {}).get("content", "") for r in runs)

        matched_heading = None
        for heading in _SKILL_HEADINGS:
            if para_text.startswith(heading):
                matched_heading = heading
                break
        if not matched_heading:
            continue

        if not runs:
            continue
        para_start = runs[0].get("startIndex", 0)
        heading_end = para_start + len(matched_heading)
        _, para_end = _para_range(runs)

        # Bold the heading label
        if heading_end > para_start:
            requests.append(_bold_requests_for_range(para_start, heading_end, True))
        # Un-bold everything after the colon
        if para_end > heading_end:
            requests.append(_bold_requests_for_range(heading_end, para_end, False))

    return requests


def _highlight_changed_requests(body_content: list, replacements: dict) -> list:
    """
    Apply yellow highlight to every paragraph that was changed,
    so the user can review and approve each change at a glance.
    """
    requests = []

    # Collect all replacement texts
    changed_texts = []
    s = replacements.get("summary") or {}
    if isinstance(s, dict) and s.get("replacement"):
        changed_texts.append(s["replacement"].strip())

    for b in (replacements.get("bullets") or []):
        if isinstance(b, dict) and b.get("replacement"):
            changed_texts.append(b["replacement"].strip())

    for key in ("skills_core", "skills_domain"):
        e = replacements.get(key) or {}
        if isinstance(e, dict) and e.get("replacement"):
            changed_texts.append(e["replacement"].strip())

    # For each changed text, find which paragraph it lives in and highlight that paragraph
    highlighted_paras = set()
    for changed in changed_texts:
        if not changed:
            continue
        # Use first 40 chars as a unique-enough search key
        fragment = changed[:40]
        for elem_idx, elem in enumerate(body_content):
            para = elem.get("paragraph")
            if not para:
                continue
            runs = para.get("elements", [])
            para_text = "".join(r.get("textRun", {}).get("content", "") for r in runs)
            if fragment in para_text and elem_idx not in highlighted_paras:
                start, end = _para_range(runs)
                if end > start:
                    requests.append(_highlight_request_for_range(start, end))
                    highlighted_paras.add(elem_idx)
                break

    return requests


def _reorder_highlight_requests(body_content: list, reorder: dict) -> list:
    """
    Apply light blue highlight to the bullet Claude recommends moving to position #1.
    This is purely advisory — the user manually moves it in the doc.
    """
    if not reorder or not reorder.get("bullet_fragment"):
        return []

    fragment = reorder["bullet_fragment"].strip()
    if not fragment:
        return []

    # Search for a paragraph containing this fragment
    for elem in body_content:
        para = elem.get("paragraph")
        if not para:
            continue
        runs = para.get("elements", [])
        para_text = "".join(r.get("textRun", {}).get("content", "") for r in runs)
        if fragment[:30] in para_text:
            start, end = _para_range(runs)
            if end > start:
                return [{
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {
                            "backgroundColor": {
                                "color": {"rgbColor": _REORDER_COLOR}
                            }
                        },
                        "fields": "backgroundColor",
                    }
                }]
    return []


# ── Fallback: append brief as plain text ─────────────────────────────────────

def _append_brief(docs, doc_id: str, brief_text: str) -> None:
    doc = docs.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertPageBreak": {"location": {"index": end_index}}}]},
    ).execute()
    doc2 = docs.documents().get(documentId=doc_id).execute()
    end_index2 = doc2["body"]["content"][-1]["endIndex"] - 1
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {
            "location": {"index": end_index2},
            "text": "TAILORING NOTES\n\n" + brief_text,
        }}]},
    ).execute()
