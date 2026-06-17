#!/usr/bin/env python3
"""Seven-era walk harness — every canonical era on the Life Map gets a chapter.

The other 9 harnesses in this family hit 3 of the 7 canonical eras
(typically earliest_years / building_years / later_years). The 7-era
walk drives all of them sequentially in one session so we can:

  1. Confirm the Life Map era-click + era_id round-trip works for
     every era_id (earliest / early_school / adolescence / coming_of_age
     / building / later / today).
  2. Surface era-specific Lori behavior — does she handle Today-era
     present-tense framing differently from Adolescence-era hindsight
     reflection? Does coming_of_age trigger pivot-questions
     differently from building_years?
  3. Exercise the era_id_to_continuation_phrase and era_id_to_warm_label
     helpers across all 7 eras in a single conv_id.

Narrator: fictional Walter ("Walt") O'Donnell, born 1948, working-class
Boston Irish family, four sons in three different decades, lifelong
teacher of mathematics, semi-retired in 2020. Spans 1948→2026 cleanly
so each era has plausible content.

USAGE:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_seven_era_walk_harness.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_lib import HarnessConfig, ChapterConfig, run_harness  # noqa: E402


INTAKE_PAYLOAD = {
    "full_legal_name": "Walter Patrick O'Donnell",
    "preferred_name": "Walt",
    "date_of_birth": "1948-03-17",
    "place_of_birth": "South Boston, Massachusetts",
    "pronouns": "he_him",
    "pronouns_other": "",
    "current_residence": "Quincy, Massachusetts",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:seven_era_walk",
    "testing_only": True,
    "family_of_origin": {
        "father_name": "Patrick O'Donnell",
        "father_birth_date": "1920-01-01",
        "mother_name": "Mary O'Donnell",
        "mother_maiden_name": "Sullivan",
        "mother_birth_date": "1923-01-01",
        "siblings": [
            {"name": "Brendan O'Donnell", "birth_date": "1946-01-01", "birth_order": 1},
            {"name": "Eileen O'Donnell", "birth_date": "1951-01-01", "birth_order": 3},
        ],
    },
    "marriage": {
        "marital_status": "married",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "Catherine Murphy",
             "year_married": 1972, "status": "current"},
        ],
    },
    "children": [
        {"name": "Sean O'Donnell", "birth_date": "1974-06-12"},
        {"name": "Michael O'Donnell", "birth_date": "1976-09-30"},
        {"name": "Brian O'Donnell", "birth_date": "1981-04-22"},
        {"name": "Daniel O'Donnell", "birth_date": "1989-11-15"},
    ],
    "education_work": {
        "highest_education_level": "masters",
        "primary_career": "High-school mathematics teacher",
        "years_working": "1970-2020",
    },
    "military": {"served": False},
    "faith": {
        "religion_raised": "Roman Catholic",
        "current_faith": "Roman Catholic",
        "ethnicity_heritage": "Irish-American (both sides; both grandparents emigrated)",
        "languages_at_home": "English",
    },
    "today": {
        "living_situation": "Lives in Quincy with wife Catherine; tutors twice a week",
        "health_considerations": "Otherwise well; knee replacement 2022",
    },
}


# ── era 1 — earliest_years (≈ 0 to 5 yrs old) ─────────────────────


CHAPTER_EARLIEST_YEARS = """\
I was born on Saint Patrick's Day, 1948, in South Boston — my father Patrick used to say I was the best Saint Patrick's Day present he ever got, which was generous because I was the second of his sons and I think he had wanted a girl. My older brother Brendan was already two. My sister Eileen came along three years later. The house was a triple-decker on G Street in Southie — second floor, three small rooms and a kitchen, a coal stove in the front room that my mother kept lit through the winter. My father worked the Charlestown Navy Yard then, the docks, hard labor that left his hands cracked and his back bent by the time he was forty. My mother kept the house and the three of us. The smells I remember are the smells of South Boston tenements in 1950 — coal smoke and boiled cabbage and the dampness off the bay and the Old Spice my father wore on Sundays. I do not remember much of being three or four, but I remember the rhythm. Mass on Sunday at Saint Augustine's. The Wednesday novena. The Friday fish. My uncle Jimmy came to dinner most Sundays after Mass, sat at the head of our small table because he was older than my father, drank Schlitz with him in the parlor after. I remember the smell of the beer foam and the radio on quiet in the background, the Red Sox broadcast in summer. I remember the noise of South Boston in those years — the streetcars on Broadway, the foghorns from the harbor at night, the church bells at six in the morning waking everybody up whether you wanted to be awake or not. I remember being held by my mother in the kitchen while she stirred something at the stove. That is what earliest means for me. Not a story. A smell. A warmth. A song my mother hummed.\
"""


