# Restaurant and Creator booking flow handlers
# These will be inserted into server.py after the booking_date_input handler

RESTAURANT_PARTY_SIZE_HANDLER = '''
                # RESTAURANT PARTY SIZE HANDLER — after time slot selection
                if not button_action and not from_me and body:
                    _rest_party_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "restaurant_party_size_input"
                    })
                    if _rest_party_state:
                        _party_body = body.strip()
                        _party_size = None
                        try:
                            _party_size = int(_party_body)
                            if _party_size < 1 or _party_size > 50:
                                _party_size = None
                        except Exception:
                            pass
                        
                        ws = get_whatsapp_service(db)
                        if not _party_size:
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message="Please reply with a valid party size (1-50 people) 👥",
                                customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "restaurant_party_invalid"}
                        
                        # Ask for special requests
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "restaurant_party_size": _party_size,
                                "action_context": "restaurant_requests_input",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=(
                                f"✅ Party size: *{_party_size} {'person' if _party_size == 1 else 'people'}*\\n\\n"
                                f"📝 *Any special requests?*\\n"
                                f"_e.g. window seat, high chair, dietary restrictions_\\n\\n"
                                f"Reply *NONE* if no special requests"
                            ),
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "restaurant_party_size_input"}

                # RESTAURANT SPECIAL REQUESTS HANDLER
                if not button_action and not from_me and body:
                    _rest_req_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "restaurant_requests_input"
                    })
                    if _rest_req_state:
                        _req_body = body.strip()
                        _special_requests = "" if _req_body.lower() in ("none", "no", "nope", "nothing") else _req_body
                        
                        # Show booking summary
                        _rest_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                        _rest_svc_name = _rest_req_state.get("booking_service_name", "")
                        _rest_price = _rest_req_state.get("booking_service_price", 0)
                        _rest_date = _rest_req_state.get("booking_date", "")
                        _rest_time = _rest_req_state.get("booking_time", "")
                        _rest_party = _rest_req_state.get("restaurant_party_size", 1)
                        _rest_price_str = f"{_rest_currency} {_rest_price:,.0f}" if _rest_price else ""
                        
                        _rest_summary = (
                            f"✅ *Reservation Summary*\\n\\n"
                            f"🍽️ Restaurant: *{_rest_svc_name}*\\n"
                            f"📅 Date: *{_rest_date}*\\n"
                            f"🕐 Time: *{_rest_time}*\\n"
                            f"👥 Party size: *{_rest_party} {'person' if _rest_party == 1 else 'people'}*\\n"
                            + (f"📝 Special requests: {_special_requests}\\n" if _special_requests else "")
                            + (f"💰 Price: *{_rest_price_str}*\\n" if _rest_price_str else "")
                            + f"\\nReply *YES* to confirm or *NO* to cancel"
                        )
                        
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "restaurant_special_requests": _special_requests,
                                "action_context": "booking_confirm",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=_rest_summary,
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "restaurant_requests_input"}
'''

