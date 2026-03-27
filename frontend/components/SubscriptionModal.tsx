import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Purchases, { PurchasesPackage } from 'react-native-purchases';

interface SubscriptionModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function SubscriptionModal({ visible, onClose, onSuccess }: SubscriptionModalProps) {
  const [packages, setPackages] = useState<PurchasesPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState(false);

  useEffect(() => {
    if (visible) {
      loadOfferings();
    }
  }, [visible]);

  const loadOfferings = async () => {
    try {
      setLoading(true);
      const offerings = await Purchases.getOfferings();
      if (offerings.current && offerings.current.availablePackages.length > 0) {
        setPackages(offerings.current.availablePackages);
      }
    } catch (error) {
      console.error('Error loading offerings:', error);
      Alert.alert('Error', 'Failed to load subscription plans');
    } finally {
      setLoading(false);
    }
  };

  const handlePurchase = async (pkg: PurchasesPackage) => {
    try {
      setPurchasing(true);
      const { customerInfo } = await Purchases.purchasePackage(pkg);
      
      if (customerInfo.entitlements.active['premium']) {
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
    try {
      setPurchasing(true);
      const customerInfo = await Purchases.restorePurchases();
      
      if (customerInfo.entitlements.active['premium']) {
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
            <>
              <View style={styles.features}>
                <Text style={styles.featuresTitle}>Premium Features:</Text>
                <View style={styles.feature}>
                  <Ionicons name="checkmark-circle" size={20} color="#2DB843" />
                  <Text style={styles.featureText}>Unlimited customers</Text>
                </View>
                <View style={styles.feature}>
                  <Ionicons name="checkmark-circle" size={20} color="#2DB843" />
                  <Text style={styles.featureText}>AI auto-reply</Text>
                </View>
                <View style={styles.feature}>
                  <Ionicons name="checkmark-circle" size={20} color="#2DB843" />
                  <Text style={styles.featureText}>Advanced analytics</Text>
                </View>
                <View style={styles.feature}>
                  <Ionicons name="checkmark-circle" size={20} color="#2DB843" />
                  <Text style={styles.featureText}>Priority support</Text>
                </View>
              </View>

              <View style={styles.packages}>
                {packages.map((pkg) => (
                  <TouchableOpacity
                    key={pkg.identifier}
                    style={styles.packageCard}
                    onPress={() => handlePurchase(pkg)}
                    disabled={purchasing}
                  >
                    <Text style={styles.packageTitle}>
                      {pkg.product.title}
                    </Text>
                    <Text style={styles.packagePrice}>
                      {pkg.product.priceString}
                    </Text>
                    <Text style={styles.packageDescription}>
                      {pkg.product.description}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <TouchableOpacity
                style={styles.restoreButton}
                onPress={restorePurchases}
                disabled={purchasing}
              >
                <Text style={styles.restoreText}>Restore Purchases</Text>
              </TouchableOpacity>
            </>
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
    paddingBottom: 40,
    maxHeight: '90%',
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
  features: {
    padding: 20,
  },
  featuresTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 12,
  },
  feature: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  featureText: {
    fontSize: 15,
    color: '#B0C4DE',
    marginLeft: 10,
  },
  packages: {
    padding: 20,
    gap: 12,
  },
  packageCard: {
    backgroundColor: '#1E3A5F',
    padding: 20,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#2DB843',
  },
  packageTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 8,
  },
  packagePrice: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#2DB843',
    marginBottom: 8,
  },
  packageDescription: {
    fontSize: 14,
    color: '#B0C4DE',
  },
  restoreButton: {
    alignSelf: 'center',
    padding: 12,
  },
  restoreText: {
    fontSize: 14,
    color: '#2DB843',
    textDecorationLine: 'underline',
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
