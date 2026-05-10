"""
capabilities.py — the approved action registry.

Every capability the workflow engine is allowed to execute lives here.
Users cannot invent new capability types — they can only configure the ones listed.

Each entry defines:
  description   — shown in AI builder + UI
  params        — input schema (type, required, description, default)
  permission    — which feature gate is needed
  audit         — whether to write an audit log entry
"""

CAPABILITIES: dict = {
    # ── Messaging ──────────────────────────────────────────────────────────
    "send_message": {
        "description": "Send a WhatsApp message to the customer, or only notify you via push",
        "params": {
            "message": {
                "type": "str",
                "required": True,
                "description": "Message text. Use {customer_name}, {business_name}, {phone} as placeholders.",
            },
            "destination": {
                "type": "str",
                "required": False,
                "default": "customer_whatsapp",
                "description": "customer_whatsapp = WhatsApp to the contact; owner_push = push notification to you only (no WhatsApp)",
            },
            "title": {
                "type": "str",
                "required": False,
                "default": "Automation",
                "description": "Title when destination is owner_push (mobile push)",
            },
        },
        "permission": "messaging",
        "audit": True,
    },

    # ── Tagging ─────────────────────────────────────────────────────────────
    "tag_contact": {
        "description": "Add a tag to the contact",
        "params": {
            "tag": {
                "type": "str",
                "required": True,
                "description": "Tag name to apply, e.g. 'hot_lead', 'vip', 'restaurant'",
            },
        },
        "permission": "contacts.write",
        "audit": True,
    },

    # ── Assignment ──────────────────────────────────────────────────────────
    "assign_owner": {
        "description": "Assign this conversation to a specific team member",
        "params": {
            "member_name": {
                "type": "str",
                "required": False,
                "description": "Name of the team member to assign to",
            },
        },
        "permission": "conversations.write",
        "audit": True,
    },

    # ── Notifications ───────────────────────────────────────────────────────
    "notify_owner": {
        "description": "Send a push notification alert to the business owner",
        "params": {
            "message": {
                "type": "str",
                "required": True,
                "description": "Alert message body",
            },
            "title": {
                "type": "str",
                "required": False,
                "default": "Workflow Alert",
                "description": "Notification title",
            },
        },
        "permission": "notifications",
        "audit": False,
    },

    # ── Follow-ups ──────────────────────────────────────────────────────────
    "create_followup": {
        "description": "Create a follow-up reminder for this customer",
        "params": {
            "note": {
                "type": "str",
                "required": True,
                "description": "Follow-up note / reason",
            },
            "due_hours": {
                "type": "int",
                "required": False,
                "default": 24,
                "description": "Hours from now when the follow-up is due",
            },
        },
        "permission": "followups.write",
        "audit": True,
    },

    # ── Pipeline ────────────────────────────────────────────────────────────
    "move_pipeline_stage": {
        "description": "Move the contact to a specific pipeline stage",
        "params": {
            "stage": {
                "type": "str",
                "required": True,
                "description": "Stage name: lead | prospect | active | won | lost",
            },
        },
        "permission": "contacts.write",
        "audit": True,
    },

    # ── Escalation ──────────────────────────────────────────────────────────
    "escalate_to_human": {
        "description": "Flag this conversation for human take-over",
        "params": {
            "reason": {
                "type": "str",
                "required": False,
                "default": "Workflow escalation",
                "description": "Reason for escalation",
            },
        },
        "permission": "conversations.write",
        "audit": True,
    },

    # ── Control flow (special — no external effect) ─────────────────────────
    "wait": {
        "description": "Pause before executing the next step",
        "params": {
            "hours": {
                "type": "float",
                "required": True,
                "description": "How many hours to wait before continuing",
            },
        },
        "permission": None,
        "audit": False,
    },

    "if_no_reply": {
        "description": "Only continue if the customer has NOT replied since the last message was sent",
        "params": {},
        "permission": None,
        "audit": False,
    },

    # ── Shopify autopilot actions ────────────────────────────────────────────
    "shopify_fulfill_order": {
        "description": "Automatically fulfill a Shopify order (optionally with tracking info)",
        "params": {
            "tracking_number": {
                "type": "str",
                "required": False,
                "default": "",
                "description": "Tracking number to attach to the fulfillment",
            },
            "tracking_company": {
                "type": "str",
                "required": False,
                "default": "",
                "description": "Carrier name, e.g. DHL, FedEx, Posta Kenya",
            },
            "notify_customer": {
                "type": "bool",
                "required": False,
                "default": True,
                "description": "Send Shopify fulfillment email to the customer",
            },
        },
        "permission": "shopify.write",
        "audit": True,
    },

    "shopify_create_discount": {
        "description": "Create a Shopify discount code automatically (for win-back or abandoned cart recovery)",
        "params": {
            "type": {
                "type": "str",
                "required": False,
                "default": "percentage",
                "description": "percentage | fixed_amount",
            },
            "value": {
                "type": "float",
                "required": True,
                "description": "Discount value — e.g. 10 for 10% off or $10 off",
            },
            "expiry_days": {
                "type": "int",
                "required": False,
                "default": 7,
                "description": "How many days until the code expires",
            },
            "usage_limit": {
                "type": "int",
                "required": False,
                "default": 1,
                "description": "Max redemptions. 1 = single-use code.",
            },
        },
        "permission": "shopify.write",
        "audit": True,
    },

    "shopify_send_recovery": {
        "description": "Send an abandoned cart recovery WhatsApp message with the checkout link (and optional discount)",
        "params": {
            "message": {
                "type": "str",
                "required": True,
                "description": "Recovery message. Use {customer_name}, {recovery_url}, {cart_value}, {discount_code} as placeholders.",
            },
            "discount_value": {
                "type": "float",
                "required": False,
                "default": 0,
                "description": "If > 0, auto-create a discount code of this % and inject it as {discount_code}",
            },
        },
        "permission": "shopify.write",
        "audit": True,
    },
}


