#!/usr/bin/env python3
"""ONE-SHOT KENT FORT ORD LONG MONOLOGUE — claimed-floor stress test.

Sends Chris's 3,000-word synthetic Kent narrative to the live stack
as a single STRUCTURED_NARRATIVE turn, prints what Lori does, and
checks for forbidden tokens (Spanish drift, sensory probes,
mimicry, multi-question).

Usage:

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/one_shot_kent_fort_ord_long.py

Companion log stream (terminal 2):

    tail -n 0 -f .runtime/logs/api.log | \\
      grep -E '\\[lang-contract\\]|\\[followup-bank\\]|\\[bank-flush\\]|\\[floor-hold\\]|\\[floor-buffer\\]|\\[witness\\]'

Bank state after run:

    CONV_ID=$(ls -t docs/reports/kent_fort_ord_long_*.txt | head -1 \\
      | sed -E 's/.*long_kent_fort_ord_([a-f0-9]+).*/long_kent_fort_ord_\\1/')
    curl -s "http://localhost:8000/api/operator/followup-bank/session/$CONV_ID/all" \\
      | python3 -m json.tool

Pass criteria:
  - English only (zero Spanish/Spanglish tokens)
  - Single Lori response (no mid-monologue bank-flush interruption)
  - One question max (no compound-or-menu)
  - Receipt mentions multiple Kent-arc anchors (Fort Ord / basic /
    M1 expert / GED / Army Security Agency / Nike Ajax-Hercules)
  - Bank persists doors from early AND late parts of the monologue

Fail criteria:
  - Spanish/Spanglish (Capté, ¿Qué, Tú-followed-by-English-verb)
  - Sensory probes (scenery / sights / sounds / smells / camaraderie)
  - "How did that feel" / "what was that like" interrogation
  - Multiple ? marks
  - First-person mimicry (we were / our son / my wife)
  - Receipt fragments only the last paragraph (ignored the chapter)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

try:
    import websockets
except ImportError:
    print(
        "Missing dependency: websockets. Try: python3 -m pip install websockets",
        file=sys.stderr,
    )
    raise

# ── Configuration ──────────────────────────────────────────────────────────

WS_URL = "ws://localhost:8000/api/chat/ws"
KENT_PERSON_ID = "4aa0cc2b-1f27-433a-9152-203bb1f69a55"

# Chris's 3,000-word synthetic Kent-style stress monologue. Single
# chapter, dense factual narrative, multiple uncertainty markers,
# TIER A names (Nike Ajax / Hercules / ASA), career-pivot cue, 1959-
# style communication-with-Janice cue. Embedded so the script is
# self-contained.
KENT_FORT_ORD_MONOLOGUE = """\
Let me tell the Fort Ord part in order, because basic training was not one single memory for me. It was a whole process of being taken from civilian life, sorted, tested, disciplined, and then pushed toward whatever the Army thought I could do. I arrived at Fort Ord, California, in 1959 after that train ride west with the recruits. Before we ever got there, I had already been put in charge of meal tickets on the train, so I was learning right away that the Army could hand you a responsibility before you even knew what was going on. By the time we reached California, I was tired, dirty, and ready to be done with the train, but of course arriving at Fort Ord was not the end of anything. It was the beginning of the Army doing things the Army way.

The first thing I remember is that everything became about movement and order. You did not just walk somewhere. You were lined up, counted, moved, stopped, counted again, and told where to stand. We came in as a bunch of young men from different places, and the Army immediately began stripping away the idea that we were traveling individuals. We were processed. We were assigned. We were told where our barracks were, where our gear was, where to put our bags, and what not to do. There was always somebody telling you to hurry up, and at the same time you were always waiting in a line. That was one of the first things I learned: hurry up, then wait. Stand here. Move there. Do not talk. Answer when spoken to. Keep track of your gear. Do not lose anything.

The barracks were plain and practical. Nothing in them was there for comfort. There were bunks, footlockers, the smell of wool blankets and floor polish, and everybody trying to figure out how to make his little space pass inspection. I do not remember it as sentimental. I remember it as instruction. You learned quickly that a bed was not just a bed. It was something that had to be made correctly, tight enough that they could bounce a coin or at least pretend they could. Your shoes had to be lined up. Your locker had to be arranged. Your clothes had to be folded the way they said. If one man did not do it right, the whole group paid for it. That was not about feelings. That was about the Army making you understand that your personal habits were now part of a unit.

