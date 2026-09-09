"""Coverage for which AI model a picker choice actually bills for.

The app used to label an option "Claude Opus 4.7" while routing it to Claude
3.5 Sonnet, and "Claude Sonnet 4.5" reached no Claude at all - the routing
tested for the substring 'claude', which "sonnet-4.5" does not contain. Any
user on any plan could also select the dearest model, so a free trial could
run GPT-4o at twelve times the default cost indefinitely.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_service import (  # noqa: E402
    FREE_MODEL_CHOICES,
    MODEL_CHOICES,
    normalise_model_choice,
)


def test_every_choice_names_a_provider_and_a_model():
    for choice, (client_type, model_name) in MODEL_CHOICES.items():
        assert client_type, choice
        assert model_name, choice


def test_only_the_default_is_free():
    assert FREE_MODEL_CHOICES == {"standard"}
    assert set(MODEL_CHOICES) - FREE_MODEL_CHOICES == {
        "premium",
        "claude",
        "deepseek",
    }


def test_the_claude_choice_reaches_claude():
    # The bug this replaces: 'sonnet-4.5' matched no branch and quietly ran
    # the default OpenAI model while the app said Claude.
    client_type, model_name = MODEL_CHOICES["claude"]
    assert client_type == "claude"
    assert model_name.startswith("claude-")


def test_grok_settings_fall_back_to_the_free_model():
    # grok-4.6 spent ~2,500 reasoning tokens per reply, so a customer waited
    # 40-49s for a greeting. Accounts that had picked it must not be stranded
    # on a choice that no longer exists.
    for value in ("grok", "grok-4.6", "grok-4"):
        assert normalise_model_choice(value) in FREE_MODEL_CHOICES


def test_settings_saved_before_the_rebuild_still_resolve():
    assert normalise_model_choice("sonnet-4.5") == "claude"
    assert normalise_model_choice("claude-4.7") == "claude"
    assert normalise_model_choice("claude-3.5") == "claude"
    assert normalise_model_choice("gpt-5") == "standard"
    assert normalise_model_choice("gpt-4") == "premium"


def test_unknown_and_empty_values_fall_back_to_the_free_model():
    for value in (None, "", "   ", "nonsense", "gpt-9000"):
        assert normalise_model_choice(value) in FREE_MODEL_CHOICES


def test_normalising_is_stable():
    # The gate stores the normalised value, so a second pass must not move it.
    for choice in MODEL_CHOICES:
        assert normalise_model_choice(choice) == choice


def test_case_and_padding_do_not_slip_past_the_gate():
    # A choice that normalised to something outside MODEL_CHOICES would be
    # treated as free and then billed as paid.
    for value in ("PREMIUM", "  Claude  ", "DeepSeek"):
        assert normalise_model_choice(value) not in FREE_MODEL_CHOICES


def test_a_paid_model_costs_more_plan_messages_than_the_included_one():
    from ai_service import model_message_cost

    included = model_message_cost("standard")
    assert included == 1
    for choice in ("deepseek", "claude", "premium"):
        assert model_message_cost(choice) > included, choice


def test_message_cost_tracks_the_api_price_order():
    # deepseek is nearest the included model, gpt-4o the dearest, so the
    # allowance must drain in that order too.
    from ai_service import model_message_cost

    assert (
        model_message_cost("standard")
        < model_message_cost("deepseek")
        < model_message_cost("claude")
        < model_message_cost("premium")
    )


def test_unknown_or_dropped_choices_cost_one_message():
    from ai_service import model_message_cost

    for value in (None, "", "grok", "grok-4.6", "nonsense"):
        assert model_message_cost(value) == 1


def test_scheduled_owner_pushes_are_free_but_alerts_are_billed():
    # Across every account, 47 of 67 outbound messages were the daily digest
    # or motivation line going to the owner. Those are the app talking to its
    # own user. The "new contact messaged you" alert is different: a real
    # customer message triggered it, so it is billed.
    from whatsapp_service import UNBILLED_OWNER_CONTEXTS

    assert UNBILLED_OWNER_CONTEXTS == {"digest", "motivation", "zilo_morning_briefing"}
    assert "auto_reply" not in UNBILLED_OWNER_CONTEXTS


def test_owner_is_recognised_on_either_of_their_numbers():
    # Alerts have gone to both the linked WhatsApp and the signup number.
    from whatsapp_service import _same_number

    owner_whatsapp, owner_login = "12026995029", "+16505553434"
    assert _same_number("+12026995029", owner_whatsapp)
    assert _same_number(owner_login, owner_login)
    # a customer must still be billed
    assert not _same_number("+254110400963", owner_whatsapp)
    assert not _same_number("+12405054127", owner_whatsapp)


def test_number_matching_survives_formatting_and_missing_values():
    from whatsapp_service import _same_number

    assert _same_number("+1 240 505 4127", "12405054127")
    assert _same_number("0110400963", "+254110400963")  # local vs international
    for a, b in ((None, None), ("", "+123"), ("+123", "")):
        assert not _same_number(a, b)


def test_only_ai_written_sends_carry_the_model_weight():
    # The weight exists because an AI reply on a paid model costs us more to
    # produce. A message the owner typed costs the same whatever model is
    # selected, so charging 12 for it was simply an overcharge.
    from ai_service import AI_GENERATED_CONTEXTS, model_message_cost

    assert AI_GENERATED_CONTEXTS == {"auto_reply", "fallback", "ai_draft"}
    for ctx in ("manual", "product_send", "broadcast", "order_confirm", "receipt"):
        assert ctx not in AI_GENERATED_CONTEXTS, ctx
    # and the weight itself is still real for the AI paths
    assert model_message_cost("premium") > model_message_cost("standard")


def test_a_sent_ai_draft_is_charged_at_the_model_rate():
    # Write with AI and follow-ups make a real call on the selected model.
    # Regenerating stays free; the charge lands on what reaches a customer.
    from ai_service import AI_GENERATED_CONTEXTS, model_message_cost

    assert "ai_draft" in AI_GENERATED_CONTEXTS
    assert model_message_cost("claude") == 10
    # and a message the owner typed is still one, whatever model is picked
    assert "manual" not in AI_GENERATED_CONTEXTS
