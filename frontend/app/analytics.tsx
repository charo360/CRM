import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { apiClient, settingsAPI } from '../context/api';

interface Analytics {
  last_30_days: {
    conversion_rate: number;
    response_rate: number;
    total_revenue: number;
    followups: number;
  };
  last_7_days: {
    conversion_rate: number;
    followups: number;
    revenue: number;
  };
  insight: {
    type: string;
    title: string;
    body: string;
    priority: string;
  } | null;
}

export default function AnalyticsScreen() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [currency, setCurrency] = useState('USD');
  const router = useRouter();

  useEffect(() => {
    const loadCurrency = async () => {
      try {
        const settings = await settingsAPI.getSettings();
        if (settings.currency) setCurrency(settings.currency);
      } catch (e) {}
    };
    loadCurrency();
  }, []);

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    try {
      const response = await apiClient.get('/analytics/summary');
      setAnalytics(response.data);
    } catch (error) {
      console.error('Error fetching analytics:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    fetchAnalytics();
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#25D366" />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Follow-up Analytics</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
        }
      >
        {/* Smart Insight */}
        {analytics?.insight && (
          <View style={[
            styles.insightCard,
            analytics.insight.priority === 'high' ? styles.insightHigh : 
            analytics.insight.priority === 'medium' ? styles.insightMedium : 
            styles.insightLow
          ]}>
            <Text style={styles.insightTitle}>{analytics.insight.title}</Text>
            <Text style={styles.insightBody}>{analytics.insight.body}</Text>
          </View>
        )}

        {/* Last 7 Days */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Last 7 Days</Text>
          <View style={styles.statsGrid}>
            <View style={styles.statBox}>
              <Ionicons name="trending-up" size={32} color="#25D366" />
              <Text style={styles.statValue}>
                {analytics?.last_7_days.conversion_rate || 0}%
              </Text>
              <Text style={styles.statLabel}>Conversion Rate</Text>
            </View>
            <View style={styles.statBox}>
              <Ionicons name="chatbubbles" size={32} color="#4A90D9" />
              <Text style={styles.statValue}>
                {analytics?.last_7_days.followups || 0}
              </Text>
              <Text style={styles.statLabel}>Follow-ups</Text>
            </View>
          </View>
          <View style={styles.revenueBox}>
            <Ionicons name="cash" size={32} color="#FFD700" />
            <View style={styles.revenueInfo}>
              <Text style={styles.revenueValue}>
                {currency} {analytics?.last_7_days.revenue?.toLocaleString() || 0}
              </Text>
              <Text style={styles.revenueLabel}>Revenue Generated</Text>
            </View>
          </View>
        </View>

        {/* Last 30 Days */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Last 30 Days</Text>
          <View style={styles.statsGrid}>
            <View style={styles.statBox}>
              <Ionicons name="trending-up" size={32} color="#25D366" />
              <Text style={styles.statValue}>
                {analytics?.last_30_days.conversion_rate || 0}%
              </Text>
              <Text style={styles.statLabel}>Conversion Rate</Text>
            </View>
            <View style={styles.statBox}>
              <Ionicons name="checkmark-done" size={32} color="#4A90D9" />
              <Text style={styles.statValue}>
                {analytics?.last_30_days.response_rate || 0}%
              </Text>
              <Text style={styles.statLabel}>Response Rate</Text>
            </View>
          </View>
          <View style={styles.statsGrid}>
            <View style={styles.statBox}>
              <Ionicons name="chatbubbles" size={32} color="#8B5CF6" />
              <Text style={styles.statValue}>
                {analytics?.last_30_days.followups || 0}
              </Text>
              <Text style={styles.statLabel}>Total Follow-ups</Text>
            </View>
            <View style={styles.statBox}>
              <Ionicons name="cash" size={32} color="#FFD700" />
              <Text style={styles.statValue}>
                {Math.round((analytics?.last_30_days.total_revenue || 0) / (analytics?.last_30_days.followups || 1))}
              </Text>
              <Text style={styles.statLabel}>Per Follow-up</Text>
            </View>
          </View>
          <View style={styles.revenueBox}>
            <Ionicons name="wallet" size={32} color="#FFD700" />
            <View style={styles.revenueInfo}>
              <Text style={styles.revenueValue}>
                {currency} {analytics?.last_30_days.total_revenue?.toLocaleString() || 0}
              </Text>
              <Text style={styles.revenueLabel}>Total Revenue</Text>
            </View>
          </View>
        </View>

        {/* Info Card */}
        <View style={styles.infoCard}>
          <Ionicons name="information-circle" size={24} color="#4A90D9" />
          <View style={styles.infoContent}>
            <Text style={styles.infoTitle}>How Analytics Work</Text>
            <Text style={styles.infoText}>
              • Conversion: Follow-ups that led to sales{'\n'}
              • Response: Customers who replied{'\n'}
              • Revenue: Total from converted follow-ups{'\n'}
              • Automatically tracked from your conversations
            </Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  backButton: {
    padding: 4,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  scrollContent: {
    paddingBottom: 40,
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
    backgroundColor: '#2D2A1B',
    borderLeftColor: '#FFA500',
  },
  insightLow: {
    backgroundColor: '#1B2D1B',
    borderLeftColor: '#25D366',
  },
  insightTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  insightBody: {
    fontSize: 14,
    color: '#8B9DC3',
    lineHeight: 20,
  },
  section: {
    paddingHorizontal: 20,
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
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
    color: '#FFFFFF',
    marginTop: 8,
    marginBottom: 4,
  },
  statLabel: {
    fontSize: 12,
    color: '#8B9DC3',
    textAlign: 'center',
  },
  revenueBox: {
    flexDirection: 'row',
    backgroundColor: '#1A2942',
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 4,
  },
  revenueInfo: {
    marginLeft: 16,
    flex: 1,
  },
  revenueValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFD700',
    marginBottom: 4,
  },
  revenueLabel: {
    fontSize: 14,
    color: '#8B9DC3',
  },
  infoCard: {
    flexDirection: 'row',
    backgroundColor: '#1A2942',
    margin: 20,
    padding: 16,
    borderRadius: 12,
  },
  infoContent: {
    marginLeft: 12,
    flex: 1,
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  infoText: {
    fontSize: 13,
    color: '#8B9DC3',
    lineHeight: 20,
  },
});
