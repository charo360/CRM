import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Switch,
  TextInput,
  Modal,
  Image,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import DateTimePicker from '@react-native-community/datetimepicker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../../context/AuthContext';
import { apiClient, settingsAPI, whatsappAPI } from '../../context/api';
import { NotificationHandler } from '../../utils/notification-handler';
import CreditBundleModal from '../../components/CreditBundleModal';
import SubscriptionModal from '../../components/SubscriptionModal';
import TeamManagementModal from '../../components/TeamManagementModal';
import PaymentSetupModal from '../../components/PaymentSetupModal';
import ProductCatalogModal from '../../components/ProductCatalogModal';
import BusinessTypePicker from '../../components/BusinessTypePicker';
import { useBusiness, BUSINESS_TYPE_OPTIONS } from '../../context/BusinessContext';
import { accountAPI } from '../../context/api';
import BusinessKnowledgeModal from '../../components/BusinessKnowledgeModal';

interface SubscriptionPlan {
  id: string;
  name: string;
  amount: number;
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

interface SubscriptionStatus {
  subscription_plan?: string | null;
  subscription_active?: boolean;
  paid_active?: boolean;
  subscription_is_trial?: boolean;
  subscription_date?: string | null;
  subscription_current_period_end?: string | null;
}

export default function AccountScreen() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(false);
  const [showCreditModal, setShowCreditModal] = useState(false);
  const [showSubModal, setShowSubModal] = useState(false);
  const [subscriptionEntryPoint, setSubscriptionEntryPoint] = useState<'upgrade' | 'whatsapp_trial'>('upgrade');
  // This is deliberately separate from user.subscription_active. The latter
  // may be stale after an expired trial; WhatsApp needs a Google Play payment
  // method that has been confirmed by the server.
  const [paidSubscriptionActive, setPaidSubscriptionActive] = useState(false);
  const [checkingWhatsAppAccess, setCheckingWhatsAppAccess] = useState(false);
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [showPaymentSetup, setShowPaymentSetup] = useState(false);
  const [showProductCatalog, setShowProductCatalog] = useState(false);
  const [showBusinessKnowledge, setShowBusinessKnowledge] = useState(false);
  const [showBusinessType, setShowBusinessType] = useState(false);
  const [extraCredits, setExtraCredits] = useState(0);
  const [subscriptionStatus, setSubscriptionStatus] = useState<SubscriptionStatus | null>(null);

  // WhatsApp connection state
  const [waConnected, setWaConnected] = useState(false);
  const [waStatus, setWaStatus] = useState('not_connected');
  const [waNumber, setWaNumber] = useState('');
  const [waPhoneInput, setWaPhoneInput] = useState('');
  const [waPairingCode, setWaPairingCode] = useState('');
  const [waQrBase64, setWaQrBase64] = useState('');
  const [waConnecting, setWaConnecting] = useState(false);
  const [waDisconnecting, setWaDisconnecting] = useState(false);
  const [waMsgSent, setWaMsgSent] = useState(0);
  const [waMsgLimit, setWaMsgLimit] = useState(50);
  const [waCountdown, setWaCountdown] = useState(0);
  const [waCopied, setWaCopied] = useState(false);
  const waCountdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const waPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const waRefreshRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Daily Pulse state
  const [pulseEnabled, setPulseEnabled] = useState(false);
  const [pulseTime, setPulseTime] = useState('20:00');
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [pulsePreview, setPulsePreview] = useState<string | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [sendingPulse, setSendingPulse] = useState(false);

