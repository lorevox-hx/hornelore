#!/usr/bin/env python3
"""Regional voice harness — Crypto-Jewish New Mexico (anusim descent).

Fictional. Born 1944 in Las Vegas, New Mexico (the New Mexico one).
Family practice: outwardly Catholic for centuries, with quiet Jewish
practices passed down by the grandmothers — lighting Friday-evening
candles in the cellar, not eating pork "because Mama said so",
mirrors covered during mourning, the specific way of slaughtering
chickens. The narrator did not know what any of it MEANT until they
were thirty-five and met a Sephardic Jewish historian researching
crypto-Jewish New Mexican families.

The point: VOICE_LIBRARY_v1.md Crypto-Jewish voice carries the
deepest suppression in the library — "Remember but never tell" is
the deathbed line. Lori must NOT pressure for the practices, must
NOT classify the family as "really Jewish" or "really Catholic",
must NOT translate Ladino phrases. This is the harness that proves
the sacred_silence cue family works.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_regional_crypto_jewish_new_mexico_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Estefana Beatriz Sandoval",
    "preferred_name": "Stefi",
    "date_of_birth": "1944-05-23",
    "place_of_birth": "Las Vegas, New Mexico",
    "pronouns": "she_her",
    "pronouns_other": "",
    "current_residence": "Santa Fe, New Mexico",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:stefi",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Eliseo Sandoval",
        "father_birth_date": "1912-01-01",
        "mother_name": "Adela Sandoval",
        "mother_maiden_name": "Carrillo",
        "mother_birth_date": "1918-01-01",
        "siblings": [
            {"name": "Antonio Sandoval", "birth_date": "1941-01-01", "birth_order": 1},
            {"name": "Rosa Sandoval", "birth_date": "1947-01-01", "birth_order": 3},
        ],
    },
    "marriage": {
        "marital_status": "divorced",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "Miguel Romero",
             "year_married": 1968, "status": "divorced_1991"},
        ],
    },
    "children": [
        {"name": "Carmen Romero", "birth_date": "1970-09-30"},
        {"name": "David Romero", "birth_date": "1973-12-15"},
    ],
    "education_work": {
        "highest_education_level": "masters",
        "primary_career": "Folklorist and oral historian (NM Historic Preservation Division)",
        "years_working": "1972-2009",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "Roman Catholic (outwardly); crypto-Jewish practices on maternal side",
        "current_faith": "Identifies as anusim descent; affiliates with Congregation Nahalat Shalom",
        "ethnicity_heritage": "Hispano (norteño New Mexican); Sephardic descent (anusim)",
        "languages_at_home": "Spanish (New Mexico Spanish) and English",
    },
    "today": {
        "living_situation": "Lives in Santa Fe near her daughter Carmen",
        "health_considerations": "Otherwise well",
    },
}


CHAPTER_1 = """\
I was born in Las Vegas, New Mexico — not the Nevada one, the New Mexico one — on the twenty-third of May, 1944. My father Eliseo was a sheep rancher in San Miguel County, third generation on the land, which his grandfather had homesteaded after the Civil War. My mother Adela — her maiden name was Carrillo, the Carrillo family had been in New Mexico for three hundred years — was a housekeeper in the Castaneda Hotel during the season and at home the rest of the year. I had an older brother Antonio and a younger sister Rosa. We were a Catholic family. We went to Mass at Our Lady of Sorrows. My mother kept holy cards on the windowsill. I made my First Communion when I was seven and my Confirmation when I was thirteen. The house was on Hot Springs Road, an adobe house my grandfather had built, with a cellar dug into the hill behind. And there were things in our house that were not in my friends' houses, and I did not know why. My mother lit two candles on Friday evening — every Friday evening — in the cellar, not in the kitchen. She would say a prayer in Spanish, the same words every week, and I did not understand most of them. When I asked her why she lit candles down there she said porque mi mama lo hacía. Because my mother did it. That was the entire answer. My grandmother — my mother's mother, Encarnación — she did it too, and her mother before her, and so on. Mirrors got covered when somebody in the family died. Pork was not in the house, ever. My mother said no comemos puerco. That was the whole reason. When you asked why, the answer was that it had always been so. We baked bread for the holy days in a particular shape — three braids — that my mother said was old-country. We did not eat with anyone after sundown on Saturday until first star. There was a specific way to slaughter a chicken — a knife sharpened just so, a particular cut, a draining of the blood — that my grandfather did and that my brother Antonio learned, and the women of the house did not touch the meat until it had been drained. I grew up doing all of these things without knowing what they were. My friends did not do them. My friends ate ham at Easter. I asked my mother once if we could have ham and she said no and the conversation was over. I learned, the way children learn things by feel, that there were two kinds of being a Catholic in Las Vegas — there was being Catholic the way our family was Catholic, and there was being Catholic the way the Lujan family across the street was Catholic, and they were not the same, and you did not talk about that.\
"""

CHAPTER_2 = """\
I went to Highlands University in Las Vegas — I lived at home, that was what the girls did then — and I studied English and Spanish. I met Miguel Romero at a dance my sophomore year. He was from Santa Fe, the Romeros of the Tesuque end. We were married in 1968 at Our Lady of Sorrows, with my mother's friend Father Padilla officiating, and Miguel was from a normal Catholic family, no candles in the cellar, no covered mirrors, ham at Easter. He noticed early. He asked me once about the no-pork thing and I said well, that's just what we do, and he let it go, and we never spoke of it again in twenty-three years of marriage. Carmen was born in 1970, David in 1973. I went back to graduate school at New Mexico Highlands for a master's in folklore — which is funny in retrospect, because what I was studying in those classes was right there in my own house and I did not know it yet. I started working for the New Mexico Historic Preservation Division in 1972 as a part-time oral historian. By 1980 I was full-time. I interviewed elderly Hispano New Mexicans about their family practices, their songs, their saints, their land. I traveled all over northern New Mexico in a state car. I sat in adobe houses across from women in their eighties and recorded what they could tell me. And one of them — Mrs. Olivas of Mora, ninety-one years old, in 1979 — said something to me at the end of an interview that I had not put on the recorder. She said in Spanish, "Mija, you have the look. You light the candles too, don't you." I said yes. She nodded. She did not say anything else. The interview was over. I did not understand what had happened until 1985 when I met Stanley Hordes at a conference in Albuquerque. He was a historian doing research on crypto-Jewish families in New Mexico. He was the first person who had a vocabulary for what my grandmother and my mother had done. Friday-evening candles. Covered mirrors. No pork. The chicken-slaughtering. The three-braid bread. The avoidance of work on Saturday. He had a list. I had every single thing on his list in my house growing up. I sat across from him for two hours and did not say much. I did not need to. He could see I was one. After that conversation I went home to Las Vegas — my mother was still alive then, my father had died in 1981 — and I asked my mother. I asked her if she knew what the candles meant. She looked at me for a long time. She said, "Mija, I do not know what they mean. My mother did not know what they meant. Her mother did not know what they meant. We do them because we were told to do them. We were told not to ask. And we were told not to tell." She would not say more.\
"""