CREATOR_TIMELINE_HANDLER = '''
                # CREATOR TIMELINE/DEADLINE HANDLER
                if not button_action and not from_me and body:
                    _cr_timeline_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "creator_timeline_input"
                    })
                    if _cr_timeline_state:
                        import re as _re_cr
                        _timeline_body = body.strip()
                        _timeline_lower = _timeline_body.lower()
                        _today_cr = datetime.utcnow().date()
                        _parsed_deadline = None
                        
                        try:
                            # Parse relative dates like "in 3 days", "in 1 week"
                            _m_days = _re_cr.search(r"in\\s+(\\d+)\\s+days?", _timeline_lower)
                            _m_weeks = _re_cr.search(r"in\\s+(\\d+)\\s+weeks?", _timeline_lower)
                            if _m_days:
                                _parsed_deadline = _today_cr + timedelta(days=int(_m_days.group(1)))
                            elif _m_weeks:
                                _parsed_deadline = _today_cr + timedelta(weeks=int(_m_weeks.group(1)))
                            elif _timeline_lower == "today":
                                _parsed_deadline = _today_cr
                            elif _timeline_lower == "tomorrow":
                                _parsed_deadline = _today_cr + timedelta(days=1)
                            elif _timeline_lower.startswith("next "):
                                _day_name = _timeline_lower.replace("next ", "").strip()
                                if _day_name in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday"):
                                    _wd_map = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
                                    _tgt_wd = _wd_map[_day_name]
                                    _days_ahead = (_tgt_wd - _today_cr.weekday()) % 7 or 7
                                    _parsed_deadline = _today_cr + timedelta(days=_days_ahead)
                            else:
                                # Try standard date formats
                                _month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                                              "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                                              "january":1,"february":2,"march":3,"april":4,"june":6,
                                              "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
                                _m2 = _re_cr.match(r"(\\d{1,2})\\s+([a-z]+)", _timeline_lower)
                                _m3 = _re_cr.match(r"([a-z]+)\\s*(\\d{1,2})", _timeline_lower)
                                if _m2 and _m2.group(2) in _month_map:
                                    _d, _mo = int(_m2.group(1)), _month_map[_m2.group(2)]
                                    _yr = _today_cr.year if (_mo, _d) >= (_today_cr.month, _today_cr.day) else _today_cr.year + 1
                                    _parsed_deadline = datetime(_yr, _mo, _d).date()
                                elif _m3 and _m3.group(1) in _month_map:
                                    _d, _mo = int(_m3.group(2)), _month_map[_m3.group(1)]
                                    _yr = _today_cr.year if (_mo, _d) >= (_today_cr.month, _today_cr.day) else _today_cr.year + 1
                                    _parsed_deadline = datetime(_yr, _mo, _d).date()
                        except Exception:
                            _parsed_deadline = None
                        
                        ws = get_whatsapp_service(db)
                        if not _parsed_deadline or _parsed_deadline < _today_cr:
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message="I didn't catch that deadline. Please reply with a date like *in 3 days*, *next Friday*, or *March 20* 📅",
                                customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "creator_timeline_invalid"}
                        
                        # Ask for budget
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "creator_deadline": str(_parsed_deadline),
                                "action_context": "creator_budget_input",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=(
                                f"✅ Deadline: *{_parsed_deadline.strftime('%A %d %B %Y')}*\\n\\n"
                                f"💰 *What's your budget?*\\n"
                                f"_Reply with an amount or *FLEXIBLE* if negotiable_"
                            ),
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "creator_timeline_input"}

                # CREATOR BUDGET HANDLER
                if not button_action and not from_me and body:
                    _cr_budget_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "creator_budget_input"
                    })
                    if _cr_budget_state:
                        _budget_body = body.strip()
                        _budget_lower = _budget_body.lower()
                        _budget_amount = None
                        _budget_text = _budget_body
                        
                        if _budget_lower in ("flexible", "negotiable", "open", "tbd"):
                            _budget_text = "Flexible/Negotiable"
                        else:
                            try:
                                import re as _re_budget
                                _num_match = _re_budget.search(r"[\\d,]+", _budget_body)
                                if _num_match:
                                    _budget_amount = int(_num_match.group().replace(",", ""))
                            except Exception:
                                pass
                        
                        # Ask for project details
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "creator_budget": _budget_text,
                                "creator_budget_amount": _budget_amount,
                                "action_context": "creator_details_input",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=(
                                f"✅ Budget: *{_budget_text}*\\n\\n"
                                f"📝 *Tell me about your project*\\n"
                                f"_What do you need? Include any specific requirements, deliverables, or details_"
                            ),
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "creator_budget_input"}

                # CREATOR PROJECT DETAILS HANDLER
                if not button_action and not from_me and body:
                    _cr_details_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "creator_details_input"
                    })
                    if _cr_details_state:
                        _details_body = body.strip()
                        
                        # Show booking summary
                        _cr_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                        _cr_svc_name = _cr_details_state.get("booking_service_name", "")
                        _cr_price = _cr_details_state.get("booking_service_price", 0)
                        _cr_deadline = _cr_details_state.get("creator_deadline", "")
                        _cr_budget = _cr_details_state.get("creator_budget", "")
                        _cr_price_str = f"{_cr_currency} {_cr_price:,.0f}" if _cr_price else ""
                        
                        _cr_summary = (
                            f"✅ *Collaboration Summary*\\n\\n"
                            f"🎨 Service: *{_cr_svc_name}*\\n"
                            f"📅 Deadline: *{_cr_deadline}*\\n"
                            f"💰 Budget: *{_cr_budget}*\\n"
                            + (f"💵 Base price: *{_cr_price_str}*\\n" if _cr_price_str else "")
                            + f"📝 Details: {_details_body[:200]}{'...' if len(_details_body) > 200 else ''}\\n"
                            + f"\\nReply *YES* to confirm or *NO* to cancel"
                        )
                        
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "creator_project_details": _details_body,
                                "action_context": "booking_confirm",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=_cr_summary,
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "creator_details_input"}
'''
