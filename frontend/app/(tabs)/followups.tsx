import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  RefreshControl,
  Modal,
  TextInput,
  ScrollView,
  Platform,
  KeyboardAvoidingView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiClient } from '../../context/api';
import { useRouter } from 'expo-router';
import DateTimePicker from '@react-native-community/datetimepicker';

interface FollowUp {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  reminder_date: string;
  message: string | null;
  status: string;
  type: 'call' | 'whatsapp' | 'meeting' | 'email';
  outcome?: string | null;
  outcome_note?: string | null;
  created_at: string;
}

interface ColdCustomer {
  id: string;
  name: string;
  phone_number: string;
  notes: string | null;
  tags: string[];
  last_message: string | null;
  last_contacted: string | null;
  days_since_contact: number | null;
  has_pending_followup: boolean;
  ai_reason?: string;
  urgency_score?: number;
  urgency_level?: 'high' | 'medium' | 'low';
}

interface Customer {
  id: string;
  name: string;
  phone_number: string;
}

interface Suggestions {
  neglected_week: number;
  neglected_month: number;
  new_no_followup: number;
  vip_neglected: number;
  total_needing_attention: number;
}

interface Message {
  id: string;
  direction: 'incoming' | 'outgoing';
  content: string;
  created_at: string;
}

interface FollowUpAnalytics {
  stats: {
    period_days: number;
    total_followups: number;
    contacted: number;
    converted: number;
    responded: number;
    no_response: number;
    not_contacted: number;
    conversion_rate: number;
    response_rate: number;
    avg_response_time_hours: number;
    total_revenue: number;
    revenue_per_followup: number;
    needs_attention_contacted?: number;
    total_all?: number;
  };
  best_times: {
    best_day: string;
    best_hour: number;
    sample_size: number;
  };
  outcome_counts?: Record<string, number>;
}

type FilterType = 'all' | 'overdue' | 'today' | 'tomorrow' | 'this_week' | 'later';

