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

interface Bundle {
  bundle_id: string;
  credits: number;
  price_usd: number;
  label: string;
}

interface CreditBundleModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess: (creditsAdded: number) => void;
  currentCredits?: number;
}

const BUNDLE_ICONS: Record<string, string> = {
  charo360_credits_500:  '⚡',
  charo360_credits_1000: '🔥',
  charo360_credits_2500: '💎',
  charo360_credits_5000: '🚀',
};

export default function CreditBundleModal({ visible, onClose, onSuccess, currentCredits = 0 }: CreditBundleModalProps) {
  const { user } = useAuth();
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState<string | null>(null); // bundle_id being purchased
  const isPreviewBuild = Constants.expoConfig?.extra?.buildChannel === 'preview';

  useEffect(() => {
    if (visible) loadBundles();
  }, [visible]);

  const loadBundles = async () => {
    try {
      setLoading(true);
      const res = await apiClient.get('/subscription/credit-bundles');
      setBundles(res.data);
    } catch (err) {
      Alert.alert('Error', 'Could not load credit bundles. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleBuy = async (bundle: Bundle) => {
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
      setPurchasing(bundle.bundle_id);
      const Purchases = require('react-native-purchases').default;

      // A RevenueCat purchase is only useful when it is associated with the
      // signed-in Zilo account.  Otherwise the secure webhook cannot know
      // which customer should receive the purchased credits.
      if (!user?.id) {
        Alert.alert('Sign in required', 'Please sign in again before buying credits.');
        return;
      }
      if ((await Purchases.getAppUserID()) !== user.id) {
        await Purchases.logIn(user.id);
      }
      if ((await Purchases.getAppUserID()) !== user.id) {
        Alert.alert(
          'Could not start checkout',
          'Zilo could not link this purchase to your account. Please check your connection and try again.'
        );
        return;
      }

      // Keep the balance from the server, not the value currently rendered in
      // the Account tab, so the confirmation below remains correct after a
      // prior top-up or an app refresh.
      let balanceBefore = currentCredits;
      try {
        const status = await apiClient.get('/subscription/status');
        balanceBefore = Number(status.data?.extra_credits ?? balanceBefore);
      } catch {
        // The secure webhook will still be the source of truth. A cached
        // balance only affects the number shown in the success message.
      }

      // Fetch all available products (consumables)
      const offerings = await Purchases.getOfferings();
      const allPackages = [
        ...(offerings.current?.availablePackages || []),
        ...Object.values(offerings.all || {}).flatMap((o: any) => o.availablePackages || []),
      ];

      // Match by exact bundle_id (which IS the Google Play product ID: charo360_credits_*)
      const pkg = allPackages.find(
        (p: any) =>
          p.product?.identifier === bundle.bundle_id ||
          p.product?.identifier?.includes(bundle.bundle_id) ||
          p.identifier === bundle.bundle_id
      );

      if (!pkg) {
        Alert.alert(
          'Credit bundle unavailable',
          `"${bundle.label}" is not yet available from Google Play for this app account. Please try another bundle or contact Zilo support.`,
          [{ text: 'OK' }]
        );
        return;
      }

      // RevenueCat sends the verified NON_RENEWING_PURCHASE event to Zilo.
      // We deliberately do not grant credits from a client-provided purchase
      // token: a retry could otherwise add the same consumable twice.
      await Purchases.purchasePackage(pkg);
      await Purchases.syncPurchases().catch(() => undefined);

      const deadline = Date.now() + 60000;
      let confirmedBalance: number | null = null;
      while (Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 3000));
        try {
          const status = await apiClient.get('/subscription/status');
          const latestBalance = Number(status.data?.extra_credits ?? balanceBefore);
          if (latestBalance > balanceBefore) {
            confirmedBalance = latestBalance;
            break;
          }
        } catch {
          // A short network interruption should not turn a completed Play
          // purchase into an error. Keep waiting for the secure confirmation.
        }
      }

      if (confirmedBalance !== null) {
        const creditsAdded = confirmedBalance - balanceBefore;
        Alert.alert(
          'Credits added',
          `${creditsAdded.toLocaleString()} extra credits were added.\n\nNew balance: ${confirmedBalance.toLocaleString()} credits`,
          [{ text: 'Great!' }]
        );
        onSuccess(creditsAdded);
        onClose();
      } else {
        Alert.alert(
          'Payment received',
          'Google Play accepted your payment. Zilo is confirming it securely and your credits will appear shortly. Please reopen Account in a minute before trying again.',
          [{ text: 'OK', onPress: onClose }]
        );
      }
    } catch (error: any) {
      if (!error.userCancelled) {
        const msg = error?.response?.data?.detail || error.message || 'Purchase failed. Please try again.';
        Alert.alert('Purchase Failed', msg);
      }
    } finally {
      setPurchasing(null);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={styles.overlay}>
        <View style={styles.modal}>
          {/* Header */}
          <View style={styles.header}>
            <View>
              <Text style={styles.title}>Buy Extra Credits</Text>
              <Text style={styles.subtitle}>Current balance: {currentCredits.toLocaleString()} credits</Text>
            </View>
            <TouchableOpacity onPress={onClose} disabled={!!purchasing}>
              <Ionicons name="close" size={28} color="#fff" />
            </TouchableOpacity>
          </View>

          {/* Info Banner */}
          <View style={styles.infoBanner}>
            <Ionicons name="information-circle-outline" size={18} color="#8A9BB5" />
            <Text style={styles.infoText}>
              Credits are used for AI features like smart replies, summaries, and automations.
            </Text>
          </View>

          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#25D366" />
            </View>
          ) : (
            <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
              <View style={styles.bundleList}>
                {bundles.map((bundle) => {
                  const isBuying = purchasing === bundle.bundle_id;
                  const isPopular = bundle.bundle_id === 'charo360_credits_2500';
                  return (
                    <TouchableOpacity
                      key={bundle.bundle_id}
                      style={[styles.bundleCard, isPopular && styles.bundleCardPopular]}
                      onPress={() => handleBuy(bundle)}
                      disabled={!!purchasing}
                    >
                      {isPopular && (
                        <View style={styles.popularBadge}>
                          <Text style={styles.popularText}>BEST VALUE</Text>
                        </View>
                      )}
                      <Text style={styles.bundleIcon}>{BUNDLE_ICONS[bundle.bundle_id] || '⭐'}</Text>
                      <View style={styles.bundleInfo}>
                        <Text style={styles.bundleLabel}>{bundle.label}</Text>
                        <Text style={styles.bundleSubtext}>One-time purchase · never expires</Text>
                      </View>
                      <View style={styles.bundleRight}>
                        {isBuying ? (
                          <ActivityIndicator size="small" color="#25D366" />
                        ) : (
                          <>
                            <Text style={styles.bundlePrice}>${bundle.price_usd}</Text>
                            <Text style={styles.bundlePerCredit}>
                              ${(bundle.price_usd / bundle.credits * 100).toFixed(2)}¢ each
                            </Text>
                          </>
                        )}
                      </View>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <Text style={styles.disclaimer}>
                • Purchases processed securely via Google Play{'\n'}
                • Credits never expire and carry over{'\n'}
                • Refunds subject to Google Play policy
              </Text>
            </ScrollView>
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
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    // Fixed height (not maxHeight): with only a maxHeight the flex:1 ScrollView
    // collapses to zero and the bundle list is unreachable.
    height: '80%',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#1E3452',
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#fff',
  },
  subtitle: {
    fontSize: 13,
    color: '#8A9BB5',
    marginTop: 2,
  },
  infoBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#111F35',
    marginHorizontal: 20,
    marginTop: 16,
    borderRadius: 10,
    padding: 12,
    gap: 8,
  },
  infoText: {
    flex: 1,
    fontSize: 13,
    color: '#8A9BB5',
    lineHeight: 18,
  },
  loadingContainer: {
    padding: 60,
    alignItems: 'center',
  },
  scroll: {
    flex: 1,
  },
  bundleList: {
    padding: 20,
    gap: 12,
  },
  bundleCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1.5,
    borderColor: '#243451',
    position: 'relative',
  },
  bundleCardPopular: {
    borderColor: '#25D366',
    backgroundColor: '#0F2318',
  },
  popularBadge: {
    position: 'absolute',
    top: -10,
    right: 16,
    backgroundColor: '#25D366',
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 10,
  },
  popularText: {
    fontSize: 9,
    fontWeight: 'bold',
    color: '#fff',
    letterSpacing: 0.5,
  },
  bundleIcon: {
    fontSize: 28,
    marginRight: 14,
  },
  bundleInfo: {
    flex: 1,
  },
  bundleLabel: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
  },
  bundleSubtext: {
    fontSize: 12,
    color: '#4A5A72',
    marginTop: 2,
  },
  bundleRight: {
    alignItems: 'flex-end',
    minWidth: 60,
  },
  bundlePrice: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#25D366',
  },
  bundlePerCredit: {
    fontSize: 11,
    color: '#4A5A72',
    marginTop: 2,
  },
  disclaimer: {
    fontSize: 11,
    color: '#4A5A72',
    textAlign: 'center',
    paddingHorizontal: 30,
    paddingBottom: 32,
    lineHeight: 18,
  },
});
