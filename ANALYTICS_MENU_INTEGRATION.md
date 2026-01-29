# 📊 Analytics in 3-Dot Menu - Integration Guide

## Overview

Analytics dashboard accessible from the 3-dot menu in the follow-ups screen, showing:
- Conversion rates
- Response rates
- Revenue tracking
- Smart insights

---

## Backend Endpoints

### 1. Quick Summary (for menu preview)
```http
GET /api/analytics/summary
Authorization: Bearer {token}
```

**Response:**
```json
{
  "last_30_days": {
    "conversion_rate": 24.5,
    "response_rate": 68.2,
    "total_revenue": 125000,
    "followups": 50
  },
  "last_7_days": {
    "conversion_rate": 30.0,
    "followups": 12,
    "revenue": 35000
  },
  "insight": {
    "type": "high_urgency",
    "title": "🔥 Hot Leads Ready",
    "body": "5 high-priority customers need attention",
    "priority": "high"
  }
}
```

### 2. Full Analytics (for detailed view)
```http
GET /api/followups/analytics?days=30
Authorization: Bearer {token}
```

**Response:**
```json
{
  "stats": {
    "total_followups": 50,
    "conversion_rate": 24.5,
    "response_rate": 68.2,
    "total_revenue": 125000,
    "revenue_per_followup": 2500
  },
  "best_times": {
    "best_day": "Tuesday",
    "best_hour": 10,
    "sample_size": 34
  }
}
```

---

## Frontend Implementation

### Add Analytics Option to 3-Dot Menu

```tsx
// In followups.tsx header section
const [showAnalytics, setShowAnalytics] = useState(false);
const [analytics, setAnalytics] = useState(null);

// Add to 3-dot menu options
const menuOptions = [
  {
    icon: 'analytics',
    label: 'View Analytics',
    onPress: () => {
      setShowAnalytics(true);
      fetchAnalytics();
    }
  },
  // ... other options
];

const fetchAnalytics = async () => {
  try {
    const response = await apiClient.get('/analytics/summary');
    setAnalytics(response.data);
  } catch (error) {
    console.error('Error fetching analytics:', error);
  }
};
```

### Analytics Modal Component

```tsx
<Modal
  visible={showAnalytics}
  animationType="slide"
  presentationStyle="pageSheet"
>
  <SafeAreaView style={styles.modalContainer}>
    <View style={styles.modalHeader}>
      <Text style={styles.modalTitle}>📊 Follow-up Analytics</Text>
      <TouchableOpacity onPress={() => setShowAnalytics(false)}>
        <Ionicons name="close" size={24} color="#FFF" />
      </TouchableOpacity>
    </View>

    <ScrollView style={styles.analyticsContent}>
      {/* Last 7 Days */}
      <View style={styles.periodSection}>
        <Text style={styles.periodTitle}>Last 7 Days</Text>
        <View style={styles.statsGrid}>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>
              {analytics?.last_7_days.conversion_rate}%
            </Text>
            <Text style={styles.statLabel}>Conversion Rate</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>
              {analytics?.last_7_days.followups}
            </Text>
            <Text style={styles.statLabel}>Follow-ups</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>
              KES {analytics?.last_7_days.revenue?.toLocaleString()}
            </Text>
            <Text style={styles.statLabel}>Revenue</Text>
          </View>
        </View>
      </View>

      {/* Last 30 Days */}
      <View style={styles.periodSection}>
        <Text style={styles.periodTitle}>Last 30 Days</Text>
        <View style={styles.statsGrid}>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>
              {analytics?.last_30_days.conversion_rate}%
            </Text>
            <Text style={styles.statLabel}>Conversion Rate</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>
              {analytics?.last_30_days.response_rate}%
            </Text>
            <Text style={styles.statLabel}>Response Rate</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>
              KES {analytics?.last_30_days.total_revenue?.toLocaleString()}
            </Text>
            <Text style={styles.statLabel}>Total Revenue</Text>
          </View>
        </View>
      </View>

      {/* Smart Insight */}
      {analytics?.insight && (
        <View style={[styles.insightCard, 
          analytics.insight.priority === 'high' ? styles.insightHigh : styles.insightMedium
        ]}>
          <Text style={styles.insightTitle}>{analytics.insight.title}</Text>
          <Text style={styles.insightBody}>{analytics.insight.body}</Text>
        </View>
      )}
    </ScrollView>
  </SafeAreaView>
</Modal>
```

---

## Smart Notifications

### How It Works

**Not Spammy:**
- Max 3 notifications per day
- Same type: min 24 hours apart
- Only sends when meaningful

**Notification Types:**

1. **⚠️ Inactivity Warning**
```
"You're Losing Money"
"No follow-ups in 7 days. 25 customers neglected. 
Potential loss: KES 125,000"
```

2. **🔥 High-Value Opportunities**
```
"Hot Leads Ready"
"5 high-priority customers: John Doe, Mary Smith..."
```

3. **❓ Unanswered Questions**
```
"Customers Waiting"
"3 customers asked questions - reply now to close sales"
```

4. **🎉 Positive Feedback**
```
"Great Work!"
"You followed up with 8 customers this week. Keep it up!"
```

### Test Smart Notification

```http
POST /api/notifications/test-smart
Authorization: Bearer {token}
```

**Response:**
```json
{
  "status": "sent",
  "message": "Smart notification sent"
}
// OR
{
  "status": "skipped",
  "message": "No meaningful insight or too frequent"
}
```

---

## Styling Guide

```tsx
const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  periodSection: {
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  periodTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  statBox: {
    flex: 1,
    backgroundColor: '#1A2942',
    padding: 16,
    borderRadius: 12,
    marginHorizontal: 4,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#25D366',
    marginBottom: 4,
  },
  statLabel: {
    fontSize: 12,
    color: '#8B9DC3',
    textAlign: 'center',
  },
  insightCard: {
    margin: 20,
    padding: 16,
    borderRadius: 12,
    borderLeftWidth: 4,
  },
  insightHigh: {
    backgroundColor: '#2D1B1B',
    borderLeftColor: '#FF4444',
  },
  insightMedium: {
    backgroundColor: '#1B2D1B',
    borderLeftColor: '#FFA500',
  },
  insightTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  insightBody: {
    fontSize: 14,
    color: '#8B9DC3',
    lineHeight: 20,
  },
});
```

---

## Summary

**Location**: 3-dot menu in follow-ups screen

**What it shows:**
- ✅ Last 7 days performance
- ✅ Last 30 days performance
- ✅ Conversion & response rates
- ✅ Revenue tracking
- ✅ Smart insights (when meaningful)

**Smart Notifications:**
- ✅ Not spammy (max 3/day)
- ✅ Only meaningful insights
- ✅ Warns about money loss
- ✅ Highlights opportunities
- ✅ Positive reinforcement

**Ready to integrate!** 🚀