export default function FollowupsScreen() {
  const router = useRouter();
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [coldCustomers, setColdCustomers] = useState<ColdCustomer[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestions | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<'reminders' | 'needs_attention' | 'analytics'>('needs_attention');
  const [analytics, setAnalytics] = useState<FollowUpAnalytics | null>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const [analyticsPeriod, setAnalyticsPeriod] = useState(30);
  const [filter, setFilter] = useState<FilterType>('all');

  // Add Reminder Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [reminderDate, setReminderDate] = useState(new Date());
  const [reminderMessage, setReminderMessage] = useState('');
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [selectedType, setSelectedType] = useState<'call' | 'whatsapp' | 'meeting' | 'email'>('call');
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [customerSearch, setCustomerSearch] = useState('');
  const [showCustomerList, setShowCustomerList] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editingFollowup, setEditingFollowup] = useState<FollowUp | null>(null);

  // Draft Message Modal State
  const [showDraftModal, setShowDraftModal] = useState(false);
  const [draftCustomer, setDraftCustomer] = useState<ColdCustomer | null>(null);
  const [draftMessage, setDraftMessage] = useState('');
  const [draftReason, setDraftReason] = useState('');
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [customDirection, setCustomDirection] = useState('');
  const [recentMessages, setRecentMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [showRecentMessages, setShowRecentMessages] = useState(false);
  const [analyzeRetries, setAnalyzeRetries] = useState(0);
  const MAX_ANALYZE_RETRIES = 3;

  useEffect(() => {
    if (activeTab === 'analytics') {
      fetchAnalytics(analyticsPeriod);
    }
  }, [activeTab, analyticsPeriod]);

  // Snooze state
  const [snoozingId, setSnoozingId] = useState<string | null>(null);

  // Outcome modal state
  const [outcomeModalVisible, setOutcomeModalVisible] = useState(false);
  const [outcomeFollowup, setOutcomeFollowup] = useState<FollowUp | null>(null);
  const [selectedOutcome, setSelectedOutcome] = useState('');
  const [outcomeNote, setOutcomeNote] = useState('');
  const [savingOutcome, setSavingOutcome] = useState(false);

  // AI note draft state
  const [noteAIDirection, setNoteAIDirection] = useState('');
  const [generatingNoteAI, setGeneratingNoteAI] = useState(false);

  // Cold customer Done modal state
  const [coldDoneModalVisible, setColdDoneModalVisible] = useState(false);
  const [coldDoneCustomer, setColdDoneCustomer] = useState<ColdCustomer | null>(null);
  const [coldSelectedOutcome, setColdSelectedOutcome] = useState('');
  const [coldOutcomeNote, setColdOutcomeNote] = useState('');
  const [savingColdOutcome, setSavingColdOutcome] = useState(false);

  const handleColdDone = async () => {
    if (!coldDoneCustomer || !coldSelectedOutcome) return;
    setSavingColdOutcome(true);
    try {
      await apiClient.post('/followup-events', {
        customer_id: coldDoneCustomer.id,
        outcome: coldSelectedOutcome,
        note: coldOutcomeNote || null,
      });
      setColdCustomers(prev => prev.filter(c => c.id !== coldDoneCustomer.id));
      setColdDoneModalVisible(false);
      setColdDoneCustomer(null);
      setColdSelectedOutcome('');
      setColdOutcomeNote('');
    } catch (e) {
      Alert.alert('Error', 'Could not save outcome');
    } finally {
      setSavingColdOutcome(false);
    }
  };

  const fetchAnalytics = useCallback(async (days = 30) => {
    setLoadingAnalytics(true);
    try {
      const res = await apiClient.get(`/followups/analytics?days=${days}`);
      // Backend now returns outcome_counts merged from reminders + needs-attention events
      setAnalytics(res.data);
    } catch (e) {
      console.error('Analytics fetch error:', e);
    } finally {
      setLoadingAnalytics(false);
    }
  }, []);

  const fetchData = useCallback(async () => {
    try {
      // Trigger daily analysis in background (don't await)
      apiClient.get('/analysis/daily-insights').catch((e: any) => console.log('Background analysis trigger:', e));

      const [followupsRes, coldRes, suggestionsRes, customersRes] = await Promise.all([
        apiClient.get('/followups?status=pending'),
        apiClient.get('/customers/cold-with-reasons?days=14').catch(() => apiClient.get('/customers/cold?days=14')),
        apiClient.get('/stats/followup-suggestions'),
        apiClient.get('/customers'),
      ]);
      setFollowups(followupsRes.data);
      setColdCustomers(coldRes.data);
      setSuggestions(suggestionsRes.data);
      setCustomers(customersRes.data);

      // Only keep analyzing if we have customers but no cold results yet (analysis still running)
      if (coldRes.data.length === 0 && customersRes.data.length > 0) {
        setIsAnalyzing(true);
        setAnalyzeRetries(prev => prev + 1);
      } else {
        setIsAnalyzing(false);
        setAnalyzeRetries(0);
      }
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Poll for insights if analysis is running (max 3 retries, 15s interval)
  useEffect(() => {
    let interval: any;
    if (isAnalyzing && coldCustomers.length === 0 && analyzeRetries < MAX_ANALYZE_RETRIES) {
      interval = setInterval(() => {
        fetchData();
      }, 15000);
    }
    if (analyzeRetries >= MAX_ANALYZE_RETRIES) {
      setIsAnalyzing(false);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isAnalyzing, coldCustomers.length, analyzeRetries, fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const getDateCategory = (dateStr: string): string => {
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    const endOfWeek = new Date(today);
    endOfWeek.setDate(endOfWeek.getDate() + 7);

    const dateOnly = new Date(date);
    dateOnly.setHours(0, 0, 0, 0);

    if (dateOnly < today) return 'overdue';
    if (dateOnly.getTime() === today.getTime()) return 'today';
    if (dateOnly.getTime() === tomorrow.getTime()) return 'tomorrow';
    if (dateOnly <= endOfWeek) return 'this_week';
    return 'later';
  };

  const filteredFollowups = followups.filter(f => {
    if (filter === 'all') return true;
    const category = getDateCategory(f.reminder_date);
    return category === filter;
  });

  const groupedFollowups = {
    overdue: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'overdue'),
    today: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'today'),
    tomorrow: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'tomorrow'),
    this_week: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'this_week'),
    later: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'later'),
  };

  const handleComplete = (followup: FollowUp) => {
    setOutcomeFollowup(followup);
    setSelectedOutcome('');
    setOutcomeNote('');
    setOutcomeModalVisible(true);
  };

  const handleSaveOutcome = async () => {
    if (!outcomeFollowup || !selectedOutcome) {
      Alert.alert('Select Outcome', 'Please select what happened with this follow-up.');
      return;
    }
    setSavingOutcome(true);
    try {
      await apiClient.put(`/followups/${outcomeFollowup.id}`, {
        status: 'completed',
        outcome: selectedOutcome,
        outcome_note: outcomeNote || null,
      });
      setFollowups(followups.filter(f => f.id !== outcomeFollowup.id));
      setOutcomeModalVisible(false);
      setOutcomeFollowup(null);
    } catch (error) {
      Alert.alert('Error', 'Failed to save outcome');
    } finally {
      setSavingOutcome(false);
    }
  };

  const handleSnooze = async (followup: FollowUp, days: number) => {
    setSnoozingId(followup.id);
    try {
      const res = await apiClient.post(`/followups/${followup.id}/snooze?days=${days}`);
      const newDate = res.data.new_date;
      setFollowups(followups.map(f =>
        f.id === followup.id ? { ...f, reminder_date: newDate } : f
      ));
      Alert.alert('Snoozed', `Reminder moved to ${new Date(newDate).toLocaleDateString('en-KE', { weekday: 'short', day: 'numeric', month: 'short' })}`);
    } catch (error) {
      Alert.alert('Error', 'Failed to snooze reminder');
    } finally {
      setSnoozingId(null);
    }
  };

  const handleDelete = (followup: FollowUp) => {
    Alert.alert(
      'Delete Follow-up',
      'Are you sure you want to delete this reminder?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.delete(`/followups/${followup.id}`);
              setFollowups(followups.filter(f => f.id !== followup.id));
            } catch (error) {
              Alert.alert('Error', 'Failed to delete follow-up');
            }
          },
        },
      ]
    );
  };

  const handleSendMessage = (customerId: string, phone: string, name: string, message?: string | null) => {
    const text = message || `Hi ${name}, just checking in!`;
    router.push({
      pathname: '/chat',
      params: {
        customerId,
        customerName: name,
        customerPhone: phone,
        prefill: text,
      },
    });
  };

  const openEditModal = (followup: FollowUp) => {
    setEditingFollowup(followup);
    setSelectedCustomer({
      id: followup.customer_id,
      name: followup.customer_name,
      phone_number: followup.customer_phone,
    });
    setReminderDate(new Date(followup.reminder_date));
    setReminderMessage(followup.message || '');
    setSelectedType(followup.type);
    setIsEditing(true);
    setShowAddModal(true);
  };

  const scheduleLocalNotification = async (date: Date, customerName: string, message: string | null, followupType: string) => {
    try {
      const Notifications = await import('expo-notifications');
      const { status } = await Notifications.requestPermissionsAsync();
      if (status !== 'granted') return;
      const trigger = new Date(date);
      if (trigger <= new Date()) return;
      await Notifications.scheduleNotificationAsync({
        content: {
          title: `Follow-up: ${customerName}`,
          body: message || `Time to ${followupType} ${customerName}`,
          sound: true,
        },
        trigger: { date: trigger },
      });
    } catch (e) {
      console.log('Notification scheduling error:', e);
    }
  };

  const handleAddReminder = async () => {
    if (!selectedCustomer) {
      Alert.alert('Error', 'Please select a customer');
      return;
    }

    setSaving(true);
    try {
      if (isEditing && editingFollowup) {
        const response = await apiClient.put(`/followups/${editingFollowup.id}`, {
          reminder_date: reminderDate.toISOString(),
          message: reminderMessage || null,
          type: selectedType,
        });

        setFollowups(followups.map(f =>
          f.id === editingFollowup.id ? { ...f, ...response.data } : f
        ));
        await scheduleLocalNotification(reminderDate, selectedCustomer.name, reminderMessage, selectedType);
        Alert.alert('Success', 'Reminder updated!');
      } else {
        const response = await apiClient.post('/followups', {
          customer_id: selectedCustomer.id,
          reminder_date: reminderDate.toISOString(),
          message: reminderMessage || null,
          type: selectedType,
        });

        setFollowups([...followups, {
          ...response.data,
          customer_name: selectedCustomer.name,
          customer_phone: selectedCustomer.phone_number,
        }]);
        await scheduleLocalNotification(reminderDate, selectedCustomer.name, reminderMessage, selectedType);
        Alert.alert('Success', 'Reminder added!');
      }

      // Reset modal
      setShowAddModal(false);
      setIsEditing(false);
      setEditingFollowup(null);
      setSelectedCustomer(null);
      setReminderDate(new Date());
      setReminderMessage('');
      setSelectedType('call');
      setCustomerSearch('');

    } catch (error) {
      Alert.alert('Error', isEditing ? 'Failed to update reminder' : 'Failed to create reminder');
    } finally {
      setSaving(false);
    }
  };

  const handleCreateFollowupFromCold = async (customer: ColdCustomer) => {
    setSelectedCustomer({
      id: customer.id,
      name: customer.name,
      phone_number: customer.phone_number,
    });
    setReminderMessage(customer.ai_reason || '');
    setShowAddModal(true);
  };

  const handleShowDraftMessage = async (customer: ColdCustomer, direction?: string) => {
    setDraftCustomer(customer);
    setShowDraftModal(true);
    setLoadingDraft(true);
    setShowRecentMessages(false);
    fetchRecentMessages(customer.id);

    try {
      const response = await apiClient.post(`/ai/draft-message`, {
        customer_id: customer.id,
        custom_instructions: direction || customDirection
      });

      setDraftMessage(response.data.message || response.data.drafted_message || '');
      setDraftReason(response.data.reason || response.data.ai_reason || customer.ai_reason || 'Based on your last interaction');
    } catch (error) {
      console.error('Error fetching draft message:', error);
      setDraftMessage(`Hi ${customer.name}, just checking in!`);
    } finally {
      setLoadingDraft(false);
    }
  };

  const fetchRecentMessages = async (customerId: string) => {
    setLoadingMessages(true);
    try {
      const response = await apiClient.get(`/customers/${customerId}/messages`);
      setRecentMessages(response.data);
    } catch (error) {
      console.error('Error fetching recent messages:', error);
    } finally {
      setLoadingMessages(false);
    }
  };

  const handleRegenerateWithDirection = () => {
    if (!draftCustomer) return;
    handleShowDraftMessage(draftCustomer, customDirection);
    // Don't clear direction yet so user can see what they typed
  };

  const handleSendDraftMessage = () => {
    if (!draftCustomer) return;

    setShowDraftModal(false);
    handleSendMessage(draftCustomer.id, draftCustomer.phone_number, draftCustomer.name, draftMessage);

    // Reset
    setDraftCustomer(null);
    setDraftMessage('');
  };

  const filteredCustomerList = customers.filter(c =>
    c.name.toLowerCase().includes(customerSearch.toLowerCase()) ||
    c.phone_number.includes(customerSearch)
  );

  const renderFollowup = (item: FollowUp) => {
    const category = getDateCategory(item.reminder_date);
    const isOverdue = category === 'overdue';

    const typeIcons = {
      call: 'call',
      whatsapp: 'logo-whatsapp',
      meeting: 'people',
      email: 'mail',
    };

    const typeColors = {
      call: '#4A90D9',
      whatsapp: '#25D366',
      meeting: '#FFD700',
      email: '#FF6B6B',
    };

    return (
      <View key={item.id} style={[styles.followupCard, isOverdue && styles.followupCardOverdue]}>
        <View style={styles.followupTop}>
          <Ionicons
            name={typeIcons[item.type] as any || 'notifications'}
            size={16}
            color={isOverdue ? '#FF4444' : (typeColors[item.type] || '#25D366')}
          />
          <View style={styles.followupInfo}>
            <Text style={styles.customerName} numberOfLines={1}>{item.customer_name}</Text>
            <Text style={styles.customerPhone}>{item.customer_phone}</Text>
          </View>
          <View style={styles.followupDateBadge}>
            <Text style={[styles.dateText, isOverdue && styles.dateTextOverdue]}>
              {isOverdue ? 'Overdue · ' : ''}
              {new Date(item.reminder_date).toLocaleDateString('en-KE', {
                month: 'short',
                day: 'numeric',
              })}
              {' · '}
              {new Date(item.reminder_date).toLocaleTimeString('en-KE', {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </Text>
          </View>
        </View>
        {item.message && (
          <Text style={styles.message} numberOfLines={1}>{item.message}</Text>
        )}
        <View style={styles.actions}>
          <TouchableOpacity
            style={styles.actionBtn}
            onPress={() => handleSendMessage(item.customer_id, item.customer_phone, item.customer_name, item.message)}
          >
            <Ionicons name="logo-whatsapp" size={16} color="#25D366" />
            <Text style={[styles.actionBtnText, { color: '#25D366' }]}>Message</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.actionBtn}
            onPress={() => Alert.alert(
              'Snooze',
              'Remind me again in...',
              [
                { text: '1 day', onPress: () => handleSnooze(item, 1) },
                { text: '3 days', onPress: () => handleSnooze(item, 3) },
                { text: '1 week', onPress: () => handleSnooze(item, 7) },
                { text: 'Cancel', style: 'cancel' },
              ]
            )}
            disabled={snoozingId === item.id}
          >
            {snoozingId === item.id
              ? <ActivityIndicator size="small" color="#F59E0B" />
              : <Ionicons name="alarm-outline" size={16} color="#F59E0B" />}
            <Text style={[styles.actionBtnText, { color: '#F59E0B' }]}>Snooze</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.actionBtn}
            onPress={() => handleComplete(item)}
          >
            <Ionicons name="checkmark-circle-outline" size={16} color="#25D366" />
            <Text style={[styles.actionBtnText, { color: '#25D366' }]}>Done</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.actionBtn}
            onPress={() => openEditModal(item)}
          >
            <Ionicons name="create-outline" size={16} color="#4A90D9" />
            <Text style={[styles.actionBtnText, { color: '#4A90D9' }]}>Edit</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.actionBtn}
            onPress={() => handleDelete(item)}
          >
            <Ionicons name="trash-outline" size={16} color="#FF4444" />
            <Text style={[styles.actionBtnText, { color: '#FF4444' }]}>Delete</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  const renderSection = (title: string, data: FollowUp[], color: string) => {
    if (data.length === 0) return null;

    return (
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <View style={[styles.sectionDot, { backgroundColor: color }]} />
          <Text style={styles.sectionTitle}>{title}</Text>
          <Text style={styles.sectionCount}>{data.length}</Text>
        </View>
        {data.map(item => renderFollowup(item))}
      </View>
    );
  };

  const renderColdCustomer = (customer: ColdCustomer) => (
    <View key={customer.id} style={styles.coldCustomerCard}>
      <View style={styles.coldCustomerHeader}>
        <View style={styles.coldAvatar}>
          <Text style={styles.coldAvatarText}>{customer.name.charAt(0)}</Text>
        </View>
        <View style={styles.coldCustomerDetails}>
          <Text style={styles.coldCustomerName} numberOfLines={1}>{customer.name}</Text>
          <Text style={styles.coldCustomerPhone}>{customer.phone_number}</Text>
        </View>
        <View style={styles.coldMetaRight}>
          <Ionicons name="time-outline" size={12} color="#FF6B6B" />
          <Text style={styles.coldDaysText}>
            {customer.days_since_contact !== null
              ? `${customer.days_since_contact}d ago`
              : 'Never'}
          </Text>
        </View>
      </View>

      {/* AI-Generated Reason */}
      <View style={styles.aiReasonContainer}>
        <Ionicons name="bulb" size={12} color="#FFD700" />
        <Text style={styles.aiReasonText} numberOfLines={1}>
          {customer.ai_reason || (customer.days_since_contact !== null
            ? `No contact in ${customer.days_since_contact} days`
            : 'New customer - never contacted')}
        </Text>
        {customer.has_pending_followup && (
          <View style={styles.hasFollowupBadge}>
            <Text style={styles.hasFollowupText}>Reminder</Text>
          </View>
        )}
      </View>

      {/* Action Bar */}
      <View style={styles.coldActions}>
        <TouchableOpacity
          style={styles.coldActionBtn}
          onPress={() => handleSendMessage(customer.id, customer.phone_number, customer.name)}
        >
          <Ionicons name="logo-whatsapp" size={16} color="#25D366" />
          <Text style={[styles.coldActionText, { color: '#25D366' }]}>Message</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.coldActionBtn}
          onPress={() => handleShowDraftMessage(customer)}
        >
          <Ionicons name="sparkles" size={16} color="#FFD700" />
          <Text style={[styles.coldActionText, { color: '#FFD700' }]}>AI Draft</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.coldActionBtn}
          onPress={() => handleCreateFollowupFromCold(customer)}
        >
          <Ionicons name="alarm-outline" size={16} color="#4A90D9" />
          <Text style={[styles.coldActionText, { color: '#4A90D9' }]}>Remind</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.coldActionBtn}
          onPress={() => {
            setColdDoneCustomer(customer);
            setColdSelectedOutcome('');
            setColdOutcomeNote('');
            setColdDoneModalVisible(true);
          }}
        >
          <Ionicons name="checkmark-circle" size={16} color="#A8FF78" />
          <Text style={[styles.coldActionText, { color: '#A8FF78' }]}>Done</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const filters: { key: FilterType; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'overdue', label: '🔴 Overdue' },
    { key: 'today', label: '📅 Today' },
    { key: 'tomorrow', label: '🌅 Tomorrow' },
    { key: 'this_week', label: '📆 This Week' },
    { key: 'later', label: '🗓 Later' },
  ];

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
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Follow-ups</Text>
        <Text style={styles.headerSubtitle}>Never miss a sale</Text>
      </View>

      {/* Stats Cards */}
      {suggestions && (
        <View style={styles.statsRow}>
          <View style={[styles.statCard, styles.statCardWarning]}>
            <Text style={styles.statNumber}>{suggestions.neglected_week}</Text>
            <Text style={styles.statLabel}>7+ days no contact</Text>
          </View>
          <View style={[styles.statCard, styles.statCardDanger]}>
            <Text style={styles.statNumber}>{suggestions.neglected_month}</Text>
            <Text style={styles.statLabel}>30+ days no contact</Text>
          </View>
          {suggestions.vip_neglected > 0 && (
            <View style={[styles.statCard, { borderLeftColor: '#FFD700', borderLeftWidth: 3 }]}>
              <Text style={[styles.statNumber, { color: '#FFD700' }]}>{suggestions.vip_neglected}</Text>
              <Text style={styles.statLabel}>VIP neglected</Text>
            </View>
          )}
        </View>
      )}

      {/* Tab Switcher */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'needs_attention' && styles.tabActive]}
          onPress={() => setActiveTab('needs_attention')}
        >
          <Ionicons name="alert-circle" size={18} color={activeTab === 'needs_attention' ? '#FFFFFF' : '#666'} />
          <Text style={[styles.tabText, activeTab === 'needs_attention' && styles.tabTextActive]}>
            Attention
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'reminders' && styles.tabActive]}
          onPress={() => setActiveTab('reminders')}
        >
          <Ionicons name="notifications" size={18} color={activeTab === 'reminders' ? '#FFFFFF' : '#666'} />
          <Text style={[styles.tabText, activeTab === 'reminders' && styles.tabTextActive]}>
            Reminders ({followups.length})
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'analytics' && styles.tabActive]}
          onPress={() => setActiveTab('analytics')}
        >
          <Ionicons name="bar-chart" size={18} color={activeTab === 'analytics' ? '#FFFFFF' : '#666'} />
          <Text style={[styles.tabText, activeTab === 'analytics' && styles.tabTextActive]}>
            Results
          </Text>
        </TouchableOpacity>
      </View>

      {/* Filter Chips - Only show for Reminders tab */}
      {activeTab === 'reminders' && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.filterContainer}
          contentContainerStyle={styles.filterContent}
        >
          {filters.map(f => (
            <TouchableOpacity
              key={f.key}
              style={[styles.filterChip, filter === f.key && styles.filterChipActive]}
              onPress={() => setFilter(f.key)}
            >
              <Text style={[styles.filterText, filter === f.key && styles.filterTextActive]}>
                {f.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}

      {/* Analytics Tab */}
      {activeTab === 'analytics' && (
        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
          {/* Period picker */}
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20 }}>
            {[7, 30, 90].map(d => (
              <TouchableOpacity
                key={d}
                style={{
                  flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center',
                  backgroundColor: analyticsPeriod === d ? '#25D366' : '#1A2942',
                }}
                onPress={() => setAnalyticsPeriod(d)}
              >
                <Text style={{ color: analyticsPeriod === d ? '#FFF' : '#888', fontWeight: '600', fontSize: 13 }}>
                  {d === 7 ? '7 days' : d === 30 ? '30 days' : '90 days'}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {loadingAnalytics ? (
            <View style={{ alignItems: 'center', paddingTop: 40 }}>
              <ActivityIndicator size="large" color="#25D366" />
              <Text style={{ color: '#666', marginTop: 12 }}>Calculating results...</Text>
            </View>
          ) : !analytics ? (
            <View style={{ alignItems: 'center', paddingTop: 40 }}>
              <Ionicons name="bar-chart-outline" size={48} color="#333" />
              <Text style={{ color: '#666', marginTop: 12, textAlign: 'center' }}>
                No data yet. Complete some follow-ups to see results.
              </Text>
            </View>
          ) : (
            <>
              {/* Summary strip */}
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
                <View style={{ flex: 1, backgroundColor: '#1A2942', borderRadius: 12, padding: 14, alignItems: 'center' }}>
                  <Text style={{ color: '#25D366', fontSize: 22, fontWeight: '800' }}>{analytics.stats.total_all ?? analytics.stats.total_followups}</Text>
                  <Text style={{ color: '#888', fontSize: 11, marginTop: 2 }}>Total Done</Text>
                </View>
                <View style={{ flex: 1, backgroundColor: '#1A2942', borderRadius: 12, padding: 14, alignItems: 'center' }}>
                  <Text style={{ color: '#FFD700', fontSize: 22, fontWeight: '800' }}>{Math.round(analytics.stats.response_rate)}%</Text>
                  <Text style={{ color: '#888', fontSize: 11, marginTop: 2 }}>Response Rate</Text>
                </View>
                <View style={{ flex: 1, backgroundColor: '#1A2942', borderRadius: 12, padding: 14, alignItems: 'center' }}>
                  <Text style={{ color: '#4A90D9', fontSize: 22, fontWeight: '800' }}>{Math.round(analytics.stats.conversion_rate)}%</Text>
                  <Text style={{ color: '#888', fontSize: 11, marginTop: 2 }}>Converted</Text>
                </View>
              </View>
              {/* Breakdown: reminders vs needs-attention */}
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20 }}>
                <View style={{ flex: 1, backgroundColor: '#0F1E33', borderRadius: 10, padding: 10, alignItems: 'center' }}>
                  <Text style={{ color: '#4A90D9', fontSize: 16, fontWeight: '700' }}>{analytics.stats.total_followups}</Text>
                  <Text style={{ color: '#555', fontSize: 10, marginTop: 2 }}>Reminders</Text>
                </View>
                <View style={{ flex: 1, backgroundColor: '#0F1E33', borderRadius: 10, padding: 10, alignItems: 'center' }}>
                  <Text style={{ color: '#A8FF78', fontSize: 16, fontWeight: '700' }}>{analytics.stats.needs_attention_contacted ?? 0}</Text>
                  <Text style={{ color: '#555', fontSize: 10, marginTop: 2 }}>Needs Attention</Text>
                </View>
              </View>

              {/* Manual outcome breakdown (from Done button) */}
              {analytics.outcome_counts && Object.values(analytics.outcome_counts).some(v => v > 0) && (
                <View style={{ backgroundColor: '#1A2942', borderRadius: 14, padding: 16, marginBottom: 16 }}>
                  <Text style={{ color: '#FFF', fontSize: 15, fontWeight: '700', marginBottom: 14 }}>What happened?</Text>
                  {[
                    { id: 'called',          label: 'Called — answered',        icon: 'call',                color: '#25D366' },
                    { id: 'replied',         label: 'Replied on WhatsApp',       icon: 'logo-whatsapp',       color: '#25D366' },
                    { id: 'converted',       label: 'Made a sale',               icon: 'trophy',              color: '#FFD700' },
                    { id: 'no_answer',       label: 'No answer / no reply',      icon: 'phone-portrait',      color: '#FF6B6B' },
                    { id: 'rescheduled',     label: 'Rescheduled',               icon: 'calendar',            color: '#4A90D9' },
                    { id: 'not_interested',  label: 'Not interested',            icon: 'close-circle',        color: '#666' },
                  ].map(o => {
                    const count = analytics.outcome_counts?.[o.id] || 0;
                    if (count === 0) return null;
                    const total = Object.values(analytics.outcome_counts || {}).reduce((a, b) => a + b, 0);
                    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                    return (
                      <View key={o.id} style={{ marginBottom: 12 }}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                            <Ionicons name={o.icon as any} size={15} color={o.color} />
                            <Text style={{ color: '#CCD6E0', fontSize: 13 }}>{o.label}</Text>
                          </View>
                          <Text style={{ color: o.color, fontWeight: '700', fontSize: 13 }}>{count}  <Text style={{ color: '#555', fontWeight: '400' }}>({pct}%)</Text></Text>
                        </View>
                        <View style={{ height: 5, backgroundColor: '#0A1628', borderRadius: 3 }}>
                          <View style={{ height: 5, width: `${pct}%`, backgroundColor: o.color, borderRadius: 3 }} />
                        </View>
                      </View>
                    );
                  })}
                </View>
              )}

              {/* Auto-detected outcomes (from message analysis) */}
              {(analytics.stats.converted + analytics.stats.responded + analytics.stats.no_response + analytics.stats.not_contacted) > 0 && (
                <View style={{ backgroundColor: '#1A2942', borderRadius: 14, padding: 16, marginBottom: 16 }}>
                  <Text style={{ color: '#FFF', fontSize: 15, fontWeight: '700', marginBottom: 4 }}>Auto-detected Activity</Text>
                  <Text style={{ color: '#555', fontSize: 11, marginBottom: 14 }}>Based on messages sent/received after each follow-up</Text>
                  {[
                    { key: 'converted',     label: 'Led to a sale',     color: '#FFD700', val: analytics.stats.converted },
                    { key: 'responded',     label: 'Customer replied',   color: '#25D366', val: analytics.stats.responded },
                    { key: 'no_response',   label: 'No reply',           color: '#FF6B6B', val: analytics.stats.no_response },
                    { key: 'not_contacted', label: 'Never messaged',     color: '#444',    val: analytics.stats.not_contacted },
                  ].map(row => (
                    <View key={row.key} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#0A1628' }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: row.color }} />
                        <Text style={{ color: '#CCD6E0', fontSize: 13 }}>{row.label}</Text>
                      </View>
                      <Text style={{ color: row.color, fontSize: 15, fontWeight: '700' }}>{row.val}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Revenue */}
              {analytics.stats.total_revenue > 0 && (
                <View style={{ backgroundColor: '#1A2942', borderRadius: 14, padding: 16, marginBottom: 16, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <View>
                    <Text style={{ color: '#888', fontSize: 12 }}>Revenue from follow-ups</Text>
                    <Text style={{ color: '#FFD700', fontSize: 22, fontWeight: '800', marginTop: 2 }}>
                      {analytics.stats.total_revenue.toLocaleString()}
                    </Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: '#888', fontSize: 12 }}>Per follow-up</Text>
                    <Text style={{ color: '#25D366', fontSize: 16, fontWeight: '700', marginTop: 2 }}>
                      {Math.round(analytics.stats.revenue_per_followup).toLocaleString()}
                    </Text>
                  </View>
                </View>
              )}

              {/* Avg response time */}
              {analytics.stats.avg_response_time_hours > 0 && (
                <View style={{ backgroundColor: '#1A2942', borderRadius: 14, padding: 16, marginBottom: 16 }}>
                  <Text style={{ color: '#888', fontSize: 12, marginBottom: 4 }}>Avg. time for customer to reply</Text>
                  <Text style={{ color: '#4A90D9', fontSize: 20, fontWeight: '700' }}>
                    {analytics.stats.avg_response_time_hours < 1
                      ? `${Math.round(analytics.stats.avg_response_time_hours * 60)} min`
                      : `${Math.round(analytics.stats.avg_response_time_hours)} hrs`}
                  </Text>
                </View>
              )}

              {/* Best time to follow up */}
              {analytics.best_times.sample_size > 0 && (
                <View style={{ backgroundColor: '#1A2942', borderRadius: 14, padding: 16, marginBottom: 16 }}>
                  <Text style={{ color: '#FFF', fontSize: 15, fontWeight: '700', marginBottom: 12 }}>Best time to follow up</Text>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-around' }}>
                    <View style={{ alignItems: 'center' }}>
                      <Ionicons name="calendar-outline" size={24} color="#25D366" />
                      <Text style={{ color: '#25D366', fontSize: 16, fontWeight: '700', marginTop: 6 }}>{analytics.best_times.best_day}</Text>
                      <Text style={{ color: '#555', fontSize: 11 }}>Best day</Text>
                    </View>
                    <View style={{ alignItems: 'center' }}>
                      <Ionicons name="time-outline" size={24} color="#FFD700" />
                      <Text style={{ color: '#FFD700', fontSize: 16, fontWeight: '700', marginTop: 6 }}>
                        {analytics.best_times.best_hour < 12
                          ? `${analytics.best_times.best_hour || 12}am`
                          : analytics.best_times.best_hour === 12
                            ? '12pm'
                            : `${analytics.best_times.best_hour - 12}pm`}
                      </Text>
                      <Text style={{ color: '#555', fontSize: 11 }}>Best hour</Text>
                    </View>
                    <View style={{ alignItems: 'center' }}>
                      <Ionicons name="checkmark-circle-outline" size={24} color="#4A90D9" />
                      <Text style={{ color: '#4A90D9', fontSize: 16, fontWeight: '700', marginTop: 6 }}>{analytics.best_times.sample_size}</Text>
                      <Text style={{ color: '#555', fontSize: 11 }}>Sample size</Text>
                    </View>
                  </View>
                </View>
              )}
            </>
          )}
        </ScrollView>
      )}

      {activeTab === 'analytics' ? null : activeTab === 'needs_attention' ? (
        <>
          {isAnalyzing && coldCustomers.length === 0 && (
            <View style={{ padding: 20, alignItems: 'center', backgroundColor: '#1A2942', margin: 16, borderRadius: 12 }}>
              <ActivityIndicator color="#25D366" style={{ marginBottom: 12 }} />
              <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600' }}>AI is analyzing your customers...</Text>
              <Text style={{ color: '#666', fontSize: 13, marginTop: 4, textAlign: 'center' }}>
                Identifying follow-up opportunities based on your recent conversations.
              </Text>
            </View>
          )}
          <FlatList
            data={coldCustomers}
            renderItem={({ item }) => renderColdCustomer(item)}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.listContent}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
            }
            ListEmptyComponent={
              !isAnalyzing ? (
                <View style={styles.emptyContainer}>
                  {customers.length === 0 ? (
                    <>
                      <Ionicons name="people-outline" size={64} color="#25D366" />
                      <Text style={styles.emptyText}>Add customers to get started</Text>
                      <Text style={styles.emptySubtext}>AI will analyze your conversations and suggest follow-ups</Text>
                    </>
                  ) : (
                    <>
                      <Ionicons name="checkmark-circle-outline" size={64} color="#25D366" />
                      <Text style={styles.emptyText}>All caught up!</Text>
                      <Text style={styles.emptySubtext}>No customers need immediate attention</Text>
                    </>
                  )}
                </View>
              ) : null
            }
          />
        </>
      ) : (
        <FlatList
          data={[1]}
          renderItem={() => (
            <>
              {filter === 'all' ? (
                <>
                  {renderSection('Overdue', groupedFollowups.overdue, '#FF4444')}
                  {renderSection('Today', groupedFollowups.today, '#25D366')}
                  {renderSection('Tomorrow', groupedFollowups.tomorrow, '#4A90D9')}
                  {renderSection('This Week', groupedFollowups.this_week, '#FFD700')}
                  {renderSection('Later', groupedFollowups.later, '#666')}
                </>
              ) : (
                filteredFollowups.map(item => renderFollowup(item))
              )}
            </>
          )}
          keyExtractor={() => 'sections'}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
          }
          ListEmptyComponent={
            filteredFollowups.length === 0 ? (
              <View style={styles.emptyContainer}>
                <Ionicons name="notifications-off-outline" size={64} color="#666" />
                <Text style={styles.emptyText}>No reminders</Text>
                <Text style={styles.emptySubtext}>
                  {filter === 'all'
                    ? 'Tap + to create a follow-up reminder'
                    : `No reminders for ${filter.replace('_', ' ')}`}
                </Text>
              </View>
            ) : null
          }
        />
      )}

      {/* Floating Add Button */}
      <TouchableOpacity
        style={styles.addButton}
        onPress={() => setShowAddModal(true)}
      >
        <Ionicons name="add" size={22} color="#FFFFFF" />
      </TouchableOpacity>


      {/* Add Reminder Modal */}
      <Modal
        visible={showAddModal}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowAddModal(false)}
      >
        <View style={styles.modalOverlay}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.keyboardView}
          >
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <Text style={styles.modalTitle}>{isEditing ? 'Edit Reminder' : 'Add Reminder'}</Text>
                <TouchableOpacity onPress={() => {
                  setShowAddModal(false);
                  setIsEditing(false);
                  setEditingFollowup(null);
                }}>
                  <Ionicons name="close" size={28} color="#FFFFFF" />
                </TouchableOpacity>
              </View>

              <ScrollView
                showsVerticalScrollIndicator={false}
                contentContainerStyle={styles.modalScrollContent}
              >
                {/* Customer Selection */}
                <Text style={styles.inputLabel}>Customer</Text>
                {selectedCustomer ? (
                  <TouchableOpacity
                    style={styles.selectedCustomer}
                    onPress={() => {
                      setSelectedCustomer(null);
                      setShowCustomerList(true);
                    }}
                  >
                    <View style={styles.selectedCustomerInfo}>
                      <View style={styles.selectedAvatar}>
                        <Text style={styles.selectedAvatarText}>{selectedCustomer.name.charAt(0)}</Text>
                      </View>
                      <View>
                        <Text style={styles.selectedName}>{selectedCustomer.name}</Text>
                        <Text style={styles.selectedPhone}>{selectedCustomer.phone_number}</Text>
                      </View>
                    </View>
                    <Ionicons name="chevron-down" size={20} color="#666" />
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity
                    style={styles.customerSelectButton}
                    onPress={() => setShowCustomerList(true)}
                  >
                    <Ionicons name="person-add-outline" size={20} color="#666" />
                    <Text style={styles.customerSelectText}>Select Customer</Text>
                  </TouchableOpacity>
                )}

                {/* Customer Search List */}
                {showCustomerList && (
                  <View style={styles.customerListContainer}>
                    <TextInput
                      style={styles.searchInput}
                      placeholder="Search customers..."
                      placeholderTextColor="#666"
                      value={customerSearch}
                      onChangeText={setCustomerSearch}
                      autoFocus
                    />
                    <ScrollView style={styles.customerList} nestedScrollEnabled={true}>
                      {filteredCustomerList.slice(0, 10).map(c => (
                        <TouchableOpacity
                          key={c.id}
                          style={styles.customerListItem}
                          onPress={() => {
                            setSelectedCustomer(c);
                            setShowCustomerList(false);
                            setCustomerSearch('');
                          }}
                        >
                          <View style={styles.customerListAvatar}>
                            <Text style={styles.customerListAvatarText}>{c.name.charAt(0)}</Text>
                          </View>
                          <View>
                            <Text style={styles.customerListName}>{c.name}</Text>
                            <Text style={styles.customerListPhone}>{c.phone_number}</Text>
                          </View>
                        </TouchableOpacity>
                      ))}
                    </ScrollView>
                    <TouchableOpacity
                      style={styles.closeListButton}
                      onPress={() => setShowCustomerList(false)}
                    >
                      <Text style={styles.closeListText}>Cancel</Text>
                    </TouchableOpacity>
                  </View>
                )}

                {/* Type Selection */}
                <Text style={styles.inputLabel}>Action Type</Text>
                <View style={styles.typeContainer}>
                  {[
                    { id: 'call', icon: 'call', label: 'Call', color: '#4A90D9' },
                    { id: 'whatsapp', icon: 'logo-whatsapp', label: 'WhatsApp', color: '#25D366' },
                    { id: 'meeting', icon: 'people', label: 'Meeting', color: '#FFD700' },
                    { id: 'email', icon: 'mail', label: 'Email', color: '#FF6B6B' },
                  ].map((type) => (
                    <TouchableOpacity
                      key={type.id}
                      style={[
                        styles.typeButton,
                        selectedType === type.id && { backgroundColor: type.color + '20', borderColor: type.color }
                      ]}
                      onPress={() => setSelectedType(type.id as any)}
                    >
                      <Ionicons
                        name={type.icon as any}
                        size={20}
                        color={selectedType === type.id ? type.color : '#666'}
                      />
                      <Text style={[
                        styles.typeText,
                        selectedType === type.id && { color: type.color, fontWeight: 'bold' }
                      ]}>
                        {type.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* Date & Time Selection */}
                <Text style={styles.inputLabel}>When?</Text>
                <View style={styles.dateTimeRow}>
                  <TouchableOpacity
                    style={styles.dateTimeButton}
                    onPress={() => setShowDatePicker(true)}
                  >
                    <Ionicons name="calendar-outline" size={20} color="#25D366" />
                    <Text style={styles.dateTimeText}>
                      {reminderDate.toLocaleDateString('en-KE', {
                        weekday: 'short',
                        day: 'numeric',
                        month: 'short',
                      })}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={styles.dateTimeButton}
                    onPress={() => setShowTimePicker(true)}
                  >
                    <Ionicons name="time-outline" size={20} color="#4A90D9" />
                    <Text style={styles.dateTimeText}>
                      {reminderDate.toLocaleTimeString('en-KE', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </Text>
                  </TouchableOpacity>
                </View>

                {showDatePicker && (
                  <DateTimePicker
                    value={reminderDate}
                    mode="date"
                    display={Platform.OS === 'ios' ? 'spinner' : 'default'}
                    onChange={(event, date) => {
                      setShowDatePicker(Platform.OS === 'ios');
                      if (date) {
                        const newDate = new Date(reminderDate);
                        newDate.setFullYear(date.getFullYear(), date.getMonth(), date.getDate());
                        setReminderDate(newDate);
                      }
                    }}
                    minimumDate={new Date()}
                    themeVariant="dark"
                  />
                )}

                {showTimePicker && (
                  <DateTimePicker
                    value={reminderDate}
                    mode="time"
                    display={Platform.OS === 'ios' ? 'spinner' : 'default'}
                    onChange={(event, date) => {
                      setShowTimePicker(Platform.OS === 'ios');
                      if (date) {
                        const newDate = new Date(reminderDate);
                        newDate.setHours(date.getHours(), date.getMinutes());
                        setReminderDate(newDate);
                      }
                    }}
                    themeVariant="dark"
                  />
                )}

                {/* Note with AI draft */}
                <Text style={styles.inputLabel}>Note (Optional)</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <TextInput
                    style={[styles.messageInput, { flex: 1, marginBottom: 0, minHeight: 40 }]}
                    placeholder="Tell AI what to write..."
                    placeholderTextColor="#555"
                    value={noteAIDirection}
                    onChangeText={setNoteAIDirection}
                  />
                  <TouchableOpacity
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#1A2942', paddingHorizontal: 10, paddingVertical: 10, borderRadius: 8 }}
                    disabled={generatingNoteAI}
                    onPress={async () => {
                      if (!selectedCustomer) { Alert.alert('Select a customer first'); return; }
                      setGeneratingNoteAI(true);
                      try {
                        const res = await apiClient.post('/ai/generate-broadcast-message', {
                          prompt: noteAIDirection.trim()
                            ? `Write a short internal follow-up note for ${selectedCustomer.name}. Direction: ${noteAIDirection}. 1 sentence max.`
                            : `Write a short internal follow-up note for ${selectedCustomer.name} (type: ${selectedType}). 1 sentence, actionable.`,
                        });
                        setReminderMessage(res.data.message);
                        setNoteAIDirection('');
                      } catch (e: any) {
                        Alert.alert('Error', 'Failed to generate note');
                      } finally {
                        setGeneratingNoteAI(false);
                      }
                    }}
                  >
                    {generatingNoteAI
                      ? <ActivityIndicator size="small" color="#FFD700" />
                      : <Ionicons name="sparkles" size={14} color="#FFD700" />}
                    <Text style={{ color: '#FFD700', fontSize: 12, fontWeight: '600' }}>
                      {generatingNoteAI ? '...' : 'Draft'}
                    </Text>
                  </TouchableOpacity>
                </View>
                <TextInput
                  style={styles.messageInput}
                  placeholder="What should you follow up about?"
                  placeholderTextColor="#666"
                  value={reminderMessage}
                  onChangeText={setReminderMessage}
                  multiline
                  numberOfLines={3}
                />

                {/* Quick Date Buttons */}
                <View style={styles.quickDates}>
                  <TouchableOpacity
                    style={styles.quickDateButton}
                    onPress={() => setReminderDate(new Date())}
                  >
                    <Text style={styles.quickDateText}>Today</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.quickDateButton}
                    onPress={() => {
                      const tomorrow = new Date();
                      tomorrow.setDate(tomorrow.getDate() + 1);
                      setReminderDate(tomorrow);
                    }}
                  >
                    <Text style={styles.quickDateText}>Tomorrow</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.quickDateButton}
                    onPress={() => {
                      const nextWeek = new Date();
                      nextWeek.setDate(nextWeek.getDate() + 7);
                      setReminderDate(nextWeek);
                    }}
                  >
                    <Text style={styles.quickDateText}>Next Week</Text>
                  </TouchableOpacity>
                </View>

                {/* Save Button */}
                <TouchableOpacity
                  style={[styles.saveButton, (!selectedCustomer || saving) && styles.saveButtonDisabled]}
                  onPress={handleAddReminder}
                  disabled={!selectedCustomer || saving}
                >
                  {saving ? (
                    <ActivityIndicator color="#FFFFFF" />
                  ) : (
                    <>
                      <Ionicons name={isEditing ? "save" : "alarm"} size={20} color="#FFFFFF" />
                      <Text style={styles.saveButtonText}>{isEditing ? 'Update Reminder' : 'Set Reminder'}</Text>
                    </>
                  )}
                </TouchableOpacity>
              </ScrollView>
            </View>
          </KeyboardAvoidingView>
        </View>
      </Modal>

      {/* Outcome Modal */}
      <Modal
        visible={outcomeModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setOutcomeModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={[styles.modalContent, { maxHeight: '70%' }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>What happened?</Text>
              <TouchableOpacity onPress={() => setOutcomeModalVisible(false)}>
                <Ionicons name="close" size={24} color="#666" />
              </TouchableOpacity>
            </View>
            {outcomeFollowup && (
              <Text style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>
                Follow-up with {outcomeFollowup.customer_name}
              </Text>
            )}
            <ScrollView showsVerticalScrollIndicator={false}>
              {[
                { id: 'called', label: '📞 Called — They answered', color: '#25D366' },
                { id: 'replied', label: '💬 Replied on WhatsApp', color: '#25D366' },
                { id: 'converted', label: '🎉 Made a sale!', color: '#FFD700' },
                { id: 'no_answer', label: '📵 No answer / No reply', color: '#FF6B6B' },
                { id: 'rescheduled', label: '📅 Rescheduled for later', color: '#4A90D9' },
                { id: 'not_interested', label: '❌ Not interested', color: '#666' },
              ].map(outcome => (
                <TouchableOpacity
                  key={outcome.id}
                  style={{
                    flexDirection: 'row', alignItems: 'center', padding: 14,
                    backgroundColor: selectedOutcome === outcome.id ? outcome.color + '22' : '#1A2942',
                    borderRadius: 10, marginBottom: 8,
                    borderWidth: selectedOutcome === outcome.id ? 1.5 : 0,
                    borderColor: selectedOutcome === outcome.id ? outcome.color : 'transparent',
                  }}
                  onPress={() => setSelectedOutcome(outcome.id)}
                >
                  <Text style={{ color: selectedOutcome === outcome.id ? outcome.color : '#CCD6E0', fontSize: 15, fontWeight: selectedOutcome === outcome.id ? '700' : '400' }}>
                    {outcome.label}
                  </Text>
                </TouchableOpacity>
              ))}
              <TextInput
                style={[styles.messageInput, { marginTop: 8 }]}
                placeholder="Add a note (optional)..."
                placeholderTextColor="#555"
                value={outcomeNote}
                onChangeText={setOutcomeNote}
                multiline
              />
              <TouchableOpacity
                style={[styles.saveButton, (!selectedOutcome || savingOutcome) && styles.saveButtonDisabled, { marginTop: 8 }]}
                onPress={handleSaveOutcome}
                disabled={!selectedOutcome || savingOutcome}
              >
                {savingOutcome
                  ? <ActivityIndicator color="#FFF" />
                  : <Text style={styles.saveButtonText}>Save & Close</Text>}
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Cold Customer Done Modal */}
      <Modal
        visible={coldDoneModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setColdDoneModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={[styles.modalContent, { maxHeight: '70%' }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>What happened?</Text>
              <TouchableOpacity onPress={() => setColdDoneModalVisible(false)}>
                <Ionicons name="close" size={24} color="#666" />
              </TouchableOpacity>
            </View>
            {coldDoneCustomer && (
              <Text style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>
                Follow-up with {coldDoneCustomer.name}
              </Text>
            )}
            <ScrollView showsVerticalScrollIndicator={false}>
              {[
                { id: 'called',         label: '📞 Called — They answered',  color: '#25D366' },
                { id: 'replied',        label: '💬 Replied on WhatsApp',      color: '#25D366' },
                { id: 'converted',      label: '🎉 Made a sale!',             color: '#FFD700' },
                { id: 'no_answer',      label: '📵 No answer / No reply',     color: '#FF6B6B' },
                { id: 'rescheduled',    label: '📅 Rescheduled for later',    color: '#4A90D9' },
                { id: 'not_interested', label: '❌ Not interested',           color: '#666' },
              ].map(o => (
                <TouchableOpacity
                  key={o.id}
                  style={{
                    flexDirection: 'row', alignItems: 'center', padding: 14,
                    backgroundColor: coldSelectedOutcome === o.id ? o.color + '22' : '#1A2942',
                    borderRadius: 10, marginBottom: 8,
                    borderWidth: coldSelectedOutcome === o.id ? 1.5 : 0,
                    borderColor: coldSelectedOutcome === o.id ? o.color : 'transparent',
                  }}
                  onPress={() => setColdSelectedOutcome(o.id)}
                >
                  <Text style={{ color: coldSelectedOutcome === o.id ? o.color : '#CCD6E0', fontSize: 15, fontWeight: coldSelectedOutcome === o.id ? '700' : '400' }}>
                    {o.label}
                  </Text>
                </TouchableOpacity>
              ))}
              <TextInput
                style={[styles.messageInput, { marginTop: 8 }]}
                placeholder="Add a note (optional)..."
                placeholderTextColor="#555"
                value={coldOutcomeNote}
                onChangeText={setColdOutcomeNote}
                multiline
              />
              <TouchableOpacity
                style={[styles.saveButton, (!coldSelectedOutcome || savingColdOutcome) && styles.saveButtonDisabled, { marginTop: 8 }]}
                onPress={handleColdDone}
                disabled={!coldSelectedOutcome || savingColdOutcome}
              >
                {savingColdOutcome
                  ? <ActivityIndicator color="#FFF" />
                  : <Text style={styles.saveButtonText}>Save & Close</Text>}
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* AI Draft Message Modal */}
      <Modal
        visible={showDraftModal}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowDraftModal(false)}
      >
        <View style={styles.modalOverlay}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.keyboardView}
            keyboardVerticalOffset={Platform.OS === 'ios' ? 40 : 0}
          >
            <View style={styles.modalContent}>
              <View style={styles.modalHeader}>
                <View style={styles.aiModalTitleRow}>
                  <Ionicons name="sparkles" size={20} color="#FFD700" />
                  <Text style={styles.modalTitle}>AI Draft Message</Text>
                </View>
                <TouchableOpacity onPress={() => setShowDraftModal(false)}>
                  <Ionicons name="close" size={24} color="#666" />
                </TouchableOpacity>
              </View>

              {loadingDraft ? (
                <View style={styles.draftLoadingContainer}>
                  <ActivityIndicator size="large" color="#4A90D9" />
                  <Text style={styles.draftLoadingText}>Writing perfect message...</Text>
                </View>
              ) : (
                <ScrollView
                  keyboardShouldPersistTaps="handled"
                  showsVerticalScrollIndicator={false}
                  contentContainerStyle={{ paddingBottom: 20 }}
                >
                  <Text style={styles.inputLabel}>Message Preview (tap to edit)</Text>
                  <TextInput
                    style={[styles.messageInput, { minHeight: 120 }]}
                    placeholder="Message..."
                    placeholderTextColor="#666"
                    value={draftMessage}
                    onChangeText={setDraftMessage}
                    multiline
                  />

                  <View style={styles.aiReasonBox}>
                    <Text style={styles.aiReasonLabel}>Why this message?</Text>
                    <Text style={styles.aiReasonTextSmall}>
                      {draftReason}
                    </Text>
                  </View>

                  {/* Recent Messages Section */}
                  <View style={styles.recentMessagesSection}>
                    <TouchableOpacity
                      style={styles.recentMessagesHeader}
                      onPress={() => setShowRecentMessages(!showRecentMessages)}
                    >
                      <View style={styles.recentMessagesTitleRow}>
                        <Ionicons name="chatbubbles-outline" size={18} color="#4A90D9" />
                        <Text style={styles.inputLabelRecent}>Recent Messages</Text>
                      </View>
                      <Ionicons
                        name={showRecentMessages ? "chevron-up" : "chevron-down"}
                        size={20}
                        color="#666"
                      />
                    </TouchableOpacity>

                    {showRecentMessages && (
                      <View style={styles.messagesList}>
                        {loadingMessages ? (
                          <ActivityIndicator size="small" color="#4A90D9" />
                        ) : recentMessages.length > 0 ? (
                          recentMessages.map((msg) => (
                            <View
                              key={msg.id}
                              style={[
                                styles.messageBubble,
                                msg.direction === 'incoming'
                                  ? styles.incomingBubble
                                  : styles.outgoingBubble,
                              ]}
                            >
                              <Text
                                style={[
                                  styles.messageText,
                                  msg.direction === 'incoming'
                                    ? styles.incomingText
                                    : styles.outgoingText,
                                ]}
                              >
                                {msg.content}
                              </Text>
                              <Text style={styles.messageTime}>
                                {new Date(msg.created_at).toLocaleTimeString([], {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                })}
                              </Text>
                            </View>
                          ))
                        ) : (
                          <Text style={styles.noMessagesText}>No recent messages</Text>
                        )}
                      </View>
                    )}
                  </View>

                  <View style={styles.regenerateSection}>
                    <Text style={styles.inputLabel}>Give AI Direction (Optional):</Text>
                    <TextInput
                      style={styles.directionInput}
                      value={customDirection}
                      onChangeText={setCustomDirection}
                      placeholder="e.g., Make it more casual, mention discount..."
                      placeholderTextColor="#666"
                      multiline
                    />
                    <TouchableOpacity
                      style={styles.regenerateButton}
                      onPress={handleRegenerateWithDirection}
                    >
                      <Ionicons name="refresh" size={20} color="#4A90D9" />
                      <Text style={styles.regenerateButtonText}>
                        {customDirection ? 'Regenerate with Direction' : 'Regenerate'}
                      </Text>
                    </TouchableOpacity>
                  </View>

                  <TouchableOpacity
                    style={styles.whatsappSendButton}
                    onPress={handleSendDraftMessage}
                  >
                    <Ionicons name="logo-whatsapp" size={24} color="#FFFFFF" />
                    <Text style={styles.whatsappSendText}>Open in WhatsApp</Text>
                  </TouchableOpacity>
                </ScrollView>
              )}
            </View>
          </KeyboardAvoidingView>
        </View>
      </Modal>
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
  header: {
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  headerSubtitle: {
    fontSize: 12,
    color: '#25D366',
    marginTop: 2,
  },
  addButton: {
    position: 'absolute',
    right: 16,
    bottom: 20,
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    zIndex: 10,
  },
  statsRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    marginBottom: 10,
    gap: 8,
  },
  statCard: {
    flex: 1,
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 10,
    alignItems: 'center',
  },
  statCardWarning: {
    borderLeftWidth: 3,
    borderLeftColor: '#FFD700',
  },
  statCardDanger: {
    borderLeftWidth: 3,
    borderLeftColor: '#FF4444',
  },
  statNumber: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  statLabel: {
    fontSize: 11,
    color: '#666',
    marginTop: 2,
  },
  tabContainer: {
    flexDirection: 'row',
    marginHorizontal: 16,
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 3,
    marginBottom: 8,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    borderRadius: 8,
    gap: 4,
  },
  tabActive: {
    backgroundColor: '#25D366',
  },
  tabText: {
    fontSize: 11,
    color: '#666',
    fontWeight: '500',
  },
  tabTextActive: {
    color: '#FFFFFF',
  },
  filterContainer: {
    maxHeight: 36,
    marginBottom: 8,
  },
  filterContent: {
    paddingHorizontal: 16,
    gap: 6,
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    backgroundColor: '#1A2942',
    borderRadius: 14,
    marginRight: 6,
  },
  filterChipActive: {
    backgroundColor: '#25D366',
  },
  filterText: {
    color: '#666',
    fontSize: 12,
    fontWeight: '500',
  },
  filterTextActive: {
    color: '#FFFFFF',
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 100,
  },
  section: {
    marginBottom: 16,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  sectionDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
    flex: 1,
  },
  sectionCount: {
    fontSize: 14,
    color: '#666',
    backgroundColor: '#1A2942',
    paddingHorizontal: 10,
    paddingVertical: 2,
    borderRadius: 10,
  },
  followupCard: {
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 10,
    marginBottom: 8,
  },
  followupCardOverdue: {
    borderLeftWidth: 3,
    borderLeftColor: '#FF4444',
  },
  followupTop: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  followupInfo: {
    flex: 1,
    marginLeft: 8,
  },
  followupDateBadge: {
    marginLeft: 8,
  },
  customerName: {
    fontSize: 13,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  customerPhone: {
    fontSize: 11,
    color: '#666',
  },
  message: {
    fontSize: 12,
    color: '#888',
    marginBottom: 6,
    marginLeft: 24,
  },
  dateText: {
    fontSize: 11,
    color: '#666',
  },
  dateTextOverdue: {
    color: '#FF4444',
  },
  actions: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.06)',
    paddingTop: 8,
    marginTop: 4,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 2,
  },
  actionBtnText: {
    fontSize: 11,
    fontWeight: '500',
  },
  emptyContainer: {
    alignItems: 'center',
    paddingTop: 60,
  },
  emptyText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginTop: 16,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#666',
    marginTop: 8,
    textAlign: 'center',
  },
  coldCustomerCard: {
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 10,
    marginBottom: 8,
    borderLeftWidth: 3,
    borderLeftColor: '#FF6B6B',
  },
  coldCustomerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  coldAvatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#FF6B6B',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  coldAvatarText: {
    fontSize: 13,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  coldCustomerDetails: {
    flex: 1,
  },
  coldCustomerName: {
    fontSize: 13,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  coldCustomerPhone: {
    fontSize: 11,
    color: '#666',
  },
  coldMetaRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  aiReasonContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 215, 0, 0.08)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    marginBottom: 8,
  },
  aiReasonText: {
    fontSize: 11,
    color: '#FFD700',
    marginLeft: 5,
    flex: 1,
  },
  coldDaysText: {
    fontSize: 11,
    color: '#FF6B6B',
  },
  hasFollowupBadge: {
    backgroundColor: '#25D366',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    marginLeft: 8,
  },
  hasFollowupText: {
    fontSize: 10,
    color: '#FFFFFF',
    fontWeight: '600',
  },
  coldActions: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.06)',
    paddingTop: 8,
    marginTop: 6,
  },
  coldActionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 2,
  },
  coldActionText: {
    fontSize: 11,
    fontWeight: '500',
  },
  // Modal Styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1A2942',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 20,
    maxHeight: '90%',
  },
  keyboardView: {
    width: '100%',
    justifyContent: 'flex-end' as const,
  },
  modalScrollContent: {
    paddingBottom: 40,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
  },
  modalTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  inputLabel: {
    fontSize: 14,
    color: '#888',
    marginBottom: 8,
    marginTop: 16,
  },
  customerSelectButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0A1628',
    borderRadius: 12,
    padding: 16,
    gap: 12,
  },
  customerSelectText: {
    fontSize: 16,
    color: '#666',
  },
  selectedCustomer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#0A1628',
    borderRadius: 12,
    padding: 12,
  },
  selectedCustomerInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  selectedAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  selectedAvatarText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  selectedName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  selectedPhone: {
    fontSize: 13,
    color: '#666',
  },
  customerListContainer: {
    backgroundColor: '#0A1628',
    borderRadius: 12,
    padding: 12,
    marginTop: 8,
    maxHeight: 300,
  },
  searchInput: {
    backgroundColor: '#1A2942',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    color: '#FFFFFF',
    marginBottom: 12,
  },
  customerList: {
    maxHeight: 200,
  },
  customerListItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  customerListAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  customerListAvatarText: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  customerListName: {
    fontSize: 15,
    fontWeight: '500',
    color: '#FFFFFF',
  },
  customerListPhone: {
    fontSize: 12,
    color: '#666',
  },
  closeListButton: {
    alignItems: 'center',
    paddingTop: 12,
  },
  closeListText: {
    fontSize: 14,
    color: '#FF4444',
  },
  dateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0A1628',
    borderRadius: 12,
    padding: 16,
    gap: 12,
  },
  dateButtonText: {
    fontSize: 16,
    color: '#FFFFFF',
  },
  messageInput: {
    backgroundColor: '#0A1628',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: '#FFFFFF',
    minHeight: 80,
    textAlignVertical: 'top',
  },
  quickDates: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 16,
  },
  quickDateButton: {
    flex: 1,
    backgroundColor: '#0A1628',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
  },
  quickDateText: {
    fontSize: 13,
    color: '#4A90D9',
    fontWeight: '500',
  },
  saveButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    borderRadius: 12,
    padding: 16,
    marginTop: 24,
    gap: 8,
  },
  saveButtonDisabled: {
    backgroundColor: '#1A2942',
  },
  saveButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  typeContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  typeButton: {
    flex: 1,
    minWidth: '45%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    paddingHorizontal: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#333',
    backgroundColor: '#1A2942',
    gap: 8,
  },
  typeText: {
    fontSize: 14,
    color: '#666',
    fontWeight: '500',
  },
  dateTimeRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
  },
  dateTimeButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#333',
    gap: 10,
  },
  dateTimeText: {
    color: '#FFFFFF',
    fontSize: 16,
  },
  dateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  aiDraftButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255, 215, 0, 0.15)', // Light gold background
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255, 215, 0, 0.3)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 3,
  },
  aiModalTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  draftLoadingContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
    gap: 16,
  },
  draftLoadingText: {
    fontSize: 16,
    color: '#666',
    fontWeight: '500',
  },

  aiReasonBox: {
    backgroundColor: 'rgba(255, 215, 0, 0.1)', // Light gold
    borderRadius: 8,
    padding: 12,
    marginBottom: 20,
    borderLeftWidth: 3,
    borderLeftColor: '#FFD700',
  },
  aiReasonLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: '#DAA520', // Darker gold
    marginBottom: 4,
  },
  aiReasonTextSmall: {
    fontSize: 13,
    color: '#666',
    lineHeight: 18,
  },
  whatsappSendButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    borderRadius: 12,
    padding: 16,
    gap: 10,
    marginTop: 'auto',
  },
  whatsappSendText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  timeText: {
    fontSize: 14,
    color: '#4A90D9',
    fontWeight: '600',
  },
  editButton: {
    padding: 8,
  },
  recentMessagesSection: {
    marginBottom: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: 12,
    overflow: 'hidden',
  },
  recentMessagesHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 12,
  },
  recentMessagesTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  inputLabelRecent: {
    fontSize: 14,
    color: '#888',
    fontWeight: '600',
  },
  messagesList: {
    paddingHorizontal: 12,
    paddingBottom: 12,
    gap: 8,
  },
  messageBubble: {
    padding: 10,
    borderRadius: 12,
    maxWidth: '85%',
  },
  incomingBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#0A1628',
    borderBottomLeftRadius: 2,
  },
  outgoingBubble: {
    alignSelf: 'flex-end',
    backgroundColor: '#25D366',
    borderBottomRightRadius: 2,
  },
  messageText: {
    fontSize: 14,
    lineHeight: 20,
  },
  incomingText: {
    color: '#FFFFFF',
  },
  outgoingText: {
    color: '#FFFFFF',
  },
  messageTime: {
    fontSize: 10,
    color: '#666',
    marginTop: 4,
    alignSelf: 'flex-end',
  },
  noMessagesText: {
    color: '#666',
    fontSize: 14,
    fontStyle: 'italic',
    textAlign: 'center',
  },
  regenerateSection: {
    marginTop: 16,
    marginBottom: 20,
  },
  directionInput: {
    backgroundColor: '#0A1628',
    borderRadius: 12,
    padding: 12,
    fontSize: 14,
    color: '#FFFFFF',
    minHeight: 60,
    textAlignVertical: 'top',
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#4A90D9',
  },
  regenerateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1A2942',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 12,
    gap: 8,
  },
  regenerateButtonText: {
    color: '#4A90D9',
    fontSize: 16,
    fontWeight: '600',
  },
  // Urgency Badge Styles
  urgencyBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    marginTop: 8,
    marginBottom: 4,
    alignSelf: 'flex-start',
    gap: 6,
  },
  urgencyBadgeHigh: {
    backgroundColor: 'rgba(255, 68, 68, 0.15)',
    borderWidth: 1,
    borderColor: '#FF4444',
  },
  urgencyBadgeMedium: {
    backgroundColor: 'rgba(255, 193, 7, 0.15)',
    borderWidth: 1,
    borderColor: '#FFC107',
  },
  urgencyBadgeLow: {
    backgroundColor: 'rgba(74, 144, 217, 0.15)',
    borderWidth: 1,
    borderColor: '#4A90D9',
  },
  urgencyBadgeIcon: {
    fontSize: 14,
  },
  urgencyBadgeText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  urgencyScore: {
    fontSize: 11,
    fontWeight: '700',
    color: '#FFD700',
    marginLeft: 4,
  },
});
