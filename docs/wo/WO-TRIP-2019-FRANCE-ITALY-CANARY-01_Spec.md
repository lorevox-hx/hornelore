# WO-TRIP-2019-FRANCE-ITALY-CANARY-01

## Purpose

Create a second trip-shaped canary using the 2019 France / Italy outline from `May 26 thru June 15.docx`.

This is not the Trip Tab build. It is a reusable test harness that verifies Lori can handle an older itinerary-style document and convert it into narrator-shaped factual chains.

## Source itinerary anchors

- May 27–28: ABQ → DFW → LHR → CDG.
- May 28–June 6: Paris base at 41 Rue de Reuilly.
- Paris chains: Luxembourg / Panthéon / Latin Quarter / Sainte-Chapelle / Notre-Dame / Pompidou; Eiffel / Trocadéro / Orsay; Montmartre; Marché d'Aligre; Louvre; Arc de Triomphe / Nissim de Camondo / Galeries Lafayette.
- June 6–13: Paris Gare de Lyon → Aix-en-Provence by TGV; base at 15 rue Suffren.
- Provence side trip: Avignon / Palais des Papes / Avignon Bridge / Arles.
- June 28–July 2: Rome base at Via Francesco Carletti.
- July 2: FCO → DFW → ABQ.

## Harness file

`/scripts/run_trip_2019_france_italy_canary_harness.py`

## Fixture file for later UI tests

`/fixtures/trips/trip_2019_france_italy_fixture.json`

## Behavior under test

- Factual-chain classification for airport, rail, base-and-spoke, and museum/monument chains.
- English-first response despite French/Italian place names and accents.
- No Spanish/Italian full-response language drift.
- No legacy “Sorry — let’s continue” fallback.
- No stub-collapse replies.
- No sensory/emotion pivot on graded factual-chain turns.
- Meta-feedback rejection of atmosphere/sensory framing.

## UI-later tests enabled by fixture

- Trip overview renders title/date range.
- Regions render in chronological order.
- Paris stops nest under Paris base.
- Aix/Provence stops nest under Aix base.
- Rome and return flight render as close/return region.
- Location Guide explains foreign terms in English without changing chat language.
- Future photo clustering can attach photos to region/stop with confidence fields.

## Acceptance

GREEN if score is >= 86% and no hard clamp fires.

Hard clamps:
- English-first violation on any graded turn.
- Stub collapse on any graded turn.
- Drift-repair dominance.
- Sensory pivot after meta-feedback.
