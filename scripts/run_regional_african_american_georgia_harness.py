#!/usr/bin/env python3
"""Regional voice harness — African American Georgia narrator.

Fictional. Born 1942 in Albany, Georgia. Father a tenant farmer.
Mother a domestic worker. Witnessed the Albany Movement of 1961-1962
firsthand as a teenager. Migrated to Detroit in 1963 for factory work.
Returned to Georgia in 2002 to retire near family.

The point of this harness: confirm Lori handles the African American
Georgia voice from VOICE_LIBRARY_v1.md correctly — coded survival
language, sacred silence around certain church/family/civil-rights
content, the Great Migration arc, the southern-to-northern-to-southern
trajectory. Specifically test that Lori does NOT ask "what was the
Code?" or otherwise demand the narrator explain in-group language.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_regional_african_american_georgia_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Mable Louise Hudson",
    "preferred_name": "Mable",
    "date_of_birth": "1942-02-10",
    "place_of_birth": "Albany, Georgia",
    "pronouns": "she_her",
    "pronouns_other": "",
    "current_residence": "Albany, Georgia",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:mable",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Clarence Hudson",
        "father_birth_date": "1915-01-01",
        "mother_name": "Ida Mae Hudson",
        "mother_maiden_name": "Wright",
        "mother_birth_date": "1919-01-01",
        "siblings": [
            {"name": "Earnest Hudson", "birth_date": "1939-01-01", "birth_order": 1},
            {"name": "Lillian Hudson", "birth_date": "1945-01-01", "birth_order": 3},
            {"name": "Frank Hudson", "birth_date": "1948-01-01", "birth_order": 4},
        ],
    },
    "marriage": {
        "marital_status": "widowed",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "Otis Bell", "year_married": 1965, "status": "deceased_2005"},
        ],
    },
    "children": [
        {"name": "Charlene Bell", "birth_date": "1966-08-15"},
        {"name": "Bernard Bell", "birth_date": "1969-03-04"},
    ],
    "education_work": {
        "highest_education_level": "high_school",
        "primary_career": "Auto plant line worker (Ford River Rouge); later school cafeteria",
        "years_working": "1963-2005",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "African Methodist Episcopal (AME)",
        "current_faith": "AME",
        "ethnicity_heritage": "African American (southwest Georgia)",
        "languages_at_home": "English",
    },
    "today": {
        "living_situation": "Lives in the family home she returned to in 2002",
        "health_considerations": "Otherwise well",
    },
}


CHAPTER_1 = """\
I was born in Albany, Georgia, on February the tenth, 1942. My daddy Clarence was a tenant farmer outside town — he worked the Mr. Coleman place, cotton mostly, some peanuts — and my mama Ida Mae did day work for white families in town. I had an older brother Earnest, and then me, and then my baby sister Lillian came in '45, and our brother Frank in '48. The house was small, two rooms and a kitchen, the floor was wood that my mama swept clean every morning. The water was from a pump out back. The outhouse was further back than that. We were not poor in the way people think poor — we ate, my mama could make a meal out of whatever was in the garden — but the money was tight all the time. My daddy worked from dark to dark and what came back at the end of the year, after Mr. Coleman took his share, was not much. The church was Mount Olive AME, and church on Sunday was a whole day, not a one-hour service. The morning service, the afternoon dinner on the grounds, the evening service. The choir was led by Mother Hampton, who was a big woman with a voice that could move the rafters. I was a little girl who could sing, and Mother Hampton put me in the children's choir at six years old, and I stayed in that choir until I was sixteen. I learned what I knew about music from her, and what I knew about how grown people talk to each other from sitting under her watching her work the room after service. There were things you did not talk about in front of certain people, even in our own church. There was a way grown folk would shift their words when somebody new came in. There was a way my mama would talk to white folks when she came home from a day's work, and that was not how my mama talked to my daddy at the kitchen table, and the children knew without being told that you did not mix up the two. You learned. You had to. We did not go into Albany itself much when I was little. Albany was for the white people. The colored part — Lincoln Heights, Harlem — was where you went if you had to get to certain stores. My daddy would say be careful and you would be careful. The summer I was eleven, Mr. Coleman raised our rent on the field and my daddy could not pay it, and we had to leave the place, and we moved into a house in Lincoln Heights with my mama's people. Things were tighter after that. My mama took on a second job. My daddy did day work where he could find it. But we made it. The thing about that time and that place is that everybody made it because everybody made it. The church helped you. The neighbor helped you. You did not have to ask. You did not have to explain. You showed up at somebody's door and they fed you and that was that.\
"""

CHAPTER_2 = """\
By 1961 I was a senior at Monroe High School and Albany had a movement starting. Dr. King came down in December of that year, and the Albany Movement had already been organized before he came, but he came and the place came alive. The mass meetings. The singing. The marches. The arrests. I was nineteen by then, working at the Tom's Coffee Shop downtown washing dishes, and I would slip out at night to the mass meetings at Shiloh Baptist or Mount Zion. My mama did not want me there. She was afraid. She had reason. She had buried three cousins and a brother already in her life and she did not want to bury a daughter. I went anyway. I sang. I marched once. I never went to jail, but I knew people who did. Some of them did not come back the same way they went in. I am not going to talk about that today. The movement did not work in Albany the way it later worked in Birmingham, and the newspapers wrote about Albany as Dr. King's failure, and that was not the story we who were there knew. The story we knew was different. Anyway, in 1963 my brother Earnest had gone north to Detroit and gotten on at Ford, at the River Rouge plant, and he wrote my daddy that they were hiring colored men and that the wages were better than anything in Georgia, and so I left. I left Albany on a Greyhound bus the third week of August 1963, by myself, with one suitcase and forty-two dollars and the address of Earnest's rooming house in Detroit. I was twenty-one. I worked at Ford for eighteen months before I met Otis Bell. He was from Mississippi originally, but he had been in Detroit since '54 and he was settled. We were married in 1965. Charlene came in '66, Bernard in '69. The riots happened the summer of '67, which we lived through and which I will not go into either. We stayed in Detroit. We bought a house on the west side, off Plymouth Road, three bedrooms and a yard. Otis worked thirty-eight years at Ford and retired in 1992. I worked at Ford for twelve years and then I left the plant for a school cafeteria job, which suited me better because the children needed somebody and the schools were good to me. I worked the cafeteria at Brown Elementary from 1975 to 2005, when I retired. The hardest thing in Detroit was not Detroit. Detroit was good to us. The hardest thing in Detroit was being a long way from my mama. She had stayed in Albany. She came up to visit twice a year for the first ten years and then she could not travel anymore. She died in 1988 and the funeral was the first time I had been back to Albany in twenty years.\
"""

