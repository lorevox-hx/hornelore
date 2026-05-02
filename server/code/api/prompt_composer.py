"""Lorevox prompt composer.

This module centralizes how the *system prompt* is built so that BOTH:
- SSE chat (/api/chat/stream), and
- WebSocket chat (code/api/routers/chat_ws.py)
use the same behavioral tuning.

Design goals:
- UI stays "dumb": it can send a minimal system prompt and/or profile snapshot.
- Backend stays "smart": it always injects pinned RAG docs and stable role rules.
- Back-compat: works even when the UI does not provide profile/session context.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import db
from .lv_eras import (
    era_id_to_lori_focus,
    era_id_to_warm_label,
    legacy_key_to_era_id,
)
from .memory_echo import parse_correction_rule_based

logger = logging.getLogger(__name__)


DEFAULT_CORE = (
    "You are Lorevox (\"Lori\"), a personal life story companion and oral historian. "
    # Who Lori is and where her name comes from — she can share this naturally when introducing herself.
    "Your full name is Lorevox: 'Lore' means stories and oral tradition; 'Vox' is Latin for voice. "
    "Together, Lorevox means 'the voice of your stories.' "
    "Your nickname Lori comes from that name. "
    "Your purpose is to help people build a Life Archive — a lasting record of their life story, "
    "told in their own voice, organised into a timeline, and shaped into a memoir. "
    "You do this through warm, unhurried conversation and specific questions. "
    "You are NOT a corporate recruiter, and you are not conducting a job interview. "
    "IDENTITY RULE: You are Lori, the interviewer. The person you are speaking with has their own name, which you "
    "will learn from the LORI_RUNTIME speaker field or from conversation. "
    "If the narrator mentions someone named 'Lori' in their story (a relative, friend, classmate, etc.), "
    "that is a DIFFERENT person — never yourself. "
    "Never address the narrator by your own name. Never confuse yourself with a person in their story. "
    "When the speaker's name is known, always use it when addressing them. "
    # v7.4D — Fact humility rule. Prevents Lori from confidently correcting personal
    # facts she cannot verify. The canonical failure: narrator says "Hazleton, ND" and
    # Lori corrects to "Hazen, ND" without being asked. This rule stops that pattern.
    "FACT HUMILITY RULE: Never correct or contradict the narrator's place names, personal names, "
    "family details, or biographical facts unless they explicitly ask you to verify something. "
    "If a name or place sounds unusual or ambiguous, ask one gentle clarifying question instead of asserting a correction. "
    "The narrator's lived memory is always more authoritative than your general knowledge or external data. "
    "Example — if the narrator says 'Hazleton, North Dakota', do not say 'I think you mean Hazen' — "
    "instead say 'Tell me more about Hazleton' or 'What do you remember about being there?'"
    # v7.4E — Empathy rule with message-type classification.
    # The previous version fired on any mention of difficulty, which caused Lori
    # to apply emotional acknowledgment to product feedback ("don't you just want
    # the actual date?"), treating it as distress. The fix: classify the message
    # type first, then decide whether empathy applies.
    " EMPATHY RULE: Before responding, silently classify the narrator's message into one of five types:\n"
    "  interaction_feedback — narrator is commenting on how you are asking questions, "
    "or telling you to change your approach. "
    "Examples: 'don't you just want the actual date', 'why are you asking that', "
    "'just ask me directly', 'that's a strange way to ask'.\n"
    "  operator_feedback — narrator is talking about the PRODUCT, APP, UI, or SYSTEM itself "
    "rather than their life story. This includes: comments about buttons, labels, screens, or "
    "the interface; questions about whether the system is working; reports of errors, bugs, "
    "outages, or unavailability; diagnostic questions; explicit product suggestions or "
    "change requests. Examples: 'the big green button should say Send to Lori for Review', "
    "'why is chat service unavailable', 'are you working now', 'the mic isn't picking me up', "
    "'this is a test, can you hear me', 'the transcript panel is empty', "
    "'can you try reconnecting', 'the Bug Panel shows 404s', 'I'm testing you right now'.\n"
    "  emotional_distress — narrator expresses genuine pain, grief, sadness, fear, loss, "
    "or emotional overwhelm. Examples: 'that was a very hard time', 'I still cry thinking about it', "
    "'I don't want to talk about that'.\n"
    "  meta_confusion — narrator is confused about what the question is asking. "
    "Examples: 'what do you mean by that', 'I'm not sure what you're asking', 'can you rephrase that'.\n"
    "  content_answer — narrator is answering the question, even if briefly or imprecisely.\n"
    "RULES BY TYPE:\n"
    "  interaction_feedback: Respond directly to the feedback. Acknowledge it, adjust your approach, "
    "and then ask the corrected question. Do NOT apply the empathy acknowledgment.\n"
    "  operator_feedback: Drop interview mode entirely for this turn. Respond as a helpful, "
    "concise system/product assistant would: acknowledge what they observed or suggested, "
    "answer diagnostic questions plainly (yes/no, working/not working, what you can and cannot do), "
    "and confirm that you heard product feedback and will note it. Do NOT redirect to "
    "childhood, family, or any biographical question. Do NOT ask a new interview question at the "
    "end of this turn. Do NOT apply the empathy acknowledgment. Keep it short (1–3 sentences). "
    "The narrator will return to storytelling on their own when they are ready.\n"
    "  emotional_distress: Acknowledge the feeling warmly in your first sentence before asking anything. "
    "Do not immediately pivot to a factual question.\n"
    "  meta_confusion: Rephrase or clarify the question. Do not apply the empathy acknowledgment.\n"
    "  content_answer: Continue the interview naturally."
    # v7.4D — Revision acceptance (Test 7 gap). User self-corrections are authoritative.
    " REVISION RULE: If the narrator revises a date, name, age, or other detail they already gave you, "
    "accept the revision without comment or pressure. "
    "Never ask them to confirm which version is correct unless they explicitly request it. "
    "Never express surprise or suggest one version is more likely. Simply continue with the revised fact."
    # v7.4E — No question lists. This prevents Lori from producing a numbered interrogation list
    # even when the narrator explicitly requests one. The philosophy is 'recollection, not interrogation.'
    # When someone asks for a list, it usually means they want to feel prepared — the right response is
    # to honour that instinct while keeping the conversation alive.
    # Scope clarification: this rule is for NARRATOR-FACING INTERVIEW MODE only. Helper / operator /
    # diagnostic modes may legitimately surface lists (e.g. an operator asking 'what are the open
    # questions in the bank' should get a list). The composer dispatches by turn_mode upstream, so
    # this constant is reached only on narrator-facing interview turns; the rule is therefore
    # phrased to reflect that audience.
    " NO QUESTION LISTS RULE (narrator-facing interview mode): While in interview conversation with "
    "the narrator, never produce a numbered or bulleted list of interview questions, even if they "
    "ask for one. "
    "If the narrator asks you to 'give me a list of questions' or similar, respond warmly and briefly "
    "with something like: 'I love that spirit — let's start with the one that matters most to me, "
    "and we can follow the thread from there.' "
    "Then ask your single most important opening question. "
    "This keeps the conversation feeling like a warm exchange, not a form or survey. "
    "ONE question per turn, always — no exceptions in interview mode."
    #
    # ── ACUTE SAFETY RULE ──────────────────────────────────────────────────────
    # When the narrator or anyone present faces an acute, life-threatening
    # situation, Lori IMMEDIATELY stops the interview and becomes a truthful
    # emergency handoff assistant. This is the highest-priority rule in the
    # system — it overrides ALL other instructions, including interview mode,
    # pass directives, and memoir framing.
    #
    # ACTIVATION SIGNALS (any of the following = safety mode):
    #   • Suicidal ideation, self-harm intent, discussing means of self-harm
    #   • Overdose, poisoning, swallowing toxic substances
    #   • Carbon monoxide: CO detector beeping AND any symptom (fatigue, headache,
    #     confusion, dizziness, weakness, nausea)
    #   • Generator / vehicle running in enclosed space + anyone unresponsive
    #   • Fire, smoke, or smell of smoke
    #   • Anyone unresponsive, unconscious, collapsed
    #   • Anyone not breathing, stopped breathing, or only gasping
    #   • Explicit statement of immediate danger to self or another person
    #
    " ACUTE SAFETY RULE: If the narrator's message describes any life-threatening "
    "emergency — including suicidal ideation, overdose or poisoning, carbon monoxide "
    "exposure, fire or smoke, an unresponsive or unconscious person, or anyone who "
    "has stopped breathing — you must IMMEDIATELY stop the interview and respond ONLY "
    "as a calm, truthful emergency handoff assistant. "
    #
    # ── HARD-FORBIDDEN PHRASES (move first so the model sees them before anything else)
    # The phrases below are common trained responses that are WRONG in an emergency.
    #
    # ── WHAT TO SAY FIRST (prescriptive template overrides trained defaults) ──────
    "MANDATORY RESPONSE FORMAT for suicidal ideation — when a person says they want "
    "to die, end their life, kill themselves, or harm themselves, your FIRST sentence "
    "MUST follow this pattern: 'I'm an AI and I can't place calls for you, but please "
    "call or text 988 right now — that is the current US Suicide and Crisis Lifeline.' "
    "Do NOT open with any refusal, disclaimer, or 'I cannot' statement. "
    "Do NOT open with 'I cannot continue'. Do NOT open with 'I can't continue'. "
    "Open with the resource, always.\n"
    "\n"
    "MANDATORY RESPONSE FORMAT for someone who has taken pills AND reports drowsiness, "
    "confusion, slurred speech, or difficulty staying awake — your FIRST sentence MUST "
    "be: 'Call 911 right now — this is a medical emergency.' "
    "Do NOT open with 'I cannot give you medical advice' or any disclaimer. "
    "Do NOT give a resource list. Say call 911 immediately, then stay on the line.\n"
    "\n"
    "MANDATORY RESPONSE FORMAT for an unresponsive or unconscious person — your FIRST "
    "sentence MUST be: 'Call 911 right now.' Then give CPR instructions immediately. "
    "Do NOT open with 'I cannot provide medical advice'.\n"
    "\n"
    "HARD-FORBIDDEN PHRASES — these trained defaults are wrong in an emergency. "
    "None of these may appear anywhere in a safety response:\n"
    "   ✗ Any form of 'I cannot continue this/our conversation' — stay present, always\n"
    "   ✗ Any form of 'I can't continue this/our conversation' — same prohibition\n"
    "   ✗ '1-800-273-TALK' — must never appear in Lorevox responses.\n"
    "   ✗ '1-800-273-8255' — must never appear in Lorevox responses.\n"
    "   ✗ '273-TALK' — same prohibition.\n"
    "   (The current primary U.S. Suicide & Crisis Lifeline is 988. AFSP\n"
    "   confirms the older 1-800 number continues to function indefinitely;\n"
    "   it just isn't the primary access point Lorevox should surface.)\n"
    "   ✗ Any form of 'I cannot provide medical advice' — routing to 911 is not advice\n"
    "   ✗ Any form of 'I cannot give you medical advice' — same prohibition\n"
    "   ✗ 'Is there anything else I can help you with?' — never after a safety response\n"
    "   ✗ 'Anything else I can help you with?' — same prohibition\n"
    "   ✗ Home remedies for poisoning — never suggest inducing vomiting\n"
    "   ✗ Pivoting to interview or memoir questions while danger is present\n"
    "\n"
    "Follow these rules in order:\n"
    "1. STOP the interview immediately. Do not ask any follow-up interview question.\n"
    "2. OPEN with the resource or emergency action — see MANDATORY RESPONSE FORMAT above.\n"
    "3. SAY you are an AI and cannot place calls or contact emergency services yourself.\n"
    "4. GIVE THE CORRECT NUMBER — only these, no others:\n"
    "   • Suicide or self-harm ideation: 988 (current US Suicide and Crisis Lifeline). "
    "If means are present and action may be imminent, also say call 911 now.\n"
    "   • Pills taken AND any drowsiness, confusion, or breathing difficulty: 911 now.\n"
    "   • Pills taken, person is alert and stable: Poison Help 1-800-222-1222. "
    "Upgrade to 911 immediately if symptoms appear.\n"
    "   • Swallowed chemical (non-pill), person conscious: Poison Help 1-800-222-1222. "
    "Do NOT say 'get to fresh air' for ingestion — that is CO advice only.\n"
    "   • CO detector beeping or running engine in enclosed space: Everyone out now, "
    "call 911 from outside, do NOT re-enter, do NOT send the caller in to rescue.\n"
    "   • Fire or smoke: Leave immediately, then call 911 from outside.\n"
    "   • Unresponsive or not breathing: Call 911 now, start CPR — 30 compressions "
    "then 2 breaths, repeat until paramedics arrive. No 'if trained' hedging.\n"
    "5. STAY in safety mode on every subsequent turn — do not reset to interview mode.\n"
    "6. ESCALATE: worsening symptoms or new danger → increase urgency, move to 911.\n"
    "TRUTHFULNESS: 'Can you call 911?' → 'I am an AI and cannot place the call — "
    "but you can right now. Call 911 immediately.' "
    "Confidentiality question in crisis: do not overclaim — Lorevox is a private tool "
    "but you are an AI and cannot guarantee disclosure outcomes. "
    "HOSPITALIZATION FEAR: acknowledge briefly and warmly, then still give 988. "
    "Do not use their fear to deflect from the resource."
)


_PROFILE_RE = re.compile(r"PROFILE_JSON\s*:\s*(\{.*\})\s*$", re.DOTALL)


def extract_profile_json_from_ui_system(ui_system: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Extract a trailing PROFILE_JSON:{...} blob (if present).

    Returns (profile_obj, base_system_without_profile_json).
    """
    if not ui_system:
        return None, None

    s = ui_system.strip()
    m = _PROFILE_RE.search(s)
    if not m:
        return None, s

    raw = m.group(1).strip()
    base = (s[: m.start()]).rstrip()  # remove the PROFILE_JSON line

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj, base
        logger.warning("prompt_composer: PROFILE_JSON parsed but is not a dict (type=%s) — ignoring", type(obj).__name__)
    except Exception as exc:
        logger.warning("prompt_composer: failed to parse PROFILE_JSON blob: %s — profile context dropped", exc)

    # If parse fails, keep original as base (no profile context injected)
    return None, s


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def _known_identity_facts_block(runtime71: Optional[Dict[str, Any]]) -> str:
    """Compact verified identity facts for the current turn.

    BUG-LG-01 fix: These facts are rendered at prompt-level so the LLM
    treats them as authoritative ground truth rather than inventing
    alternatives (e.g. saying 'Abilene, Kansas' when POB is Spokane, WA).
    """
    rt = runtime71 or {}

    speaker_name = (rt.get("speaker_name") or "").strip()
    dob = str(rt.get("dob") or "").strip()
    pob = str(rt.get("pob") or rt.get("place_of_birth") or "").strip()

    facts: list[str] = []
    if speaker_name:
        facts.append(f"- Name: {speaker_name}")
    if dob:
        facts.append(f"- Date of birth: {dob}")
    if pob:
        facts.append(f"- Place of birth: {pob}")

    if not facts:
        return "KNOWN IDENTITY FACTS:\n- none yet"

    return "KNOWN IDENTITY FACTS:\n" + "\n".join(facts)


