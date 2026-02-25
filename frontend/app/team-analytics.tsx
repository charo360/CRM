import React, { useState, useEffect, useCallback } from 'react';
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

const COLORS = ['#25D366', '#4A90E2', '#F5A623', '#E74C3C', '#9B59B6', '#1ABC9C', '#E67E22'];

interface EmployeeSale {
  user_id: string;
  name: string;
  total: number;
  count: number;
}

export default function TeamAnalyticsScreen() {
  const router = useRouter();
  const [data, setData] = useState<EmployeeSale[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [currency, setCurrency] = useState('KES');

  const fetchData = useCallback(async () => {
    try {
      const [empRes, settingsRes] = await Promise.all([
        apiClient.get('/sales/by-employee'),
        settingsAPI.getSettings(),
      ]);
      setData(empRes.data);
      if (settingsRes.currency) setCurrency(settingsRes.currency);
    } catch (e) {
      console.error('Team analytics error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleRefresh = () => { setRefreshing(true); fetchData(); };

  const grandTotal = data.reduce((s, e) => s + e.total, 0);
  const grandCount = data.reduce((s, e) => s + e.count, 0);

  const topPerformer = data[0];

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Team Analytics</Text>
        <View style={{ width: 40 }} />
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color="#25D366" />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />}
        >
          {/* Summary Cards */}
          <View style={styles.summaryRow}>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryLabel}>Total Revenue</Text>
              <Text style={styles.summaryValue}>{currency} {grandTotal.toLocaleString()}</Text>
            </View>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryLabel}>Total Sales</Text>
              <Text style={styles.summaryValue}>{grandCount}</Text>
            </View>
          </View>

          {topPerformer && (
            <View style={styles.topCard}>
              <View style={styles.topCardLeft}>
                <Ionicons name="trophy" size={28} color="#F5A623" />
                <View style={{ marginLeft: 12 }}>
                  <Text style={styles.topLabel}>Top Performer</Text>
                  <Text style={styles.topName}>{topPerformer.name}</Text>
                </View>
              </View>
              <View style={styles.topCardRight}>
                <Text style={styles.topAmount}>{currency} {topPerformer.total.toLocaleString()}</Text>
                <Text style={styles.topCount}>{topPerformer.count} sales</Text>
              </View>
            </View>
          )}

          {/* Leaderboard */}
          <Text style={styles.sectionTitle}>Sales Breakdown</Text>

          {data.length === 0 ? (
            <View style={styles.emptyContainer}>
              <Ionicons name="people-outline" size={56} color="#333" />
              <Text style={styles.emptyText}>No sales recorded yet</Text>
            </View>
          ) : (
            data.map((emp, idx) => {
              const pct = grandTotal > 0 ? (emp.total / grandTotal) * 100 : 0;
              const color = COLORS[idx % COLORS.length];
              const avgSale = emp.count > 0 ? emp.total / emp.count : 0;
              return (
                <View key={emp.user_id} style={styles.card}>
                  {/* Rank + name row */}
                  <View style={styles.cardHeader}>
                    <View style={[styles.rankBadge, { backgroundColor: color }]}>
                      <Text style={styles.rankText}>#{idx + 1}</Text>
                    </View>
                    <Text style={styles.empName}>{emp.name}</Text>
                    <Text style={styles.empTotal}>{currency} {emp.total.toLocaleString()}</Text>
                  </View>

                  {/* Progress bar */}
                  <View style={styles.barBg}>
                    <View style={[styles.barFill, { width: `${pct}%` as any, backgroundColor: color }]} />
                  </View>

                  {/* Stats row */}
                  <View style={styles.statsRow}>
                    <View style={styles.stat}>
                      <Text style={styles.statValue}>{emp.count}</Text>
                      <Text style={styles.statLabel}>Sales</Text>
                    </View>
                    <View style={styles.stat}>
                      <Text style={styles.statValue}>{pct.toFixed(1)}%</Text>
                      <Text style={styles.statLabel}>Share</Text>
                    </View>
                    <View style={styles.stat}>
                      <Text style={styles.statValue}>{currency} {Math.round(avgSale).toLocaleString()}</Text>
                      <Text style={styles.statLabel}>Avg Sale</Text>
                    </View>
                  </View>
                </View>
              );
            })
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  backBtn: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  summaryRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
  },
  summaryCard: {
    flex: 1,
    backgroundColor: '#0F1923',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#1E2D3D',
  },
  summaryLabel: {
    fontSize: 12,
    color: '#888',
    marginBottom: 6,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  summaryValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  topCard: {
    backgroundColor: '#0F1923',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#F5A62340',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  topCardLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  topLabel: {
    fontSize: 11,
    color: '#F5A623',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  topName: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  topCardRight: {
    alignItems: 'flex-end',
  },
  topAmount: {
    fontSize: 16,
    fontWeight: '700',
    color: '#25D366',
  },
  topCount: {
    fontSize: 12,
    color: '#888',
    marginTop: 2,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#888',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 12,
  },
  card: {
    backgroundColor: '#0F1923',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#1E2D3D',
    marginBottom: 12,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  rankBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  rankText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  empName: {
    flex: 1,
    fontSize: 15,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  empTotal: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  barBg: {
    height: 8,
    backgroundColor: '#1E2D3D',
    borderRadius: 4,
    overflow: 'hidden',
    marginBottom: 12,
  },
  barFill: {
    height: 8,
    borderRadius: 4,
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  stat: {
    alignItems: 'center',
  },
  statValue: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  statLabel: {
    fontSize: 11,
    color: '#666',
    marginTop: 2,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: 60,
    gap: 12,
  },
  emptyText: {
    fontSize: 16,
    color: '#555',
  },
});