# ── era 2 — early_school_years (≈ 5 to 11) ────────────────────────


CHAPTER_EARLY_SCHOOL_YEARS = """\
I started at Saint Augustine's parish school in 1953 when I was five. Sister Mary Alacoque ran the kindergarten — she was old already, ninety pounds and four feet ten and a will of iron. She taught me my letters and my prayers and how to walk in a straight line. The school was three blocks from our house, and the four of us — Brendan, me, Eileen when she started two years later, plus our cousin Patrick from across the street — walked it together every morning. Through second grade I was an obedient child and a good student. By third grade I had figured out that I liked numbers more than letters. Sister Bernadette taught third grade and she noticed. She gave me extra problems on a piece of newsprint. She let me work them in the back of the classroom while the rest of the children did spelling. By the end of third grade she had taught me long division in addition to multiplication, which was not on the curriculum until fifth grade. That was my first taste of being good at something. The thing about being good at math in a Catholic school in South Boston in 1956 is that nobody really knew what to do with it. Math was not the thing the parish school cared about. The parish school cared about whether you knew your catechism and whether you could carry a hymn at Mass and whether you behaved. So I behaved. I carried the hymn. I knew the catechism. And in the back of the classroom while the other children spelled, I did long division on the newsprint and discovered that I loved it. My father did not care. My father had quit school at sixteen and joined the dockworkers. He thought school was something you survived until you could go to work. My mother cared, in her own way. She would look at my report card every quarter and pat me on the shoulder and say "very nice, Walter," and then put it in the drawer with my brother's and my sister's. There was no extra praise. There was no announcement at the dinner table. There was the drawer. That was Irish-Catholic working-class Boston in the 1950s, and you accepted it.\
"""


# ── era 3 — adolescence (≈ 12 to 17) ──────────────────────────────


CHAPTER_ADOLESCENCE = """\
I went to Boston Latin School. I had passed the entrance exam in sixth grade — my mother had not known you could take it, but Sister Bernadette had told her, and my mother had filled out the paperwork. Boston Latin was a public school but it had selective admission and it was the oldest school in America and going to Boston Latin from Southie was an unusual thing in 1960. The trip to school was forty-five minutes on the streetcar, every morning, in my coat and my tie. The other boys at Boston Latin were mostly from the better neighborhoods — Brookline, the Back Bay, Newton, West Roxbury — and they had things my family did not have. I was the kid from Southie. The kid whose father worked the docks. The kid whose lunch was the same sandwich every day because that was what my mother could afford. The first year was hard. The second year was harder. By the third year I had found math team, and math team became my life. I made the four-school regional team my sophomore year. I made the New England team my junior year. We competed against Andover and Exeter. I traveled in the family Chevy with my coach and three teammates to New Haven and Hanover and Providence. I had never been out of Massachusetts. I was sixteen. The high-school years that mattered the most to me were those math-team trips. Boys from Brookline who had been to Europe and boys from Southie who had not been to Hartford were on the same bus, doing the same problems, and the problems did not care where you were from. The problems did not care if your father was a dockworker or a doctor. The problems only cared if you could solve them. Those were the years I figured out what I was going to do with my life. I was going to be a teacher of mathematics. I was going to be the Sister Bernadette for some other kid in some other neighborhood. That decision was made by the time I was seventeen and it ran the rest of my life and I have never once regretted it.\
"""


# ── era 4 — coming_of_age (≈ 18 to 24) ────────────────────────────


