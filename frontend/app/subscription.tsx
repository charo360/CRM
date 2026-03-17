import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as RNIap from 'react-native-iap';

const SUBSCRIPTION_SKUS = [
  'crm_starter_monthly',
  'crm_starter_yearly',
  'crm_standard_monthly',
  'crm_standard_yearly',
  'crm_pro_monthly',
  'crm_pro_yearly',
];

interface SubscriptionPlan {
  id: string;
  tier: string;
  period: string;
  name: string;
  description: string;
  price?: string;
  limits: {
    max_customers: number;
    max_products: number;
    max_team_members: number;
    ai_messages_per_month: number;
    features: string[];
  };
}

export default function SubscriptionScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState(false);
  const [currentSubscription, setCurrentSubscription] = useState<any>(null);
  const [products, setProducts] = useState<RNIap.Subscription[]>([]);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);

  useEffect(() => {
    initIAP();
    loadSubscriptionStatus();
    loadPlans();

    return () => {
      RNIap.endConnection();
    };
  }, []);

  const initIAP = async () => {
    try {
      await RNIap.initConnection();
      console.log('IAP connection initialized');

      if (Platform.OS === 'android') {
        await RNIap.flushFailedPurchasesCachedAsPendingAndroid();
      }

      const subs = await RNIap.getSubscriptions({ skus: SUBSCRIPTION_SKUS });
      setProducts(subs);
      console.log('Subscriptions loaded:', subs.length);
    } catch (error) {
      console.error('Error initializing IAP:', error);
    }
  };

  const loadSubscriptionStatus = async () => {
    try {
      const token = await AsyncStorage.getItem('token');
      const backendUrl = process.env.EXPO_PUBLIC_BACKEND_URL;

      const response = await fetch(`${backendUrl}/api/billing/subscription-status`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setCurrentSubscription(data);
      }
    } catch (error) {
      console.error('Error loading subscription:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadPlans = async () => {
    try {
      const backendUrl = process.env.EXPO_PUBLIC_BACKEND_URL;
      const response = await fetch(`${backendUrl}/api/billing/subscription-products`);

      if (response.ok) {
        const data = await response.json();
        setPlans(data.products);
      }
    } catch (error) {
      console.error('Error loading plans:', error);
    }
  };

  const handlePurchase = async (productId: string) => {
    setPurchasing(true);

    try {
      const purchase = await RNIap.requestSubscription({ sku: productId });

      if (purchase) {
        await verifyPurchase(productId, purchase.purchaseToken);
      }
    } catch (error: any) {
      if (error.code !== 'E_USER_CANCELLED') {
        Alert.alert('Purchase Failed', error.message || 'An error occurred');
      }
    } finally {
      setPurchasing(false);
    }
  };

  const verifyPurchase = async (productId: string, purchaseToken: string) => {
    try {
      const token = await AsyncStorage.getItem('token');
      const backendUrl = process.env.EXPO_PUBLIC_BACKEND_URL;

      const response = await fetch(`${backendUrl}/api/billing/verify-purchase`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          product_id: productId,
          purchase_token: purchaseToken,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setCurrentSubscription(data.subscription);
        Alert.alert('Success', 'Subscription activated!');
        await RNIap.finishTransaction({ purchase: { productId, purchaseToken } as any });
      } else {
        Alert.alert('Verification Failed', 'Could not verify your purchase');
      }
    } catch (error) {
      console.error('Error verifying purchase:', error);
      Alert.alert('Error', 'Failed to verify purchase');
    }
  };

  const handleRestorePurchases = async () => {
    setLoading(true);

    try {
      const availablePurchases = await RNIap.getAvailablePurchases();

      if (availablePurchases.length === 0) {
        Alert.alert('No Purchases', 'No previous purchases found');
        setLoading(false);
        return;
      }

      const purchases = availablePurchases.map((p) => ({
        product_id: p.productId,
        purchase_token: p.purchaseToken,
      }));

      const token = await AsyncStorage.getItem('token');
      const backendUrl = process.env.EXPO_PUBLIC_BACKEND_URL;

      const response = await fetch(`${backendUrl}/api/billing/restore-purchases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ purchases }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.restored > 0) {
          setCurrentSubscription(data.subscription);
          Alert.alert('Success', `Restored ${data.restored} subscription(s)`);
        } else {
          Alert.alert('No Active Subscriptions', 'No active subscriptions found');
        }
      }
    } catch (error) {
      console.error('Error restoring purchases:', error);
      Alert.alert('Error', 'Failed to restore purchases');
    } finally {
      setLoading(false);
    }
  };

  const getProductPrice = (productId: string) => {
    const product = products.find((p) => p.productId === productId);
    return product?.localizedPrice || 'Loading...';
  };

  const renderPlanCard = (plan: SubscriptionPlan) => {
    const isCurrentPlan =
      currentSubscription?.tier === plan.tier &&
      currentSubscription?.billing_period === plan.period;
    const isActive = currentSubscription?.status === 'active';

    return (
      <View
        key={plan.id}
        style={[styles.planCard, isCurrentPlan && styles.currentPlanCard]}
      >
        <View style={styles.planHeader}>
          <Text style={styles.planName}>{plan.name}</Text>
          {isCurrentPlan && isActive && (
            <View style={styles.currentBadge}>
              <Text style={styles.currentBadgeText}>Current</Text>
            </View>
          )}
        </View>

        <Text style={styles.planDescription}>{plan.description}</Text>

        <Text style={styles.planPrice}>{getProductPrice(plan.id)}</Text>

        <View style={styles.limitsContainer}>
          <LimitItem
            icon="people-outline"
            text={
              plan.limits.max_customers === -1
                ? 'Unlimited customers'
                : `Up to ${plan.limits.max_customers} customers`
            }
          />
          <LimitItem
            icon="cube-outline"
            text={
              plan.limits.max_products === -1
                ? 'Unlimited products'
                : `Up to ${plan.limits.max_products} products`
            }
          />
          <LimitItem
            icon="chatbubbles-outline"
            text={
              plan.limits.ai_messages_per_month === -1
                ? 'Unlimited AI messages'
                : `${plan.limits.ai_messages_per_month} AI messages/month`
            }
          />
          <LimitItem
            icon="people-circle-outline"
            text={
              plan.limits.max_team_members === -1
                ? 'Unlimited team members'
                : `Up to ${plan.limits.max_team_members} team members`
            }
          />
        </View>

        {!isCurrentPlan && (
          <TouchableOpacity
            style={styles.subscribeButton}
            onPress={() => handlePurchase(plan.id)}
            disabled={purchasing}
          >
            {purchasing ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.subscribeButtonText}>Subscribe</Text>
            )}
          </TouchableOpacity>
        )}
      </View>
    );
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#25D366" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#333" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Subscription</Text>
        <TouchableOpacity onPress={handleRestorePurchases}>
          <Text style={styles.restoreText}>Restore</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {currentSubscription && currentSubscription.tier !== 'free' && (
          <View style={styles.currentSubCard}>
            <Text style={styles.currentSubTitle}>Current Plan</Text>
            <Text style={styles.currentSubTier}>
              {currentSubscription.tier.toUpperCase()} -{' '}
              {currentSubscription.billing_period}
            </Text>
            <Text style={styles.currentSubStatus}>
              Status: {currentSubscription.status}
            </Text>
            {currentSubscription.expiry_date && (
              <Text style={styles.currentSubExpiry}>
                {currentSubscription.auto_renewing ? 'Renews' : 'Expires'} on:{' '}
                {new Date(currentSubscription.expiry_date).toLocaleDateString()}
              </Text>
            )}
          </View>
        )}

        <Text style={styles.sectionTitle}>Monthly Plans</Text>

        {plans
          .filter((p) => p.period === 'monthly')
          .map((plan) => renderPlanCard(plan))}

        <Text style={styles.sectionTitle}>Yearly Plans (Save 17%)</Text>

        {plans
          .filter((p) => p.period === 'yearly')
          .map((plan) => renderPlanCard(plan))}

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            • Subscriptions auto-renew unless canceled
          </Text>
          <Text style={styles.footerText}>
            • Cancel anytime from Google Play Store
          </Text>
          <Text style={styles.footerText}>
            • All prices in your local currency
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const LimitItem = ({ icon, text }: { icon: any; text: string }) => (
  <View style={styles.limitItem}>
    <Ionicons name={icon} size={18} color="#666" />
    <Text style={styles.limitText}>{text}</Text>
  </View>
);

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  backButton: {
    padding: 8,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
  },
  restoreText: {
    fontSize: 14,
    color: '#25D366',
    fontWeight: '500',
  },
  content: {
    flex: 1,
    padding: 16,
  },
  currentSubCard: {
    backgroundColor: '#25D366',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
  },
  currentSubTitle: {
    fontSize: 14,
    color: '#fff',
    opacity: 0.9,
  },
  currentSubTier: {
    fontSize: 20,
    fontWeight: '700',
    color: '#fff',
    marginTop: 4,
  },
  currentSubStatus: {
    fontSize: 14,
    color: '#fff',
    marginTop: 8,
  },
  currentSubExpiry: {
    fontSize: 12,
    color: '#fff',
    opacity: 0.8,
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 16,
    marginTop: 8,
  },
  planCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 2,
    borderColor: '#e0e0e0',
  },
  currentPlanCard: {
    borderColor: '#25D366',
  },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  planName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
  },
  currentBadge: {
    backgroundColor: '#25D366',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  currentBadgeText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  planDescription: {
    fontSize: 14,
    color: '#666',
    marginBottom: 12,
  },
  planPrice: {
    fontSize: 24,
    fontWeight: '700',
    color: '#25D366',
    marginBottom: 16,
  },
  limitsContainer: {
    marginBottom: 16,
  },
  limitItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  limitText: {
    fontSize: 14,
    color: '#666',
    marginLeft: 8,
  },
  subscribeButton: {
    backgroundColor: '#25D366',
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
  },
  subscribeButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    marginTop: 24,
    marginBottom: 32,
  },
  footerText: {
    fontSize: 12,
    color: '#999',
    marginBottom: 4,
  },
});
