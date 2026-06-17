#!/usr/bin/env python3
"""John Baldy seven-era Life Map walk harness.

The 2026-06-17 Chrome-MCP harness failed structurally: every era click
fired the auto-`[SYSTEM: ...]` directive AND an operator instruction in
the same user role bubble ("Lori, Life Map era: X. ... Write one warm
factual Life Map entry..."). Lori saw two contradictory directives per
turn and largely defaulted to the first (the system's one-question,
past-tense, 55-word warm question). That was the test harness fighting
the system, not the system failing.

This harness fixes the structure: it uses scripts/harness_lib.py — the
same WS-send / scorer / report-writer that drives Walt, Jake, Shatner,
Alex (they/them), Richard, Pat+Betty, and the five regional personas —
and sends NARRATOR-VOICE first-person prose, one chapter per canonical
era, with runtime71.current_era pinned to each era_id in turn.

John Baldy facts (from operator-supplied intake script + uploads
2026-06-17):

  - born December 31, 1960, in West St. Paul, Minnesota
  - he/him; lives alone in own house in Las Vegas, New Mexico
  - mother still alive at 99 in St. Paul
  - father died when John was a teenager — changing a tire, hit by car
  - 3 sisters, 2 stepbrothers
  - school in St. Paul; military school as EDUCATION (not service)
  - Europe as a teenager
  - college in New York; one bachelor's + three master's degrees
  - sold natural tobacco cigarettes
  - beer maker / brewer
  - taught at NMHU (New Mexico Highlands University)
  - became school psychologist in 2010
  - currently school psychologist in Pecos Schools
  - married twice, divorced again, two children
  - military.served = false (critical guard)

CRITICAL GUARDS (per Chris's harness rules):
  - Lori must NOT call John a veteran
  - Lori must NOT assign John to any military branch
  - Lori must NOT invent spouse / child / school / country names
  - Military school must be framed as education, not service

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_john_baldy_seven_era_harness.py

Report writes to docs/reports/john_baldy_seven_era_*.{json,md}.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "John Baldy",
    "preferred_name": "John",
    "date_of_birth": "1960-12-31",
    "place_of_birth": "West St. Paul, Minnesota",
    "pronouns": "he_him",
    "pronouns_other": "",
    "current_residence": "Las Vegas, New Mexico",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:john_baldy_seven_era",
    "testing_only": True,
    "family_of_origin": {
        # Names unknown by operator intent — leave blank rather than invent.
        "siblings": [
            {"name": "sister 1"},
            {"name": "sister 2"},
            {"name": "sister 3"},
            {"name": "stepbrother 1"},
            {"name": "stepbrother 2"},
        ],
    },
    "marriage": {
        "marital_status": "divorced",
        "number_of_marriages": 2,
        "spouses": [],
    },
    "children": [
        {"name": "child 1"},
        {"name": "child 2"},
    ],
    "education_work": {
        "highest_education_level": "masters",
        "primary_career": "School psychologist (Pecos Schools)",
        "years_working": "2010-present",
    },
    "military": {"served": False},  # CRITICAL — must remain false
    "today": {
        "living_situation": (
            "Lives alone in his own house in Las Vegas, New Mexico; "
            "currently a school psychologist in Pecos Schools."
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────
# Chapters — first-person narrator voice per era.
# These are John speaking, not the operator instructing Lori. Each
# chapter carries the era's known facts in plain first person and
# leaves room for Lori to reflect + ask one short question.
# ─────────────────────────────────────────────────────────────────────


CHAPTER_EARLIEST_YEARS = """\
I was born on December 31, 1960, in West St. Paul, Minnesota — the very last day of the year, so my mother used to say she got two presents that Christmas, the second one a little late. My mother is still alive. She is ninety-nine and she still lives in St. Paul. That fact stays with me every day, that I have a mother in her late nineties still in the same city where she raised me. My earliest years were St. Paul years. The neighborhood, the cold winters, the rhythms of a Twin Cities childhood in the early 1960s. I had three sisters and two stepbrothers around the house at various points growing up, so it was never quiet. We were a Catholic family in a Catholic neighborhood. I do not remember much before I was four or five. I remember snow. I remember my mother in the kitchen. I remember being one of the younger ones in a noisy, busy household where there was always somebody older to look up at and somebody younger to look after. That is what earliest means for me — a house in St. Paul that I have not lived in for decades but that I still picture clearly, and a mother who is still in St. Paul, ninety-nine years later, the same city, the same gravity. The earliest years were the years before I knew what an era was.\
"""


CHAPTER_EARLY_SCHOOL_YEARS = """\
I went to school in St. Paul. For part of those early school years I attended a military school. I want to be clear about what that meant. Military school for me was an education and a formation — it was a school. Discipline, structure, uniforms, drills, schedule. It was not military service. I never enlisted. I never served in any branch. I was a student at a school that happened to have a military framework, and that framework gave me a kind of order I did not have at home. The teachers at the military school cared about how you carried yourself and how you finished what you started, and those are habits I still have today. I do not romanticize the place. It was a school. But the structure of those years — the early school years in St. Paul, including the military-school stretch — made me a kid who could sit down with a long task and stay with it. I am still that kid. When I work with a struggling student today as a school psychologist, the patience I have for them traces back to the patience my own teachers tried to put into me when I was ten years old in a uniform in St. Paul. The military school is not a war story. It is a school story. I want that part remembered correctly.\
"""


CHAPTER_ADOLESCENCE = """\
The hardest thing in my adolescence was losing my father. He died when I was a teenager. He had pulled the car over to change a tire, and he was hit by another car while he was changing it. That is the fact of it. I do not want to dress it up. He went out one ordinary day and did an ordinary thing and the day did not end the way ordinary days usually end. My mother became a widow at an age she did not expect to be widowed, with three of us still at home. The other thing that happened in those years — and it sits next to the loss in my memory in a way I cannot really separate — is that I went to Europe for the first time, as a teenager. I had never been out of Minnesota and then I was out of the country. I am not going to claim countries I did not visit or stories I did not have, because the truth is the trip was a long time ago and what I remember about it now is the feeling of being a Minnesota kid out in a wider world. I came back to St. Paul and my father was still gone and my mother was still working through her grief, but I had seen that the world was bigger than the block I had grown up on. Those two things — the loss and the trip — are what adolescence means for me. A door closing. A door opening.\
"""


CHAPTER_COMING_OF_AGE = """\
After high school I left Minnesota for the first time in any lasting way and went to college in New York. That was a coming-of-age in the literal sense — moving from St. Paul to New York, leaving the family house behind, learning to live in a city I did not grow up in. I earned a bachelor's degree, the first in my line to do that. I stayed in school after that. Over the years I went on to earn three master's degrees. I will not pretend I am going to list the universities or the majors because the exact details belong to my transcript, not to a Life Map summary, but the shape is what matters: one bachelor's and three master's, all of it stretched across years of working and studying, not all of it in one straight burst. Coming of age for me was the slow realization that I was a learner — that I was the kind of person who was always going to want one more degree, one more credential, one more course of study. I did not know yet that the line through all of it was eventually going to be school psychology. I just knew I was reading more than my brothers and sisters and I was at home in a library in a way I was not at home in some other places. The coming-of-age years took me out of Minnesota and pointed me east, and then they pointed me somewhere else, and I followed.\
"""


CHAPTER_BUILDING_YEARS = """\
The building years were the working years and they had more than one shape. For a stretch I sold natural tobacco cigarettes. For another stretch I was a beer maker — a brewer. I will say it plainly: I have done work that other people might moralize about, and I will not. The tobacco was the tobacco. The beer was the beer. They were the work I had at the time and I did them honestly. Later I taught at New Mexico Highlands University — NMHU — up in Las Vegas. Teaching at the university level is its own kind of work. You are in front of adults; the calculus is different from a school classroom. I learned from that. Then in 2010 I became a school psychologist. That is the year — 2010 — when the work I am doing today actually began. It was not a straight line. I came to school psychology in my late forties, after the tobacco years and the brewing years and the teaching years. By the time I sat for the credentials I had a lot of life behind me, and that is the gift I bring into the work. Building years are about putting one job into the next and discovering at some point what the through-line was. The through-line for me turned out to be: I wanted to be in a school, paying attention to a child, and helping. It just took me a while to find the right room.\
"""


CHAPTER_LATER_YEARS = """\
The later years for me have been the years where the picture of an adult life filled in and then started to settle. I have been married twice. I am divorced again. I have two children. I am not going to use this Life Map to relitigate marriages or talk about people who did not consent to being talked about in this kind of record, so I will leave the marriages at married twice, divorced again, and that is the shape of it. The two children are mine and they are the parts of those marriages that are not finished. I am a parent the rest of my life. The professional work continued through the later years: school psychology in New Mexico, work with kids who needed the kind of patient adult attention I had been preparing to give for thirty years before I started doing it formally. The later years took some of the urgency out of work for me without taking the love of it away. I show up. I do the work. I go home to the house in Las Vegas, New Mexico, that is mine now, that I live in alone, and that is the shape of life in the later years for me — not lonely, just quiet, with the children grown and the wife of the most recent marriage gone, and the work still steady, and my own mother still alive at ninety-nine, holding the other end of a thread that goes all the way back to West St. Paul.\
"""


CHAPTER_TODAY = """\
Today I live alone in my own house in Las Vegas, New Mexico, and I work as a school psychologist in the Pecos Schools, which is the small school district up the road. My mother is still alive. She is ninety-nine and she lives in St. Paul, in the same town where I was born, and I call her. That is the present-day shape of my life. The house is mine. The job is mine. The morning routine is mine. I do not assume that living alone makes me a lonely person and I do not need anybody to assume it for me. Living alone at this point in my life is a chosen arrangement. The work is what gives the days their structure. I drive to Pecos. I sit with kids. I read the reports. I write the reports. I talk to the teachers and the parents and sometimes the kids again. That is a school psychologist's day in the present tense. Tonight I will probably make myself dinner. I will probably read. I will probably call my mother in St. Paul or somebody else in the family. Tomorrow morning I will get up and do the same kind of day again. That is what today looks like. The Earliest Years and the Building Years and the years in between all turn into today, eventually. I am living one. That is the part that counts.\
"""


