#!/usr/bin/env python3
"""Regional voice harness — Hispano + Tex-Mex (border generations).

Fictional. Born 1939 in Brownsville, Texas. Father a railroad worker
on the Mexican side, mother a Tejana whose family had been in South
Texas since the 1700s — pre-Anglo settlement. The narrator's family
straddles the border in the way many Hispano/Tex-Mex families do:
Spanish, Mexican, Texan, US, all overlapping. Catholic. Spanish at
home until starting school.

The point: VOICE_LIBRARY_v1.md Hispano + Tex-Mex voice includes the
"Sunday voice vs. Monday voice" code-switching, the "imposed name"
school experience (e.g. "Tomasita" → "Tommie"), and pride in pre-
Anglo land. Lori must NOT collapse Mexican-American / Tex-Mex /
Hispano into a single Hispanic category, and must NOT translate
Spanish phrases the narrator uses for affect (these are signal, not
gap).

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_regional_hispano_tex_mex_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Tomasita Guadalupe Reyes Cantú",
    "preferred_name": "Tomasita",
    "date_of_birth": "1939-12-12",
    "place_of_birth": "Brownsville, Texas",
    "pronouns": "she_her",
    "pronouns_other": "",
    "current_residence": "Brownsville, Texas",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:tomasita",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Roberto Reyes",
        "father_birth_date": "1908-01-01",
        "mother_name": "Guadalupe Reyes",
        "mother_maiden_name": "Cantú",
        "mother_birth_date": "1915-01-01",
        "siblings": [
            {"name": "Refugio Reyes", "birth_date": "1936-01-01", "birth_order": 1},
            {"name": "Esperanza Reyes", "birth_date": "1942-01-01", "birth_order": 3},
            {"name": "Manuel Reyes", "birth_date": "1945-01-01", "birth_order": 4},
        ],
    },
    "marriage": {
        "marital_status": "widowed",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "Domingo García",
             "year_married": 1960, "status": "deceased_2008"},
        ],
    },
    "children": [
        {"name": "Roberto García", "birth_date": "1962-04-22"},
        {"name": "Yolanda García", "birth_date": "1965-08-30"},
        {"name": "Hector García", "birth_date": "1968-11-15"},
    ],
    "education_work": {
        "highest_education_level": "high_school",
        "primary_career": "Seamstress and tortilleria owner",
        "years_working": "1957-2010",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "Roman Catholic (Marian devotion, La Virgen de Guadalupe)",
        "current_faith": "Roman Catholic",
        "ethnicity_heritage": "Tejana (Spanish colonial + Mexican); family in South Texas since 1740s",
        "languages_at_home": "Spanish and English",
    },
    "today": {
        "living_situation": "Lives in the family home in Brownsville near the church",
        "health_considerations": "Otherwise well",
    },
}


CHAPTER_1 = """\
Nací el doce de diciembre de mil novecientos treinta y nueve — I was born on the twelfth of December, 1939, the day of La Virgen de Guadalupe, which is why my mama named me Tomasita Guadalupe. My papá Roberto worked on the railroad, on the Mexican side mostly, the Ferrocarril Nacional out of Matamoros. He would cross the bridge in the morning and cross back in the evening. My mama Guadalupe — she was a Cantú on her mother's side, and the Cantús had been in South Texas before Texas was Texas, before it was the Republic, before it was even Mexico. The land grant was from the Spanish crown in 1749. The family kept it through the Mexican period, through the Texas Revolution, through the Civil War, through the Tejano expulsions in some places that did not happen as bad to us as it did to others. My mama would say that and she would say it again. La tierra ha sido de nosotros desde antes que llegaran ellos. The land has been ours since before they came. I had an older brother Refugio, and then me, and then my little sister Esperanza in '42, and then Manuel in '45. Four of us. The house was on Calle del Cuervo near the iglesia de la Inmaculada Concepción, where my mama went to Mass every morning at six. The neighborhood was completely Spanish-speaking when I was little. Brownsville was a Mexican-American town then. The Anglos were on the other side of Boca Chica Boulevard mostly. We did not see them much. My first language was Spanish. I started school at Cuauhtémoc Elementary in 1945 and the school was English-only by then — the teachers would slap your hand with a ruler if you spoke Spanish on the playground — and on the first day of school the teacher said my name was Tomasita and she said no, your name will be Tommie. And I was Tommie from 1945 until I was fifteen and I went back to Tomasita. So I had two names for ten years. The Sunday name and the Monday name. The Sunday name was Tomasita Guadalupe at Mass, and the Monday name was Tommie at school. My mama always called me Tomasita. My friends called me Tommie. My grandmother called me Mija and my grandfather called me Hijita. So I had four names depending on who was looking at me, which I tell you because that is what it was like to be a Tejana child in those years. The schools wanted to make you American. The Church wanted to make you Catholic. The family wanted to make you Cantú. And you grew up trying to be all three at once.\
"""

