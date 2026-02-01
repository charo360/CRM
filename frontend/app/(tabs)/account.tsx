import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Linking,
  Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../../context/AuthContext';
import { apiClient } from '../../context/api';
import { NotificationHandler } from '../../utils/notification-handler';

interface SubscriptionPlan {
  id: string;
  name: string;
  amount: number;
  amount_display: string;
  interval: string;
  features: string[];
}

interface Stats {
  customers_count: number;
  pending_followups: number;
  sales_this_month: number;
  revenue_this_month: number;
}

interface Product {
  id: string;
  name: string;
  price: number;
  image_url: string;
  category: string;
  in_stock: boolean;
}

export default function AccountScreen() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(false);

  const { user, logout, refreshUser } = useAuth();
  const router = useRouter();

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [plansRes, statsRes] = await Promise.all([
        apiClient.get('/subscription/plans'),
        apiClient.get('/stats'),
      ]);
      setPlans(plansRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubscribe = async (plan: SubscriptionPlan) => {
    if (!user) return;

    Alert.prompt(
      'Enter Email',
      'Enter your email for payment receipt',
      async (email) => {
        if (!email || !email.includes('@')) {
          Alert.alert('Error', 'Please enter a valid email');
          return;
        }

        setSubscribing(true);
        try {
          const response = await apiClient.post('/subscription/initialize', {
            email: email,
            plan_id: plan.id,
          });

          if (response.data.authorization_url) {
            Linking.openURL(response.data.authorization_url);
            Alert.alert(
              'Payment Started',
              'Complete the payment in your browser. Your subscription will be activated automatically.',
              [{ text: 'OK', onPress: () => refreshUser() }]
            );
          }
        } catch (error: any) {
          Alert.alert('Error', error.response?.data?.detail || 'Failed to start payment');
        } finally {
          setSubscribing(false);
        }
      },
      'plain-text',
      '',
      'email-address'
    );
  };

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/');
          },
        },
      ]
    );
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
      <ScrollView contentContainerStyle={styles.scrollContent}>

        {/* Business Info */}
        <View style={styles.section}>
          <View style={styles.businessCard}>
            <View style={styles.businessAvatar}>
              <Text style={styles.businessAvatarText}>
                {user?.business_name?.charAt(0) || 'B'}
              </Text>
            </View>
            <View style={styles.businessInfo}>
              <Text style={styles.businessName}>{user?.business_name || 'Your Business'}</Text>
              <Text style={styles.businessPhone}>{user?.phone_number}</Text>
              {user?.owner_name && (
                <Text style={styles.ownerName}>{user.owner_name}</Text>
              )}
            </View>
            <View style={[
              styles.subscriptionBadge,
              user?.subscription_active && styles.subscriptionActive,
            ]}>
              <Text style={styles.subscriptionText}>
                {user?.subscription_active ? user?.subscription_plan || 'Active' : 'Free Trial'}
              </Text>
            </View>
          </View>
        </View>

        {/* Stats */}
        {
          stats && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>This Month</Text>
              <View style={styles.statsGrid}>
                <View style={styles.statCard}>
                  <Ionicons name="people" size={24} color="#25D366" />
                  <Text style={styles.statValue}>{stats.customers_count}</Text>
                  <Text style={styles.statLabel}>Customers</Text>
                </View>
                <View style={styles.statCard}>
                  <Ionicons name="notifications" size={24} color="#FFD700" />
                  <Text style={styles.statValue}>{stats.pending_followups}</Text>
                  <Text style={styles.statLabel}>Follow-ups</Text>
                </View>
                <View style={styles.statCard}>
                  <Ionicons name="receipt" size={24} color="#4A90D9" />
                  <Text style={styles.statValue}>{stats.sales_this_month}</Text>
                  <Text style={styles.statLabel}>Sales</Text>
                </View>
                <View style={styles.statCard}>
                  <Ionicons name="cash" size={24} color="#25D366" />
                  <Text style={styles.statValue}>KES {stats.revenue_this_month.toLocaleString()}</Text>
                  <Text style={styles.statLabel}>Revenue</Text>
                </View>
              </View>
            </View>
          )
        }

        {/* Subscription Plans */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Subscription Plans</Text>
          {plans.map((plan) => (
            <View
              key={plan.id}
              style={[
                styles.planCard,
                user?.subscription_plan === plan.id && styles.planCardActive,
              ]}
            >
              <View style={styles.planHeader}>
                <Text style={styles.planName}>{plan.name}</Text>
                <Text style={styles.planPrice}>{plan.amount_display}</Text>
              </View>
              <View style={styles.planFeatures}>
                {plan.features.map((feature, index) => (
                  <View key={index} style={styles.featureRow}>
                    <Ionicons name="checkmark-circle" size={16} color="#25D366" />
                    <Text style={styles.featureText}>{feature}</Text>
                  </View>
                ))}
              </View>
              {user?.subscription_plan === plan.id ? (
                <View style={styles.currentPlanBadge}>
                  <Text style={styles.currentPlanText}>Current Plan</Text>
                </View>
              ) : (
                <TouchableOpacity
                  style={styles.subscribeButton}
                  onPress={() => handleSubscribe(plan)}
                  disabled={subscribing}
                >
                  <Text style={styles.subscribeButtonText}>
                    {subscribing ? 'Processing...' : 'Subscribe'}
                  </Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
        </View>

        {/* Settings */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Settings</Text>
          <View style={styles.settingsCard}>
            <TouchableOpacity 
              style={styles.settingItem}
              onPress={() => router.push('../analytics' as any)}
            >
              <Ionicons name="analytics-outline" size={24} color="#25D366" />
              <Text style={styles.settingText}>Follow-up Analytics</Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity style={styles.settingItem}>
              <Ionicons name="cube-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Product Catalog</Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity style={styles.settingItem}>
              <Ionicons name="book-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Business Knowledge</Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity style={styles.settingItem}>
              <Ionicons name="chatbubble-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Auto Reply</Text>
              <Switch
                value={false}
                onValueChange={() => {}}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </TouchableOpacity>
            <TouchableOpacity style={styles.settingItem}>
              <Ionicons name="notifications-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Notifications</Text>
              <Switch
                value={true}
                onValueChange={() => {}}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </TouchableOpacity>
          </View>
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={24} color="#FF4444" />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>

        <Text style={styles.version}>Version 1.0.0</Text>
      </ScrollView >

      {/* Modals */}
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
  scrollContent: {
    paddingBottom: 40,
  },
  header: {
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  section: {
    paddingHorizontal: 20,
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 12,
  },
  businessCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 16,
  },
  businessAvatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
  },
  businessAvatarText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  businessInfo: {
    flex: 1,
    marginLeft: 16,
  },
  businessName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  businessPhone: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },
  ownerName: {
    fontSize: 12,
    color: '#888',
    marginTop: 2,
  },
  subscriptionBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#666',
    borderRadius: 12,
  },
  subscriptionActive: {
    backgroundColor: '#25D366',
  },
  subscriptionText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#FFFFFF',
    textTransform: 'capitalize',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  statCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 8,
  },
  statLabel: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  planCard: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 20,
    marginBottom: 12,
  },
  planCardActive: {
    borderWidth: 2,
    borderColor: '#25D366',
  },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  planName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  planPrice: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#25D366',
  },
  planFeatures: {
    marginBottom: 16,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  featureText: {
    fontSize: 14,
    color: '#888',
    marginLeft: 8,
  },
  currentPlanBadge: {
    backgroundColor: '#25D366',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  currentPlanText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  subscribeButton: {
    backgroundColor: '#25D366',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  subscribeButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  settingsCard: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    overflow: 'hidden',
  },
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#0A1628',
  },
  settingText: {
    flex: 1,
    fontSize: 16,
    color: '#FFFFFF',
    marginLeft: 12,
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 20,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  logoutText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FF4444',
    marginLeft: 8,
  },
  version: {
    fontSize: 12,
    color: '#666',
    textAlign: 'center',
    marginTop: 20,
  },
  // Product Catalog Styles
  catalogHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: '#F5F5F5',
    borderRadius: 12,
    marginBottom: 8,
  },
  catalogHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  catalogIcon: {
    fontSize: 20,
  },
  catalogContent: {
    marginTop: 12,
  },
  uploadButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 12,
    gap: 8,
    marginBottom: 16,
  },
  uploadButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  productCount: {
    fontSize: 14,
    color: '#666',
    marginBottom: 12,
  },
  productGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  productCard: {
    width: '31%',
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#E0E0E0',
  },
  productImage: {
    width: '100%',
    height: 100,
    backgroundColor: '#F5F5F5',
  },
  productInfo: {
    padding: 8,
  },
  productName: {
    fontSize: 12,
    fontWeight: '600',
    color: '#333',
    marginBottom: 4,
  },
  productPrice: {
    fontSize: 11,
    color: '#25D366',
    fontWeight: '600',
  },
  deleteButton: {
    position: 'absolute',
    top: 4,
    right: 4,
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 4,
  },
  emptyText: {
    textAlign: 'center',
    color: '#999',
    fontSize: 14,
    paddingVertical: 20,
  },
});
