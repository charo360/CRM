"""Diagnose why the Crevo auto-reply didn't fire — replicate the poller's decision."""
import asyncio
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
ENTITY = "4eccd62d-a032-496d-8ba1-819c0b5f1e69"


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "whatsapp_crm")]
    import unipile_inbox
    from unipile_service import resolve_linkedin_account_id
    from social_autoreply import (
        _parse_ts, NEW_MESSAGE_WINDOW_MINUTES, MAX_LINKEDIN_AUTOREPLIES_PER_DAY,
        _linkedin_daily_count,
    )

    user = await db.users.find_one(
        {"$or": [{"composio_entity_id": ENTITY}, {"business_id": ENTITY}, {"_id": ENTITY}]},
        {"_id": 1, "business_id": 1, "settings.linkedin_dm_autoreply_enabled": 1},
    )
    uid = user["_id"]
    business_id = str(user.get("business_id") or uid)
    flag = (user.get("settings") or {}).get("linkedin_dm_autoreply_enabled")
    print(f"flag linkedin_dm_autoreply_enabled = {flag}")
    account_id = await resolve_linkedin_account_id(db, uid, business_id)
    print(f"account_id = {account_id}")
    cnt = await _linkedin_daily_count(db, uid, account_id)
    print(f"daily reply count today = {cnt} / cap {MAX_LINKEDIN_AUTOREPLIES_PER_DAY}")

    convs = await unipile_inbox.list_conversations(db, uid, business_id)
    org = next((c for c in convs if c.get("linkedin_channel") == "organization"), None)
    if not org:
        print("\n!! No 'organization' chat found in the first page of chats.")
        print("first chats:", [(c.get('linkedin_channel'), (c.get('participant_name') or '')[:20]) for c in convs[:8]])
        return
    cid = org["id"]
    pid = str(org.get("participantId") or "")
    print(f"\norg chat id={cid}  participant_id={pid[-10:]}")

    msgs = await unipile_inbox.get_conversation_messages(db, uid, business_id, cid, account_id)
    print(f"messages: {len(msgs)}; last 4:")
    for m in msgs[-4:]:
        sid = str(m.get("sender_id") or "")
        who = "CONTACT(inbound)" if sid == pid else "US/page(outbound)"
        print(f"   {who:18} sid={sid[-10:]:10} ts={m.get('created_at')} text={(m.get('text') or '')[:40]!r}")

    latest = msgs[-1]
    latest_inbound = str(latest.get("sender_id") or "") == pid
    latest_mid = str(latest.get("id") or "")
    state = await db.social_autoreply_state.find_one({"user_id": uid, "conversation_id": cid})
    ts = _parse_ts(latest.get("created_at") or "")
    is_live = bool(ts and (datetime.utcnow() - ts) <= timedelta(minutes=NEW_MESSAGE_WINDOW_MINUTES))

    print(f"\nlatest is inbound (from contact)? {latest_inbound}")
    print(f"latest_mid = {latest_mid}")
    print(f"state.last_handled_mid = {(state or {}).get('last_handled_mid')}")
    print(f"is_live (<{NEW_MESSAGE_WINDOW_MINUTES}min)? {is_live}  (msg ts={ts}, now={datetime.utcnow()})")

    # Replicate decision
    if not latest_inbound:
        print("\nDECISION: SKIP — newest message is NOT from the contact (our own reply or page msg).")
    elif state and state.get("last_handled_mid") == latest_mid:
        print("\nDECISION: SKIP — this message was already handled.")
    elif not state and not is_live:
        print("\nDECISION: BASELINE only — first sight + not live (older than window).")
    elif cnt >= MAX_LINKEDIN_AUTOREPLIES_PER_DAY:
        print("\nDECISION: SKIP — daily cap reached.")
    else:
        print("\nDECISION: WOULD REPLY ✓")


if __name__ == "__main__":
    asyncio.run(main())
