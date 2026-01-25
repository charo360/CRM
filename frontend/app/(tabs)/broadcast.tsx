import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
  Modal,
  Alert,
  ActivityIndicator,
  RefreshControl,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiClient } from '../context/api';

interface Customer {
  id: string;
  name: string;
  phone_number: string;
  tags: string[];
}

interface Broadcast {
  id: string;
  message: string;
  filter_type: string;
  recipients_count: number;
  sent_count: number;
  status: string;
  created_at: string;
}

const FILTERS = [
  { id: 'all', label: 'All Customers', icon: 'people' },
  { id: 'returning', label: 'Returning', icon: 'refresh' },
  { id: 'vip', label: 'VIP', icon: 'star' },
];

const TEMPLATES = [
  {
    id: 'promo',
    title: 'New Arrivals',
    message: 'New arrivals just landed \ud83d\udd25\nReply YES to see photos.',
  },
  {
    id: 'sale',
    title: 'Flash Sale',
    message: 'FLASH SALE \u26a1\n20% off everything today only!\nVisit us now.',
  },
  {
    id: 'reminder',
    title: 'Check In',
    message: 'Hi! \ud83d\udc4b Just checking in.\nWe have new stock you might like.',
  },
  {
    id: 'custom',
    title: 'Custom Message',
    message: '',
  },
];

