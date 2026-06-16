#!/usr/bin/env python3
"""Patricia "Pat" Frye long-narration harness — teacher + Betty.

Fictional narrator. Born 1948. Career elementary-school teacher in
Ohio. Married, three children. The point of this harness is the
recurring close-friend thread: Betty Cavanaugh, her best friend from
high school in 1964 through Betty's death in 2019. Betty appears in
all three chapters by name. This tests Lori's ability to track a
secondary named character across the narrator's biography without
either ignoring Betty (treating her as filler) or over-thread-banking
her (treating Betty as the narrator's spouse-equivalent).

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_pat_teacher_betty_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Patricia Anne Frye",
    "preferred_name": "Pat",
    "date_of_birth": "1948-04-17",
    "place_of_birth": "Akron, Ohio",
    "pronouns": "she_her",
    "pronouns_other": "",
    "current_residence": "Akron, Ohio",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:pat",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Harold Frye",
        "father_birth_date": "1918-01-01",
        "mother_name": "Dorothy Frye",
        "mother_maiden_name": "Henderson",
        "mother_birth_date": "1921-01-01",
        "siblings": [
            {"name": "Robert Frye", "birth_date": "1945-01-01", "birth_order": 1},
            {"name": "Susan Frye", "birth_date": "1951-01-01", "birth_order": 3},
        ],
    },
    "marriage": {
        "marital_status": "widowed",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "James Whitmore",
             "year_married": 1970,
             "status": "deceased_2018"},
        ],
    },
    "children": [
        {"name": "Karen Whitmore", "birth_date": "1972-08-30"},
        {"name": "David Whitmore", "birth_date": "1974-11-12"},
        {"name": "Laura Whitmore", "birth_date": "1978-03-08"},
    ],
    "education_work": {
        "highest_education_level": "masters",
        "primary_career": "Elementary school teacher (third and fourth grade)",
        "years_working": "1970-2010",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "Methodist",
        "current_faith": "Methodist",
        "ethnicity_heritage": "Scotch-Irish; English",
        "languages_at_home": "English",
    },
    "today": {
        "living_situation": "Lives alone in the family house since husband James passed in 2018",
        "health_considerations": "Otherwise well; arthritic knees",
    },
}


CHAPTER_1 = """\
I was born in Akron, Ohio, on the seventeenth of April in 1948. My father Harold was a rubber-plant worker — Goodyear, almost everyone's father worked at Goodyear or at Firestone in those days — and my mother Dorothy was a homemaker. I had an older brother Robert, who came in 1945, and then me in 1948, and then my younger sister Susan in 1951. So we were three, evenly spaced. The house was a small two-story bungalow on a street called Princeton Avenue, near where the rubber plants put up workers' housing after the war. The yard was small but my mother grew tomatoes in the side strip and roses against the back fence. I remember the roses. I started elementary school in 1953. Forrest Hill Elementary. The school was old even then, brick, three stories, the steps worn down in the middle from sixty years of children. I loved it from the first day. I was the kind of child who liked rules and liked routines and liked the smell of crayons and like the way the teacher would come stand by your desk and look down at your work and say "very nice, Patricia." That was all it took to make me happy. I knew by second grade I was going to be a teacher. There was a Miss McCullough, third grade, who I followed around. I would stay after school just to clap erasers and clean the chalkboard for her. I would have done anything for her. She was twenty-two years old and gorgeous to me and the most important person in the world. Adults forget what teachers are to second-graders. I have not forgotten. I met Betty Cavanaugh in 1962, freshman year of high school. She was assigned the desk in front of me in Mrs. Schultz's English class because we were both Catholic and I am not Catholic but our last names came up alphabetically next to each other — Betty Cavanaugh and Patricia Frye. She turned around the first day of class and said hi and that was that. We were inseparable from that day. Betty had a sharper tongue than I did, and a quicker laugh, and she was the one who got us into things, and I was the one who got us out of things. We balanced each other. Her mother was a piece of work — Mrs. Cavanaugh was the kind of mother who did not let her daughter do anything — and Betty would sneak over to our house on Princeton Avenue and tell my mother that she was studying when really we were just hiding from her mother. My mother knew. My mother always knew. My mother just made us iced tea and pretended she did not know.\
"""