CHAPTER_3 = """\
I am eighty years old. My mother died in 1992. Miguel and I divorced in 1991, amicably, because the marriage had run its course. I never remarried. Carmen lives in Santa Fe — she is a public-health nurse — and David is in Albuquerque, an architect. Three grandchildren. I retired from the Historic Preservation Division in 2009 after thirty-seven years. I joined Congregation Nahalat Shalom in Albuquerque in 1998. I do not consider that a conversion. I consider it a return. My rabbi understands that. The congregation has a number of us now — anusim descendants from the New Mexico families. We do not talk about specific family practices in the open. We do not put names on what our grandmothers did. We light the candles together on Friday evening and we do not have to explain to each other why. My daughter Carmen has come with me twice. My son David has not. I do not press them. They will come or they will not. The practices stop with my generation in some branches of the family and they do not stop in other branches. I have a cousin in Mora who still does everything my grandmother did and would die before she told you why. I have a cousin in Albuquerque whose children do not know any of it. The thing I would say to anyone listening — and this is the only thing I want to say at the end of this — is that for five hundred years the women of my family kept something alive without being able to name it. They lit candles. They covered mirrors. They drained blood. They baked bread the right way. They did this through the Inquisition. They did this through the colony. They did this through New Spain becoming Mexico. They did this through New Mexico becoming American. They did this through Anglo arrival and through Anglo Catholicism trying to absorb them and through forty years of my generation's children intermarrying. They did this without telling anyone what it was. They told their daughters to do it and not to ask and not to tell. Recuerda pero no digas. Remember but never tell. That was the rule. My grandmother said that to my mother on her deathbed and my mother said it to me when she was dying. Recuerda pero no digas. I am breaking that rule on this recording. I am breaking it because the chain is breaking with my generation in too many branches, and somebody has to write it down so that what was kept for five hundred years is not lost in the last forty. So I am telling you that we are here. We were always here. We were here through everything. The grandmother who lit the candles in the cellar in 1944 was lit by a grandmother who lit them in 1894 who was lit by a grandmother who lit them in 1844 who was lit by a grandmother who lit them in 1794, all the way back. That is the chain. I am one link in it. My granddaughter is going to be another one if she wants to be. That is the truth I am leaving here.\
"""


CHAPTER_ANCHORS_1 = [
    "las vegas", "1944", "eliseo", "adela", "carrillo",
    "san miguel county", "sheep rancher",
    "antonio", "rosa",
    "our lady of sorrows", "first communion",
    "hot springs road", "the cellar",
    "two candles", "friday evening",
    "porque mi mama lo hacía",
    "encarnación", "covered mirrors",
    "no comemos puerco", "three braids",
    "saturday", "first star",
    "the chicken", "the knife",
    "two kinds of being catholic",
    "the lujan family",
]
CHAPTER_ANCHORS_2 = [
    "highlands university", "english and spanish",
    "miguel", "tesuque", "1968",
    "father padilla", "no pork",
    "carmen", "1970", "david", "1973",
    "master's", "folklore",
    "historic preservation", "1972",
    "oral historian",
    "mrs. olivas", "mora", "ninety-one", "1979",
    "you have the look",
    "stanley hordes", "1985", "albuquerque",
    "the list",
    "father had died", "1981",
    "do not know what they mean",
    "told not to tell",
]
CHAPTER_ANCHORS_3 = [
    "eighty", "my mother died", "1992",
    "divorced", "1991",
    "santa fe", "public-health nurse",
    "albuquerque", "architect", "three grandchildren",
    "thirty-seven years", "2009",
    "nahalat shalom", "1998", "return",
    "anusim", "we light the candles together",
    "the cousin in mora",
    "five hundred years", "inquisition",
    "recuerda pero no digas",
    "the chain", "1844", "1794",
    "the truth i am leaving here",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Stefi Sandoval (Crypto-Jewish New Mexico)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — Candles in the cellar",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Building Years — The vocabulary arrives in 1985",
                runtime71_era="building_years",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Later Years — Breaking the rule on purpose",
                runtime71_era="later_years",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="regional_crypto_jewish_new_mexico",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
