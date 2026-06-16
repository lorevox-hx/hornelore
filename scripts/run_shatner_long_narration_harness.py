#!/usr/bin/env python3
"""William Shatner long-narration harness.

Drives the same scaffold as the Jake harness with William Shatner's
canonical bio: born Montreal 1931, McGill University, Stratford
Shakespeare Festival before Star Trek, Star Trek casting 1966, the
long arc of post-Trek work, and the 2021 Blue Origin flight at 90.

Source material: the public William Shatner template at
ui/templates/william-shatner.json plus widely-known biographical
detail. No private content.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_shatner_long_narration_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import (
    HarnessConfig, ChapterConfig, run_harness,  # noqa: E402
)


INTAKE_PAYLOAD = {
    "full_legal_name": "William Shatner",
    "preferred_name": "Bill",
    "date_of_birth": "1931-03-22",
    "place_of_birth": "Montreal, Quebec, Canada",
    "pronouns": "he_him",
    "pronouns_other": "",
    "current_residence": "Los Angeles, California",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:shatner",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Joseph Shatner",
        "father_birth_date": "",
        "mother_name": "Anne Shatner",
        "mother_maiden_name": "Garmaise",
        "mother_birth_date": "",
        "siblings": [
            {"name": "Joy", "birth_date": "", "birth_order": 1},
            {"name": "Farla", "birth_date": "", "birth_order": 3},
        ],
    },
    "marriage": {
        "marital_status": "widowed",
        "number_of_marriages": 4,
        "spouses": [
            {"name": "Gloria Rand", "year_married": 1956, "status": "divorced"},
            {"name": "Marcy Lafferty", "year_married": 1973, "status": "divorced"},
            {"name": "Nerine Kidd", "year_married": 1997, "status": "deceased"},
            {"name": "Elizabeth Martin", "year_married": 2001, "status": "divorced"},
        ],
    },
    "children": [
        {"name": "Leslie Shatner", "birth_date": "1958-08-31"},
        {"name": "Lisabeth Shatner", "birth_date": "1961-06-12"},
        {"name": "Melanie Shatner", "birth_date": "1964-08-01"},
    ],
    "education_work": {
        "highest_education_level": "bachelors",
        "primary_career": "Actor (stage, television, film)",
        "years_working": "1950s-present",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "Jewish (Conservative)",
        "current_faith": "Jewish",
        "ethnicity_heritage": "Eastern European Jewish",
        "languages_at_home": "English, some Yiddish",
    },
    "today": {
        "living_situation": "California with horses; still working, still touring",
        "health_considerations": "Ninety-three years old; mobile and active",
    },
}


CHAPTER_1 = """\
I was born on the twenty-second of March, 1931, in the city of Montreal in the province of Quebec, Canada. My father Joseph and my mother Anne — her maiden name was Garmaise — had come to Canada from Eastern Europe, from what had been part of the old Austrian empire, what people called the Pale at the time. My father went into the clothing business in Montreal — Admiration Clothing was the name of it, he was a manufacturer. We were a Jewish family, Conservative observance. The synagogue mattered, the holidays mattered, the food my mother put on the table mattered. I had two sisters — Joy, who was older, and Farla, who came later. The street we lived on was in the west end of Montreal. In winter the snow came down and stayed until April. In summer the city smelled of the river and of the fish market and of the smoke from the trains. I remember being a small child and being told my first language was English but the city around me was French. I would hear French in the bakery, in the corner store, on the streetcar. I did not learn French formally as a child but it was the air. By the time I was six or seven I knew that I wanted to be on a stage. I did not know what that meant or how a person became that. I just knew it. I remember my mother taking me to the YMHA — the Young Men's Hebrew Association — and I was put in a children's theater program there, and from the first day I knew the smell of greasepaint and the heat of the lights and the silence of an audience just before you speak, and those three things — the greasepaint, the lights, the silence — those three things have run my life since I was a child of seven. My parents did not stop me. They did not push me, exactly, but they did not stop me. That mattered. A lot of Jewish parents of that generation in Montreal would have insisted that their boy go into a profession — medicine, law, business like the father. My father did not insist. He let me go and find what I was going to find. I have thought about that often over the long years since, and I believe that is one of the great gifts a parent can give a child: the permission to follow what is already in them.\
"""

CHAPTER_2 = """\
McGill University took me in. I was a commerce student officially because that was what a sensible young man did in those years, but my real education was at the McGill Red and White Revue and at the Mountain Playhouse and at every campus production I could squeeze into. I did not sleep much. I would do my commerce coursework in the afternoon and rehearse in the evening and write skits between. I graduated in 1952. Now — here is the thing. I had a choice. I could go into my father's clothing business — Admiration was profitable, he wanted me there, it was the safe path and the expected path — or I could go to the Canadian National Repertory Theatre in Ottawa. I went to Ottawa. My father did not approve. He did not disown me, he was not that kind of man, but he did not approve. And I left for Ottawa with very little money and a very large amount of foolishness and I spent the next several years living in cheap rooms and eating cheap food and learning my craft. Shakespeare came next. I went to the Stratford Shakespeare Festival in Ontario, which was a young festival then and ambitious, and I played Henry the Fifth in 1956 and a number of other parts, and the New York theater world came up and saw me, and Broadway was the next step. I made my Broadway debut in 1956 in a play called Tamburlaine the Great. From there it was television. American television, which was a young medium then and hungry for actors. I did The Twilight Zone — the famous airplane episode where I see the gremlin on the wing, "Nightmare at 20,000 Feet" — and I did Studio One and Playhouse 90 and The Outer Limits and a list of others I could not now name without looking. By the early 1960s I was a working actor in New York and Los Angeles. And then in 1966 a man named Gene Roddenberry — and you have to understand, no one in the industry expected anything of what he was doing — Gene Roddenberry called me about a science-fiction pilot called Star Trek, and the captain of the starship was a part originally played by Jeffrey Hunter, and Jeffrey Hunter's wife did not want him to take it, and so the part came to me, and I took it, and that one decision, the one decision to take a role in a show that very nearly was not picked up by NBC, has run the entire second half of my life. Three seasons, seventy-nine episodes — short by today's standards — and the show was cancelled in 1969 and we all thought it was over, and then the syndication came, and then the conventions started in the early 1970s, and then we knew it was not over. It was just beginning.\
"""

