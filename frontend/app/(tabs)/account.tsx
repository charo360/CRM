import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Switch,
  Modal,
  Platform,
  TextInput,
} from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../../context/AuthContext';
import { apiClient, settingsAPI, whatsappAPI } from '../../context/api';

import { NotificationHandler } from '../../utils/notification-handler';

interface SubscriptionPlan {
  id: string;
  name: string;
  amount: number;
  currency: string;
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

  // WhatsApp connection state
  const [waConnected, setWaConnected] = useState(false);
  const [waStatus, setWaStatus] = useState('not_connected');
  const [waNumber, setWaNumber] = useState('');
  const [waPhoneInput, setWaPhoneInput] = useState('');
  const [waPairingCode, setWaPairingCode] = useState('');
  const [waConnecting, setWaConnecting] = useState(false);
  const [waDisconnecting, setWaDisconnecting] = useState(false);
  const [waMsgSent, setWaMsgSent] = useState(0);
  const [waMsgLimit, setWaMsgLimit] = useState(50);

  // Daily Pulse state
  const [pulseEnabled, setPulseEnabled] = useState(false);
  const [pulseTime, setPulseTime] = useState('20:00');
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [pulsePreview, setPulsePreview] = useState<string | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const [sendingPulse, setSendingPulse] = useState(false);

  const { user, logout, refreshUser } = useAuth();
  const router = useRouter();

  useEffect(() => {
    fetchData();
  }, []);

  const [currency, setCurrency] = useState('USD');

