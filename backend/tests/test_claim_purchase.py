"""Coverage for the identity filter on claiming an unapplied purchase.

Without Google Play server verification a purchase only becomes real when a
RevenueCat webhook matches it to an account, so an orphaned payment has to be
claimable. That makes the filter deciding *which* identities a caller may point
at the thing standing between a customer's subscription and somebody else.

The filter is read out of server.py rather than imported: importing the module
starts schedulers against the shared database.
"""
import io
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def claimable(app_user_ids, owner_id, user_id):
    """Run the real filter expression from server.py against given identities."""
    source = io.open(BACKEND / "server.py", encoding="utf-8").read()
    match = re.search(
        r"candidates = \[\n(.*?)\n    \]\[:5\]", source, re.S
    )
    assert match, "claim identity filter not found in server.py"
    expression = "candidates = [\n" + match.group(1) + "\n][:5]"
    namespace = {"body": {"app_user_ids": app_user_ids},
                 "owner_id": owner_id, "user": {"_id": user_id}}
    exec(expression, namespace)
    return namespace["candidates"]


OWNER = "11111111-1111-1111-1111-111111111111"
VICTIM = "22222222-2222-2222-2222-222222222222"
ANON = "$RCAnonymousID:75d817be2aca446aaa48157bdba93a6b"


def test_an_anonymous_purchase_can_be_claimed():
    """The real failure: a purchase made before the SDK knew who was buying."""
    assert claimable([ANON], OWNER, OWNER) == [ANON]


def test_your_own_account_id_can_be_claimed():
    assert claimable([OWNER], OWNER, OWNER) == [OWNER]


def test_another_account_cannot_be_named():
    """The whole point: nobody claims someone else's subscription."""
    assert claimable([VICTIM], OWNER, OWNER) == []
    assert claimable([VICTIM, ANON], OWNER, OWNER) == [ANON]


def test_a_team_member_may_claim_for_its_business_not_a_stranger():
    member = "33333333-3333-3333-3333-333333333333"
    assert claimable([OWNER], OWNER, member) == [OWNER]
    assert claimable([member], OWNER, member) == [member]
    assert claimable([VICTIM], OWNER, member) == []


def test_junk_and_empty_input_is_dropped():
    assert claimable([], OWNER, OWNER) == []
    assert claimable([None, "", "not-an-id"], OWNER, OWNER) == []


def test_no_more_than_five_identities_are_considered():
    """A caller must not be able to sweep the ledger with a long list."""
    many = [f"$RCAnonymousID:{i:032x}" for i in range(50)]
    assert len(claimable(many, OWNER, OWNER)) == 5