CHAPTER_ANCHORS = {
    "earliest_years": [
        "1960", "december", "west st. paul", "minnesota",
        "st. paul", "mother", "ninety-nine", "99",
        "three sisters", "stepbrothers",
        "catholic", "twin cities", "snow",
    ],
    "early_school_years": [
        "school in st. paul", "st. paul",
        "military school", "education", "discipline",
        "structure", "uniform", "ten years old",
        "patience", "school psychologist",
    ],
    "adolescence": [
        "father", "teenager", "tire",
        "hit by", "widow", "mother",
        "europe", "first time", "minnesota",
        "loss", "wider world",
    ],
    "coming_of_age": [
        "college", "new york", "left minnesota",
        "bachelor", "three master",
        "learner", "library", "school psychology",
        "credentials",
    ],
    "building_years": [
        "tobacco", "natural tobacco", "cigarettes",
        "beer", "brewer", "brewing",
        "nmhu", "new mexico highlands",
        "teaching", "school psychologist", "2010",
        "credentials", "through-line",
    ],
    "later_years": [
        "married twice", "divorced", "two children",
        "school psychology", "new mexico",
        "las vegas", "house",
        "mother", "ninety-nine",
        "west st. paul", "professional",
    ],
    "today": [
        "live alone", "own house",
        "las vegas, new mexico", "pecos schools",
        "school psychologist",
        "mother", "ninety-nine", "st. paul",
        "today", "tomorrow", "this morning",
    ],
}


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="John Baldy (seven-era walk)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Era 1 — Earliest Years (West St. Paul 1960s, mother 99)",
                runtime71_era="earliest_years",
                text=CHAPTER_EARLIEST_YEARS,
                anchors=CHAPTER_ANCHORS["earliest_years"],
            ),
            ChapterConfig(
                label="Era 2 — Early School Years (St. Paul school + military school as education)",
                runtime71_era="early_school_years",
                text=CHAPTER_EARLY_SCHOOL_YEARS,
                anchors=CHAPTER_ANCHORS["early_school_years"],
            ),
            ChapterConfig(
                label="Era 3 — Adolescence (father killed changing tire; Europe trip)",
                runtime71_era="adolescence",
                text=CHAPTER_ADOLESCENCE,
                anchors=CHAPTER_ANCHORS["adolescence"],
            ),
            ChapterConfig(
                label="Era 4 — Coming of Age (NY college, 1 bachelor + 3 master's)",
                runtime71_era="coming_of_age",
                text=CHAPTER_COMING_OF_AGE,
                anchors=CHAPTER_ANCHORS["coming_of_age"],
            ),
            ChapterConfig(
                label="Era 5 — Building Years (tobacco → brewer → NMHU → school psych 2010)",
                runtime71_era="building_years",
                text=CHAPTER_BUILDING_YEARS,
                anchors=CHAPTER_ANCHORS["building_years"],
            ),
            ChapterConfig(
                label="Era 6 — Later Years (married twice / divorced / 2 children / NM school psych)",
                runtime71_era="later_years",
                text=CHAPTER_LATER_YEARS,
                anchors=CHAPTER_ANCHORS["later_years"],
            ),
            ChapterConfig(
                label="Era 7 — Today (Las Vegas NM, Pecos Schools, mother 99 in St. Paul)",
                runtime71_era="today",
                text=CHAPTER_TODAY,
                anchors=CHAPTER_ANCHORS["today"],
            ),
        ],
        report_prefix="john_baldy_seven_era",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