CHAPTER_COMING_OF_AGE = """\
I went to Boston College. The Jesuits gave me a scholarship — there was no other way I was going to college, my parents had no money for it and Brendan was already at the gas company and not interested. I lived at home and took the trolley out to Chestnut Hill every morning. I majored in mathematics. My freshman year was 1966. The country was still the country my parents had voted Kennedy into in 1960 — Irish-Catholic, optimistic, before the war and the assassinations and the long unraveling. By the time I graduated in 1970, the country was a different country. Tet had happened. King had been killed. Kennedy — the second Kennedy — had been killed. Kent State happened the spring I graduated. I was twenty-two. I had a draft number that almost got called and didn't. Boston was different. Southie was changing. My father had retired from the docks in 1968 because his back finally gave out and he sat in the parlor in his chair and watched the war on television and drank his Schlitz and looked older than he was. My mother was working at the supermarket. My sister Eileen was eighteen and getting married — too young, but that was what girls did then. I had a teaching credential by the spring of 1970 and a job offer to teach at Saint Mary's of Lynn, a Catholic high school north of Boston. I took it. I started in September. I was twenty-two years old, fresh out of college, in a coat and a tie that had once been my father's, standing in front of a classroom of thirty-five teenagers, trying to teach them algebra. I met Catherine Murphy that fall. She was teaching English at the same school, a year older than me, fresh out of Emmanuel. She had grown up in Dorchester. She was Irish-Catholic. She was sharp. She had read more books in her twenty-three years than I had read in my entire life. We married in 1972 at Saint Augustine's, where I had gone to grade school, with my old pastor Father Sweeney officiating. Sean was born in 1974. Michael in 1976. Brian in 1981. Daniel — the late arrival, the surprise, the one we joked God sent because we had been so smug — Daniel came in 1989, when Catherine was thirty-eight and I was forty-one and we had thought we were done.\
"""


# ── era 5 — building_years (≈ 25 to 60) ───────────────────────────


CHAPTER_BUILDING_YEARS = """\
The building years are the years that take the longest to live and the shortest to summarize. I taught at Saint Mary's of Lynn for ten years, then moved to North Quincy High School — the public school in the town we had bought our house in, where we wanted the boys to go — in 1980. I stayed at North Quincy for thirty-five years. I taught algebra, geometry, precalculus, calculus, and AP Statistics, which I started teaching in 1996 when the program first launched. I had a generation of students. I had students whose own children later showed up in my classroom. I had students who became engineers and accountants and one who became a NASA mathematician — Patty Sullivan, class of 1993, who came back and gave the commencement speech in 2014 and started by saying "Mr. O'Donnell, I owe you everything." That made me cry on the stage in front of three hundred parents and I do not cry easily. The boys grew up. Sean played hockey through high school and went to UMass. Michael was the bookish one, like his mother, went to Boston College like me, became a lawyer. Brian was the troublemaker — sweet, loving, a troublemaker — went to community college in fits and starts, ended up running his own contracting business, the most successful of the four of them financially. Daniel was the late one, the surprise, and he is the one who never quite landed. He has been three or four things. He lives an hour north of us now in a small apartment and we worry about him still, at thirty-six, the way you do not quite worry about the others. Catherine and I built a life. Twenty-five years at North Quincy, then ten more after that, putting four boys through school, paying off the house in Quincy in 2008, taking one real vacation a year — usually Cape Cod, sometimes Ireland — and that was the building years. Most of life happens in the building years and they leave the least mark, in a way. The days were busy. They were the same. The mortgage got paid. The car got bigger. The boys got bigger. The hair got grayer. The house got quieter as they left, one by one, until it was just Catherine and me again, the way we had started in 1972.\
"""


# ── era 6 — later_years (≈ 60 to 75) ──────────────────────────────