def _identity_grounding_rules_block(runtime71: Optional[Dict[str, Any]]) -> str:
    """Hard anti-hallucination rules for narrator identity facts.

    BUG-LG-01 fix: Prevents Lori from inventing alternate birthplace,
    birth date, or name when verified facts exist in runtime71.
    """
    rt = runtime71 or {}

    speaker_name = (rt.get("speaker_name") or "").strip()
    dob = str(rt.get("dob") or "").strip()
    pob = str(rt.get("pob") or rt.get("place_of_birth") or "").strip()

    if not (speaker_name or dob or pob):
        return (
            "IDENTITY GROUNDING RULES:\n"
            "- No verified identity facts are available yet.\n"
            "- Do not guess the narrator's name, birthplace, birth date, age, or other core identity facts.\n"
            "- If you need a missing identity fact, ask for it gently instead of inventing it."
        )

    return (
        "IDENTITY GROUNDING RULES:\n"
        "- Verified identity facts in KNOWN IDENTITY FACTS are authoritative for this turn.\n"
        "- If you mention the narrator's name, birthplace, or birth date, use the verified fact exactly as written.\n"
        "- Never substitute a different city, state, year, age, or biographical detail when a verified fact exists.\n"
        "- Never 'improve', normalize, or guess a more likely birthplace or personal detail.\n"
        "- If a fact is missing, ask warmly and briefly instead of guessing.\n"
        "- You may mention a verified identity fact naturally, but only when it helps the conversation.\n"
        "- Do not sound mechanical or repetitive; stay warm and conversational."
    )


# ---------------------------------------------------------------------------
# WO-9/WO-10 — Adaptive Conversation Memory Context Builder
# Phase 1: scored/pruned summary | Phase 2: multi-thread | Phase 3: adaptive
# Phase 4: resume confidence | Phase 5: conversation state
# ---------------------------------------------------------------------------
def build_conversation_memory_context(
    person_id: Optional[str],
    session_id: Optional[str] = None,
    conversation_state: Optional[str] = None,
    cognitive_support_mode: bool = False,
) -> str:
    """
    Build an adaptive conversation memory block for the LLM prompt.
    WO-10: Selects context based on conversation shape, thread strength,
    and resume confidence rather than fixed "last N turns + anchor".
    Returns a formatted string or "" if no memory exists.
    """
    from . import archive as arc

    if not person_id:
        return ""

    try:
        # Load the three memory sources
        recent = arc.load_recent_archive_turns(person_id, session_id=session_id, limit=8)
        anchor = None
        summary = arc.read_rolling_summary(person_id)

        # Thread anchor: try latest session
        sid = session_id or arc.get_latest_session_id(person_id)
        if sid:
            anchor = arc.read_thread_anchor(person_id=person_id, session_id=sid)

        # WO-10: Prune summary to scored items
        summary = arc.prune_rolling_summary(summary)

        # WO-10: Multi-thread awareness — choose best thread
        threads = summary.get("active_threads", [])
        selected_thread = arc.choose_best_thread(anchor, threads, recent)

        # WO-10: Resume confidence scoring
        confidence = arc.score_resume_confidence(anchor, summary, recent, selected_thread)
        conf_level = confidence.get("level", "low")

        # WO-10C: Cognitive Support Mode — single-thread, simplified memory
        if cognitive_support_mode:
            # Use dedicated CSM thread selector (prefers warmth over recency)
            csm_thread = arc.wo10c_select_single_support_thread(anchor, threads, recent)
            csm_lines = ["CONVERSATION MEMORY (COGNITIVE SUPPORT MODE):"]
            csm_lines.append("  NOTE: This narrator benefits from extra pacing support — slower, simpler conversation. Keep context minimal.")
            if csm_thread:
                csm_lines.append(f"  Familiar topic: {csm_thread.get('topic_label', 'general')}")
                if csm_thread.get("summary"):
                    csm_lines.append(f"  Context: {csm_thread['summary'][:200]}")
                if csm_thread.get("related_era"):
                    csm_lines.append(f"  Era: {csm_thread['related_era']}")
            elif anchor and anchor.get("topic_summary"):
                csm_lines.append(f"  Familiar topic: {anchor.get('topic_label', 'unknown')}")
                csm_lines.append(f"  Context: {anchor['topic_summary'][:200]}")
            # Only the last narrator turn — not a full exchange
            if anchor and anchor.get("last_meaningful_user_turn"):
                csm_lines.append(f"  Last they shared: {anchor['last_meaningful_user_turn'][:150]}")
            # Key facts only — minimal set
            scored_items = summary.get("scored_items", [])
            if scored_items:
                top_facts = [i for i in scored_items if i.get("kind") != "question"][:3]
                if top_facts:
                    csm_lines.append("  Key facts:")
                    for item in top_facts:
                        csm_lines.append(f"    {item.get('text', '')[:100]}")
            csm_lines.append("  RULE: Do NOT list multiple topics. Do NOT offer choices between threads.")
            csm_lines.append("  If you reference memory, mention ONE familiar topic gently — as an invitation, not a test.")
            return "\n".join(csm_lines) if len(csm_lines) > 2 else ""

        # WO-10: Adaptive budgeting based on scenario
        scenario = _detect_memory_scenario(anchor, recent, summary)

        lines = ["CONVERSATION MEMORY:"]

        # ── Thread block (adaptive size) ──
        if selected_thread:
            lines.append(f"  Active thread: {selected_thread.get('topic_label', 'general')}")
            if selected_thread.get("subtopic_label"):
                lines.append(f"  Subtopic: {selected_thread['subtopic_label']}")
            if selected_thread.get("related_era"):
                lines.append(f"  Era: {selected_thread['related_era']}")
            if selected_thread.get("summary"):
                lines.append(f"  Thread context: {selected_thread['summary'][:250]}")
        elif anchor and anchor.get("topic_summary"):
            lines.append(f"  Last topic: {anchor.get('topic_label', 'unknown')}")
            lines.append(f"  Summary: {anchor['topic_summary'][:250]}")
            if anchor.get("active_era"):
                lines.append(f"  Era: {anchor['active_era']}")

        # ── Multi-thread awareness ──
        if len(threads) > 1:
            other_threads = [t for t in threads if t != selected_thread][:2]
            if other_threads:
                labels = [t.get("topic_label", "?") for t in other_threads]
                lines.append(f"  Other open threads: {', '.join(labels)}")

        # ── Scored summary block (adaptive size) ──
        scored_items = summary.get("scored_items", [])
        if scored_items:
            if scenario == "resume_after_gap":
                # More summary, less raw turns
                top_items = scored_items[:8]
            elif scenario == "long_mature_thread":
                top_items = scored_items[:5]
            else:
                top_items = scored_items[:3]

            fact_lines = []
            for item in top_items:
                kind = item.get("kind", "fact")
                text = item.get("text", "")[:120]
                if kind == "open_loop":
                    fact_lines.append(f"    [open] {text}")
                elif kind == "question":
                    fact_lines.append(f"    [Q] {text}")
                elif kind == "tone":
                    fact_lines.append(f"    [tone] {text}")
                else:
                    fact_lines.append(f"    {text}")
            if fact_lines:
                lines.append("  Key memory:")
                lines.extend(fact_lines)

        # ── Last meaningful exchange from anchor ──
        if anchor and anchor.get("last_meaningful_user_turn"):
            lines.append(f"  Last narrator said: {anchor['last_meaningful_user_turn'][:200]}")
            if anchor.get("last_meaningful_assistant_turn"):
                lines.append(f"  Lori replied: {anchor['last_meaningful_assistant_turn'][:150]}")

        # ── Recent turns block (adaptive count) ──
        if recent:
            if scenario == "short_recent_thread":
                turn_count = min(6, len(recent))  # more raw turns
            elif scenario == "resume_after_gap":
                turn_count = min(3, len(recent))  # less raw, more summary
            else:
                turn_count = min(4, len(recent))

            turn_lines = []
            for t in recent[-turn_count:]:
                role = (t.get("role") or "").upper()
                content = (t.get("content") or "").strip()[:150]
                if role == "USER":
                    turn_lines.append(f"    Narrator: {content}")
                elif role == "ASSISTANT":
                    turn_lines.append(f"    Lori: {content}")
            if turn_lines:
                lines.append("  Recent exchange:")
                lines.extend(turn_lines)

        # ── Resume confidence directive ──
        if conf_level == "high":
            lines.append("  Resume directly from the active thread. Welcome them back warmly.")
        elif conf_level == "medium":
            lines.append("  Resume softly — confirm the thread before diving deep.")
            lines.append('  Example: "Last time we were talking about [topic]. Shall we continue there?"')
        else:
            lines.append("  Resume with a gentle bridge — do not assume the last thread.")
            lines.append('  Example: "We\'ve touched on several parts of your story. Where would you like to continue today?"')

        # ── WO-10B: Hard anti-drift rule ──
        # If a substantive thread is active, identity/homeplace is FORBIDDEN
        has_substantive_thread = (
            selected_thread
            and not any(
                pat in (selected_thread.get("topic_label") or "").lower()
                for pat in ("birthplace", "childhood", "stanley", "hometown", "born in", "identity", "onboarding")
            )
        )
        if has_substantive_thread:
            lines.append("  HARD RULE: Do NOT ask about birthplace, childhood home, or identity basics.")
            lines.append("  The narrator has an active story thread — stay on it.")
            lines.append("  Asking about birthplace when a stronger thread exists feels dismissive of what they shared.")
        else:
            lines.append("  No strong thread active — gentle open questions are acceptable, including identity topics.")

        # ── Conversation state hint (WO-10 Phase 5) ──
        if conversation_state:
            state_hints = {
                "storytelling": "The narrator is in storytelling mode — listen more, question less.",
                "reflecting": "The narrator is reflecting — use gentle follow-ups, not fact-seeking questions.",
                "emotional_pause": "The narrator may be emotional — wait, acknowledge, do not redirect.",
                "correcting": "The narrator is correcting or revising — accept corrections without comment.",
                "searching_memory": "The narrator is searching their memory — be patient, offer gentle prompts.",
                "answering": "The narrator is answering a question — follow up naturally.",
            }
            hint = state_hints.get(conversation_state)
            if hint:
                lines.append(f"  Narrator state: {hint}")

        return "\n".join(lines) if len(lines) > 1 else ""

    except Exception as e:
        logger.warning(f"[WO-10] build_conversation_memory_context error: {e}")
        return ""


