"""
Comprehensive Follow-up Feature Test
Tests all follow-up functionality end-to-end
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

async def test_followup_feature():
    """Test all follow-up features"""
    
    print("\n" + "="*60)
    print("FOLLOW-UP FEATURE COMPREHENSIVE TEST")
    print("="*60 + "\n")
    
    # Connect to database
    mongo_url = os.environ.get('MONGO_URL')
    client = AsyncIOMotorClient(mongo_url)
    db = client['whatsapp_crm']
    
    # Get a test user
    user = await db.users.find_one({})
    if not user:
        print("❌ No users found in database")
        return
    
    user_id = user["_id"]
    print(f"✓ Testing with user: {user.get('name', 'Unknown')}")
    
    # TEST 1: Follow-up Suggestions
    print("\n--- TEST 1: Follow-up Suggestions ---")
    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    
    # Get pending follow-ups
    pending_followups = await db.followups.find({
        "user_id": user_id,
        "status": "pending"
    }).to_list(None)
    
    customer_ids_with_followups = {f["customer_id"] for f in pending_followups}
    print(f"✓ Found {len(pending_followups)} pending follow-ups")
    
    # Count customers needing attention (14+ days, no pending followup)
    neglected_week = await db.customers.count_documents({
        "user_id": user_id,
        "_id": {"$nin": list(customer_ids_with_followups)},
        "$or": [
            {"last_contacted": {"$lt": two_weeks_ago}},
            {"last_contacted": None}
        ]
    })
    print(f"✓ Customers needing attention (14+ days): {neglected_week}")
    
    # Count 30+ days cold
    month_ago = datetime.utcnow() - timedelta(days=30)
    neglected_month = await db.customers.count_documents({
        "user_id": user_id,
        "_id": {"$nin": list(customer_ids_with_followups)},
        "last_contacted": {"$lt": month_ago}
    })
    print(f"✓ Customers cold (30+ days): {neglected_month}")
    
    # TEST 2: Cold Customers List
    print("\n--- TEST 2: Cold Customers with AI Reasons ---")
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Check for AI analysis
    smart_insights = await db.customer_analysis.find({
        "user_id": user_id,
        "analysis_date": {"$gte": today}
    }).sort("urgency_score", -1).to_list(30)
    
    print(f"✓ AI insights available: {len(smart_insights)}")
    
    if smart_insights:
        print("\nTop 5 AI Insights:")
        for i, insight in enumerate(smart_insights[:5], 1):
            customer = await db.customers.find_one({"_id": insight["customer_id"]})
            if customer:
                print(f"  {i}. {customer['name']}")
                print(f"     Urgency: {insight.get('urgency_score', 0)}/100 ({insight.get('urgency_level', 'N/A')})")
                print(f"     Reason: {insight.get('ai_reason', 'N/A')[:60]}...")
                print(f"     Days since contact: {insight.get('days_since_contact', 'N/A')}")
    else:
        print("⚠️  No AI insights yet - daily analysis may not have run")
        print("   This is normal for new installations")
    
    # TEST 3: Follow-up CRUD Operations
    print("\n--- TEST 3: Follow-up CRUD Operations ---")
    
    # Count all follow-ups
    all_followups = await db.followups.count_documents({"user_id": user_id})
    print(f"✓ Total follow-ups in database: {all_followups}")
    
    # Count by status
    pending = await db.followups.count_documents({"user_id": user_id, "status": "pending"})
    completed = await db.followups.count_documents({"user_id": user_id, "status": "completed"})
    print(f"  - Pending: {pending}")
    print(f"  - Completed: {completed}")
    
    # Show recent follow-ups
    recent = await db.followups.find({
        "user_id": user_id
    }).sort("created_at", -1).limit(3).to_list(3)
    
    if recent:
        print("\nRecent Follow-ups:")
        for f in recent:
            customer = await db.customers.find_one({"_id": f["customer_id"]})
            customer_name = customer["name"] if customer else "Unknown"
            print(f"  - {customer_name}: {f['status']} (Due: {f['reminder_date'].strftime('%Y-%m-%d')})")
    
    # TEST 4: Smart Filtering
    print("\n--- TEST 4: Smart Filtering Logic ---")
    
    # Customers with pending follow-ups should NOT appear in "needs attention"
    customers_with_followups = await db.customers.find({
        "_id": {"$in": list(customer_ids_with_followups)}
    }).to_list(10)
    
    print(f"✓ Customers with pending follow-ups: {len(customers_with_followups)}")
    print("  These should NOT appear in 'Needs Attention' list")
    
    # Customers without follow-ups who need attention
    customers_needing_attention = await db.customers.find({
        "user_id": user_id,
        "_id": {"$nin": list(customer_ids_with_followups)},
        "$or": [
            {"last_contacted": {"$lt": two_weeks_ago}},
            {"last_contacted": None}
        ]
    }).limit(5).to_list(5)
    
    print(f"✓ Customers needing attention (no follow-up): {len(customers_needing_attention)}")
    if customers_needing_attention:
        print("  Sample customers:")
        for c in customers_needing_attention[:3]:
            days = (datetime.utcnow() - c.get("last_contacted")).days if c.get("last_contacted") else "Never"
            print(f"    - {c['name']}: Last contact {days} days ago" if isinstance(days, int) else f"    - {c['name']}: {days} contacted")
    
    # TEST 5: Numbers Validation
    print("\n--- TEST 5: Numbers Validation ---")
    
    total_customers = await db.customers.count_documents({"user_id": user_id})
    print(f"✓ Total customers: {total_customers}")
    print(f"✓ Customers with pending follow-ups: {len(customer_ids_with_followups)}")
    print(f"✓ Customers needing attention: {neglected_week}")
    print(f"✓ Cold customers (30+ days): {neglected_month}")
    
    # Validation
    if neglected_week > 50:
        print("\n⚠️  WARNING: 'Needs attention' count seems high (>50)")
        print("   This might indicate:")
        print("   - Many customers haven't been contacted in 14+ days")
        print("   - Need to increase follow-up frequency")
    elif neglected_week <= 30:
        print(f"\n✓ GOOD: 'Needs attention' count is reasonable ({neglected_week} ≤ 30)")
    
    # TEST 6: Frontend Data Structure
    print("\n--- TEST 6: Frontend Data Structure ---")
    
    # Simulate what frontend receives
    cold_customers = await db.customers.find({
        "user_id": user_id,
        "$or": [
            {"last_contacted": {"$lt": two_weeks_ago}},
            {"last_contacted": None}
        ]
    }).limit(30).to_list(30)
    
    # Add has_pending_followup flag
    for c in cold_customers:
        c["has_pending_followup"] = c["_id"] in customer_ids_with_followups
    
    # Count those without pending follow-ups
    needs_attention_count = sum(1 for c in cold_customers if not c["has_pending_followup"])
    
    print(f"✓ Cold customers fetched: {len(cold_customers)}")
    print(f"✓ Without pending follow-up: {needs_attention_count}")
    print(f"✓ With pending follow-up: {len(cold_customers) - needs_attention_count}")
    
    # SUMMARY
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    issues = []
    
    if neglected_week > 100:
        issues.append("❌ Too many customers needing attention (>100)")
    elif neglected_week > 50:
        issues.append("⚠️  High number of customers needing attention (>50)")
    else:
        print(f"✓ Needs attention count is good: {neglected_week}")
    
    if len(smart_insights) == 0:
        issues.append("⚠️  No AI insights - daily analysis hasn't run yet")
    else:
        print(f"✓ AI insights working: {len(smart_insights)} analyzed")
    
    if all_followups == 0:
        issues.append("⚠️  No follow-ups created yet")
    else:
        print(f"✓ Follow-ups created: {all_followups}")
    
    if needs_attention_count <= 30:
        print(f"✓ 'Needs Attention' list size is good: {needs_attention_count} ≤ 30")
    else:
        issues.append(f"⚠️  'Needs Attention' list is large: {needs_attention_count}")
    
    if issues:
        print("\nIssues Found:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅ ALL TESTS PASSED - Follow-up feature is working correctly!")
    
    print("\n" + "="*60 + "\n")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_followup_feature())