CHAPTER_LATER_YEARS = """\
I retired in 2020. My last day at North Quincy was supposed to be in June. It was actually in March, when they sent the students home for two weeks that turned out not to be two weeks. I finished out the spring teaching geometry over Zoom to twenty-eight sophomores who could barely see the screen, all of us pretending we knew what we were doing. The retirement party that the school had been planning for me happened on a Zoom call in June with sixty people on a grid, and I did not get to shake any hands or hug any students, and that is one of the things I am still sad about. I had imagined that day for years. I had imagined the cake and the speeches and the parents I had known for a generation telling me thank you. I got a grid of faces on a laptop instead. Then the long pandemic year. Catherine and I were in the house in Quincy. The boys called every week. Daniel had moved back in for six months because he had lost his job. That was hard in some ways and good in others. Hard because Daniel at thirty-one was still Daniel — drinking too much, working not enough, sleeping until noon. Good because Catherine and I got time with our youngest that we had not had in twenty years. He moved back out in the spring of 2021 when he found a job in Lowell. I started tutoring on the side. Math tutoring for middle-school and high-school kids in Quincy. Two afternoons a week. I do not need the money — my pension is enough, with what Catherine has — but I needed the work. I am happier when I am teaching. I have known that since I was nineteen years old. I had knee replacement surgery in 2022, my left knee, which had been bothering me since the building years, since the years of standing in front of a classroom seven hours a day. The surgery went fine. I walk the boardwalk at Wollaston Beach now most mornings with Catherine. We have made it past fifty years married. We see the boys some Sundays. The grandchildren are coming — Sean has two, Michael has one and another coming, Brian has three. Daniel has none. We are not sure he ever will. That is okay. The later years are the years where you start to notice what was always true, which is that the people you love are not infinitely available. You see them now while you can.\
"""


# ── era 7 — today (now / present-tense) ──────────────────────────


CHAPTER_TODAY = """\
Today is a Tuesday. Catherine and I had our usual breakfast at six-fifteen — coffee and toast and the Boston Globe spread out between us on the kitchen table. I read the sports first. She reads the obituaries first. We have done this every morning for forty years and neither of us has ever explained why we read in that order, but we do. After breakfast I walked to the post office to mail a card to my sister Eileen, who is seventy-three this week and whose husband is starting to decline. I worry about her. She is the only sister I have. Tonight I have a tutoring student at four o'clock — Aiden, eighth-grader, struggling with the order of operations the way kids do, perfectly bright, just hasn't seen it presented in a way that clicks for him yet. I think today I will use the parentheses-as-rooms metaphor that worked for one of my North Quincy students twenty years ago. We will see if it works for Aiden. Catherine is making her mother's roast chicken for dinner. Daniel is supposed to come down from Lowell on Saturday, the first weekend in a month he has been able to make it. Sean and his kids will come over on Sunday after Mass. The grandchildren will run through the house and Catherine will pretend not to want them eating in the parlor and they will eat in the parlor anyway, which is what grandchildren are for. My knees are okay today. The weather is okay today. We are okay today. Today is what we have, and I have learned slowly across seventy-seven years that today is what life is. The earliest years and the school years and the math team and the marriage and the boys and the classroom and the retirement and the tutoring — they all turn into today, eventually. They become the days you are still living. I am still living one. That is enough. Anyway, that is what today looks like. A breakfast. A walk to the post office. A tutoring session at four. A dinner with my wife. A daughter coming Saturday — I mean a son. Daniel. Why did I say daughter. I do not have a daughter. I have four sons and a sister. Today is a Tuesday, and tomorrow will be a Wednesday, and that is the entire plan.\
"""


