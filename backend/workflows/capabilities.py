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

    # ── Browser Automation (Zilo Browser Operator Extension) ────────────────
    "browser_navigate": {
        "description": "Navigate your companion browser tab to a specific website/URL",
        "params": {
            "url": {
                "type": "str",
                "required": True,
                "description": "Destination web address/URL (e.g. 'https://google.com')",
            },
        },
        "permission": "browser.control",
        "audit": True,
    },

    "browser_click": {
        "description": "Click an element inside your companion browser tab",
        "params": {
            "selector": {
                "type": "str",
                "required": True,
                "description": "Target CSS selector, XPath, or 'text=Label' pattern (e.g. 'button.submit' or 'text=Confirm')",
            },
        },
        "permission": "browser.control",
        "audit": True,
    },

    "browser_type": {
        "description": "Type text into a form input inside your companion browser tab",
        "params": {
            "selector": {
                "type": "str",
                "required": True,
                "description": "CSS selector or XPath of target input element",
            },
            "text": {
                "type": "str",
                "required": True,
                "description": "The text characters or placeholders to type in",
            },
        },
        "permission": "browser.control",
        "audit": True,
    },

    "browser_scroll": {
        "description": "Scroll a specific element or section into view on the webpage",
        "params": {
            "selector": {
                "type": "str",
                "required": True,
                "description": "CSS selector or XPath targeting the element to scroll to",
            },
        },
        "permission": "browser.control",
        "audit": False,
    },

    "browser_extract": {
        "description": "Extract text, values, or attributes from webpage elements into {extracted_text}",
        "params": {
            "selector": {
                "type": "str",
                "required": True,
                "description": "CSS selector or XPath targeting the element to extract from",
            },
            "data_type": {
                "type": "str",
                "required": False,
                "default": "text",
                "description": "text | value | html | attribute",
            },
            "attribute_name": {
                "type": "str",
                "required": False,
                "default": "",
                "description": "The name of the attribute to extract (only if data_type is 'attribute', e.g. 'href')",
            },
        },
        "permission": "browser.control",
        "audit": True,
    },

    # ── Invoicing & Accounting ──────────────────────────────────────────────
    "create_invoice_draft": {
        "description": "Draft a professional client invoice and generate a dynamic public share link {invoice_url}",
        "params": {
            "currency": {
                "type": "str",
                "required": False,
                "default": "KES",
                "description": "KES | USD | EUR",
            },
            "items": {
                "type": "list",
                "required": True,
                "description": "List of dicts representing invoice line items, e.g. [{'name': 'Consulting', 'rate': 150.0, 'qty': 2}]",
            },
        },
        "permission": "billing.write",
        "audit": True,
    },

    # ── Social Media Scheduling ─────────────────────────────────────────────
    "social_publish_post": {
        "description": "Automatically publish a media/text post to Facebook, Instagram, and LinkedIn social channels via Zernio",
        "params": {
            "message": {
                "type": "str",
                "required": True,
                "description": "Text content of the social media post",
            },
            "image_url": {
                "type": "str",
                "required": False,
                "default": "",
                "description": "Public URL of an image asset to attach",
            },
            "platforms": {
                "type": "list",
                "required": False,
                "description": "Optional subset of targets: ['facebook', 'instagram', 'linkedin']",
            },
        },
        "permission": "social.write",
        "audit": True,
    },

    "design_and_publish_post": {
        "description": "Generate an elite AI design banner with Gemini and automatically publish it to social media channels",
        "params": {
            "headline": {
                "type": "str",
                "required": True,
                "description": "Bold visual headline to render inside the image banner (e.g. 'Flash Sale KES 1000' or 'Welcome {customer_name}')",
            },
            "subtext": {
                "type": "str",
                "required": False,
                "default": "",
                "description": "Secondary sub-headline text",
            },
            "cta": {
                "type": "str",
                "required": False,
                "default": "Shop Now",
                "description": "Call to action button text label, e.g. 'Claim Offer'",
            },
            "brand_color": {
                "type": "str",
                "required": False,
                "default": "",
                "description": "Hex code (e.g. #4CD137) or color name to style the banner",
            },
            "style": {
                "type": "str",
                "required": False,
                "default": "minimalist",
                "description": "minimalist | split horizon | cinematic frame | bold typographic",
            },
            "product_description": {
                "type": "str",
                "required": False,
                "default": "",
                "description": "Details about the product/brand context to feed the AI generator",
            },
            "platforms": {
                "type": "list",
                "required": False,
                "description": "Targets: ['facebook', 'instagram', 'linkedin']",
            },
        },
        "permission": "social.write",
        "audit": True,
    },

    # ── Autonomous AI Specialist Agents (Zilo Background swarm) ────────────
    "run_ai_specialist_agent": {
        "description": "Deploy an autonomous background specialist agent (e.g. Document, Social, Support) to execute a complex task and save result to {agent_result}",
        "params": {
            "agent_id": {
                "type": "str",
                "required": True,
                "description": "The target specialist agent: document | social | booking | support | general",
            },
            "task_description": {
                "type": "str",
                "required": True,
                "description": "Detailed task instructions. Supports placeholders, e.g., 'Draft a formal NDA between {business_name} and {customer_name}.'",
            },
        },
        "permission": "ai.agents",
        "audit": True,
    },

    # ── Email Communication ──────────────────────────────────────────────────
    "gmail_send_email": {
        "description": "Send a professional customized email dynamically to a customer or partner from your linked email settings",
        "params": {
            "to_email": {
                "type": "str",
                "required": True,
                "description": "Recipient email address, e.g. '{customer_email}'",
            },
            "subject": {
                "type": "str",
                "required": True,
                "description": "Email subject line",
            },
            "body_html": {
                "type": "str",
                "required": True,
                "description": "HTML or text email content. Supports placeholders.",
            },
        },
        "permission": "email.write",
        "audit": True,
    },

    # ── Social Outreach ──────────────────────────────────────────────────────
    "linkedin_send_outreach": {
        "description": "Dispatches social network comment responses or direct messages to social lead opportunities",
        "params": {
            "url": {
                "type": "str",
                "required": True,
                "description": "Target post or comment URL to reply to",
            },
            "message": {
                "type": "str",
                "required": True,
                "description": "Text content of the social outreach message",
            },
        },
        "permission": "social.write",
        "audit": True,
    },

    # ── Paid Meta Advertising ───────────────────────────────────────────────
    "meta_pause_campaign": {
        "description": "Instantly pauses a Facebook or Instagram ad campaign in real-time to save budget",
        "params": {
            "campaign_id": {
                "type": "str",
                "required": True,
                "description": "Meta campaign identifier",
            },
        },
        "permission": "ads.write",
        "audit": True,
    },

    # ── Sourcing & Grants Sourcing ──────────────────────────────────────────
    "run_funding_scan": {
        "description": "Executes an active web crawler searching for new business grants, funding opportunities, and returns bulleted list {funding_results}",
        "params": {
            "sector": {
                "type": "str",
                "required": False,
                "default": "technology",
                "description": "Sector or industry focus for the search, e.g., 'retail' or 'agriculture'",
            },
            "location": {
                "type": "str",
                "required": False,
                "default": "global",
                "description": "Geographical eligibility, e.g., 'Kenya' or 'East Africa'",
            },
        },
        "permission": "scout.write",
        "audit": True,
    },

    # ── Presentation Slide Generation ───────────────────────────────────────
    "generate_presentation_deck": {
        "description": "Compiles analytics or client proposals into a beautiful Microsoft PowerPoint (.pptx) deck and uploads it, saving link to {presentation_url}",
        "params": {
            "title": {
                "type": "str",
                "required": True,
                "description": "Title page title",
            },
            "deck_style": {
                "type": "str",
                "required": False,
                "default": "ribbon",
                "description": "ribbon | minimal | magazine | split | spotlight",
            },
        },
        "permission": "billing.write",
        "audit": True,
    },

    # ── Daily Business Intelligence Analytics ────────────────────────────────
    "generate_business_forecast": {
        "description": "Triggers daily intelligence analyzers, compiling metrics and urgency follow-up scores for all clients into {forecast_summary}",
        "params": {},
        "permission": "analytics.read",
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

    # ── Invoicing & Accounting Triggers ──────────────────────────────────────
    "invoice_created": {
        "description": "When an invoice draft or document is created in Zilo",
        "condition_examples": [
            "always",
        ],
    },
    "invoice_paid": {
        "description": "When a client invoice is marked as fully paid",
        "condition_examples": [
            "always",
            "amount > 500",
        ],
    },

    # ── Email Communication Triggers ─────────────────────────────────────────
    "gmail_email_received": {
        "description": "When a new unread email is received/synced from linked Gmail account",
        "condition_examples": [
            "always",
        ],
    },

    # ── Social Lead Harvesting Triggers ──────────────────────────────────────
    "social_lead_discovered": {
        "description": "When ScrapeCreators, Facebook, or LinkedIn workers harvest a high-intent business lead",
        "condition_examples": [
            "always",
            "platform == 'facebook'",
            "platform == 'linkedin'",
        ],
    },

    # ── Meta Advertising Triggers ───────────────────────────────────────────
    "meta_ad_health_alert": {
        "description": "When Meta Ad Health Monitor detects a spike in CPC, drop in CTR, or underperforming ads",
        "condition_examples": [
            "always",
        ],
    },
}