export default function BroadcastScreen() {
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [sending, setSending] = useState(false);

  // Form state
  const [selectedFilter, setSelectedFilter] = useState('all');
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [message, setMessage] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const [broadcastsRes, customersRes] = await Promise.all([
        apiClient.get('/broadcasts'),
        apiClient.get('/customers'),
      ]);
      setBroadcasts(broadcastsRes.data);
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

  const getFilteredCount = () => {
    if (selectedFilter === 'all') return customers.length;
    if (selectedFilter === 'returning') {
      return customers.filter(c => c.tags.includes('Returning')).length;
    }
    if (selectedFilter === 'vip') {
      return customers.filter(c => c.tags.includes('VIP')).length;
    }
    return 0;
  };

  const handleSelectTemplate = (template: typeof TEMPLATES[0]) => {
    setSelectedTemplate(template.id);
    if (template.message) {
      setMessage(template.message);
    }
  };

  const handleSendBroadcast = async () => {
    if (!message.trim()) {
      Alert.alert('Error', 'Please enter a message');
      return;
    }

    const recipientCount = getFilteredCount();
    if (recipientCount === 0) {
      Alert.alert('Error', 'No customers match this filter');
      return;
    }

    Alert.alert(
      'Send Broadcast',
      `Send this message to ${recipientCount} customer${recipientCount > 1 ? 's' : ''}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Send',
          onPress: async () => {
            setSending(true);
            try {
              const response = await apiClient.post('/broadcasts', {
                message: message,
                filter_type: selectedFilter,
              });

              setBroadcasts([response.data, ...broadcasts]);
              setModalVisible(false);
              resetForm();

              Alert.alert(
                'Success',
                `Broadcast sent to ${response.data.recipients_count} customers!`
              );
            } catch (error: any) {
              Alert.alert('Error', error.response?.data?.detail || 'Failed to send broadcast');
            } finally {
              setSending(false);
            }
          },
        },
      ]
    );
  };

  const resetForm = () => {
    setSelectedFilter('all');
    setSelectedTemplate('');
    setMessage('');
  };

  const renderBroadcast = ({ item }: { item: Broadcast }) => (
    <View style={styles.broadcastCard}>
      <View style={styles.broadcastHeader}>
        <View style={styles.broadcastIcon}>
          <Ionicons name="megaphone" size={20} color="#25D366" />
        </View>
        <View style={styles.broadcastInfo}>
          <Text style={styles.broadcastDate}>
            {new Date(item.created_at).toLocaleDateString('en-KE', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Text>
          <View style={styles.statusRow}>
            <View style={[
              styles.statusBadge,
              item.status === 'completed' && styles.statusCompleted,
              item.status === 'sending' && styles.statusSending,
            ]}>
              <Text style={styles.statusText}>
                {item.status === 'completed' ? 'Sent' : 'Sending...'}
              </Text>
            </View>
            <Text style={styles.recipientCount}>
              {item.sent_count}/{item.recipients_count} delivered
            </Text>
          </View>
        </View>
      </View>
      <Text style={styles.broadcastMessage} numberOfLines={3}>
        {item.message}
      </Text>
      <View style={styles.filterBadge}>
        <Text style={styles.filterBadgeText}>
          {item.filter_type === 'all' ? 'All Customers' : 
           item.filter_type === 'returning' ? 'Returning' : 'VIP'}
        </Text>
      </View>
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
        <View>
          <Text style={styles.headerTitle}>Broadcast</Text>
          <Text style={styles.headerSubtitle}>Send promotions to customers</Text>
        </View>
        <TouchableOpacity style={styles.addButton} onPress={() => setModalVisible(true)}>
          <Ionicons name="add" size={24} color="#FFFFFF" />
        </TouchableOpacity>
      </View>

      <View style={styles.statsRow}>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{broadcasts.length}</Text>
          <Text style={styles.statLabel}>Broadcasts</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{customers.length}</Text>
          <Text style={styles.statLabel}>Customers</Text>
        </View>
      </View>

      <FlatList
        data={broadcasts}
        renderItem={renderBroadcast}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="megaphone-outline" size={64} color="#666" />
            <Text style={styles.emptyText}>No broadcasts yet</Text>
            <Text style={styles.emptySubtext}>Send your first promotion</Text>
          </View>
        }
      />

      {/* New Broadcast Modal */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => {
          setModalVisible(false);
          resetForm();
        }}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => {
              setModalVisible(false);
              resetForm();
            }}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>New Broadcast</Text>
            <TouchableOpacity onPress={handleSendBroadcast} disabled={sending}>
              <Text style={[styles.modalSave, sending && styles.modalSaveDisabled]}>
                {sending ? 'Sending...' : 'Send'}
              </Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalContent}>
            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Send to</Text>
              <View style={styles.filtersContainer}>
                {FILTERS.map((filter) => (
                  <TouchableOpacity
                    key={filter.id}
                    style={[
                      styles.filterOption,
                      selectedFilter === filter.id && styles.filterOptionSelected,
                    ]}
                    onPress={() => setSelectedFilter(filter.id)}
                  >
                    <Ionicons
                      name={filter.icon as any}
                      size={20}
                      color={selectedFilter === filter.id ? '#FFFFFF' : '#666'}
                    />
                    <Text
                      style={[
                        styles.filterOptionText,
                        selectedFilter === filter.id && styles.filterOptionTextSelected,
                      ]}
                    >
                      {filter.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.recipientHint}>
                {getFilteredCount()} customer{getFilteredCount() !== 1 ? 's' : ''} will receive this message
              </Text>
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Quick Templates</Text>
              <View style={styles.templatesContainer}>
                {TEMPLATES.map((template) => (
                  <TouchableOpacity
                    key={template.id}
                    style={[
                      styles.templateOption,
                      selectedTemplate === template.id && styles.templateOptionSelected,
                    ]}
                    onPress={() => handleSelectTemplate(template)}
                  >
                    <Text
                      style={[
                        styles.templateOptionText,
                        selectedTemplate === template.id && styles.templateOptionTextSelected,
                      ]}
                    >
                      {template.title}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Message *</Text>
              <TextInput
                style={styles.messageInput}
                value={message}
                onChangeText={setMessage}
                placeholder="Type your promotional message..."
                placeholderTextColor="#666"
                multiline
                numberOfLines={6}
                textAlignVertical="top"
              />
              <Text style={styles.charCount}>{message.length}/500</Text>
            </View>

            <View style={styles.warningBox}>
              <Ionicons name="information-circle" size={20} color="#FFD700" />
              <Text style={styles.warningText}>
                Messages will be sent via SMS. WhatsApp templates require approval.
              </Text>
            </View>
          </ScrollView>
        </SafeAreaView>
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
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
    color: '#666',
    marginTop: 2,
  },
  addButton: {
    width: 44,
    height: 44,
    backgroundColor: '#25D366',
    borderRadius: 22,
    justifyContent: 'center',
    alignItems: 'center',
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
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#25D366',
  },
  statLabel: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  broadcastCard: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  broadcastHeader: {
    flexDirection: 'row',
    marginBottom: 12,
  },
  broadcastIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#0A1628',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  broadcastInfo: {
    flex: 1,
  },
  broadcastDate: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 4,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: '#666',
    borderRadius: 10,
    marginRight: 8,
  },
  statusCompleted: {
    backgroundColor: '#25D366',
  },
  statusSending: {
    backgroundColor: '#FFD700',
  },
  statusText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  recipientCount: {
    fontSize: 12,
    color: '#666',
  },
  broadcastMessage: {
    fontSize: 14,
    color: '#FFFFFF',
    lineHeight: 20,
    marginBottom: 12,
  },
  filterBadge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    backgroundColor: '#0A1628',
    borderRadius: 10,
  },
  filterBadgeText: {
    fontSize: 12,
    color: '#666',
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
  // Modal styles
  modalContainer: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  modalCancel: {
    fontSize: 16,
    color: '#FF4444',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  modalSave: {
    fontSize: 16,
    fontWeight: '600',
    color: '#25D366',
  },
  modalSaveDisabled: {
    opacity: 0.5,
  },
  modalContent: {
    padding: 20,
  },
  formGroup: {
    marginBottom: 24,
  },
  formLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#FFFFFF',
    marginBottom: 12,
  },
  filtersContainer: {
    gap: 8,
  },
  filterOption: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
  },
  filterOptionSelected: {
    backgroundColor: '#25D366',
  },
  filterOptionText: {
    fontSize: 16,
    color: '#666',
    marginLeft: 12,
  },
  filterOptionTextSelected: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  recipientHint: {
    fontSize: 12,
    color: '#25D366',
    marginTop: 8,
  },
  templatesContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  templateOption: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: '#1A2942',
    borderRadius: 20,
  },
  templateOptionSelected: {
    backgroundColor: '#25D366',
  },
  templateOptionText: {
    fontSize: 14,
    color: '#666',
  },
  templateOptionTextSelected: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  messageInput: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: '#FFFFFF',
    minHeight: 150,
  },
  charCount: {
    fontSize: 12,
    color: '#666',
    textAlign: 'right',
    marginTop: 8,
  },
  warningBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    gap: 12,
  },
  warningText: {
    flex: 1,
    fontSize: 13,
    color: '#888',
    lineHeight: 18,
  },
});
