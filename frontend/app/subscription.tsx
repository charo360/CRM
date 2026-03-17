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

// These must match exactly what you create in Google Play Console
const SUBSCRIPTION_SKUS = [
  'crm_starter_monthly',
  'crm_starter_yearly',
  'crm_standard_monthly',
  'crm_standard_yearly',
  'crm_pro_monthly',
  'crm_pro_yearly',
];

interface Plan {
  id: string;          // 'starter' | 'standard' | 'pro'
  name: string;
  amount: number;
  currency: string;
  amount_display: string;
  interval: string;
  features: string[];
}

interface SubStatus {
  subscription_plan: string | null;
  subscription_active: boolean;
  subscription_date: string | null;
  subscription_expiry: string | null;
  auto_renewing: boolean;
  extra_credits: number;
  limits: Record<string, any>;
}

export default function SubscriptionScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState<string | null>(null);
  const [subStatus, setSubStatus] = useState<SubStatus | null>(null);
  const [iapProducts, setIapProducts] = useState<RNIap.Subscription[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);

  useEffect(() => {
    initIAP();
    loadData();
    return () => { RNIap.endConnection(); };
  }, []);

  const initIAP = async () => {
    try {
      await RNIap.initConnection();
      if (Platform.OS === 'android') {
        await RNIap.flushFailedPurchasesCachedAsPendingAndroid();
      }
      const subs = await RNIap.getSubscriptions({ skus: SUBSCRIPTION_SKUS });
      setIapProducts(subs);
    } catch (err) {
      console.error('IAP init error:', err);
    }
  };

  const loadData = async () => {
    try {
      const token = await AsyncStorage.getItem('token');
      const base = process.env.EXPO_PUBLIC_BACKEND_URL;
      const headers = { Authorization: `Bearer ${token}` };

      const [statusRes, plansRes] = await Promise.all([
        fetch(`${base}/api/subscription/status`, { headers }),
        fetch(`${base}/api/subscription/plans`, { headers }),
      ]);

      if (statusRes.ok) setSubStatus(await statusRes.json());
      if (plansRes.ok) setPlans(await plansRes.json());
    } catch (err) {
      console.error('Error loading subscription data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Get the Play Store price for a given SKU (e.g. crm_starter_monthly)
  const getStorePrice = (planId: string, yearly = false) => {
    const sku = `crm_${planId}_${yearly ? 'yearly' : 'monthly'}`;
    const product = iapProducts.find((p) => p.productId === sku);
    return product?.localizedPrice ?? null;
  };

  const handlePurchase = async (planId: string, yearly = false) => {
    const sku = `crm_${planId}_${yearly ? 'yearly' : 'monthly'}`;
    setPurchasing(sku);
    try {
      const purchase = await RNIap.requestSubscription({ sku });
      if (purchase) {
        await verifyPurchaseWithServer(purchase.productId, purchase.purchaseToken, 'android');
        await RNIap.finishTransaction({ purchase } as any);
      }
    } catch (err: any) {
      if (err.code !== 'E_USER_CANCELLED') {
        Alert.alert('Purchase Failed', err.message || 'An error occurred');
      }
    } finally {
      setPurchasing(null);
    }
  };

  const verifyPurchaseWithServer = async (
    productId: string,
    purchaseToken: string,
    platform: string,
  ) => {
    try {
      const token = await AsyncStorage.getItem('token');
      const base = process.env.EXPO_PUBLIC_BACKEND_URL;
      // Extract plan_id from product ID e.g. crm_pro_monthly -> pro
      const plan_id = productId.replace('crm_', '').replace('_monthly', '').replace('_yearly', '');

      const res = await fetch(`${base}/api/subscription/verify-purchase`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ plan_id, purchase_token: purchaseToken, platform }),
      });

      if (res.ok) {
        Alert.alert('Success! 🎉', 'Your subscription is now active.');
        await loadData();
      } else {
        const err = await res.json();
        Alert.alert('Verification Failed', err.detail || 'Could not verify purchase');
      }
    } catch (err) {
      console.error('Verify error:', err);
      Alert.alert('Error', 'Failed to verify purchase with server');
    }
  };

  const handleRestorePurchases = async () => {
    setLoading(true);
    try {
      const available = await RNIap.getAvailablePurchases();
      if (!available.length) {
        Alert.alert('Nothing to Restore', 'No previous purchases found on this account.');
        return;
      }

      const token = await AsyncStorage.getItem('token');
      const base = process.env.EXPO_PUBLIC_BACKEND_URL;
      const purchases = available.map((p: any) => ({
        purchase_token: p.purchaseToken,
        plan_id: p.productId.replace('crm_', '').replace('_monthly', '').replace('_yearly', ''),
        platform: 'android',
      }));

      const res = await fetch(`${base}/api/subscription/restore-purchases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ purchases }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.restored > 0) {
          await loadData();
          Alert.alert('Restored!', `Plan "${data.plan}" has been restored.`);
        } else {
          Alert.alert('Nothing Found', data.message || 'No active subscriptions found.');
        }
      }
    } catch (err) {
      Alert.alert('Error', 'Failed to restore purchases');
    } finally {
      setLoading(false);
    }
  };

  const renderPlanRow = (plan: Plan, yearly = false) => {
    const sku = `crm_${plan.id}_${yearly ? 'yearly' : 'monthly'}`;
    const storePrice = getStorePrice(plan.id, yearly);
    const isCurrentPlan = subStatus?.subscription_plan === plan.id && subStatus?.subscription_active;
    const isPurchasing = purchasing === sku;

    // For yearly, double the monthly amount as estimate (store price overrides this)
    const displayPrice = storePrice
      ? `${storePrice}/${yearly ? 'yr' : 'mo'}`
      : `${plan.currency} ${yearly ? (plan.amount * 10).toLocaleString() : plan.amount.toLocaleString()}/${yearly ? 'yr' : 'mo'}`;

    return (
      <View key={sku} style={[styles.planCard, isCurrentPlan && styles.currentPlanCard]}>
        <View style={styles.planHeader}>
          <View>
            <Text style={styles.planName}>{plan.name}</Text>
            {yearly && <Text style={styles.saveBadge}>Save ~17%</Text>}
          </View>
          {isCurrentPlan && (
            <View style={styles.activeBadge}>
              <Text style={styles.activeBadgeText}>✓ Active</Text>
            </View>
          )}
        </View>

        <Text style={styles.planPrice}>{displayPrice}</Text>

        <View style={styles.featureList}>
          {plan.features.map((f, i) => (
            <View key={i} style={styles.featureRow}>
              <Ionicons name="checkmark-circle" size={16} color="#25D366" />
              <Text style={styles.featureText}>{f}</Text>
            </View>
          ))}
        </View>

        {!isCurrentPlan && (
          <TouchableOpacity
            style={[styles.subscribeButton, isPurchasing && styles.subscribeButtonDisabled]}
            onPress={() => handlePurchase(plan.id, yearly)}
            disabled={!!purchasing}
          >
            {isPurchasing ? (
              <ActivityIndicator color="#fff" size="small" />
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
        <Text style={styles.loadingText}>Loading plans...</Text>
      </View>
    );
  }

  const isActive = subStatus?.subscription_active;
  const currentPlan = subStatus?.subscription_plan;

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
        {/* Current subscription banner */}
        {isActive && currentPlan && (
          <View style={styles.currentSubCard}>
            <Text style={styles.currentSubLabel}>Your Active Plan</Text>
            <Text style={styles.currentSubPlan}>{currentPlan.toUpperCase()}</Text>
            {subStatus?.subscription_expiry && (
              <Text style={styles.currentSubExpiry}>
                {subStatus.auto_renewing ? 'Auto-renews' : 'Expires'} on{' '}
                {new Date(subStatus.subscription_expiry).toLocaleDateString()}
              </Text>
            )}
          </View>
        )}

        {/* Free plan notice */}
        {!isActive && (
          <View style={styles.freePlanBanner}>
            <Ionicons name="information-circle-outline" size={20} color="#666" />
            <Text style={styles.freePlanText}>
              You're on the Free plan. Upgrade to unlock more features.
            </Text>
          </View>
        )}

        <Text style={styles.sectionTitle}>Monthly Plans</Text>
        {plans.map((plan) => renderPlanRow(plan, false))}

        <Text style={styles.sectionTitle}>Yearly Plans (Best Value)</Text>
        {plans.map((plan) => renderPlanRow(plan, true))}

        <View style={styles.footer}>
          <Text style={styles.footerText}>• Prices shown in your local currency via Google Play</Text>
          <Text style={styles.footerText}>• Subscriptions renew automatically unless canceled</Text>
          <Text style={styles.footerText}>• Cancel anytime in Google Play Store → Subscriptions</Text>
          <Text style={styles.footerText}>• Countries not listed use USD pricing</Text>
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
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 12, color: '#666', fontSize: 14 },
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
  backButton: { padding: 8 },
  headerTitle: { fontSize: 18, fontWeight: '600', color: '#333' },
  restoreText: { fontSize: 14, color: '#25D366', fontWeight: '500' },
  content: { flex: 1, padding: 16 },
  currentSubCard: {
    backgroundColor: '#25D366',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  currentSubLabel: { fontSize: 13, color: '#fff', opacity: 0.85 },
  currentSubPlan: { fontSize: 22, fontWeight: '700', color: '#fff', marginTop: 4 },
  currentSubExpiry: { fontSize: 12, color: '#fff', opacity: 0.8, marginTop: 6 },
  freePlanBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f0f0f0',
    borderRadius: 10,
    padding: 12,
    marginBottom: 20,
    gap: 8,
  },
  freePlanText: { flex: 1, fontSize: 13, color: '#555' },
  sectionTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: '#333',
    marginBottom: 12,
    marginTop: 8,
  },
  planCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 14,
    borderWidth: 2,
    borderColor: '#e0e0e0',
  },
  currentPlanCard: { borderColor: '#25D366' },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 6,
  },
  planName: { fontSize: 17, fontWeight: '700', color: '#222' },
  saveBadge: {
    fontSize: 11,
    color: '#25D366',
    fontWeight: '600',
    marginTop: 2,
  },
  activeBadge: {
    backgroundColor: '#e6f9ef',
    borderColor: '#25D366',
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 10,
  },
  activeBadgeText: { color: '#25D366', fontSize: 12, fontWeight: '700' },
  planPrice: {
    fontSize: 22,
    fontWeight: '700',
    color: '#25D366',
    marginBottom: 12,
  },
  featureList: { marginBottom: 14 },
  featureRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6, gap: 6 },
  featureText: { fontSize: 13, color: '#555', flex: 1 },
  subscribeButton: {
    backgroundColor: '#25D366',
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
  },
  subscribeButtonDisabled: { backgroundColor: '#a8d5bb' },
  subscribeButtonText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  footer: { marginTop: 24, marginBottom: 40 },
  footerText: { fontSize: 12, color: '#aaa', marginBottom: 5 },
  limitItem: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  limitText: { fontSize: 14, color: '#666', marginLeft: 8 },
});
