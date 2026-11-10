"""The air loader stores DEFRA's figure whole, so /v1/environment rounds it once (audit I-2, 2026-11-09).

The loader wrote 2 dp and the Lambda publishes `round(value, 1)`: two roundings, and 4.9% of DEFRA's PCM 2024 cells
showed 0.1 ug/m3 off (3.653998 -> 3.65 -> 3.6; 6.445105 -> 6.45 -> 6.5). Found by comparing the live API with DEFRA's own
file, which no parity gate does. Here: what the Lambda publishes from the stored number must equal DEFRA's value rounded
once, for the cases found and for any 6-decimal value.
"""

import importlib.util
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('load_defra_air_quality', ROOT / 'scripts' / 'load_defra_air_quality.py')
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)

LAMBDA = (ROOT / 'backend' / 'lambdas' / 'score' / 'app.py').read_text(encoding='utf-8')


def published(stored_text):
    """What /v1/environment shows for a stored number: the Lambda's own rounding, read from its source."""
    return round(float(stored_text), 1)


def test_the_lambda_still_rounds_air_to_one_place():
    # The other tests model the Lambda's rounding; this holds them to it.
    assert re.search(r"env\['no2AnnualMeanUgm3'\] = round\(no2, 1\)", LAMBDA)
    assert re.search(r"env\['pm25AnnualMeanUgm3'\] = round\(pm25, 1\)", LAMBDA)


def test_the_cases_the_spot_check_found():
    # AB42 4UL PM2.5, BN9 9NU PM2.5, W14 9PJ PM2.5 (printed 9.2 on an outreach sheet), SW5 9HP NO2.
    for defra in (3.653998, 6.445105, 9.149869, 23.988700):
        assert published(loader.ddb_number(defra)) == round(defra, 1), defra


def test_any_six_decimal_value_is_rounded_once():
    rng = random.Random(20261109)  # noqa: S311 - a repeatable test sample, not a secret
    for _ in range(20000):
        defra = round(rng.uniform(0, 60), 6)
        assert published(loader.ddb_number(defra)) == round(defra, 1), defra


def test_the_number_written_is_defras_figure():
    assert loader.ddb_number(3.653998) == '3.653998'
