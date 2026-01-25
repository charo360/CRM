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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiClient } from '../context/api';

interface FollowUp {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  reminder_date: string;
  message: string | null;
  status: string;
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
}

interface Suggestions {
  neglected_week: number;
  neglected_month: number;
  new_no_followup: number;
  vip_neglected: number;
  total_needing_attention: number;
}

export default function FollowupsScreen() {
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [coldCustomers, setColdCustomers] = useState<ColdCustomer[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestions | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<'reminders' | 'needs_attention'>('needs_attention');

  const fetchData = useCallback(async () => {
    try {
      const [followupsRes, coldRes, suggestionsRes] = await Promise.all([
        apiClient.get('/followups?status=pending'),
        apiClient.get('/customers/cold?days=14'),
        apiClient.get('/stats/followup-suggestions'),
      ]);
      setFollowups(followupsRes.data);
      setColdCustomers(coldRes.data);
      setSuggestions(suggestionsRes.data);
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

  const getDateCategory = (dateStr: string) => {
    const date = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    if (date.toDateString() === today.toDateString()) return 'today';
    if (date.toDateString() === tomorrow.toDateString()) return 'tomorrow';
    if (date < today) return 'overdue';
    return 'later';
  };

  const groupedFollowups = {
    overdue: followups.filter(f => getDateCategory(f.reminder_date) === 'overdue'),
    today: followups.filter(f => getDateCategory(f.reminder_date) === 'today'),
    tomorrow: followups.filter(f => getDateCategory(f.reminder_date) === 'tomorrow'),
    later: followups.filter(f => getDateCategory(f.reminder_date) === 'later'),
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

  const handleSendMessage = (followup: FollowUp) => {
    const message = followup.message || `Hi ${followup.customer_name}, just checking in!`;
    const url = `whatsapp://send?phone=${followup.customer_phone.replace(/\+/g, '')}&text=${encodeURIComponent(message)}`;
    Linking.openURL(url).catch(() => {
      Alert.alert('Error', 'WhatsApp is not installed on this device');
    });
  };

  const renderFollowup = (item: FollowUp) => {
    const category = getDateCategory(item.reminder_date);
    const isOverdue = category === 'overdue';

    return (
      <View key={item.id} style={[styles.followupCard, isOverdue && styles.followupCardOverdue]}>
        <View style={styles.followupInfo}>
          <View style={styles.followupHeader}>
            <Ionicons 
              name="notifications" 
              size={20} 
              color={isOverdue ? '#FF4444' : '#25D366'} 
            />
            <Text style={styles.customerName}>{item.customer_name}</Text>
          </View>
          <Text style={styles.customerPhone}>{item.customer_phone}</Text>
          {item.message && (
            <Text style={styles.message} numberOfLines={2}>{item.message}</Text>
          )}
          <Text style={[styles.dateText, isOverdue && styles.dateTextOverdue]}>
            {isOverdue ? 'Overdue: ' : ''}
            {new Date(item.reminder_date).toLocaleDateString('en-KE', {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
            })}
          </Text>
        </View>
        <View style={styles.actions}>
          <TouchableOpacity 
            style={styles.whatsappButton} 
            onPress={() => handleSendMessage(item)}
          >
            <Ionicons name="logo-whatsapp" size={24} color="#FFFFFF" />
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

  const handleMessageColdCustomer = (customer: ColdCustomer) => {
    const message = `Hi ${customer.name}! Just checking in to see how you're doing. Let me know if you need anything!`;
    const url = `whatsapp://send?phone=${customer.phone_number.replace(/\+/g, '')}&text=${encodeURIComponent(message)}`;
    Linking.openURL(url).catch(() => {
      Alert.alert('Error', 'WhatsApp is not installed on this device');
    });
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
        {customer.notes && (
          <Text style={styles.coldCustomerNotes} numberOfLines={1}>{customer.notes}</Text>
        )}
        <View style={styles.coldCustomerMeta}>
          <Ionicons name="time-outline" size={14} color="#FF6B6B" />
          <Text style={styles.coldDaysText}>
            {customer.days_since_contact !== null 
              ? `${customer.days_since_contact} days ago`
              : 'Never contacted'}
          </Text>
          {customer.has_pending_followup && (
            <View style={styles.hasFollowupBadge}>
              <Text style={styles.hasFollowupText}>Has reminder</Text>
            </View>
          )}
        </View>
      </View>
      <TouchableOpacity 
        style={styles.coldWhatsappButton} 
        onPress={() => handleMessageColdCustomer(customer)}
      >
        <Ionicons name="logo-whatsapp" size={24} color="#FFFFFF" />
      </TouchableOpacity>
    </View>
  );

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

      {activeTab === 'needs_attention' ? (
        <FlatList
          data={coldCustomers.filter(c => !c.has_pending_followup)}
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
              {renderSection('Overdue', groupedFollowups.overdue, '#FF4444')}
              {renderSection('Today', groupedFollowups.today, '#25D366')}
              {renderSection('Tomorrow', groupedFollowups.tomorrow, '#4A90D9')}
              {renderSection('Later', groupedFollowups.later, '#666')}
            </>
          )}
          keyExtractor={() => 'sections'}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
          }
          ListEmptyComponent={
            followups.length === 0 ? (
              <View style={styles.emptyContainer}>
                <Ionicons name="notifications-off-outline" size={64} color="#666" />
                <Text style={styles.emptyText}>No reminders</Text>
                <Text style={styles.emptySubtext}>Set follow-up reminders from customer profiles</Text>
              </View>
            ) : null
          }
        />
      )}
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
    marginBottom: 16,
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
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 16,
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
    paddingBottom: 20,
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
  coldCustomerNotes: {
    fontSize: 12,
    color: '#888',
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
  coldWhatsappButton: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    alignSelf: 'center',
  },
});