CHAPTER_2 = """\
I went to Kent State for my education degree. That was 1966. Kent State was about an hour from home and it was the first time I had ever been away from Akron for more than a weekend. I lived in the dorms — McDowell Hall, third floor, a roommate from Toledo named Christine — and Betty Cavanaugh ended up at Kent State too, a year later, doing nursing. So through the back half of my college years Betty was on the same campus and we ate lunch together every Tuesday and Thursday and stayed best friends. The year I graduated was 1970. May fourth, 1970. The shootings. I had graduated in December the prior year, so I was not on campus that day, but Betty was — she was in her last year of nursing — and she was at the parking lot. She saw it. She saw two of the four students who were killed. She did not talk about it for thirty years. None of us in Akron talked about it for thirty years. Kent State was a wound this whole part of Ohio carried in silence until Betty finally talked about it on the thirtieth anniversary in 2000 and even then she only told me, she did not tell anyone else. I met James Whitmore — Jim — the summer after I graduated. He worked at his father's hardware store on Market Street and I had gone in for picture-hooks for my apartment and he stood at the counter and rang me up and the next week he called the school to ask for me out. We were married in 1970. Karen came in 1972, David in 1974, Laura in 1978. I taught third grade for thirty-five years at Forrest Hill — the same school I had started in as a child, which is one of those small symmetries that a life will hand you if you stay in one town. Miss McCullough was retired by the time I started teaching there, but she came to my retirement party in 2010, eighty-three years old by then, and she remembered me. She remembered me. Betty got married too, in 1972, to a man named Don Cavanaugh — yes, the same last name as her maiden name, that was a coincidence and a running joke at our weddings — and they had two children, Patrick and Anne. Our families were close. Karen and Patrick were the same age and were thick as thieves through elementary school. Jim and Don played golf together every other Saturday for thirty years. Betty and I went to the salon together every six weeks for color and gossip for forty-six years, from 1973 to 2019.\
"""

CHAPTER_3 = """\
Jim died in 2018. Heart attack at the kitchen sink, on a Wednesday morning, while making coffee. I came down the stairs and he was on the floor. He was seventy-two. Forty-eight years married. I do not know how to tell you what that morning was like and I am not going to try. The next year, in 2019, Betty was diagnosed with pancreatic cancer. She lived four months. I was with her at the hospice three or four days a week through all of it. We did not have to say much to each other. We had been saying things to each other since 1962. Mostly I sat in her room and held her hand and read aloud whichever book she had picked. She wanted to be read to at the end. That was the most surprising thing — Betty, who had always been the one talking, the one with the sharp tongue, wanted to be read to. The last week she stopped being able to talk much and I just read. I read a book she had loved as a girl, a book by Madeleine L'Engle, A Wrinkle in Time, which she had read in seventh grade. I read it twice through that last week. She died on a Tuesday in October. I went back to her funeral and I went back to my husband's grave the same week and I do not remember anything else from that month. The years after have been quiet. Karen lives in Columbus and visits every other weekend. David is in Cleveland with his family. Laura is in Cincinnati with hers. I have grandchildren — six grandchildren now, all healthy, all loud, all wonderful. I go to church on Sunday at the Methodist church off State Road, where I have been a member since 1972. I do volunteer tutoring at Forrest Hill twice a week — they let retired teachers come in and work with the children who are behind, which is to say the children whose parents are tired or sick or working three jobs, which is to say the children who need someone to clap erasers for them after school. I am sixteen years widowed in two more years. I am thirty-six years past Karen's wedding. I am five years past Betty. I am still here. What I would say to anyone listening is that long marriages are not made of grand things. They are made of the small thing repeated. Jim and I had coffee at the same table at six-fifteen every morning for forty-eight years. That was the marriage. Coffee at six-fifteen. And friendships like Betty's are made the same way. They are not made of the drama. They are made of every six-weeks-at-the-salon for forty-six years. Repeat the small thing. That is the whole secret. Repeat the small thing.\
"""


CHAPTER_ANCHORS_1 = [
    "akron", "1948", "harold", "dorothy", "henderson",
    "goodyear", "rubber", "princeton avenue", "robert", "susan",
    "roses", "tomatoes", "forrest hill", "1953",
    "miss mccullough", "betty cavanaugh", "1962", "freshman year",
    "mrs. schultz", "english class", "iced tea", "my mother knew",
]
CHAPTER_ANCHORS_2 = [
    "kent state", "1966", "education degree", "mcdowell hall",
    "third floor", "christine", "betty", "nursing",
    "1970", "may fourth", "the shootings",
    "the parking lot", "thirty years",
    "james", "jim", "whitmore", "market street", "picture-hooks",
    "karen", "1972", "david", "1974", "laura", "1978",
    "third grade", "thirty-five years",
    "miss mccullough", "retirement",
    "don cavanaugh", "patrick", "anne", "thick as thieves",
    "the salon", "every six weeks",
]
CHAPTER_ANCHORS_3 = [
    "jim died", "2018", "kitchen sink", "wednesday morning",
    "seventy-two", "forty-eight years",
    "betty", "2019", "pancreatic cancer", "hospice",
    "madeleine l'engle", "wrinkle in time", "tuesday in october",
    "karen", "columbus", "david", "cleveland", "laura", "cincinnati",
    "six grandchildren", "methodist church", "state road",
    "forrest hill", "tutoring",
    "six-fifteen", "coffee", "repeat the small thing",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Patricia 'Pat' Frye (teacher + Betty)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — Princeton Avenue + meeting Betty",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Building Years — Kent State, Jim, the classroom",
                runtime71_era="building_years",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Later Years — Loss + tutoring + the small thing",
                runtime71_era="later_years",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="pat_teacher_betty",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
