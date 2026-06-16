#!/usr/bin/env python3
"""Regional voice harness — Native American New Mexico (Pueblo).

Fictional. Born 1947 at Cochiti Pueblo, New Mexico. Drummer / potter
family. Sent to St. Catherine Indian School in Santa Fe for boarding.
Came back to the Pueblo as a young man. Married within the Pueblo.
Worked for the Bureau of Indian Affairs and then as the Pueblo's
cultural-preservation officer until retirement.

The point: VOICE_LIBRARY_v1.md Native American New Mexico voice has
HIGH suppression — sacred Pueblo knowledge does not leave the village.
Lori must NOT ask for ceremony details, kachina names, kiva content,
or clan structure. The "remember but never tell" rule from Crypto-
Jewish lineage applies in modified form here too.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_regional_native_american_new_mexico_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Joseph Quintana",
    "preferred_name": "Joe",
    "date_of_birth": "1947-08-04",
    "place_of_birth": "Cochiti Pueblo, New Mexico",
    "pronouns": "he_him",
    "pronouns_other": "",
    "current_residence": "Cochiti Pueblo, New Mexico",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:joe_quintana",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Frank Quintana",
        "father_birth_date": "1920-01-01",
        "mother_name": "Elena Quintana",
        "mother_maiden_name": "Aguilar",
        "mother_birth_date": "1924-01-01",
        "siblings": [
            {"name": "Andrew Quintana", "birth_date": "1945-01-01", "birth_order": 1},
            {"name": "Mary Quintana", "birth_date": "1950-01-01", "birth_order": 3},
        ],
    },
    "marriage": {
        "marital_status": "married",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "Theresa Quintana (née Suina)",
             "year_married": 1972, "status": "current"},
        ],
    },
    "children": [
        {"name": "Frank Quintana Jr.", "birth_date": "1974-05-12"},
        {"name": "Maria Quintana", "birth_date": "1977-09-08"},
    ],
    "education_work": {
        "highest_education_level": "bachelors",
        "primary_career": "BIA field officer; Pueblo cultural-preservation officer",
        "years_working": "1970-2012",
    },
    "military": {"served": True,
                 "branch": "Army (drafted)",
                 "service_dates": "1968-1970",
                 "rank": "Specialist",
                 "units": "Vietnam — combat engineer",
                 "locations": "Long Binh; Pleiku",
                 "wars_conflicts": "Vietnam",
                 "decorations": "",
                 "experience_notes": "Two years; came home; do not ask further."},
    "faith": {
        "religion_raised": "Cochiti Pueblo traditional + Catholic (parallel)",
        "current_faith": "Cochiti Pueblo traditional + Catholic",
        "ethnicity_heritage": "Cochiti Pueblo",
        "languages_at_home": "Keres and English",
    },
    "today": {
        "living_situation": "Lives at the Pueblo with wife Theresa",
        "health_considerations": "Otherwise well",
    },
}


CHAPTER_1 = """\
I was born at Cochiti Pueblo on the fourth of August in 1947. My father Frank was a drummer for the kiva — that is something I can tell you, that he was a drummer — and my mother Elena was a potter, like her mother and her grandmother. The Cochiti black-on-cream pottery you may have seen in a museum, she was one of the potters who kept that tradition going through the hard middle years of the twentieth century. We lived in the old part of the village, in a house my father had built onto from his grandfather's house, which his grandfather had built from his grandfather's house. The walls were two feet thick. The roof was vigas and latillas. The fire was juniper in winter. I had an older brother Andrew, who was two years older than me, and a younger sister Mary, who came three years after me. I will tell you what I can tell you about my childhood. We were a Catholic family on the outside and a traditional Cochiti family on the inside, which is how most Pueblo families have been for four hundred years. My mother went to Mass at St. Bonaventure, which is the church the Spanish built at the Pueblo in 1628, and we children went with her. My father did some of the Catholic things and not other ones. He was a drummer and his place was at the kiva and his calendar was the calendar of the kiva, which is a thing that has not been changed in many centuries and is not going to be changed by me telling stories about it on a recording. So I will not tell you about that part. I will tell you what the village looked like in the morning when the women started baking bread in the outdoor ovens. I will tell you what the air smelled like when the wind came down off the Sangre de Cristos and through the canyon and into the village. I will tell you what it sounded like when the old people sat on the bench by the well and talked Keres at evening, and the children who were learning Keres listened and the children who were not learning Keres listened harder because they knew they were losing something. We had our own school in the village until 1953 when I started, and then the government took me to St. Catherine Indian School in Santa Fe at age seven, and I lived in a dormitory until I was eighteen, and that was the boarding school they sent us to to make us Americans. I will not talk about that today either. I will say that I came home every summer, and I came home for good when I was eighteen, and the Pueblo took me back even though I had been gone, and that is something the Pueblo does that not every place does.\
"""

CHAPTER_2 = """\
I was drafted in 1968. I was twenty-one. I was at the Pueblo when the letter came. I went to Albuquerque for the induction physical and from there to Fort Bliss for basic, and from there to Long Binh, Vietnam. I served as a combat engineer for two years. I came home in 1970. I am not going to talk about that on a recording. I made peace with what I had to make peace with at the kiva when I came back. The people who needed to know what happened to me knew. The rest of the world does not need to know. I went to college on the GI Bill at the University of New Mexico. I studied anthropology, because I wanted to understand how the outside world looked at us, and after I graduated in 1974 I went to work for the Bureau of Indian Affairs at the Albuquerque area office. I worked there for sixteen years. The BIA was a complicated place to work for somebody from a Pueblo. We were inside the institution that had made the policies that had broken our grandparents, and we were also inside the institution that was the only place to fight for our people in writing the next round of policies. Both of those things were true. I did what I could from the inside. In 1990 the Pueblo asked me to come back as our cultural-preservation officer. The position was new. It was created in response to the Native American Graves Protection and Repatriation Act, NAGPRA — Congress had just passed it that year and the Pueblos needed people who could speak both languages, the BIA bureaucratic language and the village language. I was qualified. I came back. I worked from 1990 to 2012 as the Pueblo's CPO. We brought home ancestors that had been in museums for a hundred years. We brought home grave goods from Harvard. From the Smithsonian. From the Field Museum in Chicago. From the University of Pennsylvania. Every one of those negotiations took years. Some of them took the entire twenty-two years I was in the job. They are still ongoing. The Pueblo elders made all the decisions about what came home, and what the protocols were when it came home, and what was buried where. That part is not for me to talk about. My job was the paperwork, the meetings, the letters, the phone calls. I was the one who got on the plane to fly to Boston to sit across from a museum curator and explain what NAGPRA required. I was the one who did that work for twenty-two years. And then I retired.\
"""

