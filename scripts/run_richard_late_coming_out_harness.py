#!/usr/bin/env python3
"""Richard Bellamy long-narration harness — gay man who came out late.

Fictional narrator. Born 1952. Catholic working-class family in
Pittsburgh. Married a woman in 1976. Divorced 1998. Came out as gay
in 1999 at 47. Has been with his partner Tomás since 2002.

The point of this harness: confirm Lori handles a narrator whose
life story includes a long heterosexual marriage AND a late-in-life
identity reveal without either (a) treating the marriage as a
"deception" or (b) treating the coming-out as the entire story. The
chapters intentionally hold both with the same texture.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_richard_late_coming_out_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Richard Joseph Bellamy",
    "preferred_name": "Rich",
    "date_of_birth": "1952-06-08",
    "place_of_birth": "Pittsburgh, Pennsylvania",
    "pronouns": "he_him",
    "pronouns_other": "",
    "current_residence": "Squirrel Hill, Pittsburgh, Pennsylvania",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:richard",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Frank Bellamy",
        "father_birth_date": "1924-01-01",
        "mother_name": "Mary Bellamy",
        "mother_maiden_name": "Sullivan",
        "mother_birth_date": "1927-01-01",
        "siblings": [
            {"name": "Patrick", "birth_date": "1949-01-01", "birth_order": 1},
            {"name": "Maureen", "birth_date": "1955-01-01", "birth_order": 3},
            {"name": "Kathleen", "birth_date": "1958-01-01", "birth_order": 4},
        ],
    },
    "marriage": {
        "marital_status": "divorced_and_partnered",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "Diane Bellamy (née Mazur)",
             "year_married": 1976, "status": "divorced_1998"},
            {"name": "Tomás Reyes",
             "year_married": 2015, "status": "current_partner_since_2002_married_2015"},
        ],
    },
    "children": [
        {"name": "Michael Bellamy", "birth_date": "1978-04-22"},
        {"name": "Sarah Bellamy", "birth_date": "1981-09-14"},
    ],
    "education_work": {
        "highest_education_level": "bachelors",
        "primary_career": "Accountant; later small-firm partner",
        "years_working": "1974-2018",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "Roman Catholic",
        "current_faith": "Spiritual; left the Church in his fifties",
        "ethnicity_heritage": "Irish-American on mother's side; Italian-American on father's side",
        "languages_at_home": "English",
    },
    "today": {
        "living_situation": "Lives in Squirrel Hill with husband Tomás",
        "health_considerations": "Otherwise well",
    },
}


CHAPTER_1 = """\
I was born on the eighth of June, 1952, in Pittsburgh, in Magee Hospital, the second of four children of Frank and Mary Bellamy. My father was Italian-American — Bellamy is an Anglicization, the family name back two generations was Belarmino — and my mother was Irish-American, her maiden name was Sullivan. They had grown up two blocks from each other in Oakland and they had been high school sweethearts and they got married after my father came home from the war in 1947. My older brother Patrick was born in 1949, then me in 1952, then my sisters Maureen in 1955 and Kathleen in 1958. So we were four. The neighborhood was Oakland — the lower part, near the river — and Pittsburgh in those years was a steel town, and my father worked at Jones and Laughlin, the mill, like every other man on our block. The mill ran around the clock. The mill made the air smell. The mill made the sky orange at night. I remember my mother taking the wash in before sundown because if the soot caught it the shirts would have to be washed again. The Catholic Church was the other half of life. Father Donnelly at Sacred Heart was a figure of authority larger than my father. We went to Mass on Sunday, all six of us, and we went to confession on Saturday afternoon, and the older kids — Patrick and me — were altar boys, which meant we had to be at the church earlier than the rest of the family. I remember the smell of the candles and the smell of the incense and the smell of Father Donnelly's aftershave when he leaned in to whisper instructions during the service. I remember the Latin. I remember the heavy wool of the cassock. I remember kneeling for so long that my knees went numb. I was supposed to grow up to be like Patrick, who was the kind of boy who got things right. He was good at sports. He had a girl by sophomore year of high school. He was popular without working at it. I was the quiet one. I was the one who read books in the corner. I was the one my mother worried about because I was too sensitive. I did not have words for what I was when I was a child. I just knew I was different in a way I was not supposed to be. I knew it by the time I was eleven or twelve. I knew it the first time I noticed how I felt watching my older cousin Anthony do laps at the pool. I knew it and I knew I was not supposed to know it and I knew I was not supposed to ever tell anyone, including myself. So I did not tell anyone, including myself, for the next thirty-five years.\
"""