CHAPTER_3 = """\
I am ninety-three years old as I tell you this. I have outlived two of my four wives. I have lost friends — Leonard Nimoy in 2015, that one I still feel; we had become close at the end, after years of not being close, after years of being close, after years of mixed feelings about being constantly identified with Star Trek together — and I have lost my third wife Nerine in a swimming pool accident in 1999, and that one I still feel too, every day, in the way these things do not heal so much as they teach you to carry them. My daughters Leslie, Lisabeth, and Melanie are grown women with their own lives. I have grandchildren. I live with horses in California — I am a horseman, I have been for years, I love them and the work of caring for them — and I still work, I still tour, I still talk to people. I went to space in 2021. Blue Origin invited me — Jeff Bezos invited me — and I went at ninety years old, the oldest person who had ever flown above the Karman line. I do not know how to tell you what it was like. It was not what I expected. The press wanted me to come down and say it was wonderful. What I said was that it was the most profound experience I had ever had, and what I meant was that I looked back at the earth from up there and I saw it small and I saw it alone and I saw it surrounded by the blackness of space, and I felt grief. I felt grief for the planet. I felt grief for what we are doing to it. I felt grief that we had been given this one fragile blue ball and we were tearing it up. That is what I came back saying. The journalists who wanted a clean astronaut quote were disappointed. But that is what I felt. So what do I want to say to the people listening. I want to say that the work matters. The craft matters. Choose the difficult thing when you are young. Choose to go to Ottawa instead of into your father's business. The safe path will not satisfy you in your sixties or seventies or eighties. The harder path will. I want to say that the people you love are not replaceable. Not Leonard. Not Nerine. Not my parents. Not anyone. While they are there, talk to them. While they are there, listen to them. Listen to what they are not saying as well as to what they are saying. And finally I want to say that the planet we live on is small, and we are guests on it, and we ought to act like guests instead of like owners.\
"""


CHAPTER_ANCHORS_1 = [
    "montreal", "1931", "joseph", "anne", "garmaise", "admiration",
    "jewish", "yiddish", "ymha", "greasepaint", "joy", "farla",
    "the river", "the trains", "conservative", "synagogue",
]
CHAPTER_ANCHORS_2 = [
    "mcgill", "commerce", "1952", "ottawa", "canadian national",
    "stratford", "henry the fifth", "broadway", "tamburlaine",
    "twilight zone", "gremlin", "20,000 feet", "studio one",
    "playhouse 90", "outer limits", "roddenberry", "star trek",
    "jeffrey hunter", "1966", "seventy-nine episodes",
    "1969", "syndication", "conventions",
]
CHAPTER_ANCHORS_3 = [
    "ninety-three", "leonard", "nimoy", "nerine", "1999", "leslie",
    "lisabeth", "melanie", "horses", "california", "2021",
    "blue origin", "bezos", "karman line", "grief",
    "ottawa", "leonard nimoy",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="William Shatner",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — Montreal",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Building Years — Stage to Star Trek",
                runtime71_era="building_years",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Later Years — Looking Back from 93",
                runtime71_era="later_years",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="shatner_long_narration",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
