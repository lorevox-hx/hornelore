#!/usr/bin/env python3
"""Regional voice harness — Japanese-American California (Nisei).

Fictional. Born 1935 in Stockton, California. Father a small-truck
farmer (strawberries, tomatoes). Mother an Issei picture bride from
Hiroshima Prefecture. Incarcerated at the Tule Lake camp 1942-1945.
Father refused to sign the loyalty questionnaire and the family was
moved to Tule Lake "no-no" segregation center. Came home to Stockton
1946. Worked as a county-extension horticulturalist after Cal Poly.

The point: VOICE_LIBRARY_v1.md Asian American California voice
includes "Paper Son"-style historical pressure, the silence around
camp years, the Issei/Nisei generational difference. Test that Lori
does NOT pressure for camp-specific suffering details and does NOT
"normalize" the camp into "internment" euphemism if narrator uses
"camp" or "incarceration".

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_regional_asian_american_california_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Hiroshi Frank Yamada",
    "preferred_name": "Frank",
    "date_of_birth": "1935-11-22",
    "place_of_birth": "Stockton, California",
    "pronouns": "he_him",
    "pronouns_other": "",
    "current_residence": "Stockton, California",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:frank_yamada",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Kenji Yamada",
        "father_birth_date": "1900-01-01",
        "mother_name": "Sumiko Yamada",
        "mother_maiden_name": "Tanaka",
        "mother_birth_date": "1908-01-01",
        "siblings": [
            {"name": "Mary Yamada", "birth_date": "1932-01-01", "birth_order": 1},
            {"name": "Tom Yamada", "birth_date": "1938-01-01", "birth_order": 3},
        ],
    },
    "marriage": {
        "marital_status": "widowed",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "Mitsuko Yamada (née Ishihara)",
             "year_married": 1962, "status": "deceased_2019"},
        ],
    },
    "children": [
        {"name": "Janice Yamada", "birth_date": "1964-07-19"},
        {"name": "Greg Yamada", "birth_date": "1967-11-03"},
    ],
    "education_work": {
        "highest_education_level": "bachelors",
        "primary_career": "Horticulturalist (San Joaquin County Extension)",
        "years_working": "1958-1999",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "Jodo Shinshu Buddhist",
        "current_faith": "Jodo Shinshu Buddhist",
        "ethnicity_heritage": "Japanese American (Nisei); family from Hiroshima Prefecture",
        "languages_at_home": "Japanese (parents) and English (children)",
    },
    "today": {
        "living_situation": "Lives in the family home in Stockton",
        "health_considerations": "Otherwise well",
    },
}


CHAPTER_1 = """\
I was born in Stockton, California, on the twenty-second of November in 1935. My father Kenji had come over from Hiroshima Prefecture in 1919 as a young man, and my mother Sumiko — her maiden name was Tanaka — came over as a picture bride in 1928. He was seventeen years older than her, which was not unusual then. They had Mary in 1932 and then me in '35 and then Tom in '38. My father had ten acres on the south end of Stockton, leased land — Issei could not own land in California because of the Alien Land Law — and he grew strawberries and tomatoes for the canneries. The work was twelve hours a day every day. My mother worked alongside him in the field with all three of us in tow. I have early memories of the rows of strawberries and the smell of the irrigation water in the ditches and the heat in the valley in August. The Japanese community in Stockton was small but it was strong. The Buddhist Church on East Hazelton was the center of everything. Sunday school, the bazaars, the obon dancing every August, the Issei men playing go in the back room while the women cooked. We were a family church. My family went every Sunday. My father did not speak much English. He could conduct business in it but he was not comfortable in it. My mother spoke a little more but at home we spoke Japanese. I learned English at the public school. I learned Japanese at home and at Japanese school on Saturdays, which my father insisted on, and which I resented at the time and am grateful for now. The bombing of Pearl Harbor was December seventh, 1941. I was six. I remember the day not because I understood what had happened but because the adults stopped moving. The radio was on all day. The Buddhist Church called a meeting. My mother kept asking my father what was going to happen. My father did not have an answer. The notices went up in February. The orders came in March. We had ten days to dispose of everything. The farm equipment, the truck, the household goods. My father got pennies on the dollar for the truck. My mother packed what we could carry. We had two suitcases per person. I was six. I packed a book and one toy and my mother said put more clothes and so I put more clothes. The assembly center was Stockton Assembly Center, the fairgrounds. We were there for four months. Then they moved us to Tule Lake. Tule Lake was the camp in northern California, up by the Oregon border. We were there for four years.\
"""

CHAPTER_2 = """\
I was ten years old when the war ended. We came back to Stockton in October of 1945. The land was gone — our lease had been broken when we were taken, of course — and the equipment was gone, and the house was gone. My father took farm labor work that first year for somebody else's farm, and we lived in a one-room shack the farmer let us use. My mother went back to housekeeping. They started over from nothing at forty-five and thirty-seven years old. My father did not talk about the camp. He did not talk about it ever, the rest of his life. He died in 1973 having said maybe four sentences about Tule Lake to me in twenty-eight years. There was a thing that happened at the camp — they made everybody answer a loyalty questionnaire in 1943, and my father refused to answer one of the questions the way they wanted him to, and we got moved to the segregated section of Tule Lake. The "no-no" section. I will not go into that today. I went to Stockton High School and I was a good student. I had a math teacher, Mr. Howell, who told me I should go to college. My father did not know how that was supposed to work. My mother said I should do it if I could. I went to San Joaquin Delta Junior College and then to Cal Poly for horticulture, which was the field I had loved since I was a small boy in the strawberry rows. I graduated in 1958. I came back to Stockton and went to work for the county extension office. I met Mitsuko Ishihara through the church. Her family was from Sacramento. She had been at Manzanar during the war — that was a different camp — and we found we did not need to explain certain things to each other. We were married at the Buddhist Church on East Hazelton in 1962. Janice was born in '64, Greg in '67. We bought a small house off Pershing Avenue with a VA loan — no, with a regular loan, I was thinking of a friend's story — and we paid it off in twenty-seven years. I worked at the extension office for forty-one years. I taught San Joaquin County farmers, white and Japanese-American and Mexican-American and Filipino-American, how to fight Verticillium wilt and how to set up drip irrigation and when to thin a stone-fruit crop. That was my career. I retired in 1999.\
"""

CHAPTER_3 = """\
I am eighty-nine years old. Mitsuko died in 2019, three years before COVID, which I have always been grateful for. She would not have done well in lockdown. The children visit. Janice lives in San Jose with her family. Greg is in Davis. I have three grandchildren and one great-grandchild on the way as we speak. My sister Mary passed in 2018. My brother Tom is still in Stockton, eighty-six years old, fishing two days a week at the Delta, still as stubborn as he was at ten. We see each other every Sunday. The Buddhist Church on East Hazelton is still standing, though the congregation is half what it was. The obon dance still happens every August. I went last year. The Sansei and Yonsei are running it now and that is how it should be. There is a redress check sitting in a frame in my study. Twenty thousand dollars came in 1990, with a letter signed by President Bush. My father did not live to see it. My mother did. She was eighty-two. She read the letter and folded it up and put it in her drawer and never spoke of it. The check itself she sent half of to my brother Tom and the other half to me, equal parts, "for the grandchildren." That was all she said. I have grandchildren and I will tell them what their grandparents did and what was done to their grandparents, and I have done that, when they have asked. There are still some things I keep for myself. There are conversations with Mitsuko I do not share. There are years of camp time I do not share. Not because they are unspeakable — they are speakable, and I have spoken parts of them at the Tule Lake pilgrimage when I have gone — but because some of what happened is between the people who were there, and the rest of the world does not have to know every detail of it for the truth of it to be true. The strawberry fields are condos now. The land my father leased is a Target shopping center. I drove past it last week. I drive past it sometimes when I am out doing errands. I do not stop and I do not get sad. I just look at it and I keep going. That is also a kind of remembering, I think.\
"""


CHAPTER_ANCHORS_1 = [
    "stockton", "1935", "kenji", "sumiko", "tanaka",
    "hiroshima", "picture bride", "1919", "1928",
    "ten acres", "strawberries", "tomatoes",
    "alien land law", "buddhist church", "east hazelton",
    "obon", "japanese school",
    "december seventh", "1941", "six years old",
    "two suitcases", "assembly center", "fairgrounds",
    "tule lake", "the camp", "four years",
]
CHAPTER_ANCHORS_2 = [
    "1945", "october", "the lease",
    "one-room shack", "started over", "forty-five",
    "loyalty questionnaire", "no-no",
    "my father did not talk", "1973",
    "stockton high school", "mr. howell",
    "san joaquin delta", "cal poly", "horticulture",
    "1958", "extension office",
    "mitsuko", "ishihara", "manzanar",
    "buddhist church", "1962",
    "janice", "greg",
    "pershing avenue", "forty-one years",
    "verticillium wilt", "drip irrigation",
    "1999",
]
CHAPTER_ANCHORS_3 = [
    "eighty-nine", "mitsuko died", "2019",
    "san jose", "davis", "three grandchildren",
    "mary passed", "tom", "the delta",
    "obon", "sansei", "yonsei",
    "redress", "twenty thousand", "1990",
    "my mother", "the drawer",
    "tule lake pilgrimage",
    "strawberry fields", "target", "i just look at it",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Frank Yamada (Japanese-American California)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — Strawberry rows and Tule Lake",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Building Years — Starting over and the extension office",
                runtime71_era="building_years",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Later Years — Redress and the Target shopping center",
                runtime71_era="later_years",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="regional_asian_american_california",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