CHAPTER_ANCHORS = {
    "earliest_years": [
        "saint patrick", "1948", "south boston", "southie",
        "patrick", "mary", "sullivan",
        "brendan", "eileen", "g street", "triple-decker",
        "coal stove", "charlestown navy yard",
        "saint augustine", "novena", "fish", "uncle jimmy",
        "schlitz", "red sox", "foghorns", "church bells",
        "old spice",
    ],
    "early_school_years": [
        "saint augustine", "1953", "sister mary alacoque",
        "three blocks", "patrick", "brendan", "eileen",
        "sister bernadette", "third grade", "newsprint",
        "long division", "the catechism",
        "the drawer", "very nice, walter",
        "irish-catholic", "the 1950s",
    ],
    "adolescence": [
        "boston latin", "1960", "the streetcar",
        "the entrance exam", "sister bernadette",
        "math team", "andover", "exeter",
        "new haven", "hanover", "providence",
        "the chevy", "boys from brookline",
        "boys from southie", "the problems did not care",
        "sister bernadette for some other kid",
        "seventeen", "teacher of mathematics",
    ],
    "coming_of_age": [
        "boston college", "the jesuits", "1966",
        "1970", "chestnut hill",
        "tet", "king", "kennedy",
        "kent state", "draft number",
        "saint mary's of lynn",
        "catherine", "murphy", "emmanuel", "dorchester",
        "1972", "father sweeney",
        "sean", "1974", "michael", "1976",
        "brian", "1981", "daniel", "1989",
    ],
    "building_years": [
        "saint mary's of lynn", "ten years",
        "north quincy", "1980", "thirty-five years",
        "ap statistics", "1996",
        "patty sullivan", "1993", "commencement",
        "2014", "nasa",
        "umass", "boston college", "lawyer",
        "contracting business", "daniel",
        "the late one", "thirty-six",
        "quincy", "2008",
        "cape cod", "ireland",
        "the building years",
    ],
    "later_years": [
        "2020", "march", "zoom",
        "twenty-eight sophomores", "geometry",
        "grid", "the laptop",
        "catherine", "pandemic",
        "daniel", "lowell",
        "tutoring", "two afternoons",
        "knee replacement", "2022",
        "wollaston beach", "boardwalk",
        "fifty years married",
        "sean", "two", "michael", "one", "brian", "three",
        "the grandchildren are coming",
    ],
    "today": [
        "tuesday", "six-fifteen", "boston globe",
        "the sports", "the obituaries",
        "post office", "eileen", "seventy-three",
        "aiden", "eighth-grader", "order of operations",
        "parentheses-as-rooms",
        "roast chicken", "daniel", "saturday",
        "sean", "sunday after mass",
        "the parlor", "the grandchildren",
        "today is what we have",
        "seventy-seven",
        "i do not have a daughter",
    ],
}


def build_config() -> HarnessConfig:
    return HarnessConfig(
        narrator_label="Walter O'Donnell (7-era walk)",
        intake_payload=INTAKE_PAYLOAD,
        chapters=[
            ChapterConfig(
                label="Era 1 — Earliest Years (G Street, Southie 1948-53)",
                runtime71_era="earliest_years",
                text=CHAPTER_EARLIEST_YEARS,
                anchors=CHAPTER_ANCHORS["earliest_years"],
            ),
            ChapterConfig(
                label="Era 2 — Early School Years (Saint Augustine's 1953-59)",
                runtime71_era="early_school_years",
                text=CHAPTER_EARLY_SCHOOL_YEARS,
                anchors=CHAPTER_ANCHORS["early_school_years"],
            ),
            ChapterConfig(
                label="Era 3 — Adolescence (Boston Latin + math team 1960-65)",
                runtime71_era="adolescence",
                text=CHAPTER_ADOLESCENCE,
                anchors=CHAPTER_ANCHORS["adolescence"],
            ),
            ChapterConfig(
                label="Era 4 — Coming of Age (BC + Catherine + first sons 1966-76)",
                runtime71_era="coming_of_age",
                text=CHAPTER_COMING_OF_AGE,
                anchors=CHAPTER_ANCHORS["coming_of_age"],
            ),
            ChapterConfig(
                label="Era 5 — Building Years (North Quincy 35 yrs + 4 boys)",
                runtime71_era="building_years",
                text=CHAPTER_BUILDING_YEARS,
                anchors=CHAPTER_ANCHORS["building_years"],
            ),
            ChapterConfig(
                label="Era 6 — Later Years (retire 2020 + tutoring + boardwalk)",
                runtime71_era="later_years",
                text=CHAPTER_LATER_YEARS,
                anchors=CHAPTER_ANCHORS["later_years"],
            ),
            ChapterConfig(
                label="Era 7 — Today (a Tuesday in 2026 + the slip about a daughter)",
                runtime71_era="today",
                text=CHAPTER_TODAY,
                anchors=CHAPTER_ANCHORS["today"],
            ),
        ],
        report_prefix="seven_era_walk",
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness(build_config())))
