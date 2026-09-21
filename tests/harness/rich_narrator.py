"""The rich synthetic narrator's record. Fictional. ONE definition.

Imported by `scripts/make_rich_synthetic_narrator.py`, which writes it
into a live database through the product's own routes, and by
`tests/test_biography_answers_a_rich_record.py`, which reads it straight.

Two copies of a fixture stay equal until the first change — the failure
this repository has recorded against a renderer/predicate pair, a
baseline inventory beside its registry, and a resolver about to become
two. So the data lives here and nowhere else.

WHY IT IS THIS BIG. `ZZ WALKTHROUGH 20260917` holds 1,444 bytes, and its
turns ran at 7,285-7,541 of 8,192 tokens with nothing shed. The real
failure ran at 8,187 with `memory_context` dropped and four conversation
turns gone. A fixture that cannot reach that pressure cannot test the
behaviour that broke under it.

WHAT IT DOES NOT CONTAIN: Life Map material. Measured 2026-09-21 —
`life_map` appears zero times in `prompt_composer.py` and zero times in
the chat_ws prompt path. Loading it here would simulate a cost that does
not exist.
"""
from __future__ import annotations

DISPLAY_NAME = "ZZ RICH FIXTURE 20260921"

# ── The invented family ──────────────────────────────────────────────
# Ashgrove/Vellacourt. Deliberately unlike the coastal-service names
# used in the PROMPT examples (Kellerman, Cape Thistle, Orla, Nessa):
# a fixture that shared vocabulary with the instructions would make an
# exemplar leak look like a retrieval success.

MOTHER_EVENTS = (
    "Taught the infant class at Culvert Row School for thirty-one years "
    "and kept every register. Organised the coal fund during the winter "
    "the mill closed, which meant walking the length of Prentice Street "
    "twice a week in the dark collecting sixpences. Was the first woman "
    "on the parish burial board, which she found funnier than anyone "
    "else did. Broke her wrist falling off the school roof retrieving a "
    "kite and never once explained why she had gone up there herself."
)

FATHER_EVENTS = (
    "Apprenticed at the Marrowbone foundry at fourteen and stayed until "
    "it shut in 1968. Ran the works brass band and could not play a "
    "note; he said conducting was mostly nerve. Walked out in the 1957 "
    "dispute and was the last man back, which cost him the foreman's "
    "job twice. Kept a notebook of every locomotive that passed the "
    "level crossing at Hallow Bridge between 1949 and 1961."
)

GRANDMOTHER_STORY = (
    "She came over from Trelleck with a canvas bag and a bible she "
    "could not read, having been taught only Welsh, and learned English "
    "from the Sunday paper over about four years. She would not have a "
    "photograph taken, so there is one picture of her and she is turning "
    "away from it. When the telegram came about my uncle she put it in "
    "the tea caddy and did not mention it for a fortnight."
)

