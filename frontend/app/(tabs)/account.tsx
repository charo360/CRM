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
  Modal,
  Platform,
  TextInput,
  Linking,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import DateTimePicker from '@react-native-community/datetimepicker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../../context/AuthContext';
import { apiClient, settingsAPI, whatsappAPI, accountAPI } from '../../context/api';

import { NotificationHandler } from '../../utils/notification-handler';
import TeamManagementModal from '../../components/TeamManagementModal';
// IAP stubs — real react-native-iap is linked only in native production builds
type ProductPurchase = { purchaseToken?: string; transactionId?: string };
type PurchaseError = { code?: string; message?: string };
const initConnection = async () => { };
const requestPurchase = async (_opts: any) => { throw new Error('IAP not available in this build'); };
const purchaseUpdatedListener = (_cb: any): { remove: () => void } => ({ remove: () => { } });
const purchaseErrorListener = (_cb: any): { remove: () => void } => ({ remove: () => { } });
const finishTransaction = async (_opts: any) => { };

// Product IDs for credit bundles on each platform
const CREDIT_PRODUCT_IDS: Record<string, string> = {
  credits_500: Platform.OS === 'ios' ? 'com.charo360.credits500' : 'charo360_credits_500',
  credits_1000: Platform.OS === 'ios' ? 'com.charo360.credits1000' : 'charo360_credits_1000',
  credits_2500: Platform.OS === 'ios' ? 'com.charo360.credits2500' : 'charo360_credits_2500',
  credits_5000: Platform.OS === 'ios' ? 'com.charo360.credits5000' : 'charo360_credits_5000',
};

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

  // Credit Top-up State
  const [extraCredits, setExtraCredits] = useState(0);
  const [showTopUpModal, setShowTopUpModal] = useState(false);
  const [buyingCredits, setBuyingCredits] = useState<string | null>(null);

  // AI Model State
  const [aiModel, setAiModel] = useState('standard');
  const [showModelPicker, setShowModelPicker] = useState(false);

  // Auto Reply State
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [autoReplyAudience, setAutoReplyAudience] = useState<'everyone' | 'customers_only' | 'new_contacts_only'>('everyone');
  const [showAudiencePicker, setShowAudiencePicker] = useState(false);

  // Team Management State
  const [showTeamModal, setShowTeamModal] = useState(false);

  const { user, logout, refreshUser } = useAuth();
  const router = useRouter();

  // IAP refs for purchase callbacks
  const pendingBundleIdRef = useRef<string | null>(null);
  const purchaseListenerRef = useRef<any>(null);
  const errorListenerRef = useRef<any>(null);

  useEffect(() => {
    fetchData();
    // Init IAP connection
    initConnection().catch(() => { });
    return () => {
      purchaseListenerRef.current?.remove();
      errorListenerRef.current?.remove();
    };
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
      setAiModel(settingsRes.data.ai_model || 'standard');
      setAutoReplyEnabled(settingsRes.data.auto_reply_enabled || false);
      setAutoReplyAudience(settingsRes.data.auto_reply_audience || 'everyone');

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

      // Load extra credits balance
      try {
        const statusRes = await apiClient.get('/subscription/status');
        setExtraCredits(statusRes.data.extra_credits || 0);
      } catch (e) { }
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const clearWaTimers = useCallback(() => {
    if (waCountdownRef.current) { clearInterval(waCountdownRef.current); waCountdownRef.current = null; }
    if (waPollingRef.current) { clearInterval(waPollingRef.current); waPollingRef.current = null; }
    if (waRefreshRef.current) { clearTimeout(waRefreshRef.current); waRefreshRef.current = null; }
  }, []);

  useEffect(() => {
    return () => clearWaTimers();
  }, [clearWaTimers]);

  const startPairingTimers = useCallback((code: string) => {
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

    // Auto-refresh code at 50s (before 60s expiry)
    waRefreshRef.current = setTimeout(async () => {
      try {
        const res = await whatsappAPI.connect(waPhoneInput.trim());
        if (res.pairing_code) {
          startPairingTimers(res.pairing_code);
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
  }, [clearWaTimers, waPhoneInput]);

  const handleCopyCode = async () => {
    if (!waPairingCode) return;
    await Clipboard.setStringAsync(waPairingCode);
    setWaCopied(true);
    setTimeout(() => setWaCopied(false), 2000);
  };

  const handleOpenWhatsApp = () => {
    if (waPairingCode) {
      const link = `https://wa.me/login?code=${waPairingCode}`;
      Linking.openURL(link)
        .catch(() => Linking.openURL('whatsapp://'))
        .catch(() => {
          Alert.alert('Error', 'Could not open WhatsApp. Please open it manually and go to Linked Devices.');
        });
    } else {
      Linking.openURL('whatsapp://')
        .catch(() => {
          Alert.alert('Error', 'Could not open WhatsApp. Please open it manually.');
        });
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
        startPairingTimers(res.pairing_code);
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

  const handleModelChange = async (model: string) => {
    setAiModel(model);
    setShowModelPicker(false);
    try {
      await apiClient.put('/settings', { ai_model: model });
      Alert.alert('Success', `AI Model updated to ${getModelName(model)}`);
    } catch (error) {
      setAiModel('standard'); // revert
      Alert.alert('Error', 'Failed to update AI model');
    }
  };

  const getModelName = (modelId: string) => {
    switch (modelId) {
      case 'deepseek': return 'DeepSeek V3 (1x)';
      case 'standard': return 'GPT-4o Mini (1.6x)';
      case 'grok': return 'Grok 4.1 (1.7x)';
      case 'gpt5': return 'GPT-5 (12x)';
      case 'premium': return 'GPT-4o (15x)';
      case 'claude-3.5': return 'Claude 3.5 (12x)';
      default: return 'GPT-4o Mini (1.6x)';
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
                <TouchableOpacity
                  style={{ backgroundColor: 'rgba(37,211,102,0.1)', borderRadius: 10, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginTop: 12 }}
                  onPress={async () => {
                    try {
                      Alert.alert('Syncing...', 'Pulling contacts and chat history from WhatsApp. This may take a few minutes...');
                      const result = await whatsappAPI.sync();
                      const t = result.totals || {};
                      Alert.alert(
                        'Sync Started ✅',
                        `Syncing contacts and chat history in the background.\n\nCurrently in app: ${t.customers || 0} contacts, ${t.messages || 0} messages.\n\nRefresh your Contacts tab in 1-3 minutes to see your WhatsApp contacts and chats appear.`
                      );
                    } catch (e: any) {
                      Alert.alert('Sync Failed', e.response?.data?.detail || e.message || 'Could not sync WhatsApp data. Try again.');
                    }
                  }}
                >
                  <Ionicons name="sync-outline" size={18} color="#25D366" />
                  <Text style={{ color: '#25D366', fontSize: 14, fontWeight: '600', marginLeft: 8 }}>Sync WhatsApp Contacts & Chats</Text>
                </TouchableOpacity>
              </View>
            ) : waPairingCode ? (
              <View>
                <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginBottom: 8 }}>Enter this code in WhatsApp</Text>
                <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 12 }}>
                  Open WhatsApp {'>'} Linked Devices {'>'} Link a Device {'>'} Link with phone number
                </Text>
                <TouchableOpacity
                  onPress={handleCopyCode}
                  activeOpacity={0.7}
                  style={{ backgroundColor: 'rgba(37,211,102,0.1)', borderRadius: 12, padding: 20, alignItems: 'center', marginBottom: 8 }}
                >
                  <Text style={{ color: '#25D366', fontSize: 32, fontWeight: '700', letterSpacing: 8 }}>{waPairingCode}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 10 }}>
                    <Ionicons name={waCopied ? 'checkmark-circle' : 'copy-outline'} size={16} color={waCopied ? '#25D366' : '#8B9DC3'} />
                    <Text style={{ color: waCopied ? '#25D366' : '#8B9DC3', fontSize: 12, marginLeft: 6 }}>
                      {waCopied ? 'Copied to clipboard!' : 'Tap to copy code'}
                    </Text>
                  </View>
                </TouchableOpacity>
                <View style={{ backgroundColor: 'rgba(37,211,102,0.05)', borderRadius: 10, padding: 12, marginBottom: 12 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
                    <Ionicons name="notifications" size={18} color="#25D366" />
                    <Text style={{ color: '#25D366', fontSize: 13, fontWeight: '600', marginLeft: 8 }}>Check your phone for push notification</Text>
                  </View>
                  <Text style={{ color: '#8B9DC3', fontSize: 12, lineHeight: 18 }}>
                    WhatsApp will send a notification to link this device. Tap it to open the pairing screen, then enter the code above.
                  </Text>
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginBottom: 12 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: waCountdown > 10 ? '#25D366' : '#FF4444', marginRight: 8 }} />
                  <Text style={{ color: waCountdown > 10 ? '#8B9DC3' : '#FF4444', fontSize: 12 }}>
                    {waCountdown > 0 ? `Code refreshes in ${waCountdown}s` : 'Refreshing code...'}
                  </Text>
                </View>
                <ActivityIndicator size="small" color="#25D366" />
                <Text style={{ color: '#8B9DC3', fontSize: 11, textAlign: 'center', marginTop: 6 }}>Waiting for connection...</Text>
                <TouchableOpacity
                  style={{ marginTop: 14, alignItems: 'center' }}
                  onPress={() => { clearWaTimers(); setWaPairingCode(''); setWaPhoneInput(''); }}
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

        {/* Message Credits */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Message Credits</Text>
          <View style={styles.settingsCard}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text style={{ color: '#8B9DC3', fontSize: 13 }}>Plan quota used</Text>
              <Text style={{ color: '#FFFFFF', fontSize: 13, fontWeight: '600' }}>{waMsgSent} / {waMsgLimit}</Text>
            </View>
            <View style={{ height: 4, backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 2, marginBottom: 8 }}>
              <View style={{ height: 4, backgroundColor: waMsgSent / Math.max(waMsgLimit, 1) > 0.9 ? '#FF4444' : '#25D366', borderRadius: 2, width: `${Math.min((waMsgSent / Math.max(waMsgLimit, 1)) * 100, 100)}%` }} />
            </View>
            {extraCredits > 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 }}>
                <Ionicons name="wallet-outline" size={14} color="#FFC107" />
                <Text style={{ color: '#FFC107', fontSize: 12, marginLeft: 6 }}>{extraCredits} extra credits in balance</Text>
              </View>
            )}
            <TouchableOpacity
              style={{ backgroundColor: 'rgba(255,193,7,0.1)', borderRadius: 10, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(255,193,7,0.3)' }}
              onPress={() => setShowTopUpModal(true)}
            >
              <Ionicons name="add-circle-outline" size={18} color="#FFC107" />
              <Text style={{ color: '#FFC107', fontSize: 14, fontWeight: '600', marginLeft: 8 }}>Buy Extra Credits</Text>
            </TouchableOpacity>
            <Text style={{ color: '#555', fontSize: 11, textAlign: 'center', marginTop: 8 }}>Credits never expire · Stack on top of your plan</Text>
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
              onPress={() => setShowTeamModal(true)}
            >
              <Ionicons
                name={user?.team_members_count && user.team_members_count > 1 ? "people" : "person-add-outline"}
                size={24}
                color={user?.team_members_count && user.team_members_count > 1 ? "#4A90D9" : "#25D366"}
              />
              <Text style={styles.settingText}>
                {user?.team_members_count && user.team_members_count > 1 ? "Team Management" : "Add Team Members"}
              </Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => router.push('../analytics' as any)}
            >
              <Ionicons name="analytics-outline" size={24} color="#25D366" />
              <Text style={styles.settingText}>Analytics</Text>
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
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => setShowModelPicker(true)}
            >
              <Ionicons name="hardware-chip-outline" size={24} color="#666" />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.settingText}>AI Model</Text>
                <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                  {getModelName(aiModel)}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <View style={styles.settingItem}>
              <Ionicons name="chatbubble-outline" size={24} color="#666" />
              <View style={{ flex: 1, marginLeft: 0 }}>
                <Text style={styles.settingText}>Auto Reply</Text>
                {autoReplyEnabled && (
                  <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                    {autoReplyAudience === 'everyone' ? 'Replying to everyone' :
                      autoReplyAudience === 'customers_only' ? 'Customers only' :
                        'New contacts only'}
                  </Text>
                )}
              </View>
              <Switch
                value={autoReplyEnabled}
                onValueChange={async (val) => {
                  setAutoReplyEnabled(val);
                  try {
                    await settingsAPI.updateSettings({ auto_reply_enabled: val });
                  } catch (e) {
                    setAutoReplyEnabled(!val);
                  }
                }}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </View>
            {autoReplyEnabled && (
              <TouchableOpacity
                style={[styles.settingItem, { borderTopWidth: 1, borderTopColor: '#1e2d3d' }]}
                onPress={() => setShowAudiencePicker(true)}
              >
                <Ionicons name="people-outline" size={24} color="#666" />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.settingText}>Reply Audience</Text>
                  <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                    {autoReplyAudience === 'everyone' ? 'Everyone who messages' :
                      autoReplyAudience === 'customers_only' ? 'Only saved customers' :
                        'Only new / first-time contacts'}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color="#666" />
              </TouchableOpacity>
            )}
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



        {/* AI Model Picker Modal */}
        <Modal
          visible={showModelPicker}
          transparent={true}
          animationType="slide"
          onRequestClose={() => setShowModelPicker(false)}
        >
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'flex-end' }}>
            <View style={{ backgroundColor: '#1E1E1E', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <Text style={{ fontSize: 18, fontWeight: 'bold', color: '#FFFFFF' }}>Select AI Model</Text>
                <TouchableOpacity onPress={() => setShowModelPicker(false)}>
                  <Text style={{ color: '#8B9DC3', fontSize: 16 }}>Close</Text>
                </TouchableOpacity>
              </View>

              <Text style={{ color: '#8B9DC3', marginBottom: 15, fontSize: 13 }}>
                Each model costs a different number of credits per message sent. Higher-capability models use more credits from your monthly quota.
              </Text>

              {[
                { id: 'deepseek', name: 'DeepSeek V3', desc: 'Best value — analytical & multilingual', credits: '1x', creditsColor: '#25D366' },
                { id: 'standard', name: 'GPT-4o Mini', desc: 'Fast, reliable, great for daily use', credits: '1.6x', creditsColor: '#25D366' },
                { id: 'grok', name: 'Grok 4.1', desc: 'Witty, relaxed conversational style', credits: '1.7x', creditsColor: '#FFA500' },
                { id: 'gpt5', name: 'GPT-5', desc: 'Most capable reasoning & writing', credits: '12x', creditsColor: '#FF6B6B' },
                { id: 'premium', name: 'GPT-4o', desc: 'Smarter, better reasoning, slightly slower', credits: '15x', creditsColor: '#FF6B6B' },
              ].map((model) => (
                <TouchableOpacity
                  key={model.id}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    backgroundColor: aiModel === model.id ? 'rgba(37,211,102,0.1)' : 'rgba(255,255,255,0.05)',
                    padding: 16,
                    borderRadius: 12,
                    marginBottom: 10,
                    borderWidth: 1,
                    borderColor: aiModel === model.id ? '#25D366' : 'transparent'
                  }}
                  onPress={() => handleModelChange(model.id)}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginBottom: 4 }}>{model.name}</Text>
                    <Text style={{ color: '#8B9DC3', fontSize: 12 }}>{model.desc}</Text>
                  </View>
                  <View style={{ alignItems: 'center', marginLeft: 10 }}>
                    <Text style={{ color: (model as any).creditsColor || '#8B9DC3', fontSize: 13, fontWeight: '700' }}>{(model as any).credits}</Text>
                    <Text style={{ color: '#666', fontSize: 10 }}>credits</Text>
                  </View>
                  {aiModel === model.id && (
                    <Ionicons name="checkmark-circle" size={24} color="#25D366" style={{ marginLeft: 8 }} />
                  )}
                </TouchableOpacity>
              ))}

              <View style={{ height: 20 }} />
            </View>
          </View>
        </Modal>

        {/* Credit Top-Up Modal */}
        <Modal
          visible={showTopUpModal}
          transparent={true}
          animationType="slide"
          onRequestClose={() => setShowTopUpModal(false)}
        >
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'flex-end' }}>
            <View style={{ backgroundColor: '#1E1E1E', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <Text style={{ fontSize: 18, fontWeight: 'bold', color: '#FFFFFF' }}>Buy Extra Credits</Text>
                <TouchableOpacity onPress={() => setShowTopUpModal(false)}>
                  <Text style={{ color: '#8B9DC3', fontSize: 16 }}>Close</Text>
                </TouchableOpacity>
              </View>
              <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 16 }}>
                Credits never expire and stack on top of your monthly plan quota.
              </Text>

              {extraCredits > 0 && (
                <View style={{ backgroundColor: 'rgba(37,211,102,0.1)', borderRadius: 10, padding: 10, marginBottom: 14, flexDirection: 'row', alignItems: 'center' }}>
                  <Ionicons name="wallet-outline" size={16} color="#25D366" />
                  <Text style={{ color: '#25D366', fontSize: 13, marginLeft: 8 }}>Current balance: <Text style={{ fontWeight: '700' }}>{extraCredits} credits</Text></Text>
                </View>
              )}

              {[
                { bundle_id: 'credits_500', label: '500 Credits', price: '$2.99', note: '~500 manual msgs or ~312 GPT-4o mini replies' },
                { bundle_id: 'credits_1000', label: '1,000 Credits', price: '$4.99', note: '~1,000 manual msgs or ~625 GPT-4o mini replies' },
                { bundle_id: 'credits_2500', label: '2,500 Credits', price: '$9.99', note: '~2,500 manual msgs or ~1,562 GPT-4o mini replies' },
                { bundle_id: 'credits_5000', label: '5,000 Credits', price: '$17.99', note: 'Best value — ~5,000 manual msgs or ~3,125 GPT-4o mini replies' },
              ].map((bundle) => (
                <TouchableOpacity
                  key={bundle.bundle_id}
                  style={{
                    backgroundColor: 'rgba(255,255,255,0.05)',
                    borderRadius: 12,
                    padding: 14,
                    marginBottom: 10,
                    flexDirection: 'row',
                    alignItems: 'center',
                    borderWidth: bundle.bundle_id === 'credits_2500' ? 1 : 0,
                    borderColor: bundle.bundle_id === 'credits_2500' ? '#FFC107' : 'transparent',
                  }}
                  disabled={buyingCredits !== null}
                  onPress={async () => {
                    const productId = CREDIT_PRODUCT_IDS[bundle.bundle_id];
                    if (!productId) {
                      Alert.alert('Error', 'Product not found');
                      return;
                    }
                    setBuyingCredits(bundle.bundle_id);
                    pendingBundleIdRef.current = bundle.bundle_id;

                    // Set up one-time purchase listener
                    purchaseListenerRef.current?.remove();
                    errorListenerRef.current?.remove();

                    purchaseListenerRef.current = purchaseUpdatedListener(async (purchase: ProductPurchase) => {
                      const token = purchase.purchaseToken || purchase.transactionId || '';
                      try {
                        const res = await apiClient.post('/subscription/add-credits', {
                          bundle_id: pendingBundleIdRef.current,
                          purchase_token: token,
                          platform: Platform.OS === 'ios' ? 'ios' : 'android',
                        });
                        await finishTransaction({ purchase, isConsumable: true });
                        setExtraCredits(res.data.total_extra_credits);
                        setWaMsgLimit(waMsgLimit + res.data.credits_added);
                        Alert.alert('Credits Added!', res.data.message);
                        setShowTopUpModal(false);
                      } catch (e: any) {
                        Alert.alert('Failed', e.response?.data?.detail || 'Could not verify purchase');
                      } finally {
                        setBuyingCredits(null);
                        pendingBundleIdRef.current = null;
                      }
                    });

                    errorListenerRef.current = purchaseErrorListener((error: PurchaseError) => {
                      if (error.code !== 'E_USER_CANCELLED') {
                        Alert.alert('Purchase Failed', error.message || 'Could not complete purchase');
                      }
                      setBuyingCredits(null);
                      pendingBundleIdRef.current = null;
                    });

                    try {
                      await requestPurchase({ sku: productId });
                    } catch (e: any) {
                      if (e.code !== 'E_USER_CANCELLED') {
                        Alert.alert('Purchase Failed', e.message || 'Could not start purchase');
                      }
                      setBuyingCredits(null);
                      pendingBundleIdRef.current = null;
                    }
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                      <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '700' }}>{bundle.label}</Text>
                      {bundle.bundle_id === 'credits_2500' && (
                        <View style={{ backgroundColor: '#FFC107', borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2, marginLeft: 8 }}>
                          <Text style={{ color: '#000', fontSize: 10, fontWeight: '700' }}>POPULAR</Text>
                        </View>
                      )}
                    </View>
                    <Text style={{ color: '#8B9DC3', fontSize: 11, marginTop: 3 }}>{bundle.note}</Text>
                  </View>
                  {buyingCredits === bundle.bundle_id ? (
                    <ActivityIndicator size="small" color="#FFC107" />
                  ) : (
                    <Text style={{ color: '#FFC107', fontSize: 16, fontWeight: '700' }}>{bundle.price}</Text>
                  )}
                </TouchableOpacity>
              ))}

              <View style={{ height: 10 }} />
            </View>
          </View>
        </Modal>

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

        {/* Data & Account Management */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Data & Privacy</Text>

          <TouchableOpacity
            style={styles.dataButton}
            onPress={async () => {
              try {
                Alert.alert('Exporting...', 'Preparing your data export.');
                const data = await accountAPI.exportData();
                await Clipboard.setStringAsync(JSON.stringify(data, null, 2));
                Alert.alert('Exported!', 'Your data has been copied to clipboard as JSON.');
              } catch (e: any) {
                Alert.alert('Error', e.response?.data?.detail || 'Failed to export data');
              }
            }}
          >
            <Ionicons name="download-outline" size={22} color="#25D366" />
            <Text style={styles.dataButtonText}>Export My Data</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.dataButton, { borderColor: '#FF4444' }]}
            onPress={() => {
              Alert.alert(
                'Delete Account',
                'This will permanently delete your account and ALL data (customers, messages, sales, products). This cannot be undone.',
                [
                  { text: 'Cancel', style: 'cancel' },
                  {
                    text: 'Delete Forever',
                    style: 'destructive',
                    onPress: () => {
                      Alert.alert(
                        'Are you absolutely sure?',
                        'Type DELETE to confirm.',
                        [
                          { text: 'Cancel', style: 'cancel' },
                          {
                            text: 'Yes, Delete Everything',
                            style: 'destructive',
                            onPress: async () => {
                              try {
                                await accountAPI.deleteAccount();
                                await logout();
                                router.replace('/');
                              } catch (e: any) {
                                Alert.alert('Error', e.response?.data?.detail || 'Failed to delete account');
                              }
                            },
                          },
                        ]
                      );
                    },
                  },
                ]
              );
            }}
          >
            <Ionicons name="trash-outline" size={22} color="#FF4444" />
            <Text style={[styles.dataButtonText, { color: '#FF4444' }]}>Delete Account</Text>
          </TouchableOpacity>
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={24} color="#FF4444" />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>

        <Text style={styles.version}>Version 1.0.0</Text>
      </ScrollView>

      {/* Auto Reply Audience Picker Modal */}
      <Modal
        visible={showAudiencePicker}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowAudiencePicker(false)}
      >
        <SafeAreaView style={styles.container}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: '#1e2d3d' }}>
            <TouchableOpacity onPress={() => setShowAudiencePicker(false)}>
              <Ionicons name="close" size={24} color="#FFFFFF" />
            </TouchableOpacity>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#FFFFFF' }}>Reply Audience</Text>
            <View style={{ width: 24 }} />
          </View>
          <ScrollView style={{ flex: 1, padding: 16 }}>
            <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 16 }}>
              Choose who the AI auto-reply responds to. Individual contact overrides always take priority.
            </Text>
            {([
              { value: 'everyone', label: 'Everyone', desc: 'Reply to all incoming messages' },
              { value: 'customers_only', label: 'Customers Only', desc: 'Only reply to contacts you have saved as customers' },
              { value: 'new_contacts_only', label: 'New Contacts Only', desc: 'Only reply to first-time or uncontacted messages' },
            ] as const).map((opt) => (
              <TouchableOpacity
                key={opt.value}
                style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', borderRadius: 12, padding: 16, marginBottom: 10, borderWidth: 2, borderColor: autoReplyAudience === opt.value ? '#25D366' : 'transparent' }}
                onPress={async () => {
                  setAutoReplyAudience(opt.value);
                  setShowAudiencePicker(false);
                  try {
                    await settingsAPI.updateSettings({ auto_reply_audience: opt.value });
                  } catch (e) { }
                }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 15 }}>{opt.label}</Text>
                  <Text style={{ color: '#8B9DC3', fontSize: 13, marginTop: 4 }}>{opt.desc}</Text>
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

      {/* Team Management Modal */}
      <TeamManagementModal
        visible={showTeamModal}
        onClose={() => setShowTeamModal(false)}
        userRole={user?.role || 'owner'}
        userId={user?.id || ''}
      />

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
  dataButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0D1B2A',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1A2942',
    padding: 14,
    marginBottom: 10,
  },
  dataButtonText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#25D366',
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