CHAPTER_3 = """\
Otis died in 2005. Heart attack at sixty-three. The kids were grown — Charlene was in Atlanta with her family, Bernard in Detroit still — and I sat in the house on Plymouth Road for a year by myself and I thought about whether this was where I was going to die. I decided no. I came home. I sold the Detroit house in the spring of 2006 and I came back to Albany. The family home was empty — my mama and daddy both gone, my brother Earnest had passed in 2004 — and Lillian and her family had been keeping it up. I bought it from her. I have been here ever since, eighteen years going on nineteen. Lillian and Frank are still here in Albany. We are old now, all three of us. We see each other every Sunday at Mount Olive, which is the same church I sang in as a little girl seventy-five years ago. Mother Hampton's granddaughter, Pamela, is the choir director now, which is one of those things that lets you know how long you have lived. Charlene and Bernard come down twice a year. I have four grandchildren and one great-grandchild. The great-grandbaby is named Mable, after me, which I tried to talk Bernard's daughter out of, but she would not be talked out of it, and so there is a little Mable Hudson Bell-Diggs walking around Atlanta now, three years old, who looks at me with my own face. What I would say to anybody listening is this. The South was hard. The North was hard. Both of them were hard in different ways. I do not want to make either one of them into a story it is not. Detroit gave us Ford wages and a house, which my parents could never have had. Georgia gave me the church and the singing and the way my mama swept the floor every morning, which I still do even now. I had to leave Georgia to know how to come back to Georgia. You may not understand that until you have done it yourself. The movement work mattered. I will not go further into that today. There are some things I keep for the people who were there with me. That is how it has to be sometimes. I do not have to explain it to anybody who was not there. I just want to say it mattered, and it did not fail in Albany the way the newspapers said it failed, and the people who were in the basement of Shiloh Baptist in 1961 know what we did and what we are still doing. That has to be enough.\
"""


CHAPTER_ANCHORS_1 = [
    "albany", "1942", "clarence", "ida mae", "wright",
    "tenant farmer", "mr. coleman", "cotton", "peanuts",
    "earnest", "lillian", "frank",
    "two rooms", "the pump", "the outhouse",
    "mount olive", "ame", "mother hampton",
    "children's choir", "six years old",
    "lincoln heights", "harlem",
    "1953", "rent",
    "the neighbor", "showed up at somebody's door",
]
CHAPTER_ANCHORS_2 = [
    "1961", "monroe high school", "albany movement",
    "dr. king", "december", "mass meetings",
    "shiloh baptist", "mount zion",
    "tom's coffee shop", "washing dishes",
    "my mama did not want me there",
    "earnest", "detroit", "ford", "river rouge", "1963",
    "twenty-one", "greyhound", "forty-two dollars",
    "otis", "mississippi", "1965",
    "charlene", "bernard",
    "the riots", "1967",
    "plymouth road", "thirty-eight years",
    "brown elementary", "cafeteria",
    "twice a year", "mama died", "1988",
]
CHAPTER_ANCHORS_3 = [
    "otis died", "2005", "sixty-three",
    "charlene", "atlanta", "bernard", "detroit",
    "2006", "sold the house",
    "the family home", "lillian", "frank",
    "mount olive", "pamela", "choir director",
    "four grandchildren", "great-grandbaby", "mable",
    "the church", "the singing", "the way my mama",
    "shiloh baptist", "1961",
    "i do not have to explain",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Mable Hudson (African American Georgia)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — Cotton land + Mount Olive AME",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Building Years — Movement, Greyhound, Detroit",
                runtime71_era="building_years",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Later Years — Coming home to Albany",
                runtime71_era="later_years",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="regional_african_american_georgia",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
