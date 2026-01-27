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
  Linking,
  Modal,
  TextInput,
  ScrollView,
  Platform,
  KeyboardAvoidingView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiClient } from '../../context/api';
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

type FilterType = 'all' | 'overdue' | 'today' | 'tomorrow' | 'this_week';

export default function FollowupsScreen() {
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [coldCustomers, setColdCustomers] = useState<ColdCustomer[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestions | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<'reminders' | 'needs_attention'>('needs_attention');
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

  const fetchData = useCallback(async () => {
    try {
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
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

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

  const handleComplete = async (followup: FollowUp) => {
    try {
      await apiClient.put(`/followups/${followup.id}`, { status: 'completed' });
      setFollowups(followups.filter(f => f.id !== followup.id));
    } catch (error) {
      Alert.alert('Error', 'Failed to complete follow-up');
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

  const handleSendMessage = (phone: string, name: string, message?: string | null) => {
    const text = message || `Hi ${name}, just checking in!`;
    const url = `whatsapp://send?phone=${phone.replace(/\+/g, '')}&text=${encodeURIComponent(text)}`;
    Linking.openURL(url).catch(() => {
      Alert.alert('Error', 'WhatsApp is not installed on this device');
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
        <View style={styles.followupInfo}>
          <View style={styles.followupHeader}>
            <Ionicons
              name={typeIcons[item.type] as any || 'notifications'}
              size={20}
              color={isOverdue ? '#FF4444' : (typeColors[item.type] || '#25D366')}
            />
            <Text style={styles.customerName}>{item.customer_name}</Text>
          </View>
          <Text style={styles.customerPhone}>{item.customer_phone}</Text>
          {item.message && (
            <Text style={styles.message} numberOfLines={2}>{item.message}</Text>
          )}
          <View style={styles.dateRow}>
            <Text style={[styles.dateText, isOverdue && styles.dateTextOverdue]}>
              {isOverdue ? 'Overdue: ' : ''}
              {new Date(item.reminder_date).toLocaleDateString('en-KE', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
              })}
            </Text>
            <Text style={styles.timeText}>
              {new Date(item.reminder_date).toLocaleTimeString('en-KE', {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </Text>
          </View>
        </View>
        <View style={styles.actions}>
          <TouchableOpacity
            style={styles.whatsappButton}
            onPress={() => handleSendMessage(item.customer_phone, item.customer_name, item.message)}
          >
            <Ionicons name="logo-whatsapp" size={24} color="#FFFFFF" />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.editButton}
            onPress={() => openEditModal(item)}
          >
            <Ionicons name="create-outline" size={24} color="#4A90D9" />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.completeButton}
            onPress={() => handleComplete(item)}
          >
            <Ionicons name="checkmark" size={24} color="#25D366" />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.deleteButton}
            onPress={() => handleDelete(item)}
          >
            <Ionicons name="trash-outline" size={20} color="#FF4444" />
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
      <View style={styles.coldCustomerInfo}>
        <View style={styles.coldCustomerHeader}>
          <View style={styles.coldAvatar}>
            <Text style={styles.coldAvatarText}>{customer.name.charAt(0)}</Text>
          </View>
          <View style={styles.coldCustomerDetails}>
            <Text style={styles.coldCustomerName}>{customer.name}</Text>
            <Text style={styles.coldCustomerPhone}>{customer.phone_number}</Text>
          </View>
        </View>

        {/* AI-Generated Reason */}
        <View style={styles.aiReasonContainer}>
          <Ionicons name="bulb" size={14} color="#FFD700" />
          <Text style={styles.aiReasonText}>
            {customer.ai_reason || (customer.days_since_contact !== null
              ? `No contact in ${customer.days_since_contact} days`
              : 'Never contacted')}
          </Text>
        </View>

        {customer.last_message && (
          <Text style={styles.coldLastMessage} numberOfLines={1}>
            Last: "{customer.last_message}"
          </Text>
        )}

        <View style={styles.coldCustomerMeta}>
          <Ionicons name="time-outline" size={14} color="#FF6B6B" />
          <Text style={styles.coldDaysText}>
            {customer.days_since_contact !== null
              ? `${customer.days_since_contact} days ago`
              : 'Never'}
          </Text>
          {customer.has_pending_followup && (
            <View style={styles.hasFollowupBadge}>
              <Text style={styles.hasFollowupText}>Has reminder</Text>
            </View>
          )}
        </View>
      </View>

      <View style={styles.coldActions}>
        <TouchableOpacity
          style={styles.coldWhatsappButton}
          onPress={() => handleSendMessage(customer.phone_number, customer.name)}
        >
          <Ionicons name="logo-whatsapp" size={22} color="#FFFFFF" />
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.addReminderButton}
          onPress={() => handleCreateFollowupFromCold(customer)}
        >
          <Ionicons name="alarm-outline" size={20} color="#4A90D9" />
        </TouchableOpacity>
      </View>
    </View>
  );

  const filters: { key: FilterType; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'overdue', label: 'Overdue' },
    { key: 'today', label: 'Today' },
    { key: 'tomorrow', label: 'Tomorrow' },
    { key: 'this_week', label: 'This Week' },
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
            <Text style={styles.statLabel}>Need attention</Text>
          </View>
          <View style={[styles.statCard, styles.statCardDanger]}>
            <Text style={styles.statNumber}>{suggestions.neglected_month}</Text>
            <Text style={styles.statLabel}>30+ days cold</Text>
          </View>
        </View>
      )}

      {/* Tab Switcher */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'needs_attention' && styles.tabActive]}
          onPress={() => setActiveTab('needs_attention')}
        >
          <Ionicons
            name="alert-circle"
            size={18}
            color={activeTab === 'needs_attention' ? '#FFFFFF' : '#666'}
          />
          <Text style={[styles.tabText, activeTab === 'needs_attention' && styles.tabTextActive]}>
            Needs Attention ({coldCustomers.filter(c => !c.has_pending_followup).length})
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'reminders' && styles.tabActive]}
          onPress={() => setActiveTab('reminders')}
        >
          <Ionicons
            name="notifications"
            size={18}
            color={activeTab === 'reminders' ? '#FFFFFF' : '#666'}
          />
          <Text style={[styles.tabText, activeTab === 'reminders' && styles.tabTextActive]}>
            Reminders ({followups.length})
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

      {activeTab === 'needs_attention' ? (
        <FlatList
          data={coldCustomers}
          renderItem={({ item }) => renderColdCustomer(item)}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="checkmark-circle-outline" size={64} color="#25D366" />
              <Text style={styles.emptyText}>All caught up!</Text>
              <Text style={styles.emptySubtext}>No customers need immediate attention</Text>
            </View>
          }
        />
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
        <Ionicons name="add" size={30} color="#FFFFFF" />
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

                {/* Message */}
                <Text style={styles.inputLabel}>Note (Optional)</Text>
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
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#25D366',
    marginTop: 4,
  },
  addButton: {
    position: 'absolute',
    right: 20,
    bottom: 20,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 5,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    zIndex: 10,
  },
  statsRow: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 16,
    gap: 12,
  },
  statCard: {
    flex: 1,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
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
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  statLabel: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  tabContainer: {
    flexDirection: 'row',
    marginHorizontal: 20,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 4,
    marginBottom: 12,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    borderRadius: 10,
    gap: 6,
  },
  tabActive: {
    backgroundColor: '#25D366',
  },
  tabText: {
    fontSize: 13,
    color: '#666',
    fontWeight: '500',
  },
  tabTextActive: {
    color: '#FFFFFF',
  },
  filterContainer: {
    maxHeight: 44,
    marginBottom: 12,
  },
  filterContent: {
    paddingHorizontal: 20,
    gap: 8,
  },
  filterChip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#1A2942',
    borderRadius: 20,
    marginRight: 8,
  },
  filterChipActive: {
    backgroundColor: '#25D366',
  },
  filterText: {
    color: '#666',
    fontSize: 14,
    fontWeight: '500',
  },
  filterTextActive: {
    color: '#FFFFFF',
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 100,
  },
  section: {
    marginBottom: 24,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  sectionDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  sectionTitle: {
    fontSize: 16,
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
    flexDirection: 'row',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  followupCardOverdue: {
    borderLeftWidth: 3,
    borderLeftColor: '#FF4444',
  },
  followupInfo: {
    flex: 1,
  },
  followupHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  customerName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginLeft: 8,
  },
  customerPhone: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  message: {
    fontSize: 13,
    color: '#888',
    marginBottom: 8,
  },
  dateText: {
    fontSize: 12,
    color: '#666',
  },
  dateTextOverdue: {
    color: '#FF4444',
  },
  actions: {
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  whatsappButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
  },
  completeButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#1A2942',
    borderWidth: 2,
    borderColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
  },
  deleteButton: {
    padding: 8,
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
    flexDirection: 'row',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderLeftWidth: 3,
    borderLeftColor: '#FF6B6B',
  },
  coldCustomerInfo: {
    flex: 1,
  },
  coldCustomerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  coldAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#FF6B6B',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  coldAvatarText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  coldCustomerDetails: {
    flex: 1,
  },
  coldCustomerName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  coldCustomerPhone: {
    fontSize: 13,
    color: '#666',
  },
  aiReasonContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 215, 0, 0.1)',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    marginBottom: 8,
  },
  aiReasonText: {
    fontSize: 12,
    color: '#FFD700',
    marginLeft: 6,
    flex: 1,
  },
  coldLastMessage: {
    fontSize: 12,
    color: '#888',
    fontStyle: 'italic',
    marginBottom: 8,
  },
  coldCustomerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  coldDaysText: {
    fontSize: 12,
    color: '#FF6B6B',
    marginLeft: 4,
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
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  coldWhatsappButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
  },
  addReminderButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(74, 144, 217, 0.2)',
    justifyContent: 'center',
    alignItems: 'center',
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
  timeText: {
    fontSize: 14,
    color: '#4A90D9',
    fontWeight: '600',
  },
  editButton: {
    padding: 8,
  },
});