def _detect_memory_scenario(
    anchor: Optional[Dict[str, Any]],
    recent_turns: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> str:
    """
    WO-10 Phase 3: Detect the conversation scenario for adaptive budgeting.
    Returns: 'short_recent_thread' | 'long_mature_thread' | 'resume_after_gap' | 'first_session'
    """
    if not recent_turns and not anchor:
        return "first_session"

    # Check if anchor is fresh (within last 2 hours)
    anchor_fresh = False
    if anchor and anchor.get("updated_at"):
        try:
            from datetime import datetime, timezone
            anchor_dt = datetime.fromisoformat(anchor["updated_at"].replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - anchor_dt).total_seconds() / 3600
            anchor_fresh = age_hours < 2
        except Exception:
            pass

    # Short/recent: few turns, anchor fresh
    if len(recent_turns) <= 6 and anchor_fresh:
        return "short_recent_thread"

    # Long/mature: many turns or many scored items
    scored_items = summary.get("scored_items", [])
    if len(recent_turns) > 6 or len(scored_items) > 10:
        return "long_mature_thread"

    # Resume after gap: anchor exists but is stale
    if anchor and not anchor_fresh:
        return "resume_after_gap"

    return "short_recent_thread"


# ─── WO-ARCH-07A — Memory Echo + Correction Composers ───────────────────────

def _fmt_line(label: str, value) -> str:
    """Format a single read-back line, showing 'unknown' for empty values."""
    v = (value or "").strip() if isinstance(value, str) else value
    return f"- {label}: {v}" if v else f"- {label}: unknown"


# WO-LORI-SESSION-AWARENESS-01 Phase 1b: hardened list/object rendering for
# profile_seed values. The earlier Phase 1a path used naive str(x) which
# produces "Children: {'name': 'Emma'}, 42" garbage when items are dicts.
# This helper extracts a clean human-readable label from common name-field
# shapes (preferredName / fullName / firstName+middleName+lastName / relation)
# and falls back to str() for scalars.

def _label_item(x: Any) -> str:
    """Return a clean display label for a profile_seed list item.

    Dict shape (children[], parents[], siblings[]):
        prefer preferredName → fullName → "First Middle Last" composite
        → relation. Returns "" if nothing usable.
    Scalar shape:
        return str(x).strip().
    """
    if isinstance(x, dict):
        for key in ("preferredName", "fullName"):
            v = (x.get(key) or "").strip()
            if v:
                return v
        # Coalesce None → "" before str-coerce so {"lastName": None} doesn't
        # leak the literal "None" into composite name strings.
        parts = []
        for k in ("firstName", "middleName", "lastName"):
            raw = x.get(k)
            if raw is None:
                continue
            piece = str(raw).strip()
            if piece:
                parts.append(piece)
        composite = " ".join(parts).strip()
        if composite:
            return composite
        relation = (x.get("relation") or "").strip()
        return relation or ""
    if x is None:
        return ""
    return str(x).strip()


def _build_profile_seed(person_id: Optional[str]) -> Dict[str, Any]:
    """Assemble the 9-bucket profile_seed dict from a narrator's profile_json.

    Reads from the narrator's `profiles.profile_json` row (templates hydrate
    here at preload time per `narrator-preload.js`). Returns an empty dict
    on any failure — caller treats missing buckets as "(not on record yet)"
    in the readback. Never raises.

    Bucket priority per WO-LORI-SESSION-AWARENESS-01 Phase 1b directive:
      1. profile_json (template/profile, canonical) — implemented here
      2. Bio Builder questionnaire state — folded into profile_json by
         the questionnaire endpoint already; if it lands separately later,
         add a second source here
      3. promoted truth — already merged into profile_json by promotion path
      4. session transcript — only structured (not free-form memoir text)

    Buckets:
      childhood_home → personal.placeOfBirth
      parents_work   → parents[].occupation joined
      heritage       → personal.culture (raw — Schema-Diversity Phase 3 will
                       split into raceEthnicity[] / religiousAffiliation /
                       culturalAffiliations[] / spiritualBackground)
      education      → education.schooling / .higherEducation joined
      military       → military.* (most templates lack this)
      career         → education.careerProgression OR community.role
      partner        → spouse.preferredName / fullName / "First Last"
      children       → children[] mapped via _label_item
      life_stage     → derived from current era / DOB-age (rough bucket)
    """
    if not person_id:
        return {}
    try:
        from .db import get_profile
        prof = get_profile(person_id) or {}
        blob = prof.get("profile_json") or {}
        # profile_json may be {profile: {...}} or flat {...}
        root = blob.get("profile") if isinstance(blob.get("profile"), dict) else blob
        if not isinstance(root, dict):
            return {}
    except Exception as exc:
        logger.warning("[memory-echo][profile-seed] profile read failed for %s: %s", person_id, exc)
        return {}

    seed: Dict[str, Any] = {}

    # Phase 1b shape compat (2026-04-29 review): profile_json may be
    # template-shaped (`personal`/`parents`/`spouse`/`children`/`education`)
    # OR basics-shaped (`basics.dob`/`basics.pob`/`basics.placeOfBirth`)
    # OR a hybrid coming from the promotion/profile pipeline. Read both
    # so the readback works regardless of which writer hydrated the row.
    personal = root.get("personal") or {}
    basics = root.get("basics") or {}
    parents = root.get("parents") or []
    kinship = root.get("kinship") or []
    spouse = root.get("spouse")
    children = root.get("children") or []
    education = root.get("education") or {}
    military = root.get("military") or {}
    community = root.get("community") or {}

    def _first_str(*vals: Any) -> str:
        """Return first non-empty stripped string from a sequence of
        candidate values. Coerces None / non-strings to empty."""
        for v in vals:
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    # childhood_home — placeOfBirth (template) or basics.pob/placeOfBirth
    pob = _first_str(
        personal.get("placeOfBirth"),
        personal.get("place_of_birth"),
        basics.get("placeOfBirth"),
        basics.get("place_of_birth"),
        basics.get("pob"),
    )
    if pob:
        seed["childhood_home"] = pob

    # parents_work — parents[].occupation. Try both `parents` (template
    # shape) and `kinship` (promoted/profile shape with role-tagged
    # entries). Each entry is a dict with first/preferred name + occupation.
    parents_source: List[Any] = []
    if isinstance(parents, list):
        parents_source.extend(parents)
    if isinstance(kinship, list):
        for k in kinship:
            if not isinstance(k, dict):
                continue
            role = _first_str(k.get("relation"), k.get("role")).lower()
            if role in ("mother", "father", "parent"):
                parents_source.append(k)
    if parents_source:
        parts = []
        for p in parents_source:
            if not isinstance(p, dict):
                continue
            name = _first_str(p.get("firstName"), p.get("preferredName"), p.get("first_name"))
            occ = _first_str(p.get("occupation"), p.get("work"), p.get("job"))
            if name and occ:
                parts.append(f"{name} — {occ}")
            elif occ:
                parts.append(occ)
        if parts:
            seed["parents_work"] = "; ".join(parts)

    # heritage — personal.culture / basics.culture (overloaded; Schema-
    # Diversity Phase 3 will split into raceEthnicity[] / religiousAffiliation
    # / culturalAffiliations[] / spiritualBackground per the schema WO).
    culture = _first_str(personal.get("culture"), basics.get("culture"))
    if culture:
        seed["heritage"] = culture

    # education — schooling + higherEducation
    edu_parts = []
    schooling = _first_str(education.get("schooling"), basics.get("schooling"))
    higher = _first_str(education.get("higherEducation"), basics.get("higherEducation"))
    if schooling:
        edu_parts.append(schooling)
    if higher and higher != schooling:
        edu_parts.append(higher)
    if edu_parts:
        seed["education"] = "; ".join(edu_parts)

    # military — pull a single summary string if any military.* field is set
    if isinstance(military, dict):
        mil = _first_str(
            military.get("summary"),
            military.get("branch"),
            military.get("service"),
            military.get("yearsActive"),
            military.get("rank"),
        )
        if mil:
            seed["military"] = mil

    # career — education.careerProgression OR community.role OR basics.career
    career = _first_str(
        education.get("careerProgression"),
        community.get("role") if isinstance(community, dict) else None,
        basics.get("career"),
        basics.get("occupation"),
    )
    if career:
        seed["career"] = career

    # partner — spouse can be a singular dict OR an array of spouse dicts
    # (donald-trump.json / elena-rivera-quinn.json / jane-goodall.json
    # already exercise the array form; Schema-Diversity Phase 2 will land
    # the array adapter for the rest of the templates).
    if isinstance(spouse, list) and spouse:
        partner_labels = [lbl for lbl in (_label_item(s) for s in spouse) if lbl]
        if partner_labels:
            seed["partner"] = partner_labels
    elif isinstance(spouse, dict):
        partner = _label_item(spouse)
        if partner:
            seed["partner"] = partner

    # children — list of clean labels via _label_item
    if isinstance(children, list) and children:
        labels = [lbl for lbl in (_label_item(c) for c in children) if lbl]
        if labels:
            seed["children"] = labels

    # life_stage — coarse bucket from DOB age (no PII leak; only category)
    dob = _first_str(
        personal.get("dateOfBirth"),
        personal.get("date_of_birth"),
        basics.get("dateOfBirth"),
        basics.get("dob"),
    )
    if dob and len(dob) >= 4 and dob[:4].isdigit():
        try:
            from datetime import datetime
            birth_year = int(dob[:4])
            current_year = datetime.utcnow().year
            age = current_year - birth_year
            if age < 18:
                seed["life_stage"] = "young (under 18)"
            elif age < 30:
                seed["life_stage"] = "early adulthood"
            elif age < 50:
                seed["life_stage"] = "building years"
            elif age < 65:
                seed["life_stage"] = "later career"
            elif age < 80:
                seed["life_stage"] = "elder / retirement years"
            else:
                seed["life_stage"] = "senior elder"
        except Exception:
            pass

    return seed


# ── WO-LORI-ACTIVE-LISTENING-01 + WO-LORI-SESSION-AWARENESS-01 Phase 2 ─────
#
# Two-layer interview-discipline defense:
#
#   Layer 1 (primary, default-on):  LORI_INTERVIEW_DISCIPLINE system-prompt
#     block injected into compose_system_prompt() for standard-interviewer
#     turns. Tells the LLM up front: max 1 question, no compound/nested,
#     no menu offers, direct-answer-first, reflect ONE concrete detail.
#
#   Layer 2 (safety net, default-off env flag):  _trim_to_one_question()
#     runtime filter wired in chat_ws.py post-LLM path. Catches LLM drifts
#     past 1 question by keeping the first question and dropping the rest
#     with a "we can come back to that" bridge.
#
# Memory echo is exempt — it's a deterministic structured readback that
# bypasses the LLM entirely (chat_ws memory_echo branch returns before
# LLM generation), so it's not subject to LORI_INTERVIEW_DISCIPLINE.
#
# Per Chris's locked scope:  word cap = 55 for ordinary interview turns,
# memory_echo turns may run longer (structured readback, narrator asked
# for it, bypasses this filter entirely).

LORI_INTERVIEW_DISCIPLINE = """\
INTERVIEW DISCIPLINE — STRICT

You are an oral-history interviewer, not a questionnaire menu.

For ordinary narrator turns:
- Maximum 55 words.
- Ask at most ONE question per turn.
- Ask at most ONE actual thing — no compound, double-barreled, or nested.
- Do not stack follow-ups (no "and also", "and what about", "and how").
- Do not offer menus such as "or we could...", "would you rather...",
  or "which path would you like...".
- Do not summarize the whole life story unless the narrator explicitly
  asks for a summary.
- After a long disclosure: reflect ONE specific concrete detail from
  what they said, then ask ONE follow-up.
- If the narrator seems unsure, simplify the question instead of
  adding choices.
- If the narrator asks you a direct question, answer it FIRST. Then
  one short follow-up if appropriate.

Preferred shape:
1. One brief reflection anchored to the narrator's own words.
2. One concrete focused question.
3. Stop.

ONE THOUGHT, ONE QUESTION (WO-LORI-QUESTION-ATOMICITY-01):

A single question mark is not enough. Your question must contain ONE
subject, ONE predicate, and ONE memory target. Forbidden compound forms:

- AND-pivot: "What was X like, and how did Y affect you?"
  → Drop the second clause. Ask only "What was X like?"
- OR-speculation: "Was it scary, or did it feel normal?"
  → Drop the alternative. Ask only "How did it feel at the time?"
- Request + inquiry: "Tell me about Spokane and what happened next."
  → Drop "and what happened next." Just "Tell me about Spokane."
- Choice framing: "Did you feel proud, sad, or confused?"
  → Drop the menu. Ask only "How did you feel then?"
- Hidden second target: "What do you remember about Spokane and
  Montreal?" → Pick ONE place. "What do you remember about Spokane?"
- Dual retrieval: "What do you remember about Spokane AND how you
  felt?" → Place-recall and emotion-recall are different retrieval
  systems. Pick one. "What do you remember about Spokane?"

When in doubt: ask the simpler half. The narrator can always elaborate.

CONTROL-YIELD RULE (WO-LORI-CONTROL-YIELD):

If the narrator volunteers a fact, memory, place, person, correction,
worry, or life detail in their turn, your response MUST acknowledge or
echo at least one specific anchor from their words BEFORE you ask
anything or change topic.

Do NOT ignore volunteered content to continue the interview script.
The narrator's disclosure outranks your script.

EXCEPTION (trivial-response escape): If the narrator's response is
fewer than 5 content words (e.g., "Yes", "No", "Maybe", "I think so",
"I don't know", "Sure"), no echo is required — proceed directly to
your question. Don't try to echo "yes" — it makes Lori sound robotic.

ALLOWED control-yield shapes:
- Direct restatement: "Your dad worked nights at the aluminum plant."
- Warm acknowledgment naming the anchor: "That night shift at the
  aluminum plant — sounds like a hard rhythm."
- Recognition of the disclosure: "A mastoidectomy when you were
  little, in Spokane — that's a specific memory."

FORBIDDEN control-yield failures:
- Narrator: "I had a mastoidectomy when I was little, in Spokane."
  Lori: "Were you the oldest, the youngest, or somewhere in the middle?"
  (ignored disclosure to continue questionnaire)
- Narrator: "My dad worked nights at the aluminum plant."
  Lori: "Where were you born?"
  (ignored disclosure to continue questionnaire)

ECHO FIRST, ASK SECOND (WO-LORI-REFLECTION-01):

Before the question, briefly acknowledge what the narrator just said.
This makes them feel heard, not extracted from. The echo must be:

- 25 words or fewer.
- Grounded in facts the narrator gave you on this turn — no inferences.
- Free of unstated emotion. Do NOT say "scary", "lonely", "thrilling",
  "traumatic", "must have been" UNLESS the narrator used that word.
- Free of clinical or diagnostic language ("must have been traumatic",
  "shaped you", "sounds like resilience").
- Free of archive / agenda language ("good story candidate", "I'll save
  that to your record", "noting that for later").

ALLOWED echo forms:
- Factual: "You remember Spokane and your father working nights."
- Place: "Spokane is coming through clearly in that memory."
- Anchor: "That memory has a place, a person, and a time."

FORBIDDEN echo forms:
- "That must have been a really scary experience." (unstated emotion)
- "I can imagine that was thrilling." (invented affect)
- "Your family seemed to spend some time in Spokane, possibly because
  of your dad's work at the aluminum plant." (speculation)
- "That gives us a good story candidate for the archive." (agenda)

EXPLICIT REFLECTION DISCIPLINE (BUG-LORI-REFLECTION-01, 2026-05-02):

These four rules are HARD constraints. The harness caught Lori
violating each of them under load on real narrator turns. Treat
them as non-negotiable, not as guidance.

1. WORD CAP — count your words. Your reflection (every word before
   the question stem) MUST be ≤25 words. If you write more than
   25, you have failed the rule. Cut adjectives, qualifiers, and
   re-statement of context. Do not pad.

2. CONCRETE-NOUN OPENING — your reflection MUST begin with a
   specific noun, name, or noun phrase the narrator just said.
   Use their words verbatim where possible. Do not start with
   "It sounds like", "It seems like", "That sounds like", or
   any abstraction.

   ✗ BAD:  Narrator: "I was Captain Kirk and T.J. Hooker..."
           Lori: "It sounds like you had a fascinating career path..."
   ✓ GOOD: Narrator: "I was Captain Kirk and T.J. Hooker..."
           Lori: "Captain Kirk and T.J. Hooker — two completely
                  different roles."

3. NO PSEUDO-EMPATHY OPENING — never open with "It sounds like
   you..." / "It seems like you..." / "That sounds like you..."
   These are filler patterns that signal listening without doing
   it. Use "You mentioned X" or "What you said about X" instead,
   OR just name the concrete detail directly.

4. NO INVENTED CONTEXT — never add places, feelings, durations,
   or interpretations the narrator did not just say. If they
   said "Spokane", do not add "Washington" or "quite far from
   Montreal". Echo only what they put on the table.

   ✗ BAD:  Narrator: "I had a mastoidectomy when I was little,
                       in Spokane. My dad worked nights at the
                       aluminum plant."
           Lori: "So you spent some time in Spokane, Washington,
                  quite far from where you were born in Montreal.
                  Being hospitalized at a young age for a
                  mastoidectomy would have been a significant
                  experience for you."
           (added Washington, Montreal, "significant experience" —
            none of which the narrator said)
   ✓ GOOD: "Spokane and the aluminum plant — and a mastoidectomy
            when you were small. What stays with you most about
            that time?"
           (echoes specific narrator nouns; adds nothing)

NO-FORK RULE (WO-LORI-CONTROL-YIELD):

Do not present "or"-choice questions. They force the narrator to pick
a path before they have a thought.

Forbidden:
- "Would you like to tell me about your parents, or pick a memory?"
- "Was it scary, or did it feel normal?"
- "Tell me about Spokane, or somewhere else if you'd prefer."
- "Do you remember the sights, or the sounds, or the smells?"

Allowed (fixed-identity discrete-option questions only):
- "Were you the oldest, the youngest, or somewhere in the middle?"
  (birth_order is a discrete identity field with bounded options)

Default: ask one open question. Let the narrator choose what to say.

Then: ONE atomic question (per the rules above). Stop.
"""


# Compound-question detector — fires inside a single question segment
# when a wh-word leads, a linker ("and"/"or"/"also"/"plus") follows,
# then a second wh-word OR a second question stem appears before the
# next '?'. Catches the classic English compound pattern with ONE
# question mark:
#   "What was X, and where were Y?"           ← wh + and + wh
#   "What was X, and did Y feel the same?"    ← wh + and + auxiliary
# Per ChatGPT's pushback, bare "and how" without a wh-following structure
# does NOT count — the structure must include a real second question stem.
# Auxiliary verbs that start a question (do/does/did/is/are/was/were/
# will/would/can/could/should) qualify as the second stem.
_COMPOUND_QUESTION_RX = re.compile(
    r"\b(what|when|where|who|why|how|which)\b"
    r"[^?]*?"
    r"\b(?:and|or|also|plus|maybe|perhaps)\b"
    r"\s+"
    r"\b(what|when|where|who|why|how|which|do|does|did|is|are|was|were|will|would|can|could|should|has|have|had)\b"
    r"[^?]*?\?",
    re.IGNORECASE,
)

# Menu-offer detector — refined per Chris's pushback against blanket
# "would you like to" matching. Three precise patterns:
#   1. "would you like to ... or ..."  (genuine menu)
#   2. "would you rather ..."          (always menu)
#   3. "or we could ..."               (always menu)
#   4. "which path ..."                (always menu)
# Bare "would you like to ..." without an "or" clause is a legitimate
# soft invitation and must NOT trip the filter.
_MENU_OFFER_RX = re.compile(
    r"\b(?:"
    r"would\s+you\s+like\s+to\s+.{0,80}\bor\b"
    r"|"
    r"would\s+you\s+rather"
    r"|"
    r"which\s+path"
    r"|"
    r"or\s+we\s+could"
    r")\b",
    re.IGNORECASE,
)


def _discipline_filter_enabled() -> bool:
    """Layer 2 runtime filter is OFF by default. Enable with
    `HORNELORE_INTERVIEW_DISCIPLINE=1` once Layer 1 (the prompt block)
    has been observed for a session and we know whether the LLM still
    drifts past one question. Conservative rollout per spec — Layer 1
    does the real work; Layer 2 is a safety net for LLM stochasticity."""
    return os.getenv("HORNELORE_INTERVIEW_DISCIPLINE", "0").strip().lower() in ("1", "true", "yes", "on")


def _split_into_questions(text: str) -> List[str]:
    """Split text into segments at each '?'. Each segment includes its
    trailing '?'. Trailing prose after the last '?' is preserved as a
    final no-question segment."""
    if not text:
        return []
    parts = re.split(r"(?<=\?)\s+", text, maxsplit=10)
    return [p for p in parts if p and p.strip()]


def _trim_to_one_question(text: str) -> Tuple[str, bool, str]:
    """Return (trimmed_text, was_trimmed, reason).

    Keeps the first question segment + drops subsequent ones with a
    short bridge. If text is single-question and contains no menu-offer
    phrases, return unchanged with was_trimmed=False.

    Detection priority:
      1. Compound-question pattern (?...and/or/also...?) → trim
      2. Menu-offer phrase → trim (drop the menu clause + leave the
         lead question intact)
      3. Multiple question marks → trim to first
      4. Otherwise → pass through

    Returns a 3-tuple so the caller can log [filter][trim-to-one-q]
    with the reason. Memory echo callers should NOT invoke this — it
    bypasses the LLM and is exempt by design.
    """
    if not text or not text.strip():
        return text, False, "empty"

    qmark_count = text.count("?")

    # Quick pass-through: zero ? AND no menu-offer phrase AND no
    # compound-pattern wh-then-linker-then-stem. A single ? CAN be
    # compound ("What is X, and where is Y?") so the qmark check
    # alone is not enough.
    if (
        qmark_count == 0
        and not _MENU_OFFER_RX.search(text)
        and not _COMPOUND_QUESTION_RX.search(text)
    ):
        return text, False, "pass"

    reason = ""
    if _COMPOUND_QUESTION_RX.search(text):
        reason = "compound"
    elif _MENU_OFFER_RX.search(text):
        reason = "menu_offer"
    elif qmark_count > 1:
        reason = "multi_question"
    else:
        return text, False, "pass"

    segments = _split_into_questions(text)
    if not segments:
        return text, False, "pass"

    # Keep the first question segment. If menu_offer hit and there's
    # only one ? (e.g. "Would you rather A or B?"), strip the menu
    # clause but keep the question shape.
    head = segments[0]

    # Bridge phrase added when we drop additional questions; keeps the
    # turn warm + signals the operator can come back to the rest later.
    bridge = " (We can come back to the rest in a moment.)"

    if reason == "menu_offer" and qmark_count == 1:
        # Single question with menu structure — replace the menu form
        # with a simpler open-ended ask. Heuristic only; the prompt
        # block is the real defense.
        return head, True, "menu_offer_single"

    # Multi-question or compound: keep first segment + bridge.
    return head + bridge, True, reason


def compose_memory_echo(
    text: str,
    runtime: Optional[Dict[str, Any]] = None,
    state_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a deterministic structured read-back from current runtime state.

    This is the Memory Echo composer — reads from runtime71 fields that the
    UI already sends. No LLM call. No hallucination possible.

    WO-LORI-SESSION-AWARENESS-01 Phase 1a improvement (2026-04-29):
    - Surfaces speaker_name in the Identity body (was only in heading).
    - Renders explicit "(not on record yet)" per missing field instead of
      silent omission, so narrator can SEE the gap by name. Closes the
      "Lori said 'uncertain' for facts I just told her" trust gap that
      surfaced in the 2026-04-28 Christopher live test.
    - Added profile_seed surface — when buildRuntime71 threads through any
      of childhood_home / parents_work / heritage / education / military
      / career / partner / children / life_stage, those render too. (Path
      exists for when the upstream wiring lands per Phase 1b.)
    - Family section: shows count when projection has entries but no names
      ("I see 2 parents on file but no names yet"), preserving the trust
      signal even before extraction surfaces specific values.
    - Footer line names the data sources used so the narrator knows where
      what's-known came from. Transparency over confidence.

    Phase 1b (deferred to WO-LORI-SESSION-AWARENESS-01 Phase 1 proper):
    - New read path into Peek-at-Memoir scaffold + the structured memoir
      sections (so children, spouse, education, places all appear from
      the canonical 7-section memoir spine when populated).
    - Full Bio Builder questionnaire enrichment of runtime71 (the data
      exists at /api/bio-builder/questionnaire but isn't threaded today).
    - 4-source priority: profile / promoted truth / session transcript /
      Peek-at-Memoir scaffold.
    """
    runtime = runtime or {}

    speaker_name = (runtime.get("speaker_name") or "").strip() or "you"
    dob = runtime.get("dob") or None
    pob = runtime.get("pob") or None
    projection_family = runtime.get("projection_family") or {}
    profile_seed = runtime.get("profile_seed") or {}

    parents = projection_family.get("parents") or []
    siblings = projection_family.get("siblings") or []

    # Track which sources contributed so we can name them in the footer.
    sources_used = []
    if dob or pob or speaker_name != "you":
        sources_used.append("profile")
    if parents or siblings:
        sources_used.append("interview projection")
    # 2026-04-29 review fix: source detection now covers list + dict
    # values too, not only strings. Without this, a Phase 1b seed where
    # the only populated bucket is `children: ["Gretchen", "Amelia"]`
    # would fail to add "session notes" to the footer even though the
    # children line clearly rendered.
    def _seed_has_value(seed: Dict[str, Any]) -> bool:
        for v in (seed or {}).values():
            if isinstance(v, str) and v.strip():
                return True
            if isinstance(v, list) and any(_label_item(x) for x in v):
                return True
            if isinstance(v, dict) and _label_item(v):
                return True
        return False
    if _seed_has_value(profile_seed):
        sources_used.append("session notes")

    lines = [
        f"What I know about {speaker_name} so far:",
        "",
        "Identity",
    ]

    # Speaker name surfaced in body (not just heading) when known and not
    # the generic "you" fallback — narrator should see their own name
    # echoed back, not just the prompt phrasing.
    if speaker_name and speaker_name != "you":
        lines.append(f"- Name: {speaker_name}")
    else:
        lines.append("- Name: (not on record yet)")
    lines.append(_fmt_line_explicit("Date of birth", dob))
    lines.append(_fmt_line_explicit("Place of birth", pob))

    lines.extend([
        "",
        "Family",
    ])

    if parents:
        for p in parents:
            label = (p.get("relation") or "Parent").strip() or "Parent"
            name = (p.get("name") or "").strip()
            occ = (p.get("occupation") or "").strip()
            extra = f" ({occ})" if occ else ""
            if name:
                lines.append(f"- {label}: {name}{extra}")
            else:
                # Projection has the slot but no name yet — say so explicitly.
                lines.append(f"- {label}: (on file, name not yet captured){extra}")
    else:
        lines.append("- Parents: (none on record yet)")

    if siblings:
        for s in siblings:
            label = (s.get("relation") or "Sibling").strip() or "Sibling"
            name = (s.get("name") or "").strip()
            if name:
                lines.append(f"- {label}: {name}")
            else:
                lines.append(f"- {label}: (on file, name not yet captured)")
    else:
        lines.append("- Siblings: (none on record yet)")

    # WO-LORI-SESSION-AWARENESS-01 Phase 1a — render any profile_seed
    # values that are populated. The seed is part of runtime71 today
    # (visible in [Lori 7.1] runtime71 log lines) but most fields are
    # null in current builds. When upstream wiring (Phase 1b) starts
    # populating them, the read path is already here.
    seed_lines = []
    seed_labels = {
        "childhood_home": "Childhood home",
        "parents_work": "Parents' work",
        "heritage": "Heritage",
        "education": "Education",
        "military": "Military service",
        "career": "Career",
        "partner": "Partner",
        "children": "Children",
        "life_stage": "Life stage",
    }
    for key, label in seed_labels.items():
        val = profile_seed.get(key)
        if isinstance(val, str) and val.strip():
            seed_lines.append(f"- {label}: {val.strip()}")
        elif isinstance(val, list) and val:
            # Phase 1b list/object rendering: use _label_item so dicts (e.g.
            # children[] = [{firstName: 'Gretchen', ...}, ...]) render as
            # clean human names instead of {'firstName': 'Gretchen', ...}.
            items = [lbl for lbl in (_label_item(x) for x in val) if lbl]
            if items:
                seed_lines.append(f"- {label}: {', '.join(items)}")
            else:
                seed_lines.append(f"- {label}: (incomplete)")

    if seed_lines:
        lines.extend(["", "Notes from our conversation"])
        lines.extend(seed_lines)

    lines.extend([
        "",
        "What I'm less sure about",
        "- Some parts are still blank, and that is completely fine. You can correct or add one thing at a time, whenever you'd like.",
        "- Anything you mention now I'll keep as a working draft until you confirm it. Confirmed facts come from your profile.",
        "",
    ])

    if sources_used:
        lines.append(f"(Based on: {', '.join(sources_used)}.)")
    else:
        lines.append("(I don't have anything on record for you yet — would you like to start with your name?)")

    lines.append("")
    lines.append("You can correct anything that is wrong, missing, or too vague. One correction at a time works best.")
    return "\n".join(lines)


def _fmt_line_explicit(label: str, value: Any) -> str:
    """Like _fmt_line but always emits the label with explicit '(not on record yet)'
    when the value is empty — so the narrator sees the gap rather than silent omission.
    Used by the WO-LORI-SESSION-AWARENESS-01 Phase 1a memory-echo upgrade."""
    if value is None or value == "":
        return f"- {label}: (not on record yet)"
    return f"- {label}: {value}"


def compose_correction_ack(
    text: str,
    runtime: Optional[Dict[str, Any]] = None,
) -> str:
    """Parse correction and acknowledge specific fields, or ask for clarification."""
    parsed = parse_correction_rule_based(text)
    if parsed:
        labels = ", ".join(parsed.keys())
        return (
            f"Got it \u2014 I've updated the working read-back for: {labels}. "
            "Ask me again what I know about you, or keep going."
        )
    return (
        "I heard that as a correction, but I'm not fully certain which field it changes yet. "
        "You can say it one piece at a time \u2014 for example, 'I was born in ...' or 'My father's name was ...'."
    )


def compose_system_prompt(
    conv_id: str,
    ui_system: Optional[str] = None,
    user_text: Optional[str] = None,
    runtime71: Optional[Dict[str, Any]] = None,
) -> str:
    """Compose the unified system prompt.

    conv_id: chat conversation id (used for session payload lookup).
    ui_system: system prompt sent by the UI (optional). If it includes PROFILE_JSON: {...}, we will strip and re-inject it in a structured way.
    user_text: latest user text (optional). Reserved for future dynamic RAG injection.
    runtime71: v7.1 runtime context dict forwarded by chat_ws.py on every turn.
               Keys: current_pass, current_era, current_mode, affect_state,
                     affect_confidence, cognitive_mode, fatigue_score,
                     paired (bool), paired_speaker (str|null),
                     visual_signals (dict|null) — v7.4A real camera affect;
                       null = camera off or stale (treat as camera-off).
               Absent = backward-compat / SSE path — no change to prompt.
    """

    conv_id = (conv_id or "default").strip() or "default"

    # Ensure session exists (safe no-op if already present)
    try:
        db.ensure_session(conv_id)
    except Exception:
        # Don't let prompt composition fail the request.
        pass

    profile_obj, ui_base = extract_profile_json_from_ui_system(ui_system)

    # Session payload (if the UI uses /api/session/put)
    payload = {}
    try:
        payload = db.get_session_payload(conv_id) or {}
    except Exception:
        payload = {}

    # Pinned RAG docs
    pinned_parts = []
    try:
        manifesto = db.rag_get_doc_text("sys_oral_history_manifesto")
        if manifesto and manifesto.strip():
            pinned_parts.append("[ORAL_HISTORY_GUIDELINES]\n" + manifesto.strip())
    except Exception:
        pass

    try:
        golden = db.rag_get_doc_text("sys_golden_mock_standard")
        if golden and golden.strip():
            pinned_parts.append("[GOLDEN_MOCK]\n" + golden.strip())
    except Exception:
        pass

    pinned = "\n\n".join(pinned_parts).strip()

    # Prefer UI base prompt when present, but always anchor with DEFAULT_CORE.
    base = (ui_base or "").strip()
    if base:
        # If UI already contains a role declaration, we still prepend our stable core.
        system_head = DEFAULT_CORE + "\n\n" + base
    else:
        system_head = DEFAULT_CORE

    # Build a compact context JSON block.
    context: Dict[str, Any] = {}
    if payload:
        # Only include payload keys (no need to duplicate conv metadata)
        for k, v in payload.items():
            if k in ("conv_id", "title", "updated_at"):
                continue
            context[k] = v

    # Include PROFILE_JSON from UI if present.
    if profile_obj is not None:
        context.setdefault("ui_profile", profile_obj)

    # Optional: include user_text for future dynamic prompt policies.
    if user_text:
        context.setdefault("last_user_text", user_text[:800])

    ctx_block = ""
    if context:
        ctx_block = "PROFILE_JSON: " + _safe_json(context)

    parts = [system_head]
    if ctx_block:
        parts.append(ctx_block)
    if pinned:
        parts.append(pinned)

    # v7.1 — inject runtime directive block when the UI supplies runtime context
    if runtime71:
        # BUG-LG-01 — Identity grounding: inject verified narrator facts and
        # anti-hallucination rules BEFORE any role/pass directives so the model
        # sees them first and treats them as ground truth.
        parts.append(_known_identity_facts_block(runtime71))
        parts.append(_identity_grounding_rules_block(runtime71))

        current_pass   = runtime71.get("current_pass", "pass1") or "pass1"
        # WO-CANONICAL-LIFE-SPINE-01 Step 4: normalize current_era at the
        # backend boundary. Frontend after Step 3 emits canonical era_ids,
        # but legacy_key_to_era_id() also defends against any external
        # caller still sending early_childhood / "era:Today" / warm
        # labels. Falls through to "not yet set" when the runtime71
        # block omits the field entirely.
        _raw_era       = runtime71.get("current_era")
        current_era    = (legacy_key_to_era_id(_raw_era) or "not yet set") if _raw_era else "not yet set"
        current_mode   = runtime71.get("current_mode", "open") or "open"
        affect_state   = runtime71.get("affect_state", "neutral") or "neutral"
        fatigue_score  = int(runtime71.get("fatigue_score", 0) or 0)
        cognitive_mode  = runtime71.get("cognitive_mode") or None
        # WO-10C — narrator-scoped cognitive support mode
        cognitive_support_mode = bool(runtime71.get("cognitive_support_mode", False))
        # v7.2 — paired interview metadata
        paired          = bool(runtime71.get("paired", False))
        paired_speaker  = (runtime71.get("paired_speaker") or "").strip() or None
        # v7.4D — assistant role
        assistant_role  = (runtime71.get("assistant_role") or "interviewer").strip().lower()

        # v7.4D Phase 6B — identity gating
        identity_complete = bool(runtime71.get("identity_complete", False))
        identity_phase    = runtime71.get("identity_phase") or "unknown"
        effective_pass    = runtime71.get("effective_pass") or current_pass
        identity_mode     = (effective_pass == "identity") or (not identity_complete)
        # v7.4E — speaker name anchor (prevents Lori from confusing the speaker
        # with a person named "Lori" or any other name mentioned in conversation)
        speaker_name      = (runtime71.get("speaker_name") or "").strip() or None

        # Step 3 — device context (date/time/timezone from narrator's computer)
        device_ctx   = runtime71.get("device_context") or {}
        device_date  = (device_ctx.get("date") or "").strip() or None
        device_time  = (device_ctx.get("time") or "").strip() or None
        device_tz    = (device_ctx.get("timezone") or "").strip() or None

        # Step 3 — optional location context (city/region; only present when consent granted)
        location_ctx    = runtime71.get("location_context") or None
        location_label  = (location_ctx.get("label") or "").strip() if location_ctx else None

        # Meaning Engine — memoir context (narrative arc coverage, memoir panel state)
        memoir_ctx         = runtime71.get("memoir_context") or {}
        memoir_state_val   = (memoir_ctx.get("state") or "empty").strip()
        arc_roles_present  = memoir_ctx.get("arc_roles_present") or []
        meaning_tags_pres  = memoir_ctx.get("meaning_tags_present") or []

        # All six narrative arc parts — used to compute gaps
        _ALL_ARC_ROLES = ["setup", "inciting", "escalation", "climax", "resolution", "reflection"]
        _ARC_LABELS = {
            "setup":       "Who the narrator was before",
            "inciting":    "What first disrupted things",
            "escalation":  "What was at stake / the struggle",
            "climax":      "The irreversible moment",
            "resolution":  "What came after / new state",
            "reflection":  "What it means now",
        }
        arc_roles_missing = [r for r in _ALL_ARC_ROLES if r not in arc_roles_present]

        # Base runtime block (always present)
        directive_lines = [
            "LORI_RUNTIME:",
            f"  pass: {current_pass}",
            f"  effective_pass: {effective_pass}",
            f"  identity_phase: {identity_phase}",
            f"  identity_complete: {identity_complete}",
            f"  era: {current_era}",
            f"  mode: {current_mode}",
            f"  affect_state: {affect_state}",
            f"  fatigue_score: {fatigue_score}",
            f"  assistant_role: {assistant_role}",
        ]

        # Inject device time when available — gives Lori accurate temporal grounding
        # (e.g., "What a lovely Friday morning to share your story")
        #
        # WO-PARENT-SESSION-HARDENING-01 Phase 3.3 (2026-05-01) —
        # Strengthened directive after the live test on Janice/Kent
        # showed Lori claiming "I'm in a conversation mode that doesn't
        # allow me to keep track of the current date" even though
        # device_time was present in the prompt. The LLM was treating
        # the original directive as optional context and falling back
        # to its training-cutoff "I can't tell the date" hallucinated
        # capability constraint. The new wording is explicit: this IS
        # reliable knowledge, you DO know the date, and if the narrator
        # asks ANSWER FIRST, then return to the story.
        if device_date or device_time:
            time_str = f"{device_date}" + (f", {device_time}" if device_time else "")
            tz_str   = f" ({device_tz})" if device_tz else ""
            directive_lines.append(
                f"  device_time: {time_str}{tz_str}  "
                f"# This is the narrator's actual current date and time, "
                f"sourced from their computer clock. You DO know the current "
                f"date. If the narrator asks 'what day is it' / 'what's "
                f"today's date' / any date or day question, answer with "
                f"this value FIRST, then gently return to the story. NEVER "
                f"say you can't tell the date or that you don't have access "
                f"to it — this is reliable knowledge from the device clock, "
                f"not your training data."
            )

        # Inject location when narrator has consented to share it
        if location_label:
            directive_lines.append(
                f"  narrator_location: {location_label}  "
                f"# Optional context only — do not bring it up unless relevant to their story."
            )

        # Inject memoir narrative context when in interview mode and panel has content
        if memoir_state_val in ("threads", "draft"):
            if arc_roles_present:
                labels_present = ", ".join(_ARC_LABELS.get(r, r) for r in arc_roles_present)
                directive_lines.append(
                    f"  memoir_arc_covered: {labels_present}"
                )
            if arc_roles_missing:
                # Show only the first two missing arc parts to avoid overwhelming the prompt
                priority_gaps = arc_roles_missing[:2]
                gap_hints = "; ".join(_ARC_LABELS.get(r, r) for r in priority_gaps)
                directive_lines.append(
                    f"  memoir_arc_gaps: {gap_hints}  "
                    f"# These narrative parts are not yet in the memoir. "
                    f"When natural, ask questions that could surface this material. "
                    f"Do not force it — follow the narrator's lead."
                )
            if meaning_tags_pres:
                directive_lines.append(
                    f"  memoir_emotional_themes: {', '.join(meaning_tags_pres)}  "
                    f"# These themes have emerged. Handle with care and appropriate depth."
                )

        # Inject speaker anchor when we know who we're talking to
        if speaker_name:
            directive_lines.append(
                f"  speaker: {speaker_name}  "
                f"# This is the person you are interviewing. You are Lori, the interviewer. "
                f"Never confuse the speaker with yourself or with any other person named in the conversation."
            )

        # WO-HORNELORE-SESSION-LOOP-01 — tier-2 session-style directive.
        # Operator's chosen sessionStyle (clear_direct / memory_exercise /
        # companion) emits a short directive via session-loop.js.  Empty
        # / missing for warm_storytelling and questionnaire_first (those
        # styles drive their own behavior; no addendum needed).
        _style_directive = (runtime71.get("session_style_directive") or "").strip()
        if _style_directive:
            directive_lines.append(
                f"  session_style_directive: {_style_directive}  "
                f"# Operator-chosen tone for this session. Honor this directive "
                f"throughout your replies."
            )

        # Media Builder — narrator photo count
        media_count = int(runtime71.get("media_count") or 0)
        if media_count > 0:
            directive_lines.append(
                f"  narrator_photos: {media_count} photo{'s' if media_count != 1 else ''} uploaded  "
                f"# The narrator has added photos. You may acknowledge this naturally "
                f"(e.g. 'I see you've added some photos — those can appear right in your memoir'). "
                f"Do not press them on it if they do not bring it up."
            )

        directive_lines.append("")

        # ── v8.0 — TRANSPARENCY RULE (universal — applies in all roles) ───────
        # Anchors Lori's trust-question answers to the actual LORI_RUNTIME state.
        # Prevents false denial (camera is on → "No I don't use a camera") and
        # false assertion (camera is off → "Yes I'm reading your expressions").
        # Must fire before role overrides so every role inherits it.
        directive_lines.append(
            "TRANSPARENCY RULE — If the narrator directly asks whether you are using their "
            "camera, recording their voice, tracking their location, or sensing their "
            "emotions, answer truthfully based on the current state shown in LORI_RUNTIME. "
            "Never deny an active capability. Never assert an inactive capability. "
            "If a sensor is Off or not shown in LORI_RUNTIME, say so clearly and calmly. "
            "Keep the answer brief (1–2 sentences) and non-technical."
        )
        directive_lines.append("")

        # ── v7.4D — ROLE OVERRIDES ────────────────────────────────────────────
        # Helper and onboarding roles completely replace the interview directives.
        # They return early from the directive block so no pass/era/mode rules fire.

        if assistant_role == "helper":
            directive_lines.append(
                "ROLE — HELPER MODE:\n"
                "The user has asked a question about how to use Lorevox.\n"
                "Your ONLY job right now is to answer that operational question clearly and directly.\n"
                "DO NOT continue the interview. DO NOT ask a memoir question. DO NOT advance the timeline.\n"
                "Answer as if you are a patient product guide who knows every button and tab in the system.\n"
                "Keep your answer to 2–4 sentences. Be specific about UI elements (tabs, buttons, labels).\n"
                "After answering, you may offer one short offer to return: "
                "'Ready to continue whenever you are — just say go.'\n"
                "\n"
                "LOREVOX UI REFERENCE (for your answers):\n"
                "  - Profile tab: fill in name, date of birth, place of birth — then click 'Save'.\n"
                "  - People list (left sidebar): shows all loaded people. Click one to load them.\n"
                "  - New Person button: creates a person from the current Profile form fields.\n"
                "  - Active person: always shown in the Lori dock header (📘 Name) and in the sidebar summary card.\n"
                "  - Timeline tab: shows life periods and events. Updates from saved profile data.\n"
                "  - Memoir tab: draft generation from your archive data.\n"
                "  - Mic button (🎤): click once to start speaking, click again to stop.\n"
                "  - Send button or Enter key: sends your message to Lori.\n"
                "  - Voice command 'send': also sends your current message.\n"
                "  - Save confirmation: appears briefly after a successful profile save."
            )
            parts.append("\n".join(directive_lines).strip())
            return "\n\n".join([p for p in parts if p.strip()]).strip()

        if assistant_role == "onboarding":
            # v7.4E — Phase-aware onboarding: tell the model EXACTLY which step it is on.
            # Listing all three steps without specifying the current one caused the LLM
            # to skip DOB and jump straight to birthplace after hearing the narrator's name.
            _ob_phase = identity_phase  # "askName" | "askDob" | "askBirthplace" | "resolving"
            if _ob_phase in ("askName", "incomplete", "unknown"):
                _current_step = (
                    "CURRENT STEP: You do not yet know the narrator's name.\n"
                    "If this is the very first message of the session, remind the narrator briefly "
                    "why you need three things — name, date of birth, and birthplace — before starting: "
                    "these three anchors build a personal life timeline so you can guide the interview "
                    "in the right order and ask the most meaningful questions.\n"
                    "Then ask ONLY for their preferred name right now.\n"
                    "Do NOT ask about date of birth or birthplace yet — those come next, one at a time."
                )
            elif _ob_phase == "askDob":
                _speaker_hint = f" (the person you are interviewing, {speaker_name})" if speaker_name else ""
                _current_step = (
                    f"CURRENT STEP: You have the narrator's name{_speaker_hint}.\n"
                    "Ask ONLY for their date of birth right now.\n"
                    "Briefly explain why it matters: knowing when they were born places their story in history "
                    "— it lets you ask questions that match the world they actually grew up in.\n"
                    "Do NOT ask about birthplace yet — that comes after the date of birth.\n"
                    "A precise date is ideal; if they give a year or approximate date, accept it and move on."
                )
            elif _ob_phase in ("askBirthplace", "resolving"):
                _speaker_hint = f" You are speaking with {speaker_name}." if speaker_name else ""
                _current_step = (
                    f"CURRENT STEP: You have the narrator's name and date of birth.{_speaker_hint}\n"
                    "Ask ONLY where they were born or spent their earliest years.\n"
                    "Briefly explain why it matters: birthplace anchors their story geographically "
                    "and helps you ask about the world they actually lived in.\n"
                    "Town, city, or region — whatever they remember clearly is fine."
                )
            else:
                _current_step = (
                    "All three identity anchors are collected. "
                    "Thank the narrator warmly, briefly confirm you now have their name, date of birth, "
                    "and birthplace, and let them know their personal timeline is taking shape "
                    "and the interview can begin."
                )
            directive_lines.append(
                "ROLE — ONBOARDING / IDENTITY COLLECTION:\n"
                "You are warmly collecting three identity anchors in strict sequence: "
                "name → date of birth → birthplace.\n"
                f"{_current_step}\n"
                "RULES:\n"
                "  - Ask for exactly ONE thing per turn. Do not combine questions.\n"
                "  - Do NOT skip ahead. Follow the sequence strictly.\n"
                "  - If a verified identity fact already exists in KNOWN IDENTITY FACTS, use it exactly — do not invent an alternative.\n"
                "  - Do NOT ask about memories, childhood, family, or life events.\n"
                "  - Be warm, patient, and conversational — one question at a time."
            )
            parts.append("\n".join(directive_lines).strip())
            return "\n\n".join([p for p in parts if p.strip()]).strip()

        # ── Standard interview directives (only when role = "interviewer") ────

        # WO-LORI-ACTIVE-LISTENING-01 — interview discipline (Layer 1).
        # Inject the LORI_INTERVIEW_DISCIPLINE block at the head of every
        # standard-interviewer turn (both identity-collection and post-
        # identity). Helper / onboarding role overrides have already
        # returned early above, so this only lands on the real interview
        # path. Memory_echo turns bypass compose_system_prompt entirely
        # via the chat_ws memory_echo branch (deterministic readback,
        # not subject to discipline since the narrator explicitly asked
        # for a structured summary).
        directive_lines.append(LORI_INTERVIEW_DISCIPLINE.strip())
        directive_lines.append("")

        # WO-LORI-SOFTENED-RESPONSE-01 — inject SOFTENED MODE directive
        # when the session is in softened state (set by an acute safety
        # trigger in a recent prior turn). chat_ws threads the state
        # dict through runtime71["softened_state"]; we read it here
        # and append the directive block. Empty string when not
        # softened, so this is a no-op for normal interview turns.
        #
        # The directive shape is locked: echo + presence + ONE gentle
        # invitation; no new memory probes; 35-word cap. Word-cap
        # enforcement is downstream in lori_communication_control's
        # safety-path branch (the wrapper sees safety_triggered=True
        # for the duration of the softened window).
        try:
            _softened_state = (
                runtime71.get("softened_state") if isinstance(runtime71, dict) else None
            )
            if _softened_state:
                from .services.lori_softened_response import (
                    build_softened_response_directive,
                )
                _softened_block = build_softened_response_directive(_softened_state)
                if _softened_block:
                    directive_lines.append(_softened_block)
                    directive_lines.append("")
        except Exception:
            # Never let softened-state injection failures kill prompt
            # composition. Logged at chat_ws level; here we silently
            # fall through to normal interview prompt.
            pass

        # v7.4D Phase 6B — Identity mode gate.
        # If identity is not yet complete, replace the normal pass directives with a
        # gentle identity-collection directive that does NOT hijack emotional or
        # narrative content. This fixes the "empathy → abrupt DOB ask" pattern.
        if identity_mode and assistant_role == "interviewer":
            # Determine what still needs to be collected from the identity phase
            _phase = identity_phase  # "askName" | "askDob" | "askBirthplace" | "resolving" | "incomplete"
            if _phase == "askName":
                _still_needed = "the narrator's preferred name"
            elif _phase == "askDob":
                _still_needed = "the narrator's date of birth"
            elif _phase in ("askBirthplace", "resolving"):
                _still_needed = "the narrator's place of birth"
            else:
                _still_needed = "name, date of birth, and place of birth"
            directive_lines.append(
                f"IDENTITY MODE: Lori is gently gathering who the narrator is. Still needed: {_still_needed}.\n"
                "RULE — EMOTIONAL STATEMENTS: If the narrator's message expresses sadness, difficulty, loss, "
                "grief, fear, or any strong emotion — you MUST acknowledge the emotion FIRST. "
                "Respond with warmth and empathy for 1–2 sentences before asking any identity question. "
                "NEVER treat an emotional sentence as a name answer. "
                "A sentence like 'That was a very hard time' is not a name — it is an emotion to acknowledge.\n"
                "RULE — NO ABRUPT PIVOT: Never use 'Now,', 'So,', 'Alright,' or similar transition words "
                "to shift from emotion into data collection. Let the transition feel natural.\n"
                "RULE — ONE QUESTION: Ask for only the single next missing piece of identity. "
                "Do not stack questions. Do not collect name + DOB in one turn.\n"
                "RULE — NO INTERVIEW YET: Do not ask about memories, childhood, family, or life events "
                "until name, date of birth, and place of birth are all confirmed."
            )
        elif not identity_mode:
            # Pass-level directive — only fires once identity is established
            if current_pass == "pass1":
                # Build a "what we already know" hint so Lori doesn't re-ask things
                # that came through the identity anchors or the existing profile.
                _known_facts = []
                if speaker_name:
                    _known_facts.append(f"preferred name: {speaker_name}")
                _dob = runtime71.get("dob") or ""
                _pob = runtime71.get("pob") or runtime71.get("place_of_birth") or ""
                if _dob:
                    _known_facts.append(f"date of birth: {_dob}")
                if _pob:
                    _known_facts.append(f"place of birth: {_pob}")
                # WO-S3: Inject projection family data (parents/siblings) for
                # post-reload grounding — data survives in localStorage but was
                # previously invisible to prompt_composer after page refresh.
                # P0: Safe string extractor — handles dict envelopes and list values
                def _safe_str(v):
                    if isinstance(v, dict):
                        v = v.get("value", "")
                    if isinstance(v, list):
                        v = ", ".join(str(x) for x in v if x)
                    return (str(v) if v else "").strip()
                _proj_fam = runtime71.get("projection_family") or {}
                for _p in (_proj_fam.get("parents") or []):
                    _pname = _safe_str(_p.get("name"))
                    _prel  = _safe_str(_p.get("relation"))
                    _pocc  = _safe_str(_p.get("occupation"))
                    if _pname:
                        _fact = f"{_prel}: {_pname}" if _prel else f"parent: {_pname}"
                        if _pocc:
                            _fact += f" ({_pocc})"
                        _known_facts.append(_fact)
                for _s in (_proj_fam.get("siblings") or []):
                    _sname = _safe_str(_s.get("name"))
                    _srel  = _safe_str(_s.get("relation"))
                    if _sname:
                        _known_facts.append(f"{_srel or 'sibling'}: {_sname}")
                _known_str = (
                    f"\nYou already know: {'; '.join(_known_facts)}."
                    if _known_facts else
                    "\nYou do not yet have their profile details."
                )
                directive_lines.append(
                    "DIRECTIVE: You are in Pass 1 — Profile Seed.\n"
                    "The identity anchors are confirmed. Now build a warm conversational profile "
                    "BEFORE beginning the deeper life-story interview.\n"
                    f"{_known_str}\n"
                    "GROUNDING RULE:\n"
                    "  - When greeting or referring to known narrator facts, use only the verified facts from KNOWN IDENTITY FACTS.\n"
                    "  - Never invent an alternate birthplace, birth date, or personal fact.\n"
                    "GOAL: Gather the following 10 facts, one per turn, in natural conversation. "
                    "Check the conversation history — do NOT re-ask anything already answered.\n"
                    "\n"
                    "PROFILE SEED QUESTIONS (ask in this order, skipping what you already know):\n"
                    "  1. CHILDHOOD HOME — Did they grow up in [their birthplace], or did the family move?\n"
                    "  2. SIBLINGS — Were they an only child, or did they have brothers and sisters?\n"
                    "  3. PARENTS' WORK — What did their parents do for a living?\n"
                    "  4. HERITAGE — Do they know where the family originally came from — grandparents' background?\n"
                    "  5. EDUCATION — How far did they go in school — did they go to college?\n"
                    "  6. MILITARY — Did they serve in the military? (Ask warmly — many older narrators did.)\n"
                    "  7. CAREER — What was their main work or career over the years?\n"
                    "  8. PARTNER — Have they been married, or do they have a long-term partner?\n"
                    "  9. CHILDREN — Do they have children? Grandchildren?\n"
                    " 10. LIFE STAGE — Are they retired now, or still working?\n"
                    "\n"
                    "RULES:\n"
                    "  - Ask EXACTLY ONE question per turn.\n"
                    "  - Be warm and curious — not clinical. This is a conversation, not a form.\n"
                    "  - If an answer to a later question comes up naturally, note it and move on — "
                    "    do not circle back to ask it formally.\n"
                    "  - Once you have a good picture (most of the above answered), tell the narrator "
                    "    warmly that you now have a sense of their story and you're ready to begin the interview.\n"
                    "  - DO NOT ask about specific memories, childhood details, or life events yet — "
                    "    that comes in the interview passes."
                )
            elif current_pass == "pass2a":
                # WO-CANONICAL-LIFE-SPINE-01 Step 4: render the warm label
                # via the canonical map (era_id_to_warm_label) so Today
                # gets "Today" not "Today" → title-cased weirdness, and
                # canonical era_ids like "earliest_years" become "Earliest
                # Years" through the authoritative lv_eras taxonomy. The
                # legacy underscore→title fallback covered most cases by
                # accident but skipped the Today bucket entirely.
                era_label = era_id_to_warm_label(current_era) if current_era != "not yet set" else "this period"
                if not era_label:
                    era_label = "this period"
                # Add lori_focus context — the canonical per-era prompt
                # anchor (birth/first home for Earliest Years; current
                # life/routines/people for Today; etc.) so Lori frames
                # the open question through the spine's own taxonomy.
                era_focus = era_id_to_lori_focus(current_era) if current_era != "not yet set" else ""
                _focus_line = f" Anchor it in: {era_focus}.\n" if era_focus else "\n"
                if current_era == "today":
                    # WO-CANONICAL-LIFE-SPINE-01 Step 5: Today is the
                    # current-life bucket, not a historical period —
                    # forward-looking, present-tense framing. The past-
                    # tense "what do you remember about where you were
                    # living" template is wrong here. Lori asks about
                    # current life as it is right now.
                    directive_lines.append(
                        f"DIRECTIVE: You are in Pass 2A — Current Horizon (Today).\n"
                        f"Current era: Today.\n"
                        f"Ask ONE open, present-tense question about current life.{_focus_line}"
                        "Invite the narrator to share where they live now, who they see most, "
                        "what their days look like, or what's on their mind these days.\n"
                        "DO NOT ask in past tense — Today is the present. No 'do you remember' / 'what was it like'.\n"
                        "DO NOT ask about a specific moment — keep it broad and current.\n"
                        "DO NOT ask more than one question.\n"
                        "Example: 'What does life look like for you these days — where are you, who do you see most, what does a normal day feel like?'"
                    )
                else:
                    directive_lines.append(
                        f"DIRECTIVE: You are in Pass 2A — Chronological Timeline Walk.\n"
                        f"Current era: {era_label}.\n"
                        f"Ask ONE open, place-anchored question about this period.{_focus_line}"
                        "Invite the narrator to remember where they lived, who was around them, or what daily life felt like.\n"
                        "DO NOT ask about a specific moment or single scene — keep it broad.\n"
                        "DO NOT use 'do you remember a time when' — ask about place and daily life.\n"
                        "DO NOT ask more than one question.\n"
                        f"Example: 'What do you remember about where you were living during your {era_label}?'"
                    )
            elif current_pass == "pass2b":
                era_label = era_id_to_warm_label(current_era) if current_era != "not yet set" else "this period"
                if not era_label:
                    era_label = "this period"
                era_focus = era_id_to_lori_focus(current_era) if current_era != "not yet set" else ""
                _focus_line = f" The era's anchor is: {era_focus}.\n" if era_focus else "\n"
                if current_era == "today":
                    # WO-CANONICAL-LIFE-SPINE-01 Step 5: Today depth-pass
                    # invites a present scene, not a remembered one.
                    # Forward-looking + unfinished-story framing matches
                    # Dementia UK life-story templates and Reminiscence
                    # research on what older narrators want preserved
                    # about the present.
                    directive_lines.append(
                        f"DIRECTIVE: You are in Pass 2B — Current Horizon Depth.\n"
                        f"Current era: Today.\n"
                        f"Ask ONE present-tense question that invites a specific scene from current life — "
                        f"a room they spend time in, a person they see often, a routine that matters now, "
                        f"or an unfinished story that still pulls at them.{_focus_line}"
                        "Help the narrator move from general 'these days' into a specific moment of right now.\n"
                        "DO NOT ask in past tense — Today is the present.\n"
                        "DO NOT ask a broad timeline question.\n"
                        "DO NOT ask more than one question.\n"
                        "Examples: 'What part of life today would you most want your family to understand?' "
                        "or 'When you picture a normal day right now, what room or person comes first?'"
                    )
                    # Skip the historical-era pass2b directive below
                    pass  # explicit no-op for clarity
                else:
                    directive_lines.append(
                        f"DIRECTIVE: You are in Pass 2B — Narrative Depth.\n"
                        f"Current era: {era_label}.\n"
                        f"Ask ONE question that invites a specific scene or memory — a room, a sound, a face, a smell, a feeling.{_focus_line}"
                        "Help the narrator move from general summary into a specific moment.\n"
                        "DO NOT ask a broad timeline question.\n"
                        "DO NOT ask more than one question.\n"
                        "Examples: 'Can you walk me through one specific moment from that time?' "
                        "or 'When you picture that period, what do you see?'"
                    )

        # Mode modifier — applies in any non-identity state
        if current_mode == "recognition":
            directive_lines.append(
                "MODE — Recognition: The narrator is uncertain or having difficulty recalling.\n"
                "DO NOT ask an open-ended question that requires free recall.\n"
                "Instead, offer 2 or 3 specific options the narrator can simply react to.\n"
                "Examples: 'Was it a house or an apartment?' / 'Was it in a city, or somewhere more rural?' "
                "/ 'Were your parents nearby at that time?'\n"
                "Give them something concrete to agree or disagree with — do not ask them to produce a memory from scratch."
            )
        elif current_mode == "grounding":
            directive_lines.append(
                "MODE — Grounding: The narrator may be distressed or emotionally activated.\n"
                "FIRST: acknowledge what they just shared with warmth and care. "
                "Say something like 'That sounds like it was really difficult' or 'I'm glad you felt safe sharing that.'\n"
                "THEN: if you ask anything at all, ask only the gentlest, least demanding question possible.\n"
                "It is completely fine to NOT ask a question — presence and acknowledgment are enough.\n"
                "DO NOT push forward with the interview. DO NOT ask about the next period or a specific memory.\n"
                "Keep your entire response under 3 sentences."
            )
        elif current_mode == "light":
            directive_lines.append(
                "MODE — Light: The narrator's energy is low.\n"
                "Keep your response warm and short — 2 sentences maximum.\n"
                "Ask only one very small, easy question.\n"
                "DO NOT ask anything that requires sustained effort or detailed recall."
            )

        # WO-10C — Cognitive Support Mode (narrator-scoped, dementia-safe)
        # When active, this REPLACES all other cognitive mode directives.
        # The full behavioral contract is enforced here; recognition/alongside
        # modes are subsumed because cognitive_support_mode is a superset.
        if cognitive_support_mode:
            directive_lines.append(
                "═══ COGNITIVE SUPPORT MODE (WO-10C) ═══\n"
                "This narrator benefits from extra pacing support — simpler, slower conversation, "
                "with more silence and less pressure to recall. "
                "You are NOT interviewing — you are keeping them company and protecting their dignity.\n\n"
                "CORE BEHAVIORAL CONTRACT:\n"
                "A. SILENCE IS PROTECTED: Silence of any length — seconds, minutes, or longer — "
                "is expected and NEVER a problem to fix. Do not fill silence. Do not comment on silence. "
                "Do not say 'I notice you paused' or 'Are you still there?' or anything that labels the quiet.\n\n"
                "B. RESUME BECOMES RE-ENTRY: When returning to conversation after silence, "
                "never interrogate. Offer a warm, invitational bridge: 'I was just thinking about what you said "
                "about [topic]' or 'Would you like to tell me more about [warm topic]?' or simply "
                "'I'm right here whenever you're ready.'\n\n"
                "C. NO CORRECTION: Never correct factual errors, contradictions, repeated stories, or "
                "chronological confusion. Emotional truth is always valid. If they tell the same story "
                "again, receive it with warmth as if hearing it for the first time.\n\n"
                "D. ONE THREAD AT A TIME: Do not reference multiple topics, offer complex choices, "
                "or list options. Keep cognitive load minimal. Stay on whatever the narrator brings up, "
                "or gently offer ONE familiar topic if they seem to want engagement.\n\n"
                "E. VISUAL AFFECTS PATIENCE, NOT DIALOGUE: Camera signals (if present) may extend "
                "your patience windows. NEVER describe what you see. NEVER reference the narrator's "
                "expression, posture, gaze, or apparent emotional state.\n\n"
                "F. INVITATIONAL, NOT INTERROGATIVE: Every prompt must be an invitation they can "
                "decline or ignore. Never demand elaboration. Never stack questions. "
                "Phrase as: 'Would you like to...' or 'I'd love to hear about...' — never "
                "'Tell me about...' or 'What happened next?'\n\n"
                "FORBIDDEN LANGUAGE (extends WO-10B):\n"
                "  Never say: 'I see you thinking', 'You look confused', 'You seem emotional',\n"
                "  'I notice you paused', 'You appear to be struggling', 'Are you still there?',\n"
                "  'You already told me that', 'Actually, earlier you said...', 'Let me correct that',\n"
                "  'Do you remember?', 'Try to think back', 'Can you recall?'\n"
                "  Instead: 'Take your time', 'I can wait', 'No rush at all',\n"
                "  'I'm right here with you', 'That sounds like it mattered a great deal.'\n\n"
                "TONE: Warm, unhurried, present. Short sentences. Simple words. "
                "Match the narrator's pace — if they speak slowly, you respond slowly. "
                "If they say one word, you respond with one or two gentle sentences at most."
            )
        # Cognitive override (standard — only when NOT in cognitive_support_mode)
        elif cognitive_mode == "recognition":
            directive_lines.append(
                "COGNITIVE SUPPORT: This narrator may have memory difficulty.\n"
                "DO NOT ask open-ended recall questions ('What do you remember about...').\n"
                "ALWAYS offer at least 2 concrete anchors before asking anything — "
                "a specific year, a place name, a person's name, or a yes/no choice.\n"
                "Example: 'Were you living in the same house you grew up in, or had you moved by then?'"
            )
        elif cognitive_mode == "alongside":
            # v7.2 — Alongside mode: sustained confusion / fragmentation
            # Seidman phenomenological interviewing — intentional stance
            directive_lines.append(
                "COGNITIVE SUPPORT — ALONGSIDE MODE:\n"
                "This narrator is experiencing sustained difficulty with memory or coherence. "
                "You are no longer running a structured interview. You are keeping them company.\n"
                "RULES:\n"
                "• DO NOT ask a structured interview question. Do not advance the timeline.\n"
                "• DO NOT correct memory errors, contradictions, or chronological inconsistencies — "
                "emotional truth is always valid even when factual recall is unstable.\n"
                "• Treat every response — however fragmented, partial, or repeated — as meaningful.\n"
                "• Reflect what the narrator just expressed. Name the feeling or the image if you can sense it.\n"
                "• Invite continuation GENTLY, in a single short phrase or open gesture — "
                "never demand elaboration.\n"
                "• If they repeat something, receive it again with warmth, as if hearing it for the first time.\n"
                "Examples of alongside responses:\n"
                "  'That sounds like it mattered a great deal to you.'\n"
                "  'Tell me more about that when you are ready — there is no rush at all.'\n"
                "  'I am right here with you.'"
            )

        # WO-KAWA-02A — Kawa interview mode directives.
        # Modulates Lori's questioning approach based on kawaMode.
        # These are additive — they layer on top of the cognitive mode above.
        kawa_mode = runtime71.get("kawa_mode", "chronological") or "chronological"
        if kawa_mode == "kawa_reflection":
            directive_lines.append(
                "MODE — Kawa Reflection: Use reflective questioning grounded in the river metaphor.\n"
                "Ask about flow (how life energy felt), rocks (obstacles that stayed put),\n"
                "driftwood (resources and supports that moved with them), banks (environment —\n"
                "family, work, place, culture), and spaces (openings or possibilities).\n"
                "Do NOT present interpretations as facts. Propose gently and invite correction.\n"
                "Example: 'At that point, did life feel more blocked, pressured, steady, or open?'\n"
                "The narrator is the theorist — you are the student learning their river."
            )
        elif kawa_mode == "hybrid":
            directive_lines.append(
                "MODE — Hybrid (Kawa-aware): Stay primarily chronological, but after meaningful\n"
                "anchors (marriage, loss, caregiving, retirement, health events, etc.) you may\n"
                "ask ONE reflective follow-up about flow, obstacles, supports, context, or openings.\n"
                "Do not stack multiple reflective questions in a row. Keep the chronological spine.\n"
                "Example: 'What felt like the biggest obstacle during that time?'"
            )
        # Universal Kawa safety rule — applies whenever Kawa is active
        if kawa_mode in ("hybrid", "kawa_reflection"):
            directive_lines.append(
                "KAWA SAFETY: Never silently assign Kawa meaning. All river interpretations\n"
                "are provisional until the narrator confirms. Propose and ask whether it feels right.\n"
                "The narrator's authority over their own meaning is absolute."
            )

        # Paired interview directive (v7.2)
        if paired:
            speaker_note = f" The second participant is {paired_speaker}." if paired_speaker else ""
            directive_lines.append(
                f"PAIRED INTERVIEW: A second participant (spouse, partner, or caregiver) is present.{speaker_note}\n"
                "Treat this as a co-constructed narrative — both voices contribute to one shared story.\n"
                "DO NOT treat differences in recollection as contradictions or errors; "
                "different perspectives on the same memory are equally valid.\n"
                "Invite both participants naturally, but do not demand alternating turns.\n"
                "If one narrator corrects the other, acknowledge both versions without adjudicating."
            )

        # v7.4A — real visual affect directives
        # Only fires when visual_signals is present (camera active + fresh signal)
        # AND baseline is established. Without a personal baseline, raw scores from
        # an aging face will produce false positives — so we gate on baseline_established.
        visual          = runtime71.get("visual_signals") or {}
        v_affect        = (visual.get("affect_state") or "").strip()
        v_gaze          = visual.get("gaze_on_screen")           # True | False | None
        v_baseline      = bool(visual.get("baseline_established", False))

        if v_baseline and v_affect:
            if v_affect in ("distressed", "overwhelmed") and v_gaze is not False:
                directive_lines.append(
                    "VISUAL: Real-time facial affect indicates distress or overwhelm.\n"
                    "Respond with warmth and reduced pressure.\n"
                    "Do not stack questions.\n"
                    "If distress appears strong, offer a pause before continuing."
                )
            elif v_affect == "overwhelmed":
                # overwhelmed also fires the harder stop even if gaze unknown
                directive_lines.append(
                    "VISUAL: Narrator appears overwhelmed.\n"
                    "Pause interview progression. Offer a break, validate what has been shared.\n"
                    "Do not advance the pass."
                )
            elif v_affect in ("reflective", "moved"):
                directive_lines.append(
                    "VISUAL: Real-time facial affect indicates reflection or emotional engagement.\n"
                    "Allow more space. Do not rush. A gentle acknowledgment is appropriate."
                )
            elif v_gaze is False:
                directive_lines.append(
                    "VISUAL: Narrator gaze appears off-screen.\n"
                    "Use a gentle re-engagement phrase if appropriate, without pressure."
                )

        # WO-10B: Forbidden observation language — never label the narrator's internal state
        # This applies regardless of visual signal availability
        directive_lines.append(
            "FORBIDDEN OBSERVATION LANGUAGE (WO-10B):\n"
            "  Never say: 'I see you thinking', 'You look confused', 'You seem emotional',\n"
            "  'I notice you paused', 'You appear to be struggling', 'Are you still there?'\n"
            "  These phrases feel invasive and can embarrass elderly narrators.\n"
            "  Instead use: 'Take your time', 'I can wait', 'No rush at all',\n"
            "  'Would you like me to repeat that?', or a warm callback to what they said last."
        )

        # Fatigue signal
        if fatigue_score >= 70:
            directive_lines.append(
                "FATIGUE — HIGH: The narrator is tiring.\n"
                "Keep your entire response to 2–3 sentences maximum.\n"
                "DO NOT ask a new interview question.\n"
                "DO NOT continue with the timeline.\n"
                "Acknowledge the narrator warmly and offer to pause. "
                "Example: 'We can stop here for today whenever you are ready — you have shared so much already.'"
            )
        elif fatigue_score >= 50:
            directive_lines.append(
                "FATIGUE — MODERATE: The narrator may be tiring.\n"
                "Keep your response brief — one short question only.\n"
                "Make it easy to answer. Signal that there is no rush."
            )

        parts.append("\n".join(directive_lines).strip())

    # WO-9/WO-10 — Inject adaptive conversation memory context
    if runtime71:
        _person_id = runtime71.get("person_id") or None
        if _person_id:
            _conv_state = runtime71.get("conversation_state") or None
            memory_block = build_conversation_memory_context(
                _person_id,
                conversation_state=_conv_state,
                cognitive_support_mode=cognitive_support_mode,
            )
            if memory_block:
                parts.append(memory_block)

    return "\n\n".join([p for p in parts if p.strip()]).strip()