  const fetchData = async () => {
    try {
      const [plansRes, statsRes, settingsRes] = await Promise.all([
        apiClient.get('/subscription/plans'),
        apiClient.get('/stats'),
        apiClient.get('/settings'),
      ]);
      setPlans(plansRes.data);
      setStats(statsRes.data);
      setPulseEnabled(settingsRes.data.daily_pulse_enabled || false);
      setPulseTime(settingsRes.data.daily_pulse_time || '20:00');
      if (settingsRes.data.currency) setCurrency(settingsRes.data.currency);

      // Fetch WhatsApp status
      try {
        const waRes = await whatsappAPI.getStatus();
        setWaConnected(waRes.connected);
        setWaStatus(waRes.status);
        setWaNumber(waRes.number || '');
        setWaMsgSent(waRes.messages_sent || 0);
        setWaMsgLimit(waRes.messages_limit || 50);
      } catch (e) {
        console.log('WhatsApp status not available');
      }
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleWhatsAppConnect = async () => {
    if (!waPhoneInput.trim()) {
      Alert.alert('Error', 'Please enter your WhatsApp phone number');
      return;
    }
    setWaConnecting(true);
    setWaPairingCode('');
    try {
      const res = await whatsappAPI.connect(waPhoneInput.trim());
      if (res.pairing_code) {
        setWaPairingCode(res.pairing_code);
      } else {
        Alert.alert('Error', res.message || 'Failed to get pairing code');
      }
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to connect WhatsApp');
    } finally {
      setWaConnecting(false);
    }
  };

  const handleWhatsAppDisconnect = async () => {
    Alert.alert(
      'Disconnect WhatsApp',
      'Are you sure? You will need to re-pair to send messages.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: async () => {
            setWaDisconnecting(true);
            try {
              await whatsappAPI.disconnect();
              setWaConnected(false);
              setWaStatus('not_connected');
              setWaNumber('');
              setWaPairingCode('');
              setWaPhoneInput('');
            } catch (error: any) {
              Alert.alert('Error', error.response?.data?.detail || 'Failed to disconnect');
            } finally {
              setWaDisconnecting(false);
            }
          },
        },
      ]
    );
  };

  const handleSubscribe = async (plan: SubscriptionPlan) => {
    if (!user) return;

    Alert.alert(
      'Subscribe',
      `Subscribe to ${plan.name} plan (${plan.currency || currency} ${plan.amount_display})?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Subscribe',
          onPress: async () => {
            setSubscribing(true);
            try {
              await apiClient.post('/subscription/verify-purchase', {
                plan_id: plan.id,
                purchase_token: `manual_${Date.now()}`,
                platform: Platform.OS,
              });
              Alert.alert('Success', 'Your subscription has been activated!');
              refreshUser();
            } catch (error: any) {
              Alert.alert('Error', error.response?.data?.detail || 'Failed to activate subscription');
            } finally {
              setSubscribing(false);
            }
          },
        },
      ]
    );
  };

  const handleTogglePulse = async (value: boolean) => {
    setPulseEnabled(value);
    try {
      await apiClient.put('/settings', { daily_pulse_enabled: value });
      if (value) {
        Alert.alert('Daily Pulse Enabled', `You'll receive your business summary every day at ${formatTime(pulseTime)} via WhatsApp.`);
      }
    } catch (error) {
      setPulseEnabled(!value);
      Alert.alert('Error', 'Failed to update setting');
    }
  };

  const handlePulseTimeChange = async (event: any, selectedDate?: Date) => {
    setShowTimePicker(false);
    if (event.type === 'set' && selectedDate) {
      const hours = selectedDate.getHours().toString().padStart(2, '0');
      const minutes = selectedDate.getMinutes().toString().padStart(2, '0');
      const newTime = `${hours}:${minutes}`;
      setPulseTime(newTime);
      try {
        await apiClient.put('/settings', { daily_pulse_time: newTime });
      } catch (error) {
        Alert.alert('Error', 'Failed to update time');
      }
    }
  };

  const formatTime = (time: string) => {
    const [h, m] = time.split(':');
    const hour = parseInt(h);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const hour12 = hour % 12 || 12;
    return `${hour12}:${m} ${ampm}`;
  };

  const handlePreviewPulse = async () => {
    setLoadingPreview(true);
    setPreviewVisible(true);
    try {
      const res = await apiClient.get('/daily-pulse/preview');
      setPulsePreview(res.data.message);
    } catch (error) {
      setPulsePreview('Failed to load preview. Please try again.');
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleSendPulseNow = async () => {
    setSendingPulse(true);
    try {
      await apiClient.post('/daily-pulse/send');
      Alert.alert('Sent!', 'Daily pulse sent to your WhatsApp!');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to send pulse');
    } finally {
      setSendingPulse(false);
    }
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

        {/* WhatsApp Business */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>WhatsApp Business</Text>
          <View style={styles.settingsCard}>
            {waConnected ? (
              <View>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: '#25D366', marginRight: 10 }} />
                  <Text style={{ color: '#25D366', fontSize: 16, fontWeight: '600', flex: 1 }}>Connected</Text>
                  <TouchableOpacity onPress={handleWhatsAppDisconnect} disabled={waDisconnecting}>
                    <Text style={{ color: '#FF4444', fontSize: 14 }}>{waDisconnecting ? 'Disconnecting...' : 'Disconnect'}</Text>
                  </TouchableOpacity>
                </View>
                <Text style={{ color: '#8B9DC3', fontSize: 14 }}>Number: {waNumber}</Text>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                  <Text style={{ color: '#8B9DC3', fontSize: 13 }}>Messages this month</Text>
                  <Text style={{ color: '#FFFFFF', fontSize: 13, fontWeight: '600' }}>{waMsgSent} / {waMsgLimit}</Text>
                </View>
                <View style={{ height: 4, backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 2, marginTop: 6 }}>
                  <View style={{ height: 4, backgroundColor: waMsgSent / waMsgLimit > 0.9 ? '#FF4444' : '#25D366', borderRadius: 2, width: `${Math.min((waMsgSent / waMsgLimit) * 100, 100)}%` }} />
                </View>
              </View>
            ) : waPairingCode ? (
              <View>
                <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginBottom: 8 }}>Enter this code in WhatsApp</Text>
                <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 16 }}>
                  Open WhatsApp {'>'} Settings {'>'} Linked Devices {'>'} Link a Device {'>'} Link with phone number
                </Text>
                <View style={{ backgroundColor: 'rgba(37,211,102,0.1)', borderRadius: 12, padding: 20, alignItems: 'center', marginBottom: 16 }}>
                  <Text style={{ color: '#25D366', fontSize: 32, fontWeight: '700', letterSpacing: 8 }}>{waPairingCode}</Text>
                </View>
                <Text style={{ color: '#8B9DC3', fontSize: 12, textAlign: 'center' }}>Code expires in 60 seconds. Waiting for connection...</Text>
                <ActivityIndicator size="small" color="#25D366" style={{ marginTop: 12 }} />
                <TouchableOpacity
                  style={{ marginTop: 16, alignItems: 'center' }}
                  onPress={() => { setWaPairingCode(''); setWaPhoneInput(''); }}
                >
                  <Text style={{ color: '#8B9DC3', fontSize: 14 }}>Cancel</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
                  <Ionicons name="logo-whatsapp" size={24} color="#25D366" />
                  <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginLeft: 10 }}>Connect WhatsApp</Text>
                </View>
                <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 16 }}>
                  Link your WhatsApp number to send messages directly from the app.
                </Text>
                <TextInput
                  style={{
                    backgroundColor: 'rgba(255,255,255,0.08)',
                    borderRadius: 10,
                    paddingHorizontal: 16,
                    paddingVertical: 12,
                    fontSize: 16,
                    color: '#FFFFFF',
                    marginBottom: 12,
                  }}
                  placeholder="+1234567890"
                  placeholderTextColor="#666"
                  value={waPhoneInput}
                  onChangeText={setWaPhoneInput}
                  keyboardType="phone-pad"
                />
                <TouchableOpacity
                  style={{
                    backgroundColor: '#25D366',
                    borderRadius: 10,
                    paddingVertical: 14,
                    alignItems: 'center',
                    opacity: waConnecting ? 0.7 : 1,
                  }}
                  onPress={handleWhatsAppConnect}
                  disabled={waConnecting}
                >
                  {waConnecting ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600' }}>Get Pairing Code</Text>
                  )}
                </TouchableOpacity>
              </View>
            )}
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
                  <Text style={styles.statValue}>{currency} {stats.revenue_this_month.toLocaleString()}</Text>
                  <Text style={styles.statLabel}>Revenue</Text>
                </View>
              </View>
            </View>
          )
        }

        {/* Smart Sourcing Agent - Prominent Access */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Smart Sourcing</Text>
          <TouchableOpacity
            style={styles.businessCard} // Reusing business card style for consistency
            onPress={() => router.push('/(tabs)/customers?mode=suppliers')}
          >
            <View style={[styles.businessAvatar, { backgroundColor: '#4A90D9' }]}>
              <Ionicons name="cube" size={24} color="#FFFFFF" />
            </View>
            <View style={styles.businessInfo}>
              <Text style={styles.businessName}>Sourcing Agent</Text>
              <Text style={styles.businessPhone}>Manage suppliers & inventory alerts</Text>
            </View>
            <Ionicons name="chevron-forward" size={24} color="#666" />
          </TouchableOpacity>
        </View>

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
                <Text style={styles.planPrice}>{plan.currency || currency} {plan.amount_display}</Text>
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
                onValueChange={() => { }}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </TouchableOpacity>
            <TouchableOpacity style={styles.settingItem}>
              <Ionicons name="notifications-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Notifications</Text>
              <Switch
                value={true}
                onValueChange={() => { }}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </TouchableOpacity>
            <View style={styles.settingItem}>
              <Ionicons name="pulse" size={24} color="#25D366" />
              <Text style={styles.settingText}>Daily Pulse</Text>
              <Switch
                value={pulseEnabled}
                onValueChange={handleTogglePulse}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </View>
          </View>
        </View>

        {/* Daily Pulse */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Daily Pulse</Text>
          <View style={styles.settingsCard}>
            <View style={styles.pulseHeader}>
              <View style={styles.pulseIconContainer}>
                <Ionicons name="pulse" size={24} color="#25D366" />
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: '#FFFFFF' }}>Business Summary</Text>
                <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                  Get your daily sales, profit & insights via WhatsApp
                </Text>
              </View>
              <Switch
                value={pulseEnabled}
                onValueChange={handleTogglePulse}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </View>

            {pulseEnabled && (
              <>
                <View style={styles.pulseDivider} />
                <TouchableOpacity
                  style={styles.pulseTimeRow}
                  onPress={() => setShowTimePicker(true)}
                >
                  <Ionicons name="time-outline" size={20} color="#8B9DC3" />
                  <Text style={{ flex: 1, fontSize: 14, color: '#FFFFFF', marginLeft: 12 }}>
                    Send at
                  </Text>
                  <View style={styles.pulseTimeBadge}>
                    <Text style={styles.pulseTimeText}>{formatTime(pulseTime)}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color="#666" style={{ marginLeft: 8 }} />
                </TouchableOpacity>

                <View style={styles.pulseDivider} />
                <View style={styles.pulseActions}>
                  <TouchableOpacity
                    style={styles.pulsePreviewButton}
                    onPress={handlePreviewPulse}
                  >
                    <Ionicons name="eye-outline" size={18} color="#4A90D9" />
                    <Text style={{ color: '#4A90D9', fontSize: 14, fontWeight: '600', marginLeft: 6 }}>Preview</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.pulseSendButton}
                    onPress={handleSendPulseNow}
                    disabled={sendingPulse}
                  >
                    <Ionicons name="send" size={16} color="#FFFFFF" />
                    <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600', marginLeft: 6 }}>
                      {sendingPulse ? 'Sending...' : 'Test Now'}
                    </Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>
        </View>

        {showTimePicker && (
          <DateTimePicker
            value={(() => {
              const [h, m] = pulseTime.split(':');
              const d = new Date();
              d.setHours(parseInt(h), parseInt(m), 0, 0);
              return d;
            })()}
            mode="time"
            display="default"
            onChange={handlePulseTimeChange}
          />
        )}

        {/* Logout */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={24} color="#FF4444" />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>

        <Text style={styles.version}>Version 1.0.0</Text>
      </ScrollView>

      {/* Daily Pulse Preview Modal */}
      <Modal
        visible={previewVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setPreviewVisible(false)}
      >
        <SafeAreaView style={styles.container}>
          <View style={styles.pulseModalHeader}>
            <TouchableOpacity onPress={() => setPreviewVisible(false)}>
              <Ionicons name="close" size={24} color="#FFFFFF" />
            </TouchableOpacity>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#FFFFFF' }}>Daily Pulse Preview</Text>
            <View style={{ width: 24 }} />
          </View>
          <ScrollView style={{ flex: 1, padding: 20 }}>
            {loadingPreview ? (
              <View style={{ alignItems: 'center', paddingTop: 40 }}>
                <ActivityIndicator size="large" color="#25D366" />
                <Text style={{ color: '#8B9DC3', marginTop: 12 }}>Generating your pulse...</Text>
              </View>
            ) : (
              <>
                <View style={styles.pulsePreviewCard}>
                  <View style={styles.pulsePreviewWhatsApp}>
                    <Ionicons name="logo-whatsapp" size={16} color="#25D366" />
                    <Text style={{ color: '#25D366', fontSize: 12, marginLeft: 6 }}>WhatsApp Message Preview</Text>
                  </View>
                  <Text style={styles.pulsePreviewText}>{pulsePreview}</Text>
                </View>
                <Text style={{ color: '#8B9DC3', fontSize: 12, textAlign: 'center', marginTop: 16 }}>
                  This is what you'll receive every day at {formatTime(pulseTime)}
                </Text>
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

    </SafeAreaView >
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
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  section: {
    paddingHorizontal: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  businessCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 12,
  },
  businessAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
  },
  businessAvatarText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  businessInfo: {
    flex: 1,
    marginLeft: 12,
  },
  businessName: {
    fontSize: 16,
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
    gap: 8,
  },
  statCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 10,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 6,
  },
  statLabel: {
    fontSize: 11,
    color: '#666',
    marginTop: 2,
  },
  planCard: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
  },
  planCardActive: {
    borderWidth: 2,
    borderColor: '#25D366',
  },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  planName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  planPrice: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#25D366',
  },
  planFeatures: {
    marginBottom: 10,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  featureText: {
    fontSize: 12,
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
    borderRadius: 12,
    overflow: 'hidden',
  },
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#0A1628',
  },
  settingText: {
    flex: 1,
    fontSize: 14,
    color: '#FFFFFF',
    marginLeft: 10,
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 16,
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 12,
    marginTop: 8,
  },
  logoutText: {
    fontSize: 14,
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
  // Daily Pulse styles
  pulseHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
  },
  pulseIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#1A3A2A',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pulseDivider: {
    height: 1,
    backgroundColor: '#0A1628',
    marginHorizontal: 16,
  },
  pulseTimeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
  },
  pulseTimeBadge: {
    backgroundColor: '#0A1628',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  pulseTimeText: {
    color: '#25D366',
    fontSize: 14,
    fontWeight: '600',
  },
  pulseActions: {
    flexDirection: 'row',
    padding: 16,
    gap: 12,
  },
  pulsePreviewButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#4A90D9',
  },
  pulseSendButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: '#25D366',
  },
  pulseModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  pulsePreviewCard: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 20,
    borderLeftWidth: 4,
    borderLeftColor: '#25D366',
  },
  pulsePreviewWhatsApp: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#0A1628',
  },
  pulsePreviewText: {
    color: '#FFFFFF',
    fontSize: 14,
    lineHeight: 22,
  },
});
