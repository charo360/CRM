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
import Purchases, { PurchasesPackage } from 'react-native-purchases';
import { apiClient } from '../context/api';

interface SubscriptionModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess: () => void;
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

export default function SubscriptionModal({ visible, onClose, onSuccess }: SubscriptionModalProps) {
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
    try {
      setPurchasing(true);
      
      // Check if running in Expo Go (RevenueCat not available)
      try {
        const offerings = await Purchases.getOfferings();
        if (!offerings.current) {
          throw new Error('No offerings available');
        }

        // Find the matching package
        const pkg = offerings.current.availablePackages.find(
          p => p.identifier.includes(plan.id)
        );

        if (!pkg) {
          throw new Error('Product not found');
        }

        const { customerInfo } = await Purchases.purchasePackage(pkg);
        
        if (customerInfo.entitlements.active['premium']) {
          Alert.alert('Success', 'Subscription activated!');
          onSuccess();
          onClose();
        }
      } catch (revenueCatError: any) {
        // If RevenueCat is not available (Expo Go), show helpful message
        if (revenueCatError.message?.includes('native store is not available')) {
          Alert.alert(
            'Development Mode',
            'In-app purchases require a real build. This is a preview of the subscription UI.\n\nTo test purchases:\n1. Build the app with EAS\n2. Install on a real device\n3. Set up RevenueCat with real API keys',
            [{ text: 'OK' }]
          );
        } else {
          throw revenueCatError;
        }
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
            <ScrollView 
              style={styles.scrollView}
              contentContainerStyle={styles.scrollContent}
              showsVerticalScrollIndicator={false}
            >
              <Text style={styles.subtitle}>
                Choose the plan that fits your business needs
              </Text>

              <View style={styles.packages}>
                {plans.map((plan, index) => (
                  <TouchableOpacity
                    key={plan.id}
                    style={[
                      styles.packageCard,
                      index === 1 && styles.popularCard
                    ]}
                    onPress={() => handlePurchase(plan)}
                    disabled={purchasing}
                  >
                    {index === 1 && (
                      <View style={styles.popularBadge}>
                        <Text style={styles.popularText}>MOST POPULAR</Text>
                      </View>
                    )}
                    
                    <Text style={styles.packageTitle}>{plan.name}</Text>
                    
                    <View style={styles.priceContainer}>
                      <Text style={styles.packagePrice}>
                        {plan.currency} {plan.amount.toLocaleString()}
                      </Text>
                      <Text style={styles.priceInterval}>/month</Text>
                    </View>

                    <View style={styles.featuresContainer}>
                      {plan.features.map((feature, idx) => (
                        <View key={idx} style={styles.feature}>
                          <Ionicons name="checkmark-circle" size={18} color="#2DB843" />
                          <Text style={styles.featureText}>{feature}</Text>
                        </View>
                      ))}
                    </View>

                    <View style={styles.selectButton}>
                      <Text style={styles.selectButtonText}>
                        {purchasing ? 'Processing...' : 'Select Plan'}
                      </Text>
                    </View>
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

              <Text style={styles.disclaimer}>
                • Prices shown in your local currency{'\n'}
                • Cancel anytime from Play Store{'\n'}
                • Free tier: 100 messages/month
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
  packagePrice: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#2DB843',
  },
  priceInterval: {
    fontSize: 14,
    color: '#8B9DC3',
    marginLeft: 4,
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
  selectButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#fff',
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