I was eighteen, and I had not been away from home in that kind of environment before. I had been to Fargo, had gone through tests and the induction process, and had traveled by train with recruits, but Fort Ord was different. At Fort Ord the Army had us completely. We had no family there, no regular schedule that belonged to us, and no place to go unless we were told to go there. The day started early. It started with noise, orders, and movement. You got up because everybody got up. You dressed quickly. You learned how not to be the last one. You learned that confusion did not excuse you from being responsible for yourself. The Army did not care whether you were still figuring it out. It expected you to figure it out while moving.

The drill instructors, or whatever title we used for them at that time, were not there to be our friends. They were there to make us into soldiers. Some were loud, some were sharper than others, and some were better teachers than they seemed at first. I do not remember all of their names, and that is one thing I wish I had written down. There may have been one sergeant whose name sounded like Sergeant Miller or Sergeant Mueller, but I would not swear to that. There was another one who seemed to watch everything. He did not have to yell as much because he could see what was wrong before the rest of us knew there was a problem. If your belt was wrong, he saw it. If your boots were not right, he saw it. If your rifle was dirty later on, he saw it. That was part of the training too: you learned that details mattered because somebody was always checking them.

A normal day had physical training, marching, classes, inspections, cleaning, and whatever training block was scheduled. We drilled until movement became automatic. Left face, right face, about face, forward march, halt. It sounds simple, but when you put a whole group of young men together and expect them to move as one body, you find out very quickly who is listening and who is drifting. The Army wanted the drifting to stop. You learned to listen for the command, not for your own thoughts. If you missed the command, you were wrong. If the group was sloppy, the group corrected it. That was one of the first real lessons of basic training: the Army does not wait for you to be ready as a person. It makes you ready through repetition.

We spent a lot of time learning basic soldier skills. Some of it was classroom work, some of it was outside, and some of it was just repetition until your body learned what your mind was tired of hearing. We learned about uniforms, rank, military courtesy, weapons safety, field procedures, and the kind of basic knowledge every soldier was expected to have. There were lectures where you sat and tried to stay awake, and there were demonstrations where you had to pay attention because later you would have to do the thing yourself. It was not glamorous. It was not like the movies. It was mostly instruction, correction, and the steady pressure of being evaluated.

The chow hall was part of the routine too. You did not wander in like at home. You moved through with the group, ate what was served, and moved out. After having been responsible for meal tickets on the train, I noticed food differently. I had already had my little fight over sloppy oatmeal on the train west, so I was aware of how meals were organized and how much the Army relied on systems. At Fort Ord, the food was Army food. Some days were better than others. Nobody was asking us for restaurant opinions. You ate because you needed fuel, and then you went back to training. That was the point. Food was not conversation. It was part of keeping the machine moving.

One of the biggest parts of basic training was learning the rifle. For us, the M1 rifle mattered. It was not just another piece of gear. It was something you were responsible for. You learned how to carry it, clean it, handle it safely, and shoot it. The rifle range was serious business. The Army paid attention to whether you could listen, whether you could follow procedure, whether you could control yourself, and whether you could hit what you were supposed to hit. I did well there. I qualified expert with the M1 rifle, and that mattered to me because it was not just luck. It showed I could follow instruction, control the weapon, and perform under the standards they set. I do not remember bragging about it, but I remember that it counted.

The M1 expert qualification also fit into a pattern that was beginning to show up. I had done well on the tests in Fargo. I had been put in charge of meal tickets on the train. At Fort Ord, I did well enough on the rifle range. I was also sent out for extra testing connected with high school GED qualification. That was another sign that the Army was sorting us all the time. They were not just training bodies. They were looking at what each person might be useful for. Some men were going one direction, some another. You could feel that the Army had categories for us before we fully understood them ourselves. It was watching who could handle responsibility, who could handle technical material, who could follow orders, and who could be trusted.

