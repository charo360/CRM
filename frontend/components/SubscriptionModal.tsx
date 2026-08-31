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
import { useAuth } from '../context/AuthContext';

interface SubscriptionModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess: () => void | Promise<void>;
  currentPlan?: string | null;
  entryPoint?: 'upgrade' | 'whatsapp_trial';
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

interface StorePrice {
  price: number;
  priceString: string;
  currencyCode: string;
  // Introductory offer price from the store (e.g. 50% off first 3 months
  // configured in Play Console). Null when the product has no intro offer.
  introPriceString: string | null;
}

function formatPrice(amount: number, currencyCode: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currencyCode }).format(amount);
  } catch {
    return `${currencyCode} ${Math.round(amount).toLocaleString()}`;
  }
}

export default function SubscriptionModal({
  visible,
  onClose,
  onSuccess,
  currentPlan,
  entryPoint = 'upgrade',
}: SubscriptionModalProps) {
  const { user } = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [storePrices, setStorePrices] = useState<Record<string, StorePrice>>({});
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState(false);
  const isPreviewBuild = Constants.expoConfig?.extra?.buildChannel === 'preview';
  const isWhatsAppTrial = entryPoint === 'whatsapp_trial';

  useEffect(() => {
    if (visible) {
      loadPlans();
      loadStorePrices();
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

  // The store (Google Play / App Store) is the source of truth for what users
  // are actually charged. Show its localized prices when available; the
  // backend amounts are only a fallback for builds without IAP (e.g. Expo Go).
  const loadStorePrices = async () => {
    if (Constants.appOwnership === 'expo' || isPreviewBuild) return;
    try {
      const Purchases = require('react-native-purchases').default;
      const offerings = await Purchases.getOfferings();
      const allPackages = [
        ...(offerings.current?.availablePackages || []),
        ...Object.values(offerings.all || {}).flatMap((o: any) => o.availablePackages || []),
      ];
      const map: Record<string, StorePrice> = {};
      for (const planId of ['starter', 'standard', 'pro']) {
        const pkg = allPackages.find(
          (p: any) =>
            p.product?.identifier?.includes(planId) || p.identifier?.includes(planId)
        );
        if (pkg?.product?.priceString) {
          map[planId] = {
            price: pkg.product.price,
            priceString: pkg.product.priceString,
            currencyCode: pkg.product.currencyCode || '',
            introPriceString: pkg.product.introPrice?.priceString || null,
          };
        }
      }
      setStorePrices(map);
    } catch (error) {
      console.warn('Store prices unavailable, using backend display prices:', error);
    }
  };

  const handlePurchase = async (plan: Plan) => {
    const isExpoGo = Constants.appOwnership === 'expo';
    if (isExpoGo || isPreviewBuild) {
      Alert.alert(
        'Payments unavailable in this test app',
        'This direct preview APK is for testing Zilo features. To test a real payment, install Zilo through a Google Play internal test track or from the Play Store.',
        [{ text: 'OK' }]
      );
      return;
    }
    try {
      setPurchasing(true);
      const Purchases = require('react-native-purchases').default;

      // RevenueCat has to be identified as this Zilo user before money moves.
      // The SDK starts anonymous and is only named by the effect in
      // AuthContext, which logs out whenever `user` is briefly null and
      // swallows its own failures — so a purchase can reach Google Play while
      // the SDK still holds an $RCAnonymousID. The webhook then reports that
      // id, it matches no account, and the subscription silently never
      // activates while the caller waits on a confirmation that cannot arrive.
      if (!user?.id) {
        Alert.alert('Sign in required', 'Please sign in again before subscribing.');
        return;
      }
      if ((await Purchases.getAppUserID()) !== user.id) {
        await Purchases.logIn(user.id);
        if ((await Purchases.getAppUserID()) !== user.id) {
          Alert.alert(
            'Could not start checkout',
            'Zilo could not link this purchase to your account. Please check your connection and try again.'
          );
          return;
        }
      }

      const offerings = await Purchases.getOfferings();

      // Search all offerings for a matching product
      const allPackages = [
        ...(offerings.current?.availablePackages || []),
        ...Object.values(offerings.all || {}).flatMap((o: any) => o.availablePackages || []),
      ];
      const pkg = allPackages.find(
        (p: any) =>
          p.product?.identifier?.includes(plan.id) ||
          p.identifier?.includes(plan.id)
      );

      if (!pkg) {
        Alert.alert(
          'Coming Soon',
          'Subscriptions are being set up in the Play Store. They will be available very soon!',
          [{ text: 'OK' }]
        );
        return;
      }

      // Google Play is the authority for trial eligibility and the exact terms
      // shown before checkout. RevenueCat can briefly return cached product
      // metadata after an offer is changed in Play Console; blocking on that
      // cache made valid trial offers appear unavailable. Prefer the explicit
      // zero-cost option when it is present, otherwise let the Play checkout
      // present the eligible offer and require the customer's confirmation.
      const trialOption = [
        pkg.product?.defaultOption,
        ...(pkg.product?.subscriptionOptions ?? []),
      ].find((option: any) => option?.freePhase);
      const { customerInfo, transaction } = isWhatsAppTrial && trialOption
        ? await Purchases.purchaseSubscriptionOption(trialOption)
        : await Purchases.purchasePackage(pkg);
      if (customerInfo.entitlements.active['premium']) {
        try {
          const purchaseToken = transaction?.purchaseToken || transaction?.transactionIdentifier || transaction?.revenueCatId || '';
          const platform = require('react-native').Platform.OS === 'ios' ? 'ios' : 'android';
          const verificationResponse = await apiClient.post('/subscription/verify-purchase', {
            plan_id: plan.id,
            purchase_token: purchaseToken,
            platform,
          });

          // If direct Google verification is intentionally unavailable, wait
          // for the signed RevenueCat webhook to mark this authenticated user
          // active. This never grants access from client-side purchase data.
          if (verificationResponse.data?.status === 'pending') {
            const deadline = Date.now() + 60000;
            let confirmed = false;
            while (Date.now() < deadline) {
              await new Promise(resolve => setTimeout(resolve, 3000));
              const statusResponse = await apiClient.get('/subscription/status');
              if (statusResponse.data?.subscription_active) {
                confirmed = true;
                break;
              }
            }
            if (!confirmed) {
              Alert.alert(
                'Confirming your subscription',
                'Google Play accepted your trial. Zilo is waiting for the secure confirmation, which can take up to a minute. Please try connecting WhatsApp again shortly.'
              );
              return;
            }
          }
        } catch (syncErr) {
          console.warn('Backend subscription sync failed:', syncErr);
          Alert.alert(
            'Subscription needs verification',
            'Google Play confirmed your purchase, but Zilo could not verify it yet. Please try Restore Purchases in a moment.'
          );
          return;
        }
        Alert.alert(
          isWhatsAppTrial ? 'Trial started' : 'Subscription active',
          isWhatsAppTrial
            ? 'Your payment method is verified. Your Google Play free trial has started.'
            : 'Your subscription is now active!'
        );
        await onSuccess();
        onClose();
      }
    } catch (error: any) {
      if (!error.userCancelled) {
        Alert.alert('Error', error.message || 'Purchase failed. Please try again.');
      }
    } finally {
      setPurchasing(false);
    }
  };

  const restorePurchases = async () => {
    const isExpoGo = Constants.appOwnership === 'expo';
    if (isExpoGo || isPreviewBuild) {
      Alert.alert('Payments unavailable in this test app', 'Restore purchases works from the Google Play test or released app, not a direct preview APK.', [{ text: 'OK' }]);
      return;
    }
    try {
      setPurchasing(true);
      const Purchases = require('react-native-purchases').default;
      const customerInfo = await Purchases.restorePurchases();

      if (customerInfo.entitlements.active['premium']) {
        try {
          const entitlement = customerInfo.entitlements.active['premium'];
          const productId = entitlement?.productIdentifier || '';
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
        Alert.alert('Restored!', 'Your subscription has been restored.');
        onSuccess();
        onClose();
      } else {
        Alert.alert('No Subscription Found', 'No active subscription found on this account.');
      }
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Restore failed. Please try again.');
    } finally {
      setPurchasing(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={styles.overlay}>
        <View style={styles.modal}>
          <View style={styles.header}>
            <Text style={styles.title}>{isWhatsAppTrial ? 'Verify payment method' : 'Upgrade to Premium'}</Text>
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
                <Text style={styles.introEmoji}>{isWhatsAppTrial ? '🔒' : '🎉'}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.introTitle}>
                    {isWhatsAppTrial ? 'VERIFY BEFORE CONNECTING WHATSAPP' : '50% OFF — First 3 Months'}
                  </Text>
                  <Text style={styles.introSub}>
                    {isWhatsAppTrial
                      ? 'Google Play will securely verify your payment method. No charge today.'
                      : 'Limited-time launch offer for new subscribers'}
                  </Text>
                </View>
              </View>

              <Text style={styles.subtitle}>
                {isWhatsAppTrial
                  ? 'Choose a plan, verify your payment method in Google Play, then Zilo will connect WhatsApp automatically.'
                  : 'Choose the plan that fits your business needs'}
              </Text>

              <View style={styles.packages}>
                {plans.map((plan, index) => {
                  const isCurrentPlan = currentPlan === plan.id;
                  const store = storePrices[plan.id];
                  const fullPrice = store
                    ? store.priceString
                    : `${plan.currency} ${plan.amount.toLocaleString()}`;
                  // Prefer the real intro offer from the store; only compute
                  // 50% as a display fallback when the store didn't provide one.
                  const introPrice = store
                    ? (store.introPriceString || formatPrice(store.price / 2, store.currencyCode))
                    : `${plan.currency} ${Math.round(plan.amount * 0.5).toLocaleString()}`;
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

                      {isWhatsAppTrial ? (
                        <>
                          <Text style={styles.trialPrice}>Free for 14 days</Text>
                          <Text style={styles.afterIntro}>then {fullPrice}/month</Text>
                        </>
                      ) : (
                        <>
                          <View style={styles.priceContainer}>
                            <Text style={styles.packagePriceStrike}>
                              {fullPrice}
                            </Text>
                            <Text style={styles.packagePrice}>
                              {introPrice}
                            </Text>
                            <Text style={styles.priceInterval}>/mo · first 3 months</Text>
                          </View>
                          <Text style={styles.afterIntro}>
                            then {fullPrice}/month
                          </Text>
                        </>
                      )}

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
                          {isCurrentPlan
                            ? 'Active'
                            : purchasing
                              ? 'Processing...'
                              : isWhatsAppTrial
                                ? 'Verify & start 14-day free trial'
                                : 'Claim 50% Off'}
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
                {isWhatsAppTrial
                  ? '• A payment method is required by Google Play to activate the trial\n• No charge is made today\n• Cancel anytime in Google Play before the trial ends'
                  : '• 50% discount applied to first 3 billing months\n• Full price resumes from month 4 automatically\n• Cancel anytime from Play Store / App Store'}
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
    alignItems: 'flex-end',
    marginBottom: 16,
  },
  packagePriceStrike: {
    fontSize: 16,
    fontWeight: '500',
    color: '#6B7C93',
    textDecorationLine: 'line-through',
    marginRight: 8,
    marginBottom: 2,
  },
  packagePrice: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#2DB843',
  },
  trialPrice: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#2DB843',
    marginBottom: 8,
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
