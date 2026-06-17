from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class NarratorCase:
    label: str
    narrator_text: str
    lori_bad: str
    lori_good: str
    anchors: List[str]
    expected_failed_rows: List[str]


JOHN_ADOLESCENCE_ACCIDENT_FIRST_PERSON = (
    "When I was a teenager, my father died. He was changing a tire on the side "
    "of the road and was hit by a car. I also traveled in Europe as a teenager, "
    "so that period of my life had both loss and a wider view of the world."
)

JOHN_ADOLESCENCE_ACCIDENT_THIRD_PERSON = (
    "John's father died when John was a teenager. His father was changing a tire "
    "on the side of the road and was hit by a car. John also traveled in Europe "
    "as a teenager."
)

STEFI_INNOCENT_FAMILY_TEXT = (
    "I was born in Las Vegas, New Mexico. My father Eliseo was a sheep rancher, "
    "and my mother kept the house and the old family stories. We had Catholic "
    "words around us, but there were older customs underneath that nobody named "
    "out loud when I was little."
)

TRUE_CHILD_ABUSE_DISCLOSURE = (
    "When I was a child, my father hit me and hurt me. I was afraid to go home "
    "because it kept happening."
)

CANONICAL_JOHN_TODAY_NARRATOR = (
    "Today I live alone in my own house in Las Vegas, New Mexico. I currently "
    "work as a school psychologist in Pecos Schools. My mother is still alive "
    "at 99 and lives in St. Paul. I want Lori to understand that those facts "
    "are already known, and I want her to ask about the lived meaning, not ask "
    "me to confirm the basic information again."
)

MABLE_EARLIEST_NARRATOR = (
    "I was born in Albany, Georgia, in 1942, on cotton land outside town. "
    "Mount Olive AME was the church that held our family together. The adults "
    "did not explain every danger to children, but we knew which roads to walk "
    "and which doors not to open. My earliest memories are heat, hymns, and the "
    "sound of women getting food ready before sunrise."
)

RICHARD_EARLIEST_NARRATOR = (
    "I was born at Magee Hospital in Pittsburgh and grew up in Oakland near the "
    "river. My father worked at Jones and Laughlin, and the Catholic Church was "
    "a big part of the rhythm of the week. I remember Mass, the smell of the "
    "church, and the feeling that there were rules for everything."
)

JOE_EARLIEST_NARRATOR = (
    "I was born at Cochiti Pueblo. My parents Frank and Elena took us to Mass, "
    "and my siblings Andrew and Mary were part of every early memory. I also "
    "remember that some things from the Pueblo were not for outsiders, and I do "
    "not want Lori to ask me to explain sacred details."
)

STEFI_CRYPTO_JEWISH_NARRATOR = (
    "I had an older brother Antonio. I made my First Communion, but there were "
    "candles in the cellar that my mother would not explain. I asked her why "
    "she lit them down there, and she said some things are remembered quietly. "
    "This should be treated as English unless I actually speak Spanish."
)

