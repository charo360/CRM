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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../context/api';

interface Customer {
  id: string;
  name: string;
  phone_number: string;
  notes: string | null;
  tags: string[];
  last_message: string | null;
  last_contacted: string | null;
  created_at: string;
}

const TAGS = ['New', 'Returning', 'VIP'];

export default function CustomersScreen() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  
  // New customer form
  const [newName, setNewName] = useState('');
  const [newPhone, setNewPhone] = useState('+254');
  const [newNotes, setNewNotes] = useState('');
  const [newTags, setNewTags] = useState<string[]>(['New']);
  const [saving, setSaving] = useState(false);

  const { user } = useAuth();

  const fetchCustomers = useCallback(async () => {
    try {
      const params = selectedTag ? `?tag=${selectedTag}` : '';
      const response = await apiClient.get(`/customers${params}`);
      setCustomers(response.data);
    } catch (error) {
      console.error('Error fetching customers:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedTag]);

  useEffect(() => {
    fetchCustomers();
  }, [fetchCustomers]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchCustomers();
  };

  const handleAddCustomer = async () => {
    if (!newName.trim() || !newPhone.trim()) {
      Alert.alert('Error', 'Please fill in name and phone number');
      return;
    }

    setSaving(true);
    try {
      const response = await apiClient.post('/customers', {
        name: newName,
        phone_number: newPhone,
        notes: newNotes || null,
        tags: newTags,
      });
      
      setCustomers([response.data, ...customers]);
      setModalVisible(false);
      resetForm();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to add customer');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateCustomer = async () => {
    if (!selectedCustomer) return;

    setSaving(true);
    try {
      const response = await apiClient.put(`/customers/${selectedCustomer.id}`, {
        name: newName,
        notes: newNotes || null,
        tags: newTags,
      });
      
      setCustomers(customers.map(c => c.id === selectedCustomer.id ? response.data : c));
      setEditModalVisible(false);
      resetForm();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to update customer');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCustomer = (customer: Customer) => {
    Alert.alert(
      'Delete Customer',
      `Are you sure you want to delete ${customer.name}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.delete(`/customers/${customer.id}`);
              setCustomers(customers.filter(c => c.id !== customer.id));
            } catch (error) {
              Alert.alert('Error', 'Failed to delete customer');
            }
          },
        },
      ]
    );
  };

  const resetForm = () => {
    setNewName('');
    setNewPhone('+254');
    setNewNotes('');
    setNewTags(['New']);
    setSelectedCustomer(null);
  };

  const openEditModal = (customer: Customer) => {
    setSelectedCustomer(customer);
    setNewName(customer.name);
    setNewPhone(customer.phone_number);
    setNewNotes(customer.notes || '');
    setNewTags(customer.tags);
    setEditModalVisible(true);
  };

  const filteredCustomers = customers.filter(c =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.phone_number.includes(searchQuery)
  );

  const toggleTag = (tag: string) => {
    if (newTags.includes(tag)) {
      setNewTags(newTags.filter(t => t !== tag));
    } else {
      setNewTags([...newTags, tag]);
    }
  };

  const renderCustomer = ({ item }: { item: Customer }) => (
    <TouchableOpacity style={styles.customerCard} onPress={() => openEditModal(item)}>
      <View style={styles.customerAvatar}>
        <Text style={styles.avatarText}>{item.name.charAt(0).toUpperCase()}</Text>
      </View>
      <View style={styles.customerInfo}>
        <Text style={styles.customerName}>{item.name}</Text>
        <Text style={styles.customerPhone}>{item.phone_number}</Text>
        <View style={styles.tagsContainer}>
          {item.tags.map((tag, index) => (
            <View key={index} style={[styles.tag, tag === 'VIP' && styles.tagVip, tag === 'Returning' && styles.tagReturning]}>
              <Text style={styles.tagText}>{tag}</Text>
            </View>
          ))}
        </View>
      </View>
      <View style={styles.customerRight}>
        {item.notes && (
          <View style={styles.notesPreview}>
            <Ionicons name="document-text-outline" size={12} color="#25D366" />
            <Text style={styles.notesPreviewText} numberOfLines={2}>{item.notes}</Text>
          </View>
        )}
        <TouchableOpacity onPress={() => handleDeleteCustomer(item)} style={styles.deleteButton}>
          <Ionicons name="trash-outline" size={20} color="#FF4444" />
        </TouchableOpacity>
      </View>
    </TouchableOpacity>
  );

  const renderModal = (isEdit: boolean) => (
    <Modal
      visible={isEdit ? editModalVisible : modalVisible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={() => {
        isEdit ? setEditModalVisible(false) : setModalVisible(false);
        resetForm();
      }}
    >
      <SafeAreaView style={styles.modalContainer}>
        <View style={styles.modalHeader}>
          <TouchableOpacity onPress={() => {
            isEdit ? setEditModalVisible(false) : setModalVisible(false);
            resetForm();
          }}>
            <Text style={styles.modalCancel}>Cancel</Text>
          </TouchableOpacity>
          <Text style={styles.modalTitle}>{isEdit ? 'Edit Customer' : 'Add Customer'}</Text>
          <TouchableOpacity onPress={isEdit ? handleUpdateCustomer : handleAddCustomer} disabled={saving}>
            <Text style={[styles.modalSave, saving && styles.modalSaveDisabled]}>
              {saving ? 'Saving...' : 'Save'}
            </Text>
          </TouchableOpacity>
        </View>

        <View style={styles.modalContent}>
          <View style={styles.formGroup}>
            <Text style={styles.formLabel}>Name *</Text>
            <TextInput
              style={styles.formInput}
              value={newName}
              onChangeText={setNewName}
              placeholder="Customer name"
              placeholderTextColor="#666"
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.formLabel}>Phone Number *</Text>
            <TextInput
              style={[styles.formInput, isEdit && styles.inputDisabled]}
              value={newPhone}
              onChangeText={setNewPhone}
              placeholder="+254 7XX XXX XXX"
              placeholderTextColor="#666"
              keyboardType="phone-pad"
              editable={!isEdit}
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.formLabel}>Notes</Text>
            <TextInput
              style={[styles.formInput, styles.formTextarea]}
              value={newNotes}
              onChangeText={setNewNotes}
              placeholder="e.g., Asked for size 32, Budget 3k"
              placeholderTextColor="#666"
              multiline
              numberOfLines={3}
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.formLabel}>Tags</Text>
            <View style={styles.tagsSelector}>
              {TAGS.map((tag) => (
                <TouchableOpacity
                  key={tag}
                  style={[
                    styles.tagOption,
                    newTags.includes(tag) && styles.tagOptionSelected,
                  ]}
                  onPress={() => toggleTag(tag)}
                >
                  <Text style={[
                    styles.tagOptionText,
                    newTags.includes(tag) && styles.tagOptionTextSelected,
                  ]}>{tag}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </View>
      </SafeAreaView>
    </Modal>
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
        <Text style={styles.headerTitle}>Customers</Text>
        <Text style={styles.headerCount}>{customers.length} contacts</Text>
      </View>

      <View style={styles.searchContainer}>
        <Ionicons name="search" size={20} color="#666" style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          value={searchQuery}
          onChangeText={setSearchQuery}
          placeholder="Search customers..."
          placeholderTextColor="#666"
        />
      </View>

      <View style={styles.filterContainer}>
        <TouchableOpacity
          style={[styles.filterChip, !selectedTag && styles.filterChipActive]}
          onPress={() => setSelectedTag(null)}
        >
          <Text style={[styles.filterText, !selectedTag && styles.filterTextActive]}>All</Text>
        </TouchableOpacity>
        {TAGS.map((tag) => (
          <TouchableOpacity
            key={tag}
            style={[styles.filterChip, selectedTag === tag && styles.filterChipActive]}
            onPress={() => setSelectedTag(selectedTag === tag ? null : tag)}
          >
            <Text style={[styles.filterText, selectedTag === tag && styles.filterTextActive]}>{tag}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <FlatList
        data={filteredCustomers}
        renderItem={renderCustomer}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="people-outline" size={64} color="#666" />
            <Text style={styles.emptyText}>No customers yet</Text>
            <Text style={styles.emptySubtext}>Add your first customer to get started</Text>
          </View>
        }
      />

      {/* WhatsApp-style Floating Action Button */}
      <TouchableOpacity 
        style={styles.fab} 
        onPress={() => setModalVisible(true)}
        activeOpacity={0.8}
      >
        <Ionicons name="add" size={28} color="#FFFFFF" />
      </TouchableOpacity>

      {renderModal(false)}
      {renderModal(true)}
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
  headerCount: {
    fontSize: 14,
    color: '#666',
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    marginHorizontal: 20,
    borderRadius: 12,
    paddingHorizontal: 16,
    marginBottom: 12,
  },
  searchIcon: {
    marginRight: 12,
  },
  searchInput: {
    flex: 1,
    height: 48,
    fontSize: 16,
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
  customerCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  customerAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  avatarText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  customerInfo: {
    flex: 1,
  },
  customerRight: {
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    marginLeft: 8,
    maxWidth: 120,
  },
  notesPreview: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#0D2137',
    borderRadius: 8,
    padding: 8,
    marginBottom: 8,
  },
  notesPreviewText: {
    fontSize: 11,
    color: '#25D366',
    marginLeft: 4,
    flex: 1,
    lineHeight: 14,
  },
  customerName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 2,
  },
  customerPhone: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  tagsContainer: {
    flexDirection: 'row',
  },
  tag: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: '#25D366',
    borderRadius: 10,
    marginRight: 6,
  },
  tagVip: {
    backgroundColor: '#FFD700',
  },
  tagReturning: {
    backgroundColor: '#4A90D9',
  },
  tagText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#FFFFFF',
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
    marginBottom: 20,
  },
  formLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  formInput: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: '#FFFFFF',
  },
  formTextarea: {
    height: 100,
    textAlignVertical: 'top',
  },
  inputDisabled: {
    opacity: 0.5,
  },
  tagsSelector: {
    flexDirection: 'row',
  },
  tagOption: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    backgroundColor: '#1A2942',
    borderRadius: 20,
    marginRight: 10,
  },
  tagOptionSelected: {
    backgroundColor: '#25D366',
  },
  tagOptionText: {
    fontSize: 14,
    color: '#666',
  },
  tagOptionTextSelected: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
});
