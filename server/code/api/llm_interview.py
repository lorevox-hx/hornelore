"""Lorevox interview LLM helpers.

Synchronous helpers for:
- end-of-section summaries (mini memoir drafts)
- follow-up questions after the base plan is complete
- a final memoir draft at the end

This reuses the same local model pipeline as /api/chat by calling the internal
chat() function in code.api.api.

If Lorevox is started in TTS-only mode (USE_TTS=1), importing the LLM stack
raises; these helpers then return safe fallbacks (None / empty lists).
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

# WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 5.
#
# Module scope, NOT a local import inside _try_call_llm. The whole point
# of this class here is to be named in an `except` clause that runs
# ahead of the blanket handler; a lazy import could fail at exactly the
# moment the refusal needed catching, and the blanket clause would then
# swallow it -- reintroducing the fail-open this was written to close.
#
# Safe to import eagerly even in USE_TTS=1 mode, which is why the module
# docstring's warning about the LLM stack does not apply: services.
# extraction_budget is pure stdlib and pulls in no model machinery.
from .services.extraction_budget import ExtractionPromptBudgetExceeded

# WO-10M: Summary / memoir token cap is launcher-tunable via env var.
# Used by draft_section_summary() and draft_final_memoir(). Extraction has
# its own env var (MAX_NEW_TOKENS_EXTRACT) handled in routers/extract.py.
_WO10M_SUMMARY_CAP = int(os.getenv("MAX_NEW_TOKENS_SUMMARY", "1024"))


def _try_call_llm(system_prompt: str, user_prompt: str, *, max_new: int, temp: float, top_p: float, conv_id: Optional[str] = None, prompt_mode: str = "composed", request_kind: str = "chat", budget_components: Optional[Dict[str, int]] = None) -> Optional[str]:
    """Return model text, or None if the LLM stack is unavailable.

    FIX-3: Accept optional conv_id to isolate extraction calls from shared
    session context. When conv_id is None, falls back to 'default' (legacy).
    Extraction callers should pass a unique ephemeral conv_id to prevent
    cross-narrator context contamination.

    WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (follow-up hardening):
    "composed" (default) goes through api.chat() with the legacy composed
    system prompt (DEFAULT_CORE + PROFILE_JSON + pinned RAG under the
    'default' session when conv_id is None). "raw_ephemeral" does NOT go
    through chat() at all — it calls the INTERNAL api._generate_raw_ephemeral
    directly (the public /api/chat surface is composed-only and rejects raw
    mode), sending system_prompt/user_prompt VERBATIM with no composition
    and no persistence of any kind — the mode for operator evidence
    drafting. A conv_id combined with raw_ephemeral is a programming error
    and raises ValueError loudly (an ephemeral conv_id would persist turns
    via add_turn on the composed path).
    """
    import logging
    logger = logging.getLogger("lorevox.llm")
    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: loud contract check
    # BEFORE the failure-tolerant try block — never degrade this to None.
    if prompt_mode == "raw_ephemeral" and (conv_id or "").strip():
        raise ValueError(
            "raw_ephemeral is stateless — conv_id is forbidden "
            "(nothing may be persisted from a raw drafting call)")
    # P1: Global temperature safety gate — clamp to minimum safe value.
    # This is the single choke point for ALL LLM calls via this wrapper.
    # chat()/chat_stream()/chat_ws all have their own guards too, but this
    # catches any caller that might pass temp=0 before it reaches generate().
    if temp <= 0:
        logger.warning("[llm] temp=%s clamped to 0.01 (greedy-safe minimum)", temp)
        temp = 0.01
    try:
        if prompt_mode == "raw_ephemeral":
            # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (follow-up
            # hardening): raw mode uses the internal function directly —
            # never the public chat() endpoint. Local import so the server
            # can still boot in USE_TTS=1 mode.
            from .api import _generate_raw_ephemeral  # type: ignore

            txt = (_generate_raw_ephemeral(
                system_prompt, user_prompt,
                temp=temp, top_p=top_p, max_new=max_new,
                request_kind=request_kind,
                budget_components=budget_components) or "").strip()
        else:
            # Local import so the server can still boot in USE_TTS=1 mode.
            from .api import chat, _ChatReq, ChatTurn  # type: ignore

            # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: explicit
            # ChatTurn construction (identical under real pydantic, which
            # coerced the previous dicts; required for the offline
            # pydantic-stub test lane).
            req = _ChatReq(
                messages=[
                    ChatTurn(role="system", content=system_prompt),
                    ChatTurn(role="user", content=user_prompt),
                ],
                temp=temp,
                top_p=top_p,
                max_new=max_new,
                conv_id=conv_id,
            )
            out = chat(req)
            txt = (out.get("text") or "").strip()
        if not txt:
            logger.warning("[llm] LLM returned empty text for extraction request")
        return txt or None
    except ExtractionPromptBudgetExceeded:
        # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 5.
        #
        # THIS RE-RAISE IS LOAD-BEARING. Without it the blanket handler
        # below returns None, the caller reads that as "the LLM produced
        # nothing", marks the LLM unavailable and falls through to the
        # rules extractor -- so a prompt that was refused for being too
        # big would come back as an ordinary empty result and the
        # narrator's turn would be extracted by a weaker path with
        # nobody told. That is fail-OPEN, and Chris's Phase 5 ruling
        # forbids it: a budget violation must reach the ledger as
        # error_class=ExtractionPromptBudgetExceeded.
        #
        # It sits ABOVE `except Exception` because ordering is the whole
        # mechanism -- Python takes the first matching clause. This is
        # the same shape as the raw_ephemeral/conv_id contract check
        # above, which is deliberately outside the try block for the
        # same reason, and the same lesson as INC-2026-07-09: a
        # defensive except around a structural failure is a silencer,
        # not a safety net.
        #
        # Deliberately narrow. Every OTHER extraction error keeps its
        # existing degrade-to-None behaviour; widening that is a
        # separate decision with its own evidence.
        raise
    except ImportError as e:
        logger.warning("[llm] LLM stack not available (import failed): %s", e)
        return None
    except Exception as e:
        logger.error("[llm] LLM call failed: %s: %s", type(e).__name__, e)
        return None


def draft_section_summary(
    *,
    section_title: str,
    instruction: str,
    transcript: str,
    person_name: str = "the speaker",
    pronouns: str = "",
    max_new: Optional[int] = None,
) -> Optional[str]:
    # WO-10M: Honor MAX_NEW_TOKENS_SUMMARY when caller doesn't override.
    if max_new is None:
        max_new = _WO10M_SUMMARY_CAP
    """Draft a short end-of-section narrative summary."""
    transcript = (transcript or "").strip()
    if not transcript:
        return None

    pronoun_note = f" Use {pronouns} pronouns for this person." if pronouns else ""
    system = (
        "You are Lori, a warm, neutral, professional oral historian. "
        "You help turn interview answers into accurate memoir drafts. "
        f"Rules: do not invent facts; do not correct the speaker; keep the tone respectful and clear.{pronoun_note}"
    )

    user = (
        f"Section title: {section_title}\n"
        f"Instruction: {instruction}\n\n"
        f"Transcript (Q&A):\n{transcript}\n\n"
        "Write a cohesive, first-person narrative summary (1–3 short paragraphs) "
        f"as if {person_name} is speaking. "
        "Preserve the speaker's phrasing when possible. "
        "If details are missing, stay general rather than guessing."
    )

    return _try_call_llm(system, user, max_new=max_new, temp=0.45, top_p=0.9)


def propose_followup_questions(
    *,
    transcript: str,
    n: int = 5,
    max_new: int = 280,
) -> List[str]:
    """Ask the LLM for follow-up questions. Returns a list (possibly empty)."""
    transcript = (transcript or "").strip()
    if not transcript:
        return []

    system = (
        "You are Lori, a warm, neutral, professional oral historian. "
        "You generate helpful follow-up interview questions. "
        "Rules: one question at a time; neutral; do not assume facts; focus on clarifying dates, names, places, and vivid details."
    )

    user = (
        f"Based on the transcript below, propose {n} follow-up questions to deepen the story.\n"
        "Return ONLY a JSON array of strings (no markdown, no commentary).\n\n"
        f"Transcript:\n{transcript}"
    )

    txt = _try_call_llm(system, user, max_new=max_new, temp=0.65, top_p=0.95)
    if not txt:
        return []

    # Try strict JSON first.
    try:
        arr = json.loads(txt)
        if isinstance(arr, list):
            out = [str(x).strip() for x in arr]
            out = [q for q in out if q]
            return out[:n]
    except Exception:
        pass

    # Fallback: parse lines.
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    qs: List[str] = []
    for ln in lines:
        ln = re.sub(r"^[\-\*\d\.)\s]+", "", ln).strip()
        if not ln:
            continue
        qs.append(ln)

    # De-dup preserve order.
    seen = set()
    uniq: List[str] = []
    for q in qs:
        k = q.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(q)
    return uniq[:n]


def draft_travel_section(
    *,
    scope_title: str,
    instruction: str,
    evidence_text: str,
    max_new: Optional[int] = None,
) -> Optional[str]:
    """Draft a travelogue section paragraph from assembled operator evidence.

    Operator-side writing aid for Travel Doc (WO-TRAVEL-DOC-OPERATOR-DRAFT-
    ASSISTANT-01). Unlike draft_section_summary this is NOT a Q&A transcript
    and NOT first-person-speaker — it turns labeled travel evidence (approved
    photo context, operator notes, sources) into readable travelogue prose.
    Returns None if the LLM stack is unavailable or there is no evidence.

    WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: calls the LLM with
    prompt_mode="raw_ephemeral" and NO conversation id — the system prompt
    below reaches the model verbatim, never wrapped by compose_system_prompt
    (DEFAULT_CORE persona, default-session PROFILE_JSON, pinned RAG). The
    composed wrap was a live invention vector (a kept draft opened "As I
    stepped off the train in Prague…" with no train anywhere in evidence),
    and the prompt now carries explicit anti-invention prohibitions too.
    """
    if max_new is None:
        max_new = _WO10M_SUMMARY_CAP
    evidence_text = (evidence_text or "").strip()
    if not evidence_text:
        return None

    system = (
        "You are a careful travel-memoir drafting assistant helping an operator "
        "build a travelogue. You turn assembled evidence into a warm, readable "
        "first-draft. Hard rules: use ONLY the evidence provided; never invent "
        "place names, dates, people, prices, or events; if the evidence is thin, "
        "write something short and general rather than guessing. Evidence marked "
        "'Approved' may be stated plainly. Evidence marked 'Draft' is unconfirmed "
        "— write it suggestively ('appears to', 'seems to', 'may have') and never "
        "assert it as fact. Output draft prose ONLY — no preamble, no 'Here is', "
        "no markdown headings, no bullet lists unless the instruction asks. "
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: explicit
        # anti-invention prohibitions (supplementing the composer bypass).
        "Additional hard prohibitions: do not invent the mode of arrival or "
        "departure — no trains, stations, airports, flights, cars, buses, or "
        "walking unless the evidence explicitly states them. Do not invent "
        "weather. Do not invent crowds, bustle, atmosphere, sensory detail, or "
        "emotions. Add no chronology beyond explicitly supplied dates. Never "
        "turn a bare place name into a scene. When the evidence is thin, "
        "write FEWER sentences."
    )
    user = (
        f"Scope: {scope_title}\n"
        f"Operator instruction: {instruction}\n\n"
        f"Evidence (use only this):\n{evidence_text}\n\n"
        "Write the draft now. Stay strictly within the evidence above."
    )
    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: raw ephemeral — no
    # conversation id, no composed wrap; routed by _try_call_llm to the
    # INTERNAL api._generate_raw_ephemeral, never the public chat() surface.
    return _try_call_llm(system, user, max_new=max_new, temp=0.5, top_p=0.9,
                         prompt_mode="raw_ephemeral")


def draft_final_memoir(
    *,
    transcript: str,
    person_name: str,
    pronouns: str = "",
    max_new: Optional[int] = None,
) -> Optional[str]:
    """Draft a short memoir from the full transcript."""
    # WO-10M: Honor MAX_NEW_TOKENS_SUMMARY when caller doesn't override.
    if max_new is None:
        max_new = _WO10M_SUMMARY_CAP
    transcript = (transcript or "").strip()
    if not transcript:
        return None

    pronoun_note = f" Use {pronouns} pronouns for this person." if pronouns else ""
    system = (
        "You are Lori, a warm, neutral, professional oral historian and memoir biographer. "
        "You write accurate memoir drafts from interviews. "
        f"Rules: do not invent facts; do not correct the speaker; keep it readable; use first person as the speaker.{pronoun_note}"
    )

    user = (
        f"Write a memoir-style draft in first person for {person_name}.\n"
        "Length: ~500–900 words.\n"
        "Structure: 5–9 short paragraphs, chronological where possible.\n"
        "Only use details explicitly present in the transcript; if something is missing, do not guess.\n\n"
        f"Transcript:\n{transcript}"
    )

    return _try_call_llm(system, user, max_new=max_new, temp=0.55, top_p=0.95)
