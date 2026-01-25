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
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<'all' | 'today' | 'tomorrow' | 'later'>('all');

  const fetchFollowups = useCallback(async () => {
    try {
      const response = await apiClient.get('/followups?status=pending');
      setFollowups(response.data);
    } catch (error) {
      console.error('Error fetching followups:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchFollowups();
  }, [fetchFollowups]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchFollowups();
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

  const filteredFollowups = followups.filter(f => {
    if (filter === 'all') return true;
    const category = getDateCategory(f.reminder_date);
    if (filter === 'today') return category === 'today' || category === 'overdue';
    return category === filter;
  });

  const groupedFollowups = {
    overdue: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'overdue'),
    today: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'today'),
    tomorrow: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'tomorrow'),
    later: filteredFollowups.filter(f => getDateCategory(f.reminder_date) === 'later'),
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

      <View style={styles.filterContainer}>
        {(['all', 'today', 'tomorrow', 'later'] as const).map((f) => (
          <TouchableOpacity
            key={f}
            style={[styles.filterChip, filter === f && styles.filterChipActive]}
            onPress={() => setFilter(f)}
          >
            <Text style={[styles.filterText, filter === f && styles.filterTextActive]}>
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <FlatList
        data={[1]} // Single item to render all sections
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
          filteredFollowups.length === 0 ? (
            <View style={styles.emptyContainer}>
              <Ionicons name="notifications-off-outline" size={64} color="#666" />
              <Text style={styles.emptyText}>No follow-ups</Text>
              <Text style={styles.emptySubtext}>Set reminders from customer profiles</Text>
            </View>
          ) : null
        }
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
});