# ── Trigger registry ───────────────────────────────────────────────────────────

TRIGGER_TYPES: dict = {
    "incoming_message": {
        "description": "When a customer sends any message",
        "condition_examples": [
            "always",
            "message_contains('price')",
            "message_contains('hello')",
        ],
    },
    "intent_detected": {
        "description": "When the AI classifies a specific intent in the customer's message",
        "condition_examples": [
            "intent == 'order'",
            "intent == 'booking'",
            "intent == 'inquiry'",
            "intent == 'complaint'",
            "intent == 'payment_received'",
        ],
    },
    "tag_added": {
        "description": "When a tag is added to a contact",
        "condition_examples": [
            "tag == 'hot_lead'",
            "tag == 'vip'",
            "always",
        ],
    },
    "customer_created": {
        "description": "When a new customer is added (first contact)",
        "condition_examples": ["always"],
    },
    "pipeline_stage_changed": {
        "description": "When a contact's pipeline stage changes",
        "condition_examples": [
            "stage == 'won'",
            "stage == 'lost'",
            "stage == 'prospect'",
        ],
    },

    # ── PayHero (M-Pesa) ──────────────────────────────────────────────────────
    "payhero_payment_received": {
        "description": "When a customer pays via M-Pesa through PayHero (auto-confirmed, no screenshot needed)",
        "condition_examples": [
            "always",
        ],
    },

    # ── Shopify autopilot triggers ─────────────────────────────────────────────
    "shopify_order_created": {
        "description": "When a new Shopify order is placed",
        "condition_examples": [
            "always",
            "order_value > 100",
            "financial_status == 'paid'",
            "fulfillment_status == 'unfulfilled'",
        ],
    },
    "shopify_order_fulfilled": {
        "description": "When a Shopify order is marked as fulfilled",
        "condition_examples": [
            "always",
        ],
    },
    "shopify_abandoned_cart": {
        "description": "When a Shopify cart is abandoned (items added but checkout not completed) for 60+ minutes",
        "condition_examples": [
            "always",
            "cart_value > 50",
        ],
    },
    "shopify_low_stock": {
        "description": "When a Shopify product's stock drops below the threshold (polled every 15 minutes)",
        "condition_examples": [
            "always",
            "quantity < 5",
            "quantity == 0",
        ],
    },
    "shopify_refund_created": {
        "description": "When a Shopify refund is issued on an order",
        "condition_examples": [
            "always",
        ],
    },
}
