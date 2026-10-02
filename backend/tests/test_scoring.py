import pytest

from backend.services.assessment import compute_iq, level_for


@pytest.mark.parametrize(("correct", "iq"), [(0, 85), (1, 95), (2, 110), (3, 128)])
def test_iq_table_is_exact(correct: int, iq: int) -> None:
    assert compute_iq(correct) == iq


@pytest.mark.parametrize(
    ("iq", "level"),
    [
        (0, "Foundation"),
        (85, "Foundation"),
        (95, "Basic"),
        (110, "Intermediate"),
        (128, "Advanced"),
    ],
)
def test_level_for_bands(iq: int, level: str) -> None:
    assert level_for(iq) == level


@pytest.mark.parametrize("correct", [-1, 4])
def test_compute_iq_rejects_out_of_range(correct: int) -> None:
    with pytest.raises(ValueError):
        compute_iq(correct)
