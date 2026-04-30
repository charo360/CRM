mods = [
    'fastapi',
    'motor.motor_asyncio',
    'ai_service',
    'daily_analyzer',
    'notification_service',
    'image_handler',
    'product_organizer',
    'whatsapp_service',
    'followup_analytics',
    'smart_notifications',
    'supplier_analyzer',
    'contact_classifier',
    'daily_scheduler',
    'mongo_http_client',
]

for m in mods:
    print('IMPORTING', m, flush=True)
    __import__(m)
    print('OK', m, flush=True)

print('ALL_OK', flush=True)
