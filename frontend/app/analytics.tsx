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
  currency: string;
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
  top_products: Array<{
    name: string;
    quantity: number;
    revenue: number;
    orders: number;
  }>;
  top_items: Array<{ name: string; count: number; revenue: number }>;
  best_days: Array<{ day: string; revenue: number }>;
  best_times: {
    best_day: string;
    best_hour: number;
    sample_size: number;
  };
  customers: { total: number; new_this_month: number };
  insight: {
    type: string;
    title: string;
    body: string;
    priority: string;
  } | null;
}

interface StockAnalytics {
  total_products: number;
  in_stock_count: number;
  out_of_stock_count: number;
  low_stock_count: number;
  total_inventory_value: number;
  out_of_stock: Array<{ name: string; category: string; stock_quantity?: number }>;
  low_stock: Array<{ name: string; category: string; stock_quantity: number }>;
}

export default function AnalyticsScreen() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [stock, setStock] = useState<StockAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [currency, setCurrency] = useState('USD');
  const router = useRouter();

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    try {
      const summaryRes = await apiClient.get('/analytics/summary');
      setAnalytics(summaryRes.data);
      if (summaryRes.data.currency) setCurrency(summaryRes.data.currency);
    } catch (error) {
      console.error('Error fetching analytics summary:', error);
    }
    try {
      const stockRes = await apiClient.get('/analytics/stock');
      setStock(stockRes.data);
    } catch (error) {
      console.error('Error fetching stock analytics:', error);
      setStock({ total_products: 0, in_stock_count: 0, out_of_stock_count: 0, low_stock_count: 0, total_inventory_value: 0, out_of_stock: [], low_stock: [] });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    fetchAll();
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
        <Text style={styles.headerTitle}>Analytics</Text>
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

        {/* Top Products */}
        {analytics?.top_products && analytics.top_products.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Best Selling Products (30d)</Text>
            <View style={styles.productsCard}>
              {analytics.top_products.map((product, index) => (
                <View key={index} style={[styles.productRow, index === analytics.top_products.length - 1 && { borderBottomWidth: 0 }]}>
                  <View style={styles.productInfo}>
                    <Text style={styles.productName}>{product.name}</Text>
                    <Text style={styles.productSubtext}>{product.orders} orders • {product.quantity} units</Text>
                  </View>
                  <Text style={styles.productRevenue}>
                    {currency} {product.revenue.toLocaleString()}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        )}

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

        {/* Customers */}
        {analytics?.customers && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Customers</Text>
            <View style={styles.statsGrid}>
              <View style={styles.statBox}>
                <Ionicons name="people" size={32} color="#25D366" />
                <Text style={styles.statValue}>{analytics.customers.total}</Text>
                <Text style={styles.statLabel}>Total Customers</Text>
              </View>
              <View style={styles.statBox}>
                <Ionicons name="person-add" size={32} color="#4A90D9" />
                <Text style={styles.statValue}>{analytics.customers.new_this_month}</Text>
                <Text style={styles.statLabel}>New This Month</Text>
              </View>
            </View>
          </View>
        )}

        {/* Top Selling Items */}
        {analytics?.top_items && analytics.top_items.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Top Selling Items (30d)</Text>
            <View style={styles.productsCard}>
              {analytics.top_items.map((item, index) => (
                <View key={index} style={[styles.productRow, index === analytics.top_items.length - 1 && { borderBottomWidth: 0 }]}>
                  <View style={styles.productInfo}>
                    <Text style={styles.productName}>{item.name}</Text>
                    <Text style={styles.productSubtext}>{item.count} sales</Text>
                  </View>
                  <Text style={styles.productRevenue}>{currency} {item.revenue.toLocaleString()}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Best Days of Week */}
        {analytics?.best_days && analytics.best_days.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Best Days of Week</Text>
            <View style={styles.productsCard}>
              {analytics.best_days.slice(0, 5).map((d, index) => {
                const maxRevenue = analytics.best_days[0].revenue;
                const pct = maxRevenue > 0 ? (d.revenue / maxRevenue) * 100 : 0;
                return (
                  <View key={index} style={[styles.productRow, index === Math.min(analytics.best_days.length, 5) - 1 && { borderBottomWidth: 0 }]}>
                    <View style={[styles.productInfo, { flexDirection: 'row', alignItems: 'center', gap: 10 }]}>
                      <Text style={[styles.productName, { width: 90 }]}>{d.day}</Text>
                      <View style={{ flex: 1, height: 8, backgroundColor: '#0A1628', borderRadius: 4 }}>
                        <View style={{ width: `${pct}%` as any, height: 8, backgroundColor: index === 0 ? '#25D366' : '#4A90D9', borderRadius: 4 }} />
                      </View>
                    </View>
                    <Text style={styles.productRevenue}>{currency} {d.revenue.toLocaleString()}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        )}

        {/* Best Follow-up Times */}
        {analytics?.best_times && analytics.best_times.sample_size > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Best Follow-up Times</Text>
            <View style={styles.revenueBox}>
              <Ionicons name="time" size={32} color="#8B5CF6" />
              <View style={styles.revenueInfo}>
                <Text style={[styles.revenueValue, { color: '#8B5CF6', fontSize: 18 }]}>
                  {analytics.best_times.best_day} at {analytics.best_times.best_hour}:00
                </Text>
                <Text style={styles.revenueLabel}>
                  Best time to follow up • {analytics.best_times.sample_size} data points
                </Text>
              </View>
            </View>
          </View>
        )}

        {/* Stock Analytics */}
        {stock && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Stock Overview</Text>
            <View style={styles.statsGrid}>
              <View style={styles.statBox}>
                <Ionicons name="cube-outline" size={32} color="#25D366" />
                <Text style={styles.statValue}>{stock.total_products}</Text>
                <Text style={styles.statLabel}>Total Products</Text>
              </View>
              <View style={styles.statBox}>
                <Ionicons name="checkmark-circle-outline" size={32} color="#25D366" />
                <Text style={styles.statValue}>{stock.in_stock_count}</Text>
                <Text style={styles.statLabel}>In Stock</Text>
              </View>
            </View>
            <View style={styles.statsGrid}>
              <View style={[styles.statBox, stock.low_stock_count > 0 && { borderWidth: 1, borderColor: '#FFA500' }]}>
                <Ionicons name="warning-outline" size={32} color="#FFA500" />
                <Text style={[styles.statValue, { color: '#FFA500' }]}>{stock.low_stock_count}</Text>
                <Text style={styles.statLabel}>Low Stock</Text>
              </View>
              <View style={[styles.statBox, stock.out_of_stock_count > 0 && { borderWidth: 1, borderColor: '#FF6B6B' }]}>
                <Ionicons name="close-circle-outline" size={32} color="#FF6B6B" />
                <Text style={[styles.statValue, { color: '#FF6B6B' }]}>{stock.out_of_stock_count}</Text>
                <Text style={styles.statLabel}>Out of Stock</Text>
              </View>
            </View>
            {stock.total_inventory_value > 0 && (
              <View style={styles.revenueBox}>
                <Ionicons name="pricetag" size={32} color="#4A90D9" />
                <View style={styles.revenueInfo}>
                  <Text style={[styles.revenueValue, { color: '#4A90D9' }]}>
                    {currency} {stock.total_inventory_value.toLocaleString()}
                  </Text>
                  <Text style={styles.revenueLabel}>Total Inventory Value</Text>
                </View>
              </View>
            )}
            {stock.low_stock.length > 0 && (
              <View style={{ marginTop: 12 }}>
                <Text style={[styles.sectionTitle, { fontSize: 14, color: '#FFA500', marginBottom: 8 }]}>⚠️ Low Stock Items</Text>
                <View style={styles.productsCard}>
                  {stock.low_stock.map((p, i) => (
                    <View key={i} style={[styles.productRow, i === stock.low_stock.length - 1 && { borderBottomWidth: 0 }]}>
                      <View style={styles.productInfo}>
                        <Text style={styles.productName}>{p.name}</Text>
                        <Text style={styles.productSubtext}>{p.category}</Text>
                      </View>
                      <Text style={[styles.productRevenue, { color: '#FFA500' }]}>{p.stock_quantity} left</Text>
                    </View>
                  ))}
                </View>
              </View>
            )}
            {stock.out_of_stock.length > 0 && (
              <View style={{ marginTop: 12 }}>
                <Text style={[styles.sectionTitle, { fontSize: 14, color: '#FF6B6B', marginBottom: 8 }]}>🚫 Out of Stock</Text>
                <View style={styles.productsCard}>
                  {stock.out_of_stock.map((p, i) => (
                    <View key={i} style={[styles.productRow, i === stock.out_of_stock.length - 1 && { borderBottomWidth: 0 }]}>
                      <View style={styles.productInfo}>
                        <Text style={styles.productName}>{p.name}</Text>
                        <Text style={styles.productSubtext}>{p.category}</Text>
                      </View>
                      <Text style={[styles.productRevenue, { color: '#FF6B6B' }]}>Out</Text>
                    </View>
                  ))}
                </View>
              </View>
            )}
          </View>
        )}

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
  productsCard: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 8,
  },
  productRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#2A3A52',
  },
  productInfo: {
    flex: 1,
  },
  productName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 2,
  },
  productSubtext: {
    fontSize: 12,
    color: '#8B9DC3',
  },
  productRevenue: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FFD700',
    marginLeft: 12,
  },
});