CHAPTER_2 = """\
I went to Duquesne for my undergraduate degree — Catholic university, my mother insisted — and I majored in accounting. I was good at it. Numbers were safe. Numbers did not ask you questions about who you were. I met Diane Mazur in my junior year at a Newman Club mixer. She was studying to be a teacher. She was kind. She was Catholic. She was pretty in the way Pittsburgh girls of our generation were pretty — sensible hair, sensible dresses, an easy laugh. We dated for two years and we got engaged and we got married in 1976 at Sacred Heart, with Father Donnelly officiating, who had baptized me twenty-four years earlier. Our son Michael was born in 1978. Our daughter Sarah was born in 1981. I made partner at the firm in 1986. We bought a house in Squirrel Hill. We sent the kids to Catholic school. We went on vacation to Ocean City, Maryland, every summer. We did everything we were supposed to do. And the whole time, the whole twenty-two years, I was doing what I had taught myself to do as a child, which was to not know what I knew. I was a good husband to Diane. I want to say that. I was attentive and I was loving and I was loyal, all the years we were married, including the years I did not understand myself. I was not living a double life in any literal sense. I never strayed. I never cheated. I never did the thing the movies tell you men like me do. I just lived inside myself with a door closed, and on the other side of that door was the part of me I had decided when I was twelve I was not allowed to know. The doors opens when the doors are ready. Mine opened in 1998. I was forty-six. The kids were grown — Michael was at Carnegie Mellon for graduate school, Sarah was finishing at Pitt. The marriage had been getting quieter and quieter for years. Diane and I had stopped really talking — not in a hostile way, just in the way that long marriages can quiet down. And one evening I was alone in the house, she was visiting her sister, and I sat down at the kitchen table and I admitted to myself, for the first time in thirty-five years, that I was gay. I said it out loud in the empty kitchen. I said it out loud and I cried. I told Diane the next month. She did not cry in front of me. She cried later, I know that, but she did not cry in front of me. She said she had known for years. She said she had been waiting for me to know. We were divorced in 1998. We did it ourselves. Without lawyers fighting. Without bitterness. I told the kids that fall, and Michael — who is the one most like me, who is also the one who reads books in the corner — Michael said something I have never forgotten. He said, "Dad, I am angry at you for not telling me, but I am angry on your behalf, not on my own behalf." That is what he said. Twenty years old, and he said that.\
"""

CHAPTER_3 = """\
I met Tomás in 2002. I was fifty. He was forty-three. He was a clinical psychologist who had immigrated from Mexico City as a young man. We met at a gallery opening — a friend of mine was showing photographs at a small place in the Strip District, and Tomás was there, and we ended up talking about Pittsburgh, about how someone like him had ended up in this city, about how someone like me had finally come home to himself in this city, and we did not stop talking for twenty-two years. We moved in together in 2003. We got married in 2015, the year same-sex marriage became legal nationwide. By then my brother Patrick had died — heart attack, suddenly, in 2010 — and I had reconciled with my sister Maureen, who had taken a long time to be okay with who I was, and I had stayed close with Kathleen, who had been okay with it from the start. My mother lived long enough to know Tomás. She did not exactly approve, in the way you would understand that word in a Catholic mother of her generation, but she was unfailingly kind to him. She invited him for Thanksgiving every year. She made him pierogis the way her mother had made them. She died in 2014, the year before Tomás and I were married, and she did not live to see the wedding. I am sorry about that. My father had died years earlier, in 1989. I think he never knew about me. I think he would not have known what to do with it if he had known. I am sorry about that too, sometimes. The kids — Michael is forty-six now, Sarah is forty-three — both of them are good with us. Both of them are good with Tomás. Sarah has two children of her own and Tomás is grandpa-Tomás to them. Michael never married. Michael lives in Boston and does research at MIT. The Catholic Church and I parted ways for good in 2002. I had stayed even after coming out — I had wanted to believe the Church could find a place for me — and finally I had to accept that it could not, or would not, and I left. That was its own grief. I miss the rituals more than the doctrine. What I would say to anyone listening — and I am thinking specifically of any man somewhere in his fifties who is sitting on his kitchen floor and finally letting himself know what he has always known — is this. There is a life on the other side of the door. You will not lose your children. You will not lose your friends, the ones who are real. You will lose the marriage that was always going to end, and you will grieve it, and the grief is real and it is permanent and it is okay. The person you finally become on the other side of the door is the person you always were. You are not late. You are not late at all. You are right on time, because you are here.\
"""


CHAPTER_ANCHORS_1 = [
    "pittsburgh", "1952", "frank", "mary", "sullivan", "patrick",
    "maureen", "kathleen", "oakland", "jones and laughlin", "mill",
    "sacred heart", "father donnelly", "altar boys", "cassock",
    "anthony", "the pool", "italian-american", "irish-american",
    "magee", "belarmino",
]
CHAPTER_ANCHORS_2 = [
    "duquesne", "accounting", "diane", "mazur", "newman club", "1976",
    "michael", "1978", "sarah", "1981", "partner", "1986",
    "squirrel hill", "ocean city", "thirty-five years", "1998",
    "forty-six", "carnegie mellon", "pitt", "diane cried",
    "divorced", "twenty years old",
]
CHAPTER_ANCHORS_3 = [
    "tomás", "2002", "fifty", "psychologist", "mexico city",
    "strip district", "gallery", "2003", "2015", "patrick died",
    "2010", "maureen", "kathleen", "my mother", "pierogis",
    "thanksgiving", "2014", "1989", "michael", "sarah", "boston",
    "mit", "the church", "the rituals", "you are not late",
]


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Richard Bellamy (late coming-out)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Earliest Years — Oakland, Pittsburgh",
                runtime71_era="earliest_years",
                text=CHAPTER_1,
                anchors=CHAPTER_ANCHORS_1,
            ),
            ChapterConfig(
                label="Building Years — Marriage + the door",
                runtime71_era="building_years",
                text=CHAPTER_2,
                anchors=CHAPTER_ANCHORS_2,
            ),
            ChapterConfig(
                label="Later Years — Tomás and the life after",
                runtime71_era="later_years",
                text=CHAPTER_3,
                anchors=CHAPTER_ANCHORS_3,
            ),
        ],
        report_prefix="richard_late_coming_out",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