CHAPTER_2 = """\
I met Domingo García at a dance at the parish hall in 1957. I was seventeen. He was nineteen. He was from Matamoros — he had been born on the Mexican side and brought across as a baby in 1939 — and his family had ended up in Brownsville too, on the south side. We were married in 1960 at Inmaculada Concepción. Roberto came in 1962, Yolanda in 1965, Hector in 1968. Three kids in six years. I was a seamstress at first — I had been sewing since I was eight, my mama had taught me — and I would take in piecework from the dress factories. Then in 1972 my mama and I opened a small tortillería on Sixth Street. Two windows, three tables, a comal in the back, my mama's recipes for the dough and the salsa. We called it Las Dos — The Two — for my mama and me. We ran that place for thirty-eight years. Domingo worked at the port. The Port of Brownsville was getting bigger in those years and he was a longshoreman, which paid well for South Texas in the 1960s and 1970s. He worked the docks for thirty-five years. He came home tired every night. He came home smelling of the ocean and the diesel. He was a good man to me, all those years. He did not drink much. He went to Mass with me on Sunday. He played guitar in the evenings. He sang corridos he had learned from his uncles. When the kids were growing up he would sit on the porch with his guitar and the children of the whole street would come and listen. We sent all three kids to college. Roberto went to UT-Pan American — what they now call UT Rio Grande Valley — and became a teacher. Yolanda went to St. Edward's in Austin and became a lawyer. She works on immigration cases now, which makes sense to me, you know, given what our family has lived. Hector went to UT-Austin and is an engineer and lives in San Antonio. So that is the story of the second part. Hard work, a tortillería, three children who all turned out, a husband who was good to me. That is the part you can put in a book and people will say "what a nice story." The part you do not put in a book is what it cost to send three Mexican-American kids to college in those years, and what it cost my mama to keep the tortillería running through the chemo when she was sick in 1991 and through her stroke in 1994, and what it cost Domingo to work the port for thirty-five years and come home tired every night. The hidden cost. La cuenta que no se ve. That is what it really was.\
"""

CHAPTER_3 = """\
I am eighty-five years old. Domingo passed in 2008. The tortillería I ran for two more years after that and then I closed it in 2010 — sold the building, gave most of the equipment to a young family who was starting one on the south side. The kids are grown and good. Roberto is a school principal in Harlingen. Yolanda is in Brownsville too now, after years in Austin, and she runs an immigration clinic. Hector and his wife are in San Antonio with my grandbabies — three of them — and they come down for Easter and Thanksgiving and every Christmas. I have seven grandchildren and four great-grandchildren. The neighborhood is changing. The street I grew up on is half Anglos now — they are calling it gentrification, that is the word, and the houses my grandfather's grandfather built are being bought up and torn down and replaced. The iglesia is still standing. Father Estrada is still saying the Spanish Mass at six in the morning. I still go. My grandbabies do not all speak Spanish. The oldest does. The next two do not. The youngest is learning. So the language is going in some branches of the family and staying in other branches, which is how it goes. My sister Esperanza died in 2019. She lived in Houston, married into the Cisneros family, and was a teacher for forty years. My brothers are still here in Brownsville. Refugio is eighty-eight and Manuel is seventy-nine. We have lunch on Sunday after Mass with whoever can come. The Sunday I tell you about is the Sunday that has been happening for sixty years. The faces around the table change. The food is the same. La cocina de mi mama. The kitchen of my mother. I want to say to anybody listening that being Tejana means you belong to both sides and you belong to neither side and that has been the truth since 1749 when the Spanish crown gave my family that land. My grandkids the ones who do not speak Spanish are still Tejanos. They will figure it out. They are still ours. La sangre no se cambia. The blood does not change.\
"""


CHAPTER_ANCHORS_1 = [
    "doce de diciembre", "1939", "la virgen de guadalupe",
    "tomasita", "guadalupe", "roberto", "ferrocarril",
    "matamoros", "cantú", "1749", "spanish crown",
    "la tierra", "antes que llegaran ellos",
    "refugio", "esperanza", "manuel",
    "calle del cuervo", "inmaculada concepción",
    "boca chica", "cuauhtémoc elementary",
    "english-only", "the ruler", "tommie",
    "mija", "hijita",
    "the sunday name", "the monday name",
]
CHAPTER_ANCHORS_2 = [
    "1957", "dance", "parish hall", "domingo",
    "garcía", "1939", "1960",
    "yolanda", "hector",
    "seamstress", "piecework",
    "1972", "tortillería", "sixth street",
    "las dos", "comal", "thirty-eight years",
    "port of brownsville", "longshoreman",
    "thirty-five years", "corridos",
    "ut-pan american", "ut rio grande valley", "teacher",
    "st. edward's", "lawyer", "immigration",
    "ut-austin", "engineer", "san antonio",
    "1991", "chemo", "1994", "stroke",
    "la cuenta", "the hidden cost",
]
CHAPTER_ANCHORS_3 = [
    "eighty-five", "2008", "2010",
    "harlingen", "principal",
    "brownsville", "immigration clinic",
    "san antonio", "three grandbabies",
    "seven grandchildren", "four great-grandchildren",
    "gentrification",
    "father estrada", "six in the morning",
    "the oldest does", "the youngest is learning",
    "esperanza", "2019", "houston", "cisneros",
    "refugio", "manuel",
    "la cocina de mi mama",
    "tejana", "belong to both sides",
    "la sangre",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Tomasita Reyes Cantú (Hispano + Tex-Mex)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — Brownsville and four names",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Building Years — Domingo, the tortillería, the port",
                runtime71_era="building_years",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Later Years — La sangre no se cambia",
                runtime71_era="later_years",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="regional_hispano_tex_mex",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
