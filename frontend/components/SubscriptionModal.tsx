import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { apiClient } from '../context/api';

interface SubscriptionModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess: () => void;
  currentPlan?: string | null;
}

interface Plan {
  id: string;
  name: string;
  amount: number;
  currency: string;
  amount_display: string;
  interval: string;
  features: string[];
}

export default function SubscriptionModal({ visible, onClose, onSuccess, currentPlan }: SubscriptionModalProps) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState(false);

  useEffect(() => {
    if (visible) {
      loadPlans();
    }
  }, [visible]);

  const loadPlans = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/subscription/plans');
      setPlans(response.data);
    } catch (error) {
      console.error('Error loading plans:', error);
      Alert.alert('Error', 'Failed to load subscription plans');
    } finally {
      setLoading(false);
    }
  };

  const handlePurchase = async (plan: Plan) => {
    const isExpoGo = Constants.appOwnership === 'expo';
    if (isExpoGo) {
      Alert.alert(
        'Development Mode',
        'In-app purchases require a real build installed from the Play Store / App Store.',
        [{ text: 'OK' }]
      );
      return;
    }
    try {
      setPurchasing(true);
      const Purchases = require('react-native-purchases').default;
      const offerings = await Purchases.getOfferings();
      if (!offerings.current && !offerings.all) throw new Error('No offerings available');

      // Search all offerings by product identifier (crm_starter_monthly contains 'starter', etc.)
      const allPackages = [
        ...(offerings.current?.availablePackages || []),
        ...Object.values(offerings.all || {}).flatMap((o: any) => o.availablePackages || []),
      ];
      const pkg = allPackages.find(
        (p: any) =>
          p.product?.identifier?.includes(plan.id) ||
          p.identifier?.includes(plan.id)
      );
      if (!pkg) throw new Error('Product not found');

      const { customerInfo, transaction } = await Purchases.purchasePackage(pkg);
      if (customerInfo.entitlements.active['premium']) {
        // Sync subscription to backend so subscription_plan/subscription_active are updated in DB
        try {
          const purchaseToken = transaction?.transactionIdentifier || transaction?.revenueCatId || '';
          const platform = require('react-native').Platform.OS === 'ios' ? 'ios' : 'android';
          await apiClient.post('/subscription/verify-purchase', {
            plan_id: plan.id,
            purchase_token: purchaseToken,
            platform,
          });
        } catch (syncErr) {
          console.warn('Backend subscription sync failed (non-fatal):', syncErr);
        }
        Alert.alert('Success', 'Subscription activated!');
        onSuccess();
        onClose();
      }
    } catch (error: any) {
      if (!error.userCancelled) {
        Alert.alert('Error', error.message || 'Purchase failed');
      }
    } finally {
      setPurchasing(false);
    }
  };

  const restorePurchases = async () => {
    const isExpoGo = Constants.appOwnership === 'expo';
    if (isExpoGo) {
      Alert.alert('Development Mode', 'Restore purchases requires a real build.', [{ text: 'OK' }]);
      return;
    }
    try {
      setPurchasing(true);
      const Purchases = require('react-native-purchases').default;
      const customerInfo = await Purchases.restorePurchases();

      if (customerInfo.entitlements.active['premium']) {
        // Sync restored subscription to backend
        try {
          const entitlement = customerInfo.entitlements.active['premium'];
          const productId = entitlement?.productIdentifier || '';
          // Map RevenueCat product ID to plan_id (e.g. crm_pro_monthly → pro)
          const planMatch = productId.match(/crm_(starter|standard|pro)/);
          if (planMatch) {
            const platform = require('react-native').Platform.OS === 'ios' ? 'ios' : 'android';
            await apiClient.post('/subscription/restore-purchases', {
              purchases: [{ plan_id: planMatch[1], purchase_token: entitlement?.productPlanIdentifier || productId, platform }],
            });
          }
        } catch (syncErr) {
          console.warn('Backend restore sync failed (non-fatal):', syncErr);
        }
        Alert.alert('Success', 'Subscription restored!');
        onSuccess();
        onClose();
      } else {
        Alert.alert('No Subscription', 'No active subscription found');
      }
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Restore failed');
    } finally {
      setPurchasing(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={styles.overlay}>
        <View style={styles.modal}>
          <View style={styles.header}>
            <Text style={styles.title}>Upgrade to Premium</Text>
            <TouchableOpacity onPress={onClose} disabled={purchasing}>
              <Ionicons name="close" size={28} color="#fff" />
            </TouchableOpacity>
          </View>

          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#2DB843" />
            </View>
          ) : (
            <ScrollView 
              style={styles.scrollView}
              contentContainerStyle={styles.scrollContent}
              showsVerticalScrollIndicator={false}
            >
              {/* ── Intro Offer Banner ── */}
              <View style={styles.introBanner}>
                <Text style={styles.introEmoji}>🎉</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.introTitle}>50% OFF — First 3 Months</Text>
                  <Text style={styles.introSub}>Limited-time launch offer for new subscribers</Text>
                </View>
              </View>

              <Text style={styles.subtitle}>
                Choose the plan that fits your business needs
              </Text>

              <View style={styles.packages}>
                {plans.map((plan, index) => {
                  const isCurrentPlan = currentPlan === plan.id;
                  return (
                    <TouchableOpacity
                      key={plan.id}
                      style={[
                        styles.packageCard,
                        index === 1 && styles.popularCard,
                        isCurrentPlan && styles.currentPlanCard
                      ]}
                      onPress={() => handlePurchase(plan)}
                      disabled={purchasing || isCurrentPlan}
                    >
                      {index === 1 && !isCurrentPlan && (
                        <View style={styles.popularBadge}>
                          <Text style={styles.popularText}>MOST POPULAR</Text>
                        </View>
                      )}
                      {isCurrentPlan && (
                        <View style={styles.currentBadge}>
                          <Text style={styles.currentBadgeText}>CURRENT PLAN</Text>
                        </View>
                      )}
                      
                      <Text style={styles.packageTitle}>{plan.name}</Text>

                      <View style={styles.priceContainer}>
                        <Text style={styles.packagePriceStrike}>
                          {plan.currency} {plan.amount.toLocaleString()}
                        </Text>
                        <Text style={styles.packagePrice}>
                          {plan.currency} {Math.round(plan.amount * 0.5).toLocaleString()}
                        </Text>
                        <Text style={styles.priceInterval}>/mo · first 3 months</Text>
                      </View>
                      <Text style={styles.afterIntro}>
                        then {plan.currency} {plan.amount.toLocaleString()}/month
                      </Text>

                      <View style={styles.featuresContainer}>
                        {plan.features.map((feature, idx) => (
                          <View key={idx} style={styles.feature}>
                            <Ionicons name="checkmark-circle" size={18} color="#2DB843" />
                            <Text style={styles.featureText}>{feature}</Text>
                          </View>
                        ))}
                      </View>

                      <View style={[
                        styles.selectButton,
                        isCurrentPlan && styles.selectButtonDisabled
                      ]}>
                        <Text style={[
                          styles.selectButtonText,
                          isCurrentPlan && styles.selectButtonTextDisabled
                        ]}>
                          {isCurrentPlan ? 'Active' : purchasing ? 'Processing...' : 'Claim 50% Off'}
                        </Text>
                      </View>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <TouchableOpacity
                style={styles.restoreButton}
                onPress={restorePurchases}
                disabled={purchasing}
              >
                <Text style={styles.restoreText}>Restore Purchases</Text>
              </TouchableOpacity>

              <Text style={styles.disclaimer}>
                • 50% discount applied to first 3 billing months{`\n`}
                • Full price resumes from month 4 automatically{`\n`}
                • Cancel anytime from Play Store / App Store
              </Text>
            </ScrollView>
          )}

          {purchasing && (
            <View style={styles.purchasingOverlay}>
              <ActivityIndicator size="large" color="#2DB843" />
              <Text style={styles.purchasingText}>Processing...</Text>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.8)',
    justifyContent: 'flex-end',
  },
  modal: {
    backgroundColor: '#0A1628',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    height: '85%',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#1E3A5F',
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#fff',
  },
  loadingContainer: {
    padding: 60,
    alignItems: 'center',
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 40,
  },
  subtitle: {
    fontSize: 14,
    color: '#8B9DC3',
    textAlign: 'center',
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 8,
  },
  packages: {
    padding: 20,
    gap: 16,
  },
  packageCard: {
    backgroundColor: '#1E3A5F',
    padding: 20,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#2D4A6F',
    position: 'relative',
  },
  popularCard: {
    borderColor: '#2DB843',
    backgroundColor: '#1A3A4F',
  },
  popularBadge: {
    position: 'absolute',
    top: -10,
    right: 20,
    backgroundColor: '#2DB843',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  popularText: {
    fontSize: 10,
    fontWeight: 'bold',
    color: '#fff',
    letterSpacing: 0.5,
  },
  currentBadge: {
    position: 'absolute',
    top: -10,
    right: 20,
    backgroundColor: '#25D366',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  currentBadgeText: {
    fontSize: 10,
    fontWeight: 'bold',
    color: '#fff',
    letterSpacing: 0.5,
  },
  currentPlanCard: {
    borderColor: '#25D366',
    opacity: 0.7,
  },
  packageTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 8,
  },
  priceContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
    marginBottom: 16,
  },
  packagePriceStrike: {
    fontSize: 16,
    fontWeight: '500',
    color: '#6B7C93',
    textDecorationLine: 'line-through',
    marginRight: 8,
    alignSelf: 'flex-end',
    marginBottom: 2,
  },
  packagePrice: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#2DB843',
  },
  afterIntro: {
    fontSize: 11,
    color: '#6B7C93',
    marginTop: -10,
    marginBottom: 12,
    fontStyle: 'italic',
  },
  priceInterval: {
    fontSize: 12,
    color: '#8B9DC3',
    marginLeft: 4,
    alignSelf: 'flex-end',
    marginBottom: 3,
  },
  introBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0F2D1A',
    borderWidth: 1.5,
    borderColor: '#25D366',
    borderRadius: 12,
    marginHorizontal: 20,
    marginTop: 16,
    padding: 12,
    gap: 10,
  },
  introEmoji: {
    fontSize: 24,
  },
  introTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#25D366',
  },
  introSub: {
    fontSize: 12,
    color: '#6B9E7A',
    marginTop: 2,
  },
  featuresContainer: {
    marginBottom: 16,
  },
  feature: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  featureText: {
    fontSize: 13,
    color: '#B0C4DE',
    marginLeft: 8,
    flex: 1,
  },
  selectButton: {
    backgroundColor: '#2DB843',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  selectButtonDisabled: {
    backgroundColor: '#1E3A5F',
  },
  selectButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#fff',
  },
  selectButtonTextDisabled: {
    color: '#8B9DC3',
  },
  restoreButton: {
    alignSelf: 'center',
    padding: 16,
    marginTop: 8,
  },
  restoreText: {
    fontSize: 14,
    color: '#2DB843',
    textDecorationLine: 'underline',
  },
  disclaimer: {
    fontSize: 11,
    color: '#6B7C93',
    textAlign: 'center',
    paddingHorizontal: 30,
    paddingBottom: 20,
    lineHeight: 16,
  },
  purchasingOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(10, 22, 40, 0.95)',
    justifyContent: 'center',
    alignItems: 'center',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  purchasingText: {
    fontSize: 16,
    color: '#fff',
    marginTop: 12,
  },
});
