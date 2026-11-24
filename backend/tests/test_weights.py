import pytest

from app.models import OfferBinding
from app.weights import WeightError, redistribute, validate_publish


def binding(offer_id: int, share: int = 0, *, present: bool = True, pinned: bool = False) -> OfferBinding:
    return OfferBinding(campaign_id=1, stream_id=2, offer_id=offer_id,
                        present=present, share=share, pinned=pinned)


def test_three_active_offers_sum_to_one_hundred():
    rows = [binding(3), binding(1), binding(2)]
    redistribute(rows)
    assert [row.share for row in sorted(rows, key=lambda row: row.offer_id)] == [34, 33, 33]
    assert sum(row.share for row in rows) == 100


def test_pinned_offer_keeps_share_and_remainder_is_balanced():
    rows = [binding(1, 25, pinned=True), binding(2), binding(3)]
    redistribute(rows)
    assert {row.offer_id: row.share for row in rows} == {1: 25, 2: 38, 3: 37}


def test_removed_offers_are_zero_and_excluded():
    rows = [binding(1), binding(2), binding(3, present=False, pinned=True)]
    redistribute(rows)
    assert {row.offer_id: row.share for row in rows} == {1: 50, 2: 50, 3: 0}
    assert validate_publish(rows) == rows[:2]


def test_cannot_publish_when_no_active_offer_is_free():
    with pytest.raises(WeightError, match="без pin"):
        validate_publish([binding(1, 50, pinned=True), binding(2, 50, pinned=True)])


def test_cannot_distribute_without_an_active_unpinned_offer():
    with pytest.raises(WeightError, match="без pin"):
        redistribute([binding(1, 100, pinned=True)])
