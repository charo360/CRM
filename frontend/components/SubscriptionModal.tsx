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
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
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
      const planOrder = ['starter', 'standard', 'pro'];
      const planRank = (id: string) => {
        const rank = planOrder.indexOf(id);
        return rank === -1 ? planOrder.length : rank;
      };
      const orderedPlans = [...response.data].sort(
        (a: Plan, b: Plan) => planRank(a.id) - planRank(b.id)
      );
      setPlans(orderedPlans);
      setSelectedPlanId((selected) =>
        orderedPlans.some((plan: Plan) => plan.id === selected)
          ? selected
          : orderedPlans[0]?.id || null
      );
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

  /**
   * Wait for the server to recognise a subscription Google Play already holds.
   *
   * Access is granted by the server, never by what the app can see, so this
   * polls until the backend has heard the signed confirmation.
   */
  const waitForServerToConfirm = async (timeoutMs = 60000) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const statusResponse = await apiClient.get('/subscription/status');
        // Only a paid subscription counts as confirmation. Not
        // subscription_active, a raw flag an account can carry with no plan
        // behind it; and not dashboard_access, which the free trial satisfies
        // — accepting that reported a subscription found for someone who had
        // only ever started a trial, and then refused them at the door.
        if (statusResponse.data?.paid_active) {
          return true;
        }
      } catch (statusErr) {
        console.warn('Could not read subscription status:', statusErr);
      }
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
    return false;
  };

  /**
   * Adopt a subscription this Google account already owns.
   *
   * Play refuses a second purchase of a subscription it already holds, and the
   * app used to surface that refusal as a bare error - so someone who deleted
   * their account and signed up again was told to buy a subscription, then told
   * they already had one, with no way past. Claiming the existing purchase is
   * the correct move, and it is what the person meant to do anyway.
   */
  const adoptExistingSubscription = async (): Promise<boolean> => {
    try {
      const Purchases = require('react-native-purchases').default;
      let info = await Purchases.getCustomerInfo();
      if (!info.entitlements.active['premium']) {
        // Not visible yet on this install; ask Play directly before giving up.
        info = await Purchases.restorePurchases();
      }
      // Ask the signed server ledger immediately. The old implementation first
      // waited 20 seconds, then claimed, then waited another 20 seconds. That
      // made every checkout feel frozen even for people who had never paid.
      try {
        await apiClient.post('/subscription/claim-purchase', {
          app_user_ids: [
            await Purchases.getAppUserID(),
            info.originalAppUserId,
          ].filter(Boolean),
        });
      } catch (claimErr) {
        console.warn('Could not claim an unapplied purchase:', claimErr);
      }
      return await waitForServerToConfirm(8000);
    } catch (err) {
      console.warn('Could not adopt an existing subscription:', err);
      return false;
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

      // Open Google Play promptly. If Play says this account already owns a
      // subscription, the error handler below runs the recovery path once.
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
      if (error.userCancelled) return;
      // Play refuses to sell a subscription this account already owns. That is
      // not a failure to report - it means the subscription exists and should
      // be claimed.
      const message = String(error?.message || '');
      const alreadyOwned =
        /already\s+(subscribed|own)/i.test(message) ||
        error?.code === 'ProductAlreadyPurchasedError' ||
        error?.underlyingErrorMessage?.includes('already');
      if (alreadyOwned && (await adoptExistingSubscription())) {
        Alert.alert(
          'Subscription found',
          'You already have an active Zilo subscription, so it has been linked to this account. No new charge was made.',
        );
        await onSuccess();
        onClose();
        return;
      }
      if (alreadyOwned) {
        Alert.alert(
          'Already subscribed',
          'Google Play confirms this account already owns Zilo, but it could not be linked automatically. Do not purchase again; contact support so the existing subscription can be attached.',
        );
        return;
      }
      Alert.alert('Error', message || 'Purchase failed. Please try again.');
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
      // Name the SDK as this Zilo user before restoring. The SDK starts
      // anonymous, and restoring while it still is attaches the subscription to
      // an anonymous id: RevenueCat then reports that id, it matches no
      // account, and the payment is recorded against nobody. There is already
      // a live subscription on this project sitting under an $RCAnonymousID
      // for exactly that reason.
      if (!user?.id) {
        Alert.alert('Sign in required', 'Please sign in again before restoring.');
        return;
      }
      if ((await Purchases.getAppUserID()) !== user.id) {
        await Purchases.logIn(user.id);
        if ((await Purchases.getAppUserID()) !== user.id) {
          Alert.alert(
            'Could not restore',
            'Zilo could not link this purchase to your account. Please check your connection and try again.',
          );
          return;
        }
      }
      const customerInfo = await Purchases.restorePurchases();

      if (customerInfo.entitlements.active['premium']) {
        // A previous purchase can be sitting in the signed RevenueCat ledger
        // under this install's anonymous identity. Point the server at every
        // identity the SDK can prove belongs to this install before polling.
        // The endpoint still grants access only from RevenueCat's signed event.
        try {
          await apiClient.post('/subscription/claim-purchase', {
            app_user_ids: [
              await Purchases.getAppUserID(),
              customerInfo.originalAppUserId,
            ].filter(Boolean),
          });
        } catch (claimErr) {
          console.warn('Could not claim restored purchase:', claimErr);
        }

        const confirmed = await waitForServerToConfirm(15000);

        if (!confirmed) {
          Alert.alert(
            'Still confirming your subscription',
            'Google Play has your subscription, but Zilo could not link it automatically. Contact support with this screen; do not purchase again.'
          );
          return;
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
                    <View
                      key={plan.id}
                      style={[
                        styles.packageCard,
                        index === 1 && styles.popularCard,
                        isCurrentPlan && styles.currentPlanCard,
                        selectedPlanId === plan.id && styles.selectedPlanCard,
                      ]}
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

                      <TouchableOpacity
                        onPress={() => setSelectedPlanId(plan.id)}
                        disabled={purchasing || isCurrentPlan}
                        style={[
                        styles.selectButton,
                        selectedPlanId === plan.id && styles.selectedButton,
                        isCurrentPlan && styles.selectButtonDisabled
                      ]}>
                        <Text style={[
                          styles.selectButtonText,
                          isCurrentPlan && styles.selectButtonTextDisabled
                        ]}>
                          {isCurrentPlan
                            ? 'Active'
                            : selectedPlanId === plan.id
                              ? 'Selected'
                              : `Choose ${plan.name}`}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  );
                })}
              </View>

              {selectedPlanId && (() => {
                const selectedPlan = plans.find(plan => plan.id === selectedPlanId);
                if (!selectedPlan) return null;
                return (
                  <TouchableOpacity
                    style={styles.checkoutButton}
                    onPress={() => handlePurchase(selectedPlan)}
                    disabled={purchasing}
                  >
                    <Text style={styles.checkoutButtonText}>
                      {purchasing
                        ? 'Processing...'
                        : isWhatsAppTrial
                          ? `Continue with ${selectedPlan.name} — verify payment method`
                          : `Continue with ${selectedPlan.name}`}
                    </Text>
                  </TouchableOpacity>
                );
              })()}

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
  selectedPlanCard: {
    borderColor: '#25D366',
    borderWidth: 3,
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
  selectedButton: {
    backgroundColor: '#176B2C',
  },
  checkoutButton: {
    backgroundColor: '#2DB843',
    marginHorizontal: 20,
    marginBottom: 12,
    paddingVertical: 15,
    paddingHorizontal: 16,
    borderRadius: 10,
    alignItems: 'center',
  },
  checkoutButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '700',
    textAlign: 'center',
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
