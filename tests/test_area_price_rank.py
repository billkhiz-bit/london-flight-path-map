"""An area page says "joint" exactly when the API gives its price rank to more than one area (audit M-23, 2026-11-12).

The API ranks tied prices with the same, better rank, so the Bay Area's 16 cities at the Census's top code ("$2M or
more") each read "35 of 50 here by price, cheapest first": an order where there is none. The builder counts the tie from
the API's own answers (price_ranks), never from a second ranking of its own.
"""
from __future__ import annotations

from collections import Counter

from .conftest import load_script

pages = load_script('build_area_pages')


def affordability_note(city: str, borough: str) -> str:
    data = pages.gather(city, borough)
    return next((f['note'] or '') for f in data['facts'] if f['label'] == 'Affordability')


def test_a_shared_rank_says_joint_and_a_single_one_does_not():
    seen_tie = False
    for city in ('bayarea', 'london'):
        counts = Counter(pages.price_ranks(city))
        for borough in pages.app.CITIES[city]['boroughs']:
            body, status = pages.answer(city, borough)
            rank = ((body.get('context') or {}).get('priceRankInCity') or {}).get('rank') if status == 200 else None
            if not rank:
                continue
            note = affordability_note(city, borough)
            if counts[rank] > 1:
                seen_tie = True
                assert f'joint {pages.ordinal(rank)} of ' in note and f'({counts[rank]} areas share that figure)' in note, (city, borough, note)
            else:
                assert 'joint' not in note and f' - {rank} of ' in note and 'cheapest first' in note, (city, borough, note)
    assert seen_tie, 'no tie found: the Bay Area top-code cities used to tie at 35th; read the data before relaxing this'


def test_ordinals():
    assert [pages.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 35, 101, 111, 112)] == [
        '1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd', '35th', '101st', '111th', '112th']