  // Auto Reply / Notifications state
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [autoReplyAudience, setAutoReplyAudience] = useState<'everyone' | 'customers_only' | 'new_contacts_only'>('everyone');
  const [showAudiencePicker, setShowAudiencePicker] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);

  const { user, logout, refreshUser } = useAuth();
  const { businessType, refresh: refreshBusiness } = useBusiness();
  const router = useRouter();

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [plansRes, statsRes, statusRes] = await Promise.all([
        apiClient.get('/subscription/plans'),
        apiClient.get('/stats'),
        apiClient.get('/subscription/status'),
      ]);
      setPlans(plansRes.data);
      setStats(statsRes.data);
      setExtraCredits(statusRes.data.extra_credits || 0);
      setPaidSubscriptionActive(Boolean(statusRes.data.paid_active));
      setSubscriptionStatus(statusRes.data);

      // Load user settings (daily pulse, auto reply, notifications)
      try {
        const settings = await settingsAPI.getSettings();
        setPulseEnabled(settings.daily_pulse_enabled || false);
        setPulseTime(settings.daily_pulse_time || '20:00');
        setAutoReplyEnabled(settings.auto_reply_enabled || false);
        setAutoReplyAudience(settings.auto_reply_audience || 'everyone');
        setNotificationsEnabled(settings.notification_enabled !== false);
      } catch (e) {
        console.log('Settings not available');
      }

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

  const handleSubscribe = async (plan: SubscriptionPlan) => {
    setShowSubModal(true);
  };

  const clearWaTimers = useCallback(() => {
    if (waCountdownRef.current) { clearInterval(waCountdownRef.current); waCountdownRef.current = null; }
    if (waPollingRef.current) { clearInterval(waPollingRef.current); waPollingRef.current = null; }
    if (waRefreshRef.current) { clearTimeout(waRefreshRef.current); waRefreshRef.current = null; }
  }, []);

  useEffect(() => {
    return () => clearWaTimers();
  }, [clearWaTimers]);

  const startPairingTimers = useCallback((code: string, phone: string) => {
    clearWaTimers();
    setWaPairingCode(code);
    setWaCountdown(60);
    setWaCopied(false);

    // Copy to clipboard immediately
    Clipboard.setStringAsync(code).then(() => {
      setWaCopied(true);
      setTimeout(() => setWaCopied(false), 2000);
    });

    // Countdown timer
    waCountdownRef.current = setInterval(() => {
      setWaCountdown(prev => {
        if (prev <= 1) {
          if (waCountdownRef.current) clearInterval(waCountdownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    // Auto-refresh code at 50s (before 60s expiry). This endpoint intentionally
    // keeps the existing WhatsApp session instead of recreating it.
    waRefreshRef.current = setTimeout(async () => {
      try {
        const res = await whatsappAPI.refreshPairingCode(phone);
        if (res.pairing_code) {
          startPairingTimers(res.pairing_code, phone);
        }
      } catch (e) {
        console.log('Auto-refresh pairing code failed');
      }
    }, 50000);

    // Poll for connection every 5s
    waPollingRef.current = setInterval(async () => {
      try {
        const waRes = await whatsappAPI.getStatus();
        if (waRes.connected) {
          clearWaTimers();
          setWaConnected(true);
          setWaStatus(waRes.status);
          setWaNumber(waRes.number || '');
          setWaPairingCode('');
          setWaMsgSent(waRes.messages_sent || 0);
          setWaMsgLimit(waRes.messages_limit || 50);
          Alert.alert('Connected!', 'WhatsApp linked successfully.');
        }
      } catch (e) { /* ignore */ }
    }, 5000);
  }, [clearWaTimers]);

  const startQrTimers = useCallback((qrBase64: string) => {
    clearWaTimers();
    setWaPairingCode('');
    setWaQrBase64(qrBase64);

    // WhatsApp rotates QR codes. Refresh the image without recreating the
    // WAHA session, while polling connection state as with phone pairing.
    waRefreshRef.current = setTimeout(async () => {
      try {
        const res = await whatsappAPI.getQr();
        if (res.qr_base64) startQrTimers(res.qr_base64);
      } catch (e) {
        console.log('QR refresh failed');
      }
    }, 20000);

    waPollingRef.current = setInterval(async () => {
      try {
        const waRes = await whatsappAPI.getStatus();
        if (waRes.connected) {
          clearWaTimers();
          setWaConnected(true);
          setWaStatus(waRes.status);
          setWaNumber(waRes.number || '');
          setWaQrBase64('');
          setWaMsgSent(waRes.messages_sent || 0);
          setWaMsgLimit(waRes.messages_limit || 50);
          Alert.alert('Connected!', 'WhatsApp linked successfully.');
        }
      } catch (e) { /* ignore a transient status poll failure */ }
    }, 5000);
  }, [clearWaTimers]);

  const handleCopyCode = async () => {
    if (!waPairingCode) return;
    await Clipboard.setStringAsync(waPairingCode);
    setWaCopied(true);
    setTimeout(() => setWaCopied(false), 2000);
  };

  const handleShowWhatsAppGuide = () => {
    Alert.alert(
      'How to link WhatsApp',
      '1. Open WhatsApp yourself.\n\n2. Tap Settings (or the three-dot menu) > Linked devices.\n\n3. Tap Link a device, then Link with phone number instead.\n\n4. Enter the code shown in Zilo.\n\nThe code is already copied for you.'
    );
  };

  const showWhatsAppTrial = () => {
    setSubscriptionEntryPoint('whatsapp_trial');
    setShowSubModal(true);
  };

  const beginWhatsAppPairing = async () => {
    setWaConnecting(true);
    setWaPairingCode('');
    setWaQrBase64('');
    try {
      const res = await whatsappAPI.connect(waPhoneInput.trim());
      if (res.pairing_code) {
        startPairingTimers(res.pairing_code, waPhoneInput.trim());
      } else if (res.qr_base64) {
        startQrTimers(res.qr_base64);
      } else {
        Alert.alert('Error', res.message || 'Failed to get a WhatsApp link code');
      }
    } catch (error: any) {
      // A server-side entitlement check is the final authority. If the local
      // state has gone stale, send the customer into the Google Play trial
      // flow instead of leaving them at an error alert.
      if (error.response?.status === 402) {
        setPaidSubscriptionActive(false);
        showWhatsAppTrial();
        return;
      }
      Alert.alert('Error', error.response?.data?.detail || 'Failed to connect WhatsApp');
    } finally {
      setWaConnecting(false);
    }
  };

  const handleWhatsAppConnect = async () => {
    if (!waPhoneInput.trim()) {
      Alert.alert('Error', 'Please enter your WhatsApp phone number');
      return;
    }
    setCheckingWhatsAppAccess(true);
    try {
      // Read the live entitlement before creating a WAHA pairing session.
      // This avoids treating an old account flag as a completed Play payment.
      const statusResponse = await apiClient.get('/subscription/status');
      const hasConfirmedPaymentMethod = Boolean(statusResponse.data?.paid_active);
      setPaidSubscriptionActive(hasConfirmedPaymentMethod);

      if (!hasConfirmedPaymentMethod) {
        showWhatsAppTrial();
        return;
      }

      await beginWhatsAppPairing();
    } catch (error: any) {
      // If the status check itself is temporarily unavailable, the pairing
      // endpoint will still enforce the same entitlement safely.
      await beginWhatsAppPairing();
    } finally {
      setCheckingWhatsAppAccess(false);
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
            clearWaTimers();
            try {
              await whatsappAPI.disconnect();
              setWaConnected(false);
              setWaStatus('not_connected');
              setWaNumber('');
              setWaPairingCode('');
              setWaQrBase64('');
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

  const formatTime = (time: string) => {
    const [h, m] = time.split(':');
    const hour = parseInt(h);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const hour12 = hour % 12 || 12;
    return `${hour12}:${m} ${ampm}`;
  };

  const handleTogglePulse = async (value: boolean) => {
    setPulseEnabled(value);
    try {
      await settingsAPI.updateSettings({ daily_pulse_enabled: value });
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
        await settingsAPI.updateSettings({ daily_pulse_time: newTime });
      } catch (error) {
        Alert.alert('Error', 'Failed to update time');
      }
    }
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

  const handleToggleAutoReply = async (value: boolean) => {
    setAutoReplyEnabled(value);
    try {
      await settingsAPI.updateSettings({ auto_reply_enabled: value });
    } catch (error) {
      setAutoReplyEnabled(!value);
      Alert.alert('Error', 'Failed to update setting');
    }
  };

  const handleSelectAudience = async (audience: 'everyone' | 'customers_only' | 'new_contacts_only') => {
    const previous = autoReplyAudience;
    setAutoReplyAudience(audience);
    setShowAudiencePicker(false);
    try {
      await settingsAPI.updateSettings({ auto_reply_audience: audience });
    } catch (error) {
      setAutoReplyAudience(previous);
      Alert.alert('Error', 'Failed to update setting');
    }
  };

  const handleToggleNotifications = async (value: boolean) => {
    setNotificationsEnabled(value);
    try {
      await settingsAPI.updateSettings({ notification_enabled: value });
    } catch (error) {
      setNotificationsEnabled(!value);
      Alert.alert('Error', 'Failed to update setting');
    }
  };

  const handleDeleteAccount = () => {
    // Irreversible and takes the business with it, so ask twice: once for
    // intent, once with the consequences spelled out.
    Alert.alert(
      'Delete account',
      'This permanently deletes your business, customers, products and orders. It cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Continue',
          style: 'destructive',
          onPress: () => Alert.alert(
            'Delete everything?',
            `${user?.business_name || 'This business'} and all its data will be erased. Your shop link will stop working.`,
            [
              { text: 'Keep my account', style: 'cancel' },
              {
                text: 'Delete forever',
                style: 'destructive',
                onPress: async () => {
                  try {
                    await accountAPI.deleteAccount();
                    await logout();
                  } catch {
                    Alert.alert('Could not delete', 'Please check your connection and try again.');
                  }
                },
              },
            ],
          ),
        },
      ],
    );
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
            router.replace('/(auth)/login');
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

  const isSubscriptionActive = Boolean(
    subscriptionStatus?.paid_active ?? user?.subscription_active
  );
  const activePlanId = String(
    subscriptionStatus?.subscription_plan || user?.subscription_plan || ''
  ).toLowerCase();
  const activePlanName = ({
    starter: 'Starter',
    standard: 'Growth',
    growth: 'Growth',
    pro: 'Pro',
  } as Record<string, string>)[activePlanId] || 'Zilo';
  const subscriptionStartedAt = subscriptionStatus?.subscription_date
    ? new Date(subscriptionStatus.subscription_date)
    : null;
  const hasSubscriptionStart = Boolean(
    subscriptionStartedAt && !Number.isNaN(subscriptionStartedAt.getTime())
  );
  // Older verified purchases did not retain the period type. A live purchase
  // with no end date is the legacy free-trial record, so label it clearly too.
  const isGooglePlayTrial = Boolean(subscriptionStatus?.subscription_is_trial)
    || (isSubscriptionActive && !subscriptionStatus?.subscription_current_period_end && hasSubscriptionStart);
  const renewalDate = subscriptionStatus?.subscription_current_period_end
    ? new Date(subscriptionStatus.subscription_current_period_end)
    : isGooglePlayTrial && subscriptionStartedAt
      ? new Date(subscriptionStartedAt.getTime() + (14 * 24 * 60 * 60 * 1000))
      : null;
  const renewalLabel = renewalDate && !Number.isNaN(renewalDate.getTime())
    ? isGooglePlayTrial
      ? `Trial ends ${renewalDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
      : `Renews ${renewalDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
    : 'Google Play payment verified';
  const subscriptionBadgeLabel = !isSubscriptionActive
    ? 'Start 14-day trial'
    : isGooglePlayTrial
      ? '14-day trial active'
      : `${activePlanName} active`;
  const subscriptionDetail = !isSubscriptionActive
    ? 'Add a payment method in Google Play to start your free trial.'
    : isGooglePlayTrial
      ? `${renewalLabel} • Then ${activePlanName} continues unless you cancel in Google Play.`
      : renewalLabel;

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
              <Text style={styles.subscriptionDetail} numberOfLines={2}>{subscriptionDetail}</Text>
              {user?.owner_name && (
                <Text style={styles.ownerName}>{user.owner_name}</Text>
              )}
            </View>
            <View style={[
              styles.subscriptionBadge,
              isSubscriptionActive && styles.subscriptionActive,
            ]}>
              <Text style={styles.subscriptionText}>
                {subscriptionBadgeLabel}
              </Text>
            </View>
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
                  <Text style={styles.statValue}>KES {stats.revenue_this_month.toLocaleString()}</Text>
                  <Text style={styles.statLabel}>Revenue</Text>
                </View>
              </View>
            </View>
          )
        }

        {/* WhatsApp Business */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>WhatsApp Business</Text>
          <View style={styles.settingsCard}>
            {waConnected ? (
              <View style={styles.whatsappConnectedContent}>
                <View style={styles.whatsappConnectedHeader}>
                  <View style={styles.whatsappStatus}>
                    <View style={styles.whatsappStatusDot} />
                    <Text style={styles.whatsappStatusText}>Connected</Text>
                  </View>
                  <TouchableOpacity
                    onPress={handleWhatsAppDisconnect}
                    disabled={waDisconnecting}
                    style={[styles.disconnectButton, waDisconnecting && styles.disconnectButtonDisabled]}
                  >
                    <Text style={styles.disconnectButtonText} numberOfLines={1}>
                      {waDisconnecting ? 'Disconnecting...' : 'Disconnect'}
                    </Text>
                  </TouchableOpacity>
                </View>
                <Text style={{ color: '#8A9BB5', fontSize: 14 }}>Number: {waNumber}</Text>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                  <Text style={{ color: '#8A9BB5', fontSize: 13 }}>Messages this month</Text>
                  <Text style={{ color: '#FFFFFF', fontSize: 13, fontWeight: '600' }}>{waMsgSent} / {waMsgLimit}</Text>
                </View>
                <View style={{ height: 4, backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 2, marginTop: 6 }}>
                  <View style={{ height: 4, backgroundColor: waMsgSent / waMsgLimit > 0.9 ? '#FF4444' : '#25D366', borderRadius: 2, width: `${Math.min((waMsgSent / waMsgLimit) * 100, 100)}%` }} />
                </View>
              </View>
            ) : (waPairingCode || waQrBase64) ? (
              <View>
                {waPairingCode ? (
                  <>
                    <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginBottom: 8 }}>Enter this code in WhatsApp</Text>
                    <Text style={{ color: '#8A9BB5', fontSize: 13, marginBottom: 12 }}>
                      Open WhatsApp {'>'} Settings {'>'} Linked Devices {'>'} Link a Device {'>'} Link with phone number
                    </Text>
                    <TouchableOpacity
                      onPress={handleCopyCode}
                      activeOpacity={0.7}
                      style={{ backgroundColor: 'rgba(37,211,102,0.1)', borderRadius: 12, padding: 20, alignItems: 'center', marginBottom: 12 }}
                    >
                      <Text style={{ color: '#25D366', fontSize: 32, fontWeight: '700', letterSpacing: 8 }}>{waPairingCode}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 10 }}>
                        <Ionicons name={waCopied ? 'checkmark-circle' : 'copy-outline'} size={16} color={waCopied ? '#25D366' : '#8A9BB5'} />
                        <Text style={{ color: waCopied ? '#25D366' : '#8A9BB5', fontSize: 12, marginLeft: 6 }}>
                          {waCopied ? 'Copied to clipboard!' : 'Tap to copy code'}
                        </Text>
                      </View>
                    </TouchableOpacity>
                  </>
                ) : (
                  <>
                    <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginBottom: 8 }}>Scan this QR code in WhatsApp</Text>
                    <Text style={{ color: '#8A9BB5', fontSize: 13, marginBottom: 12 }}>
                      WhatsApp {'>'} Settings {'>'} Linked Devices {'>'} Link a Device
                    </Text>
                    <View style={{ backgroundColor: '#FFFFFF', borderRadius: 12, padding: 12, alignItems: 'center', marginBottom: 12 }}>
                      <Image source={{ uri: waQrBase64 }} style={{ width: 220, height: 220 }} resizeMode="contain" />
                    </View>
                  </>
                )}
                <TouchableOpacity
                  style={{ backgroundColor: '#25D366', borderRadius: 10, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}
                  onPress={handleShowWhatsAppGuide}
                >
                  <Ionicons name="help-circle-outline" size={18} color="#FFFFFF" />
                  <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600', marginLeft: 8 }}>Show linking steps</Text>
                </TouchableOpacity>
                {waPairingCode && <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginBottom: 12 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: waCountdown > 10 ? '#25D366' : '#FF4444', marginRight: 8 }} />
                  <Text style={{ color: waCountdown > 10 ? '#8A9BB5' : '#FF4444', fontSize: 12 }}>
                    {waCountdown > 0 ? `Code refreshes in ${waCountdown}s` : 'Refreshing code...'}
                  </Text>
                </View>}
                <ActivityIndicator size="small" color="#25D366" />
                <Text style={{ color: '#8A9BB5', fontSize: 11, textAlign: 'center', marginTop: 6 }}>Waiting for connection...</Text>
                <TouchableOpacity
                  style={{ marginTop: 14, alignItems: 'center' }}
                  onPress={() => { clearWaTimers(); setWaPairingCode(''); setWaQrBase64(''); setWaPhoneInput(''); }}
                >
                  <Text style={{ color: '#8A9BB5', fontSize: 14 }}>Cancel</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
                  <Ionicons name="logo-whatsapp" size={24} color="#25D366" />
                  <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginLeft: 10 }}>Connect WhatsApp</Text>
                </View>
                <Text style={{ color: '#8A9BB5', fontSize: 13, marginBottom: 16 }}>
                  Start a Google Play free trial before linking your number. A payment method is required, but you will not be charged today.
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
                  disabled={waConnecting || checkingWhatsAppAccess}
                >
                  {waConnecting || checkingWhatsAppAccess ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600' }}>
                      {checkingWhatsAppAccess
                        ? 'Checking payment method...'
                        : paidSubscriptionActive
                          ? 'Get Pairing Code'
                          : 'Verify payment method to connect'}
                    </Text>
                  )}
                </TouchableOpacity>
              </View>
            )}
          </View>
        </View>

        {/* Online payments — Kenya is deliberately app-first. */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Online Payments</Text>
          <View style={styles.settingsCard}>
            <View style={styles.paymentSetupHeader}>
              <View style={styles.paymentSetupIcon}>
                <Ionicons name="wallet-outline" size={24} color="#25D366" />
              </View>
              <View style={styles.paymentSetupCopy}>
                <Text style={styles.paymentSetupTitle}>Receive customer payments</Text>
                <Text style={styles.paymentSetupText}>
                  Set up M-Pesa or a bank payout for your shared product catalog.
                </Text>
              </View>
            </View>
            <TouchableOpacity
              style={styles.paymentSetupButton}
              onPress={() => setShowPaymentSetup(true)}
            >
              <Text style={styles.paymentSetupButtonText}>Set up payments</Text>
              <Ionicons name="chevron-forward" size={18} color="#062414" />
            </TouchableOpacity>
            <Text style={styles.paymentSetupFootnote}>
              No website or Paystack login required. Paid catalog orders appear in Sales.
            </Text>
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
                <Text style={{ fontSize: 12, color: '#8A9BB5', marginTop: 2 }}>
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
                  <Ionicons name="time-outline" size={20} color="#8A9BB5" />
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
                      {sendingPulse ? 'Sending...' : 'Send Now'}
                    </Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>
        </View>

        {/* Credits Card */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Extra Messages</Text>
          <View style={styles.creditsCard}>
            <View style={styles.creditsLeft}>
              <Ionicons name="flash" size={28} color="#F59E0B" />
              <View style={styles.creditsDetails}>
                <Text style={styles.creditsValue}>{extraCredits.toLocaleString()}</Text>
                <Text style={styles.creditsLabel}>Extra WhatsApp messages available</Text>
              </View>
            </View>
            <TouchableOpacity
              style={styles.buyCreditsButton}
              onPress={() => setShowCreditModal(true)}
            >
              <Text style={styles.buyCreditsText}>Buy More</Text>
            </TouchableOpacity>
          </View>
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
                <Text style={styles.planPrice}>{plan.amount_display}</Text>
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
            {(user?.role === 'owner' || user?.role === 'manager' || !user?.role) && (
              <TouchableOpacity
                style={styles.settingItem}
                onPress={() => setShowTeamModal(true)}
              >
                <Ionicons name="people-outline" size={24} color="#25D366" />
                <Text style={styles.settingText}>Team Management</Text>
                <Ionicons name="chevron-forward" size={20} color="#666" />
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => setShowProductCatalog(true)}
              accessibilityRole="button"
              accessibilityLabel="Open product catalog"
            >
              <Ionicons name="cube-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Product Catalog</Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => setShowBusinessKnowledge(true)}
              accessibilityRole="button"
              accessibilityLabel="Open business knowledge"
            >
              <Ionicons name="book-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Business Knowledge</Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => setShowBusinessType(true)}
              accessibilityRole="button"
              accessibilityLabel="Change business type"
            >
              <Ionicons name="briefcase-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Business Type</Text>
              <Text style={{ color: '#8A9BB5', fontSize: 13, marginRight: 8 }}>
                {BUSINESS_TYPE_OPTIONS.find((o) => o.id === businessType)?.label || 'Not set'}
              </Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <View style={styles.settingItem}>
              <Ionicons name="chatbubble-outline" size={24} color="#666" />
              <View style={{ flex: 1 }}>
                <Text style={styles.settingText}>Auto Reply</Text>
                {autoReplyEnabled && (
                  <Text style={{ fontSize: 12, color: '#8A9BB5', marginTop: 2, marginLeft: 12 }}>
                    {autoReplyAudience === 'everyone' ? 'Replying to everyone' :
                     autoReplyAudience === 'customers_only' ? 'Customers only' :
                     'New contacts only'}
                  </Text>
                )}
              </View>
              <Switch
                value={autoReplyEnabled}
                onValueChange={handleToggleAutoReply}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </View>
            {autoReplyEnabled && (
              <TouchableOpacity
                style={styles.settingItem}
                onPress={() => setShowAudiencePicker(true)}
              >
                <Ionicons name="people-outline" size={24} color="#666" />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={[styles.settingText, { marginLeft: 0 }]}>Reply Audience</Text>
                  <Text style={{ fontSize: 12, color: '#8A9BB5', marginTop: 2 }}>
                    {autoReplyAudience === 'everyone' ? 'Everyone who messages' :
                     autoReplyAudience === 'customers_only' ? 'Only saved customers' :
                     'Only new / first-time contacts'}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color="#666" />
              </TouchableOpacity>
            )}
            <View style={styles.settingItem}>
              <Ionicons name="notifications-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Notifications</Text>
              <Switch
                value={notificationsEnabled}
                onValueChange={handleToggleNotifications}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </View>
          </View>
        </View>

        {/* Logout */}
        <TouchableOpacity
          style={styles.deleteAccountButton}
          onPress={handleDeleteAccount}
          accessibilityRole="button"
          accessibilityLabel="Delete account"
        >
          <Text style={styles.deleteAccountText}>Delete account</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={24} color="#FF4444" />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>

        <Text style={styles.version}>Version 1.0.0</Text>
      </ScrollView>

      {/* Daily Pulse Time Picker */}
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

      {/* Auto Reply Audience Picker Modal */}
      <Modal
        visible={showAudiencePicker}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowAudiencePicker(false)}
      >
        <SafeAreaView style={styles.container}>
          <View style={styles.pulseModalHeader}>
            <TouchableOpacity onPress={() => setShowAudiencePicker(false)}>
              <Ionicons name="close" size={24} color="#FFFFFF" />
            </TouchableOpacity>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#FFFFFF' }}>Reply Audience</Text>
            <View style={{ width: 24 }} />
          </View>
          <ScrollView style={{ flex: 1, padding: 16 }}>
            <Text style={{ color: '#8A9BB5', fontSize: 13, marginBottom: 16 }}>
              Choose who the AI auto-reply responds to. Individual contact overrides always take priority.
            </Text>
            {([
              { value: 'everyone', label: 'Everyone', desc: 'Reply to all incoming messages' },
              { value: 'customers_only', label: 'Customers Only', desc: 'Only reply to contacts you have saved as customers' },
              { value: 'new_contacts_only', label: 'New Contacts Only', desc: 'Only reply to first-time or uncontacted messages' },
            ] as const).map((opt) => (
              <TouchableOpacity
                key={opt.value}
                style={[
                  styles.audienceOption,
                  autoReplyAudience === opt.value && styles.audienceOptionActive,
                ]}
                onPress={() => handleSelectAudience(opt.value)}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 15 }}>{opt.label}</Text>
                  <Text style={{ color: '#8A9BB5', fontSize: 13, marginTop: 4 }}>{opt.desc}</Text>
                </View>
                {autoReplyAudience === opt.value && (
                  <Ionicons name="checkmark-circle" size={24} color="#25D366" />
                )}
              </TouchableOpacity>
            ))}
          </ScrollView>
        </SafeAreaView>
      </Modal>

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
                <Text style={{ color: '#8A9BB5', marginTop: 12 }}>Generating your pulse...</Text>
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
                <Text style={{ color: '#8A9BB5', fontSize: 12, textAlign: 'center', marginTop: 16 }}>
                  This is what you'll receive every day at {formatTime(pulseTime)}
                </Text>
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Modals */}
      <CreditBundleModal
        visible={showCreditModal}
        onClose={() => setShowCreditModal(false)}
        onSuccess={(added) => {
          setExtraCredits(prev => prev + added);
          setShowCreditModal(false);
        }}
        currentCredits={extraCredits}
      />
      <SubscriptionModal
        visible={showSubModal}
        onClose={() => {
          setShowSubModal(false);
          setSubscriptionEntryPoint('upgrade');
        }}
        onSuccess={async () => {
          const shouldStartPairing = subscriptionEntryPoint === 'whatsapp_trial';
          setShowSubModal(false);
          setSubscriptionEntryPoint('upgrade');
          await refreshUser();
          await fetchData();
          if (shouldStartPairing) {
            await beginWhatsAppPairing();
          }
        }}
        currentPlan={user?.subscription_plan}
        entryPoint={subscriptionEntryPoint}
      />
      <TeamManagementModal
        visible={showTeamModal}
        onClose={() => setShowTeamModal(false)}
        userRole={user?.role || 'owner'}
        userId={user?.id || ''}
      />
      <PaymentSetupModal
        visible={showPaymentSetup}
        businessName={user?.business_name}
        onClose={() => setShowPaymentSetup(false)}
        onConnectionChanged={fetchData}
      />
      <Modal
        visible={showBusinessType}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowBusinessType(false)}
      >
        <SafeAreaView style={styles.container}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 20, borderBottomWidth: 1, borderBottomColor: '#1A2942' }}>
            <Text style={{ fontSize: 18, fontWeight: 'bold', color: '#FFFFFF' }}>Business Type</Text>
            <TouchableOpacity onPress={() => setShowBusinessType(false)} accessibilityLabel="Close">
              <Ionicons name="close" size={26} color="#FFFFFF" />
            </TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={{ padding: 20 }}>
            <Text style={{ color: '#8A9BB5', fontSize: 13, marginBottom: 16 }}>
              This sets what your app calls things, whether Bookings appears, and whether your shop link takes orders or bookings.
            </Text>
            <BusinessTypePicker
              value={businessType}
              onChange={async (type) => {
                setShowBusinessType(false);
                try {
                  await settingsAPI.updateSettings({ business_type: type });
                  await refreshBusiness();
                } catch {
                  Alert.alert('Could not save', 'Please check your connection and try again.');
                }
              }}
            />
          </ScrollView>
        </SafeAreaView>
      </Modal>

      <ProductCatalogModal
        visible={showProductCatalog}
        onClose={() => setShowProductCatalog(false)}
      />
      <BusinessKnowledgeModal
        visible={showBusinessKnowledge}
        onClose={() => setShowBusinessKnowledge(false)}
      />
    </SafeAreaView>
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
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  section: {
    paddingHorizontal: 20,
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 12,
  },
  businessCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 16,
  },
  businessAvatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
  },
  businessAvatarText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  businessInfo: {
    flex: 1,
    marginLeft: 16,
  },
  businessName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  businessPhone: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },
  subscriptionDetail: {
    fontSize: 11,
    color: '#8A9BB5',
    marginTop: 4,
    lineHeight: 15,
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
    gap: 12,
  },
  statCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 8,
  },
  statLabel: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  planCard: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 20,
    marginBottom: 12,
  },
  planCardActive: {
    borderWidth: 2,
    borderColor: '#25D366',
  },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  planName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  planPrice: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#25D366',
  },
  planFeatures: {
    marginBottom: 16,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  featureText: {
    fontSize: 14,
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
  paymentSetupHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    paddingBottom: 12,
  },
  paymentSetupIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#113727',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  paymentSetupCopy: {
    flex: 1,
  },
  paymentSetupTitle: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 3,
  },
  paymentSetupText: {
    color: '#8A9BB5',
    fontSize: 12,
    lineHeight: 17,
  },
  paymentSetupButton: {
    marginHorizontal: 16,
    backgroundColor: '#25D366',
    borderRadius: 10,
    minHeight: 46,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  paymentSetupButtonText: {
    color: '#062414',
    fontSize: 14,
    fontWeight: '800',
  },
  paymentSetupFootnote: {
    color: '#8A9BB5',
    fontSize: 11,
    lineHeight: 16,
    padding: 16,
    paddingTop: 11,
  },
  settingsCard: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    overflow: 'hidden',
  },
  whatsappConnectedContent: {
    padding: 16,
  },
  whatsappConnectedHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
    gap: 12,
  },
  whatsappStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    minWidth: 0,
  },
  whatsappStatusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#25D366',
    marginRight: 10,
  },
  whatsappStatusText: {
    color: '#25D366',
    fontSize: 16,
    fontWeight: '600',
  },
  disconnectButton: {
    backgroundColor: 'rgba(255, 68, 68, 0.12)',
    borderColor: 'rgba(255, 68, 68, 0.35)',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
    flexShrink: 0,
  },
  disconnectButtonDisabled: {
    opacity: 0.65,
  },
  disconnectButtonText: {
    color: '#FF7373',
    fontSize: 13,
    fontWeight: '600',
  },
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#0A1628',
  },
  settingText: {
    flex: 1,
    fontSize: 16,
    color: '#FFFFFF',
    marginLeft: 12,
  },
  deleteAccountButton: {
    alignItems: 'center',
    paddingVertical: 14,
    marginTop: 8,
  },
  deleteAccountText: {
    color: '#8A9BB5',
    fontSize: 14,
    textDecorationLine: 'underline',
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 20,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  logoutText: {
    fontSize: 16,
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
  creditsCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1.5,
    borderColor: '#2A3F5A',
  },
  creditsLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    minWidth: 0,
  },
  creditsDetails: {
    flex: 1,
    minWidth: 0,
    marginLeft: 12,
  },
  creditsValue: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  creditsLabel: {
    fontSize: 12,
    color: '#8A9BB5',
    marginTop: 2,
    flexShrink: 1,
    flexWrap: 'wrap',
  },
  buyCreditsButton: {
    backgroundColor: '#F59E0B',
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginLeft: 12,
    flexShrink: 0,
  },
  buyCreditsText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
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
  // Auto Reply audience picker styles
  audienceOption: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  audienceOptionActive: {
    borderColor: '#25D366',
  },
});