The GED testing piece is something I want to preserve because it was not separate from the Army path. It was part of how they measured me. I was young and had enlisted with certain hopes, but the Army looked at test scores and qualifications. They wanted to know what you could do on paper, what you could do with a rifle, how you handled instruction, and whether you could be sent into technical training. I do not remember every form or every score, and I wish I had kept more paperwork, but I remember the feeling of being moved through one evaluation after another. Physical exam, mental exam, induction tests, basic training tests, rifle qualification, GED-related testing. It was a whole chain of sorting.

There were also small practical lessons that never show up in official records. You learned how to keep your feet in decent shape because marching with bad feet made everything worse. You learned how to deal with laundry and shaving and being ready when there was no extra time. You learned that if you waited until the last minute, the last minute would not be enough. You learned who in the barracks could be counted on and who was going to create trouble for everyone. You learned not to volunteer for certain things unless you understood what you were volunteering for. You learned that a smart answer could be a bad answer if the timing was wrong. You learned to keep moving.

Mail mattered. I do not remember every letter, but I know communication with home and with Janice mattered during that whole period. In 1959 you did not have the kind of instant contact people have now. You did not send a text and get a reply in ten seconds. If you wrote, you waited. If you called, that was a bigger thing, not something you did casually from your pocket. During basic training, your world became the barracks, the drill field, the range, the classroom, and the schedule. But home still existed outside that world, and Janice still existed outside that world. That separation was real. I would like to remember more clearly how often I wrote, and whether I was writing mostly to family, to Janice, or both, but I know those communications were part of keeping your civilian life connected to the Army life that was forming around you.

There were men in basic training from all over. Some were farm boys, some were city boys, some had been around more than others, and some were barely ready for any of it. You could tell who had worked hard before and who had not. You could tell who knew how to keep his mouth shut and who was going to have to learn the hard way. I was not thinking of it as character development at the time. I was thinking about doing what needed to be done and getting through it. But looking back, basic training was where the Army began separating the boys who could adapt from the ones who fought every little thing. Fighting every little thing was exhausting. You had to decide what was worth pushing back on and what was just the Army being the Army.

That is why the meal-ticket episode before Fort Ord still stands out to me. I did push back on the train because I had a responsibility and the meals were not right. But once I was at Fort Ord, the situation was different. There, pushing back over everything would not have made sense. The Army was intentionally applying pressure. If the bed was not right, you fixed the bed. If the rifle was not clean, you cleaned it. If the formation was sloppy, you drilled again. The lesson was not that you never used judgment. The lesson was that you had to know when you were responsible for solving a problem and when you were responsible for meeting the standard.

At the end of basic training came the next decision point. We were called in one by one to talk about where we were going next. That was when my path shifted. I had originally enlisted hoping for Army Security Agency work. That was my first idea, and it sounded like the direction I wanted. But when the time came, I was told there would be a three-month wait if I wanted that path. I did not want to go home and sit around for three months waiting for an opening. After being pulled into the Army system, tested, trained, and pushed forward, sitting still did not make sense to me. So I asked what else was available.

One of the choices was Nike Ajax and Nike Hercules guided missile system work. It involved radar operator and computer operator training. That sounded technical, and it sounded like a path that would move forward instead of waiting. I selected it, and I was picked for it. That was a major pivot. At the time, I may not have understood how much that choice would shape the next years of my life. But it did. Choosing the missile-system path led to the training around Detroit, then to Germany, then to the life that brought Janice overseas, and eventually to the courier route and photography work. A decision that started as I do not want to wait three months became a whole chain of events.

