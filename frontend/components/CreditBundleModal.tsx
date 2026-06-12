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
import { Platform } from 'react-native';
import { apiClient } from '../context/api';

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
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState<string | null>(null); // bundle_id being purchased

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
    if (isExpoGo) {
      Alert.alert(
        'Not Available Yet',
        'Purchasing credits requires the full Play Store version of the app.',
        [{ text: 'OK' }]
      );
      return;
    }

    try {
      setPurchasing(bundle.bundle_id);
      const Purchases = require('react-native-purchases').default;

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
          'Coming Soon',
          `The "${bundle.label}" bundle is being set up in the Play Store and will be available very soon!`,
          [{ text: 'OK' }]
        );
        return;
      }

      // Purchase the consumable package
      const { customerInfo, transaction } = await Purchases.purchasePackage(pkg);
      const purchaseToken =
        transaction?.transactionIdentifier ||
        transaction?.revenueCatId ||
        transaction?.purchaseToken ||
        '';

      // Sync purchase to backend to add credits
      const platform = Platform.OS === 'ios' ? 'ios' : 'android';
      const res = await apiClient.post('/subscription/add-credits', {
        bundle_id: bundle.bundle_id,
        purchase_token: purchaseToken,
        platform,
      });

      Alert.alert(
        '✅ Credits Added!',
        `${bundle.label} have been added to your account.\n\nNew balance: ${res.data.total_extra_credits} credits`,
        [{ text: 'Great!' }]
      );
      onSuccess(bundle.credits);
      onClose();
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
                  const isPopular = bundle.bundle_id === 'credits_2500';
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