CHAPTER_3 = """\
I am seventy-seven years old. Theresa and I have been married fifty-two years. She is from Cochiti as well — her maiden name is Suina — and she has been my partner in everything since 1972. Our son Frank Jr. is fifty. He lives at the Pueblo with his family. He is a drummer like his grandfather was. Our daughter Maria is forty-seven. She is in Santa Fe with her family. She makes pottery like her grandmother did. So the line continues. We have four grandchildren and two great-grandchildren. The Pueblo is changing. The young people drive to Santa Fe for work. The young people post things on Instagram. The young people are bilingual in a way my generation was not bilingual — they speak English fluently and Keres fluently, where my generation was punished for speaking Keres at boarding school and lost some of it. So they have something we did not have. They also do not have some things we had, because the elders who taught me are now passed, and what they taught was not all passed on because they could not pass all of it on. That is the truth of it. We held what we could hold. Some of it slipped between the generations. We are doing what we can. The boarding school in Santa Fe — St. Catherine — was closed in 1998. There are now memorial events for the children who did not come back from it. My older brother Andrew did not come back from it, in the sense that he made it home but he was never the same. He drank for thirty years and he died in 1989 at forty-four. Mary, my sister, who went there too, did better. She is in Albuquerque now, retired teacher, three grown children. The thing I want to say to anybody listening is this. There are stories that do not leave the village. There are songs that do not leave the kiva. There are names that do not get written down. That is not because we are hiding. That is because some things are alive only when they are held in the right place by the right people. When you put them on a recording and you send them around the world, they are not alive anymore. They are something else. So when I have not told you certain things on this recording, that is what I am doing. I am keeping the things that need to be kept where they need to be kept. I am telling you the things that can be told. I trust that you understand the difference.\
"""


CHAPTER_ANCHORS_1 = [
    "cochiti pueblo", "1947", "frank", "elena", "aguilar",
    "drummer", "kiva", "potter", "black-on-cream",
    "andrew", "mary", "vigas", "latillas",
    "st. bonaventure", "1628", "spanish",
    "catholic on the outside", "traditional on the inside",
    "outdoor ovens", "sangre de cristos", "the well",
    "keres", "the children who were not learning",
    "st. catherine", "santa fe", "boarding school",
    "1953", "age seven",
]
CHAPTER_ANCHORS_2 = [
    "drafted", "1968", "twenty-one",
    "fort bliss", "long binh", "vietnam",
    "combat engineer", "1970",
    "the kiva when i came back",
    "gi bill", "university of new mexico", "anthropology",
    "1974", "bureau of indian affairs", "bia",
    "albuquerque area office", "sixteen years",
    "1990", "cultural-preservation officer",
    "nagpra", "harvard", "smithsonian", "field museum",
    "university of pennsylvania",
    "twenty-two years",
    "2012",
]
CHAPTER_ANCHORS_3 = [
    "seventy-seven", "theresa", "suina", "fifty-two years",
    "frank jr.", "drummer", "grandfather",
    "maria", "santa fe", "pottery",
    "four grandchildren", "two great-grandchildren",
    "the young people", "instagram", "keres",
    "boarding school", "1998",
    "andrew", "1989", "forty-four", "mary",
    "the stories that do not leave",
    "names that do not get written down",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Joe Quintana (Cochiti Pueblo)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — The village and the boarding school",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Building Years — Vietnam, BIA, NAGPRA",
                runtime71_era="building_years",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Later Years — What stays at the Pueblo",
                runtime71_era="later_years",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="regional_native_american_new_mexico",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