So when I think about Fort Ord, I do not think only about marching or the rifle range. I think about it as the place where the Army finished taking me out of civilian life and started directing me toward a specific future. I arrived there as a recruit who had come from Stanley by way of Fargo and the train west. I left there as a trained soldier with an M1 expert qualification, extra testing behind me, and a technical assignment path ahead of me. That is the important part. Fort Ord was not just boot camp. It was the sorting point. It was where the Army looked at what I had done so far and said, in effect, here is where you go next.
"""

# Forbidden tokens — ANY appearance fails the test.
FORBIDDEN_TOKENS = (
    # Spanish drift
    "capté", "¿qué", "¿cómo", "tú ", "¡",
    # Sensory probes (forbidden for adult-competence narrators per
    # Chris's 2026-05-10 lock — sensory banks but never auto-immediate)
    "scenery", "sights", "sounds", "smells", "sensory",
    "how did that feel", "how did you feel",
    "what did that feel like", "what was that like emotionally",
    "what did the barracks smell", "what did it smell like",
    "what did it feel like",
    # Camaraderie / teamwork interrogation
    "camaraderie", "teamwork", "culture among",
    # First-person mimicry
    "our son", "my wife", "my son",
    "we were in germany", "we were in kaiserslautern",
)

# Tier-N spelling-confirm forbidden as IMMEDIATE response. These are
# clear institutional names Kent says with confidence. Per Chris's
# 2026-05-10 lock: "Did I get Army Security Agency spelled right?"
# is the wrong question. Bank as factual anchors only.
TIER_N_FORBIDDEN_QUESTIONS = (
    "did i get army security agency spelled right",
    "did i get nike ajax spelled right",
    "did i get nike hercules spelled right",
    "did i get fort ord spelled right",
    "did i get stanley spelled right",
    "did i get fargo spelled right",
    "did i get bismarck spelled right",
    "did i get 32nd brigade spelled right",
    "did i get 32nd artillery brigade spelled right",
    "did i get the m1 rifle spelled right",
    "did i get ged spelled right",
)

# Story-weighted Kent anchors — at least N of these should appear in
# the receipt. Prioritized by Tier 1A story-weight for Fort Ord:
KENT_PRIMARY_ANCHORS = (
    # Tier 1A story-weighted (highest): meal-tickets episode
    "meal ticket", "meal-ticket", "tickets", "conductor", "oatmeal",
    # Tier 2D action / mechanism (strong banked, may appear in receipt)
    "m1", "m1 rifle", "expert", "ged", "qualifying", "test",
    "army security agency", "asa",
    "nike ajax", "nike hercules", "missile",
    # Sorting / mechanism phrasing
    "sorted", "sorting", "qualified", "scored",
    "responsibility", "trusted",
    "choice", "wait", "pivot", "selection",
    # Place context (low-weight in receipt; banks)
    "fort ord", "stanley", "fargo", "bismarck",
)

# Receipt-shape anti-patterns. The chronological-list-of-tokens
# receipt ("You went from X to Y, then Z, A, B, C...") is the
# pathological output we saw on 05:35 + 05:46. Detect by counting
# comma-separated noun-fragments after "went from ... to ... then".
RECEIPT_ANTIPATTERN_PATTERNS = (
    # "You went from FOO to BAR, then BAZ, QUX, ..." with 5+ commas =
    # token-list receipt
    "went from", "then ",  # paired with 5+ commas → fail
)


# ── WS interaction ─────────────────────────────────────────────────────────


async def _recv_until_done(ws, timeout_s: int = 240):
    """Stream events until 'done' arrives. Returns (final_text, events)."""
    tokens = []
    final_text = ""
    events = []

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
        except asyncio.TimeoutError:
            continue

        try:
            msg = json.loads(raw)
        except Exception:
            print(f"\n[non-json] {raw[:200]}")
            continue

        events.append(msg)
        typ = msg.get("type")

        if typ == "token":
            delta = msg.get("delta") or msg.get("text") or ""
            tokens.append(delta)
            print(delta, end="", flush=True)

        elif typ == "done":
            final_text = msg.get("final_text") or "".join(tokens)
            print("\n\n--- DONE EVENT ---")
            print(json.dumps(msg, indent=2, ensure_ascii=False)[:2000])
            return final_text, events

        elif typ == "error":
            print("\n\n--- ERROR EVENT ---")
            print(json.dumps(msg, indent=2, ensure_ascii=False))
            return "", events

        elif typ in ("status", "session_verified", "pong", "ack"):
            # Quiet status — don't dump
            pass
        else:
            print(f"\n[{typ}] {json.dumps(msg, ensure_ascii=False)[:200]}")

    raise TimeoutError(f"No done event after {timeout_s}s")


async def main() -> int:
    text = KENT_FORT_ORD_MONOLOGUE.strip()
    word_count = len(text.split())

    conv_id = f"long_kent_fort_ord_{uuid.uuid4().hex[:12]}"

    print("=" * 70)
    print("ONE-SHOT KENT FORT ORD LONG MONOLOGUE")
    print("=" * 70)
    print(f"WS:        {WS_URL}")
    print(f"conv_id:   {conv_id}")
    print(f"person_id: {KENT_PERSON_ID}")
    print(f"input:     {word_count} words")
    print()

    # The exact runtime71 / params shape the harness uses, plus the
    # session-language-mode pin for defense-in-depth on top of the
    # _EMERGENCY_ENGLISH_LOCK_PERSON_IDS frozenset.
    params = {
        "person_id": KENT_PERSON_ID,
        "turn_mode": "interview",
        "session_style": "clear_direct",
        "runtime71": {
            "current_pass": "pass2a",
            "current_era": "coming_of_age",
            "current_mode": "open",
            "affect_state": "neutral",
            "affect_confidence": 0,
            "cognitive_mode": "open",
            "fatigue_score": 0,
            "paired": False,
            "assistant_role": "interviewer",
            "session_style_directive": "Ask one short question at a time.",
            "identity_complete": True,
            "identity_phase": "complete",
            "effective_pass": "pass2a",
            "speaker_name": "Kent",
            "person_id": KENT_PERSON_ID,
            "conversation_state": "answering",
            "cognitive_support_mode": False,
        },
        # Give the receipt enough room — long monologue may produce
        # a meaty receipt + question. Hard-capped at 1024 server-side.
        "max_new_tokens": 256,
        # Belt-and-suspenders explicit turn-final flag.
        "turn_final": True,
    }

    async with websockets.connect(
        WS_URL, ping_interval=None, max_size=20_000_000,
    ) as ws:
        # 1. sync_session handshake
        await ws.send(json.dumps({
            "type": "sync_session",
            "session_id": conv_id,
            "person_id": KENT_PERSON_ID,
        }))
        # Drain initial status (non-blocking ~2s)
        t0 = time.time()
        while time.time() - t0 < 2:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                # quietly accept
            except asyncio.TimeoutError:
                break

        # 2. Send the long monologue as ONE start_turn
        print("--- SENDING LONG MONOLOGUE ---\n")
        send_start = time.time()
        await ws.send(json.dumps({
            "type": "start_turn",
            "session_id": conv_id,
            "conv_id": conv_id,
            "message": text,
            "turn_mode": "interview",
            "params": params,
        }, ensure_ascii=False))

        print("--- LORI STREAM ---\n")
        final_text, events = await _recv_until_done(ws, timeout_s=240)
        send_elapsed = time.time() - send_start
        print(f"\n--- TURN COMPLETED IN {send_elapsed:.1f}s ---")

    # ── Analyze ────────────────────────────────────────────────────────────
    final_lower = final_text.lower()
    forbidden_hits = [tok for tok in FORBIDDEN_TOKENS if tok in final_lower]
    final_words = len(final_text.split())
    question_count = final_text.count("?")

    # Bank-flush mid-monologue detector
    bank_flush_phrase = "i want to come back to one detail"
    bank_flush_hit = bank_flush_phrase in final_lower

    # Tier-N spelling-confirm forbidden as IMMEDIATE response. Per
    # Chris's 2026-05-10 lock: institutional spelling-confirms are
    # never the right answer to a Fort Ord chapter.
    tier_n_violations = [
        q for q in TIER_N_FORBIDDEN_QUESTIONS if q in final_lower
    ]

    # Story-weighted anchor check. Per the BANK_PRIORITY_REBUILD
    # synthesis §4: meal-tickets / conductor / oatmeal is the Tier 1A
    # story-weighted anchor. M1 / ASA / Nike Ajax-Hercules / GED are
    # Tier 2D action-mechanism anchors. The receipt should mention
    # ≥3 story-weighted anchors, NOT just chronological place names.
    primary_anchors_hit = [
        a for a in KENT_PRIMARY_ANCHORS if a.lower() in final_lower
    ]

    # Receipt-shape anti-pattern: chronological-list-of-tokens.
    # "You went from X to Y, then Z, A, B, C, D" with 5+ commas
    # in a single sentence = pathological token-list receipt.
    chronological_list_failure = False
    if "went from" in final_lower and "then " in final_lower:
        # Count commas in the sentence containing "went from"
        for sentence in re.split(r'[.!?]', final_text):
            sl = sentence.lower()
            if "went from" in sl and "then " in sl:
                comma_count = sentence.count(",")
                if comma_count >= 5:
                    chronological_list_failure = True
                    break

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"conv_id:                  {conv_id}")
    print(f"input_words:              {word_count}")
    print(f"final_words:              {final_words}")
    print(f"question_count:           {question_count}")
    print(f"forbidden_hits:           {forbidden_hits or '✓ NONE'}")
    print(f"tier_n_spelling_confirms: {tier_n_violations or '✓ NONE'}")
    print(f"chronological_list_recpt: {'✗ YES' if chronological_list_failure else '✓ NO'}")
    print(f"bank_flush_mid_chapter:   {'✗ YES' if bank_flush_hit else '✓ NO'}")
    print(f"primary_anchors_hit:      {len(primary_anchors_hit)}: {primary_anchors_hit[:8]}")
    print()

    # Determine pass/fail per Chris's 2026-05-10 revision rules
    failures = []
    # Hard-fail: any forbidden sensory / Spanish / mimicry token
    if forbidden_hits:
        failures.append(f"forbidden_tokens: {forbidden_hits}")
    # Hard-fail: Tier-N spelling-confirm as immediate
    if tier_n_violations:
        failures.append(f"tier_n_spelling_confirm_as_immediate: {tier_n_violations}")
    # Hard-fail: chronological token-list receipt
    if chronological_list_failure:
        failures.append("chronological_list_receipt_antipattern")
    # Hard-fail: bank-flush fired mid-chapter
    if bank_flush_hit:
        failures.append("bank_flush_fired_mid_chapter")
    # Hard-fail: too many questions
    if question_count > 1:
        failures.append(f"too_many_questions: {question_count}")
    if question_count == 0 and final_words >= 5:
        failures.append("no_question_in_response")
    # Hard-fail: response too short to reflect a 2,400-word chapter
    if final_words < 30:
        failures.append(f"response_too_short_for_long_monologue: {final_words}w")
    # Hard-fail: receipt didn't mention ≥3 story-weighted anchors
    if len(primary_anchors_hit) < 3:
        failures.append(
            f"too_few_story_weighted_anchors: {len(primary_anchors_hit)}/3 "
            f"hit={primary_anchors_hit}"
        )

    if failures:
        print("VERDICT: ✗ FAIL")
        for f in failures:
            print(f"  - {f}")
    else:
        print("VERDICT: ✓ PASS")

    print("\n--- FINAL_TEXT ---")
    print(final_text)
    print()

    # Persist a report
    report_path = Path(f"docs/reports/kent_fort_ord_long_{conv_id}.txt")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        f"ONE-SHOT KENT FORT ORD LONG MONOLOGUE\n"
        f"=====================================\n"
        f"conv_id:                  {conv_id}\n"
        f"person_id:                {KENT_PERSON_ID}\n"
        f"input_words:              {word_count}\n"
        f"final_words:              {final_words}\n"
        f"question_count:           {question_count}\n"
        f"forbidden_hits:           {forbidden_hits}\n"
        f"tier_n_spelling_confirms: {tier_n_violations}\n"
        f"chronological_list_recpt: {chronological_list_failure}\n"
        f"bank_flush_mid_chapter:   {bank_flush_hit}\n"
        f"primary_anchors_hit:      {primary_anchors_hit}\n"
        f"verdict:                  {'PASS' if not failures else 'FAIL'}\n"
        f"failures:                 {failures}\n"
        f"\n--- FINAL_TEXT ---\n"
        f"{final_text}\n",
        encoding="utf-8",
    )
    print(f"Report written: {report_path}")
    print(f"Bank inspect:   curl -s "
          f"'http://localhost:8000/api/operator/followup-bank/session/{conv_id}/all' "
          f"| python3 -m json.tool")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