FAILURE_CASES: List[NarratorCase] = [
    NarratorCase(
        label="john_stub_west_st",
        narrator_text=(
            "I was born on December 31, 1960, in West St. Paul, Minnesota. "
            "My mother is still alive at 99 and lives in St. Paul, so those "
            "earliest roots are still connected to my life now."
        ),
        lori_bad="West St.",
        lori_good=(
            "West St. Paul and your mother still being there give those earliest "
            "roots a clear place in your story. What do you remember about that "
            "place when you were very young?"
        ),
        anchors=["west st. paul", "mother", "st. paul"],
        expected_failed_rows=["response_not_fragmented", "minimum_anchor_count", "direct_human_voice"],
    ),
    NarratorCase(
        label="shatner_phrase_as_name",
        narrator_text=(
            "Montreal was the air I grew up breathing. The Jewish neighborhood, "
            "the winter streets, and the pull of performance were all there "
            "before I had words for them."
        ),
        lori_bad="Got it — It Was The Air. Did I get that name right? What happened next?",
        lori_good=(
            "Montreal and that feeling of the air around you are strong earliest "
            "anchors. What do you remember about those winter streets when you "
            "were a boy?"
        ),
        anchors=["montreal", "winter", "streets"],
        expected_failed_rows=[
            "no_false_name_confirmation",
            "no_got_it_stub",
            "no_titlecase_phrase_as_name",
        ],
    ),
    NarratorCase(
        label="richard_meta_response_leak",
        narrator_text=RICHARD_EARLIEST_NARRATOR,
        lori_bad=(
            "Here is a response that follows the rules and guidelines:\n\n"
            "\"You mentioned Magee Hospital where you were born, the Catholic Church, "
            "and your father's work at Jones and Laughlin. What do you remember "
            "about your daily life in Oakland?\"\n\n"
            "This response reflects the narrator's mentions and asks a follow-up question."
        ),
        lori_good=(
            "Magee Hospital, Oakland, the river, and your father's work at Jones "
            "and Laughlin all sit close together in that early world. What do you "
            "remember about the rhythm of daily life there?"
        ),
        anchors=["magee", "oakland", "jones and laughlin"],
        expected_failed_rows=["no_meta_response_leak", "direct_human_voice"],
    ),
    NarratorCase(
        label="joe_anchor_cascade",
        narrator_text=JOE_EARLIEST_NARRATOR,
        lori_bad=(
            "You went from Cochiti Pueblo to August, then Frank, Elena, Andrew, "
            "Mary, Catholic, and Mass. What happened next?"
        ),
        lori_good=(
            "Cochiti Pueblo, your parents Frank and Elena, and the boundary around "
            "sacred details are important here. What daily memory from those early "
            "years feels safe to tell?"
        ),
        anchors=["cochiti pueblo", "frank", "elena"],
        expected_failed_rows=["no_titlecased_anchor_cascade", "direct_human_voice"],
    ),
    NarratorCase(
        label="mable_seeded_fact_question",
        narrator_text=MABLE_EARLIEST_NARRATOR,
        lori_bad=(
            "Mount Olive AME. What a rich and evocative narrative! I'm so grateful "
            "to be listening to your story. Let me capture a few key points. "
            "You were born in Albany, Georgia, in 1942?"
        ),
        lori_good=(
            "Albany, Mount Olive AME, the heat, and those early hymns are already "
            "part of the ground of your story. What do you remember about being "
            "little in that world before sunrise?"
        ),
        anchors=["albany", "mount olive", "ame", "1942"],
        expected_failed_rows=["no_seeded_fact_intake_question", "no_meta_response_leak"],
    ),
    NarratorCase(
        label="stefi_broken_code_mix",
        narrator_text=STEFI_CRYPTO_JEWISH_NARRATOR,
        lori_bad=(
            "Tú had an older brother Antonio, made my First Communion, asked her "
            "why she lit candles down there, y asked my mother. ¿Qué pasó después?"
        ),
        lori_good=(
            "Antonio, First Communion, and the candles in the cellar all belong "
            "to that quiet layer of your family memory. What do you remember about "
            "the first time you noticed those candles?"
        ),
        anchors=["antonio", "first communion", "candles"],
        expected_failed_rows=["no_broken_code_mix", "direct_human_voice"],
    ),
]

SEEDED_FACT_PROFILE_MABLE: Dict[str, object] = {
    "personal": {
        "preferredName": "Mable",
        "dateOfBirth": "1942-01-01",
        "placeOfBirth": "Albany, Georgia",
        "currentResidence": "Detroit, Michigan",
        "pronouns": "she/her",
    },
    "faith": {"religionRaised": "AME"},
}

SEEDED_FACT_PROFILE_JOHN: Dict[str, object] = {
    "personal": {
        "preferredName": "John",
        "dateOfBirth": "1960-12-31",
        "placeOfBirth": "West St. Paul, Minnesota",
        "currentResidence": "Las Vegas, New Mexico",
        "pronouns": "he/him",
    },
    "family": {
        "mother": {"alive": True, "age": 99, "residence": "St. Paul"},
        "children": [{"count": 2}],
    },
    "education_work": {
        "primary_career": "school psychologist",
        "current_work": "Pecos Schools",
        "career_start_year": 2010,
        "past_work": ["NMHU", "natural tobacco cigarettes", "beer maker"],
    },
    "military": {"served": False},
}
