"""Short, reply-based feedback surveys that run entirely in WhatsApp."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple


def _phone_key(value: Optional[str]) -> str:
    return "".join(character for character in (value or "") if character.isdigit())


def _question_id(question: Dict[str, Any], index: int) -> str:
    return str(question.get("id") or question.get("_id") or question.get("question_id") or f"question_{index + 1}")


def _question_prompt(question: Dict[str, Any], index: int, total: int) -> str:
    text = str(question.get("text") or question.get("title") or "Please share your feedback.").strip()
    kind = str(question.get("type") or "text").lower()
    prompt = f"*Question {index + 1} of {total}*\n{text}"
    if kind == "nps":
        return f"{prompt}\n\nReply with a number from *0 to 10*."
    if kind == "rating":
        return f"{prompt}\n\nReply with a number from *1 to 5*."
    if kind == "choice":
        options = [str(option).strip() for option in question.get("options", []) if str(option).strip()]
        if options:
            choices = "\n".join(f"{position + 1}. {option}" for position, option in enumerate(options))
            return f"{prompt}\n\n{choices}\n\nReply with the option number."
    return f"{prompt}\n\nReply with your answer."


def _parse_answer(question: Dict[str, Any], body: str) -> Tuple[bool, Any, str]:
    value = (body or "").strip()
    kind = str(question.get("type") or "text").lower()
    if not value:
        return False, None, "Please send an answer to continue."

    if kind in {"nps", "rating"}:
        try:
            score = int(value)
        except ValueError:
            maximum = 10 if kind == "nps" else 5
            return False, None, f"Please reply with a number from 0 to {maximum}." if kind == "nps" else "Please reply with a number from 1 to 5."
        minimum, maximum = (0, 10) if kind == "nps" else (1, 5)
        if minimum <= score <= maximum:
            return True, score, ""
        return False, None, f"Please reply with a number from {minimum} to {maximum}."

    if kind == "choice":
        options = [str(option).strip() for option in question.get("options", []) if str(option).strip()]
        if not options:
            return True, value[:1000], ""
        if value.isdigit() and 1 <= int(value) <= len(options):
            return True, options[int(value) - 1], ""
        for option in options:
            if value.casefold() == option.casefold():
                return True, option, ""
        return False, None, f"Please reply with a number from 1 to {len(options)}."

    return True, value[:1000], ""


def _nps_score(survey: Dict[str, Any], answers: list[Dict[str, Any]]) -> Optional[int]:
    by_question = {answer.get("question_id"): answer.get("answer") for answer in answers}
    for index, question in enumerate(survey.get("questions", [])):
        if str(question.get("type") or "").lower() != "nps":
            continue
        try:
            return max(0, min(10, int(by_question.get(_question_id(question, index)))))
        except (TypeError, ValueError):
            return None
    return None


async def start_conversation(db, *, user_id: str, survey: Dict[str, Any], customer: Dict[str, Any], whatsapp_service) -> Dict[str, Any]:
    """Start a tracked, one-question-at-a-time WhatsApp feedback session."""
    questions = [question for question in survey.get("questions", []) if str(question.get("text") or question.get("title") or "").strip()]
    if not questions:
        raise ValueError("Add at least one question before sending this survey")

    phone = str(customer.get("phone_number") or customer.get("phone") or "").strip()
    phone_key = _phone_key(phone)
    if not phone_key:
        raise ValueError("This customer does not have a WhatsApp phone number")

    now = datetime.utcnow()
    await db.feedback_conversations.update_many(
        {"user_id": user_id, "customer_phone_key": phone_key, "status": "active"},
        {"$set": {"status": "replaced", "closed_at": now, "updated_at": now}},
    )
    conversation_id = str(uuid.uuid4())
    conversation = {
        "_id": conversation_id,
        "user_id": user_id,
        "survey_id": survey["_id"],
        "customer_id": customer["_id"],
        "customer_name": customer.get("name", ""),
        "customer_phone": phone,
        "customer_phone_key": phone_key,
        "status": "active",
        "current_question_index": 0,
        "answers": [],
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=7),
    }
    await db.feedback_conversations.insert_one(conversation)

    business = await db.users.find_one({"_id": user_id}, {"business_name": 1, "owner_name": 1}) or {}
    business_name = business.get("business_name") or business.get("owner_name") or "we"
    customer_name = customer.get("name") or "there"
    opening = (
        f"Hi {customer_name}, {business_name} would appreciate your feedback. "
        "Please reply here in WhatsApp. Type *CANCEL* at any time to stop.\n\n"
        + _question_prompt(questions[0], 0, len(questions))
    )
    result = await whatsapp_service.send_message(
        user_id=user_id,
        to_number=phone,
        message=opening,
        customer_name=customer.get("name"),
        send_context="feedback_survey",
    )
    if result.get("status") != "success":
        message = result.get("message") or "WhatsApp did not accept the survey message"
        await db.feedback_conversations.update_one(
            {"_id": conversation_id},
            {"$set": {"status": "failed", "error": message, "updated_at": datetime.utcnow()}},
        )
        raise RuntimeError(message)

    await db.feedback_conversations.update_one(
        {"_id": conversation_id},
        {"$set": {"sent_at": datetime.utcnow(), "message_id": result.get("message_id"), "updated_at": datetime.utcnow()}},
    )
    return {"conversation_id": conversation_id, "message_id": result.get("message_id")}


async def handle_incoming_reply(db, *, user: Dict[str, Any], from_number: str, body: str, whatsapp_service) -> bool:
    """Consume an inbound WhatsApp reply only when a feedback session is active."""
    user_id = str(user.get("business_id") or user.get("_id") or "")
    phone_key = _phone_key(from_number)
    if not user_id or not phone_key or not (body or "").strip():
        return False

    now = datetime.utcnow()
    conversation = await db.feedback_conversations.find_one(
        {
            "user_id": user_id,
            "customer_phone_key": phone_key,
            "status": "active",
            "expires_at": {"$gt": now},
        },
        sort=[("created_at", -1)],
    )
    if not conversation:
        return False

    response_text = body.strip()
    if response_text.casefold() == "cancel":
        await db.feedback_conversations.update_one(
            {"_id": conversation["_id"]},
            {"$set": {"status": "cancelled", "closed_at": now, "updated_at": now}},
        )
        await whatsapp_service.send_message(
            user_id=user_id,
            to_number=conversation["customer_phone"],
            message="No problem — the feedback survey has been cancelled.",
            customer_name=conversation.get("customer_name"),
            send_context="feedback_survey",
        )
        return True
    if response_text.casefold() == "stop":
        # Let Zilo's normal STOP handler unsubscribe the customer too.
        await db.feedback_conversations.update_one(
            {"_id": conversation["_id"]},
            {"$set": {"status": "cancelled", "closed_at": now, "updated_at": now}},
        )
        return False

    survey = await db.feedback_surveys.find_one(
        {"_id": conversation["survey_id"], "user_id": user_id, "active": True}
    )
    if not survey:
        await db.feedback_conversations.update_one(
            {"_id": conversation["_id"]},
            {"$set": {"status": "cancelled", "error": "Survey is no longer active", "updated_at": now}},
        )
        return False

    questions = [question for question in survey.get("questions", []) if str(question.get("text") or question.get("title") or "").strip()]
    question_index = int(conversation.get("current_question_index", 0))
    if question_index < 0 or question_index >= len(questions):
        return False
    question = questions[question_index]
    valid, answer, error = _parse_answer(question, response_text)
    if not valid:
        await whatsapp_service.send_message(
            user_id=user_id,
            to_number=conversation["customer_phone"],
            message=f"{error}\n\n{_question_prompt(question, question_index, len(questions))}",
            customer_name=conversation.get("customer_name"),
            send_context="feedback_survey",
        )
        return True

    answers = list(conversation.get("answers") or [])
    answers.append({"question_id": _question_id(question, question_index), "answer": answer})
    next_index = question_index + 1
    if next_index < len(questions):
        await db.feedback_conversations.update_one(
            {"_id": conversation["_id"]},
            {"$set": {"answers": answers, "current_question_index": next_index, "updated_at": now}},
        )
        await whatsapp_service.send_message(
            user_id=user_id,
            to_number=conversation["customer_phone"],
            message=_question_prompt(questions[next_index], next_index, len(questions)),
            customer_name=conversation.get("customer_name"),
            send_context="feedback_survey",
        )
        return True

    score = _nps_score(survey, answers)
    response_id = str(uuid.uuid4())
    await db.feedback_responses.insert_one({
        "_id": response_id,
        "user_id": user_id,
        "survey_id": survey["_id"],
        "customer_id": conversation["customer_id"],
        "customer_name": conversation.get("customer_name", ""),
        "customer_phone": conversation.get("customer_phone", ""),
        "nps_score": score,
        "nps_category": "promoter" if score is not None and score >= 9 else ("passive" if score is not None and score >= 7 else ("detractor" if score is not None else None)),
        "answers": answers,
        "comment": "",
        "source": "whatsapp_chat",
        "created_at": now,
        "updated_at": now,
    })
    await db.feedback_surveys.update_one({"_id": survey["_id"]}, {"$inc": {"response_count": 1}})
    await db.feedback_conversations.update_one(
        {"_id": conversation["_id"]},
        {"$set": {"answers": answers, "status": "completed", "response_id": response_id, "completed_at": now, "updated_at": now}},
    )
    await whatsapp_service.send_message(
        user_id=user_id,
        to_number=conversation["customer_phone"],
        message="Thank you — your feedback has been recorded. 🙏",
        customer_name=conversation.get("customer_name"),
        send_context="feedback_survey",
    )
    return True