QUESTIONNAIRE = {
    "personal": {
        "firstName": "Idris",
        "lastName": "Ashgrove",
        "dateOfBirth": "1951-04-02",
        "placeOfBirth": "Hallow Bridge",
    },
    "parents": [
        {
            "relation": "Mother",
            "firstName": "Marguerite",
            "lastName": "Ashgrove",
            "maidenName": "Vellacourt",
            "birthDate": "1919-08-14",
            "birthPlace": "Culvert Row",
            "occupation": "infant-school teacher",
            "deceased": "Yes",
            "notableLifeEvents": MOTHER_EVENTS,
            "notes": "kept boiled sweets in a tin marked BUTTONS",
        },
        {
            "relation": "Father",
            "firstName": "Emrys",
            "lastName": "Ashgrove",
            "birthDate": "1916-01-27",
            "birthPlace": "Marrowbone",
            "occupation": "foundry moulder",
            "deceased": "Yes",
            "notableLifeEvents": FATHER_EVENTS,
            "notes": "the notebook is still in the sideboard",
        },
    ],
    "siblings": [
        {"relation": "Sister", "firstName": "Tamsin", "lastName": "Ashgrove",
         "birthDate": "1944-06-30", "birthOrder": 1,
         "occupation": "district nurse",
         "notableLifeEvents": "Nursed at Prentice Street Infirmary through "
                              "the 1962 outbreak and would not talk about it."},
        {"relation": "Brother", "firstName": "Rhodri", "lastName": "Ashgrove",
         "birthDate": "1947-02-11", "birthOrder": 2,
         "occupation": "merchant seaman", "deceased": "Yes",
         "notableLifeEvents": "Went to sea at seventeen. Sent a postcard "
                              "from every port and signed them all 'your "
                              "brother, R. Ashgrove', as though we might "
                              "have forgotten."},
        {"relation": "Sister", "firstName": "Gwenllian", "lastName": "Prosser",
         "maidenName": "Ashgrove", "birthDate": "1949-11-05", "birthOrder": 3,
         "occupation": "seamstress",
         "notableLifeEvents": "Made the curtains for the chapel hall and "
                              "refused payment, then complained about it "
                              "for twenty years."},
        {"relation": "Brother", "firstName": "Caradog", "lastName": "Ashgrove",
         "birthDate": "1956-09-19", "birthOrder": 5,
         "occupation": "signalman",
         "notableLifeEvents": "The youngest, and the only one who stayed. "
                              "Took over the level crossing our father used "
                              "to watch trains at."},
    ],
    "grandparents": [
        {"relation": "Maternal grandmother", "firstName": "Eirlys",
         "lastName": "Vellacourt", "birthPlace": "Trelleck",
         "memorableStories": GRANDMOTHER_STORY},
        {"relation": "Maternal grandfather", "firstName": "Tudur",
         "lastName": "Vellacourt", "occupation": "quarryman",
         "memorableStories": "Lost the sight in one eye to a chip of slate "
                             "in 1931 and went back the following Monday, "
                             "because there was no money in not going."},
        {"relation": "Paternal grandmother", "firstName": "Sarah",
         "lastName": "Ashgrove", "occupation": "laundress"},
    ],
    "spouse": [
        {"relation": "Wife", "firstName": "Nerys", "lastName": "Ashgrove",
         "maidenName": "Cadwalader", "birthDate": "1953-03-22",
         "birthPlace": "Prentice Street", "occupation": "school secretary",
         "notableLifeEvents": "Met at the chapel hall the night the roof "
                              "leaked into the tea urn. Married 1974. Ran "
                              "the box office for the operatic society for "
                              "twenty years and never once watched a whole "
                              "performance from the front."},
    ],
    "children": [
        {"relation": "Daughter", "firstName": "Bethan", "lastName": "Ashgrove",
         "birthDate": "1976-05-08", "occupation": "veterinary surgeon",
         "notableLifeEvents": "Qualified in 1999, the first in the family to "
                              "finish university. Came back to practise "
                              "eleven miles from where she was born, which "
                              "she says was not sentimental and plainly was."},
        {"relation": "Son", "firstName": "Owain", "lastName": "Ashgrove",
         "birthDate": "1979-10-14", "occupation": "structural engineer",
         "notableLifeEvents": "Worked on the Hallow Bridge replacement and "
                              "argued to keep the old signal box, and lost."},
    ],
    "military": [
        {"branch": "Royal Engineers", "yearEnlisted": "1969",
         "yearDischarged": "1972", "rank": "Sapper",
         "notableEvents": "Posted to Osnabrück for two years building "
                          "bridging for exercises that were always "
                          "cancelled. Came home with a German phrasebook "
                          "and about nine words."},
    ],
    "residences": [
        {"place": "Hallow Bridge", "startYear": "1951", "endYear": "1969",
         "notes": "the house by the crossing"},
        {"place": "Osnabrück", "startYear": "1969", "endYear": "1972"},
        {"place": "Prentice Street", "startYear": "1974", "endYear": "1988",
         "notes": "two rooms over the ironmonger's"},
        {"place": "Culvert Row", "startYear": "1988",
         "notes": "still there"},
    ],
    "work": [
        {"role": "signalling technician", "organization": "regional railway",
         "startYear": "1972", "endYear": "2011",
         "notableEvents": "Thirty-nine years. Was on shift the night of the "
                          "1987 derailment at Marrowbone and gave evidence "
                          "at the inquiry, which he has never discussed at "
                          "home and discusses readily with strangers."},
    ],
    "faith": {
        "denomination": "Welsh Independent chapel",
        "traditions": "Gymanfa ganu at Whitsun, and the long walk back.",
    },
    "education": {
        "schooling": "Culvert Row School, then Hallow Bridge secondary "
                     "modern until fifteen.",
        "gradeLevel": "left at fifteen",
    },
    "earlyMemories": {
        "firstMemory": "The brass band practising in the yard and the "
                       "windows going in the frames.",
        "favoriteToy": "A tin signal lamp with the red glass cracked.",
    },
}

#: (section, field, value, route) — written AFTER the bulk PUT so the
#: provenance rows are genuine. 'operator' = somebody typed it in;
#: 'narrator' = the narrator said it. Everything not listed here has NO
#: provenance row, which is the pre-WO-03A state and is itself a case
#: Lori has to describe honestly.
PROVENANCE = [
    ("parents", "occupation", "infant-school teacher", "operator"),
    ("parents", "birthPlace", "Culvert Row", "operator"),
    ("earlyMemories", "firstMemory",
     "The brass band practising in the yard and the windows going in "
     "the frames.", "narrator"),
    ("education", "schooling",
     "Culvert Row School, then Hallow Bridge secondary modern until "
     "fifteen.", "narrator"),
]
