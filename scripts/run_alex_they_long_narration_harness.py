#!/usr/bin/env python3
"""Alex Park (they/them) long-narration harness.

Fictional narrator. They/them pronouns. Born 1988. Came out as
nonbinary in 2014. Software engineer in Seattle. Korean-American.

The point of this harness: confirm Lori's reflection layer handles
they/them pronouns CORRECTLY (no he/she misgendering, no avoidance,
no "they (singular)" awkward gloss). Anchors include kinship terms
("my mom and dad") in singular while subject is plural-grammatical.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_alex_they_long_narration_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Alex Eunseo Park",
    "preferred_name": "Alex",
    "date_of_birth": "1988-09-14",
    "place_of_birth": "Seattle, Washington",
    "pronouns": "they_them",
    "pronouns_other": "",
    "current_residence": "Seattle, Washington",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:alex",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Sang-Ho Park",
        "father_birth_date": "",
        "mother_name": "Min-Jung Park",
        "mother_maiden_name": "Kim",
        "mother_birth_date": "",
        "siblings": [
            {"name": "Jamie Park", "birth_date": "1991-04-22", "birth_order": 2},
        ],
    },
    "marriage": {
        "marital_status": "partnered_not_married",
        "number_of_marriages": 0,
        "spouses": [
            {"name": "Sam Rivera", "year_married": "", "status": "current_partner"},
        ],
    },
    "children": [],
    "education_work": {
        "highest_education_level": "bachelors",
        "primary_career": "Software engineer",
        "years_working": "2010-present",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "Catholic (Korean)",
        "current_faith": "None / spiritual but not religious",
        "ethnicity_heritage": "Korean American",
        "languages_at_home": "Korean and English",
    },
    "today": {
        "living_situation": "Lives in Seattle with partner Sam Rivera",
        "health_considerations": "Otherwise well",
    },
}


CHAPTER_1 = """\
I was born in Seattle in 1988. My parents had come over from Seoul in 1985 — my mom and dad, Min-Jung and Sang-Ho — and they were running a dry cleaner on Capitol Hill when I was little. My mom worked the counter. My dad ran the back. They did not talk much in front of me. They were tired. They were always tired. I was an only child until I was three and then my brother Jamie came along, and after that the house was always a little louder, which I needed. My memory of being very little is the smell of the dry cleaning chemicals, the press of the steam machine, the bell on the door when a customer came in. I would sit at the counter with my mom and color while she did the tickets. My dad would come out from the back smelling like cleaning fluid and ruffle my hair and go back. We spoke Korean at home. I did not speak English until I went to kindergarten. The first year of school I was the kid who did not talk, and the teacher kept asking my mom if I was okay, and my mom kept saying I was fine, I was just thinking. Which was true. I was thinking. I was thinking about everything. I was thinking about why the other kids' families ate sandwiches and we ate kimchi-jjigae. I was thinking about why my mom called me by my Korean name Eunseo at home and my school called me Alex. I was thinking about why my mom wore a cross to church and my school did not seem to know what Catholic was. I was the only Asian kid in my class for the first three years, and then a Vietnamese family moved in down the block and there were two of us, and then more, and by the time I was in middle school the school was actually pretty mixed. But for those first three years I was the kid who did not speak and the kid who was different and the kid who watched. I learned a lot from watching. I learned that white kids' parents did not stand at the school gate the way my mom did. I learned that other kids could ask their parents for things at the dinner table, and that I could not, that asking at our dinner table was not how it worked, that my dad would shake his head and that would be the end of it. I learned that I was supposed to be grateful for the cleaner and for the house and for the fact that we were here at all, because we were here at all, because they had crossed an ocean to put us here.\
"""

CHAPTER_2 = """\
College took me to the University of Washington. Computer science. My parents were happy about that — engineering was respectable, engineering paid, engineering had a clear path. I was happy too, mostly. I was good at it. I got an internship the summer after sophomore year at a small startup that turned into a bigger company that I won't name. I was nineteen, twenty, doing real software work, getting paid more than my parents had ever made. I sent money home. I felt good about that. The thing I did not tell my parents about, the thing I did not tell most people about for a long time, was that something was wrong, or not wrong exactly, but I was not what I was supposed to be. I had grown up being told I was a girl. I had a girl's Korean name, a girl's English name, I had been put in dresses at the Korean church, I had played with the other girls at school. And I had never felt right in any of it. I had assumed for years that everyone felt like that, that it was just life, that it was just being a teenager. But it kept not going away. It got worse, actually, the further into my twenties I went. The body issues. The discomfort at being she'd. The way I avoided pictures. The way I dressed myself to be unreadable. I came out as nonbinary in 2014. I was twenty-six. I did it gradually. First to my best friend from college, who I had been roommates with sophomore year and who was the safest person in my life at the time. Then to a few coworkers. Then to my brother Jamie, who is younger than me but who took it better than anyone else and who has been the best ally I have. Then a year later — only a year later — to my parents. That was the hard one. My mom cried. Not in anger. In grief. She kept asking what she had done wrong and I kept telling her she had done nothing wrong, that this was not about her, that I was still her child, that I just needed her to use the right name and the right pronouns. My dad did not say anything for almost a year. He did not stop speaking to me. He just stopped knowing what to say. And then on my twenty-eighth birthday he sent me a text in Korean. It said "I am proud of who you are. I am still learning. Be patient with me." And I cried for an hour reading that text and I have it saved still.\
"""

CHAPTER_3 = """\
I am thirty-six. I live with my partner Sam in a small house on the edge of Capitol Hill, not far from where the dry cleaner used to be. The cleaner is gone — my parents retired in 2018 and sold the business, the building got demolished and turned into condos, and they moved out to Bellevue. I see them every other Sunday. My mom calls me Alex now. My dad calls me Alex now. They use they when they refer to me to other people, which I know was hard for them, which I know is still sometimes hard for them, because Korean does not have gendered pronouns the way English does and they are translating in their head every time. They are doing the work. Sam and I have been together five years. We are not married. We may or may not get married. We talk about kids sometimes and then we don't talk about it for six months and then we talk about it again. Jamie and his wife have a baby now, my niece Soo-bin, who is the brightest thing in the family. I see her every weekend if I can. I am an aunt-uncle figure to her. My mom calls me her samchon-imo, which is a made-up word, a smash of the Korean for uncle and the Korean for aunt, and I love that my mom invented a word for me, which is what her generation never knew was a thing you could do. At work I do machine learning now. I lead a small team. I have been at the same company nine years, which is unusual in software, and the reason is that they have done right by me. They put my pronouns in the directory the day I came out. They covered surgery I needed. They did not make me explain. The thing I would say to anyone listening — and I am thinking specifically of any other people like me who are being told they are someone they are not — is that the people who matter will catch up. They will take time. They will fumble. My mom called me by my old name for two years after I came out, by accident every time, and corrected herself every time. The fumbling is not a sign that they are not trying. The fumbling is a sign that they are trying. Wait for them. And in the meantime, find your Jamie. Find the person in your family who gets it first. Hold on to them.\
"""


CHAPTER_ANCHORS_1 = [
    "seattle", "1988", "min-jung", "sang-ho", "park",
    "dry cleaner", "capitol hill", "korean", "kimchi", "kindergarten",
    "jamie", "eunseo", "catholic", "the bell", "the cleaner",
    "steam machine",
]
CHAPTER_ANCHORS_2 = [
    "university of washington", "computer science", "internship",
    "startup", "nonbinary", "2014", "twenty-six", "roommate",
    "brother jamie", "korean", "my mom cried", "twenty-eighth birthday",
    "text in korean", "proud of who you are",
]
CHAPTER_ANCHORS_3 = [
    "thirty-six", "sam", "rivera", "capitol hill", "bellevue",
    "they", "machine learning", "nine years", "surgery",
    "soo-bin", "samchon-imo", "jamie", "wait for them",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Alex Eunseo Park (they/them)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — Capitol Hill",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Coming of Age — UW + coming out",
                runtime71_era="coming_of_age",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Today — Thirty-six and grounded",
                runtime71_era="today",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="alex_they_long_narration",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
