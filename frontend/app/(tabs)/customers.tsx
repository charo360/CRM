import React, { useState, useEffect, useCallback, useRef } from 'react';
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
  Platform,
  ScrollView,
  Image,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { apiClient, productsAPI, settingsAPI } from '../../context/api';
import { useRouter } from 'expo-router';
import * as Contacts from 'expo-contacts';
import CountryPicker, { Country, COUNTRIES } from '../../components/CountryPicker';

interface Customer {
  id: string;
  name: string;
  phone_number: string;
  notes: string | null;
  tags: string[];
  purchase_count: number;
  total_spent: number;
  last_message: string | null;
  last_contacted: string | null;
  created_at: string;
}

interface PhoneContact {
  id: string;
  name: string;
  phoneNumber: string;
  selected: boolean;
}

const TAGS = ['New', 'Returning', 'VIP'];

interface Message {
  id: string;
  direction: 'incoming' | 'outgoing';
  content: string;
  created_at: string;
}

export default function CustomersScreen() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'recently_added' | 'recently_contacted'>('recently_added');
  const [modalVisible, setModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);

  // New customer form
  const [newName, setNewName] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [customerCountry, setCustomerCountry] = useState<Country>(
    COUNTRIES.find(c => c.code === 'KE')!
  );
  const [newNotes, setNewNotes] = useState('');
  const [newTags, setNewTags] = useState<string[]>(['New']);
  const [saving, setSaving] = useState(false);
  const [showTagInput, setShowTagInput] = useState(false);
  const [newTagText, setNewTagText] = useState('');

  // Contact import
  const [contactsModalVisible, setContactsModalVisible] = useState(false);
  const [phoneContacts, setPhoneContacts] = useState<PhoneContact[]>([]);
  const [loadingContacts, setLoadingContacts] = useState(false);
  const [importingContacts, setImportingContacts] = useState(false);
  const [contactSearch, setContactSearch] = useState('');

  // AI Draft Message Modal State
  const [showDraftModal, setShowDraftModal] = useState(false);
  const [draftMessage, setDraftMessage] = useState('');
  const [draftReason, setDraftReason] = useState('');
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [draftCustomer, setDraftCustomer] = useState<Customer | null>(null);
  const [customDirection, setCustomDirection] = useState('');
  const [recentMessages, setRecentMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [showRecentMessages, setShowRecentMessages] = useState(false);

  // Product picker state
  const [showProductPicker, setShowProductPicker] = useState(false);
  const [productPickerCustomer, setProductPickerCustomer] = useState<Customer | null>(null);
  const [pickerProducts, setPickerProducts] = useState<any[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [sendingProduct, setSendingProduct] = useState<string | null>(null);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [sendingCatalog, setSendingCatalog] = useState(false);
  const [currency, setCurrency] = useState('USD');

  const { user } = useAuth();
  const insets = useSafeAreaInsets();

  const fetchCustomers = useCallback(async () => {
    try {
      let params = '';

      // Intelligent Search Logic
      const queryLower = searchQuery.toLowerCase().trim();

      if (queryLower.includes('top') || queryLower.includes('best') || queryLower.includes('highest')) {
        params = '?sort_by=purchases';
      } else if (queryLower.includes('new')) {
        params = '?tag=New';
      } else if (queryLower.includes('vip')) {
        params = '?tag=VIP';
      } else if (queryLower.includes('returning')) {
        params = '?tag=Returning';
      } else if (selectedTag) {
        params = `?tag=${selectedTag}`;
      } else {
        // Apply sorting based on toggle
        params = sortBy === 'recently_contacted' ? '?sort_by=recently_contacted' : '';
      }

      const response = await apiClient.get(`/customers${params}`);
      setCustomers(response.data);
    } catch (error) {
      console.error('Error fetching customers:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedTag, searchQuery, sortBy]);

  useEffect(() => {
    const loadCurrency = async () => {
      try {
        const settings = await settingsAPI.getSettings();
        if (settings.currency) setCurrency(settings.currency);
      } catch (e) {}
    };
    loadCurrency();
  }, []);

  useEffect(() => {
    // Debounce search to prevent too many API calls
    const timeoutId = setTimeout(() => {
      fetchCustomers();
    }, 500);
    return () => clearTimeout(timeoutId);
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
      // Build full phone number with country code
      let fullPhone = newPhone.trim();
      if (!fullPhone.startsWith('+')) {
        fullPhone = fullPhone.replace(/^0+/, '');
        fullPhone = `${customerCountry.dial}${fullPhone}`;
      }
      const response = await apiClient.post('/customers', {
        name: newName,
        phone_number: fullPhone,
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
    setNewPhone('');
    setNewNotes('');
    setNewTags(['New']);
    setSelectedCustomer(null);
  };

  // Import contacts from phone
  const loadPhoneContacts = async () => {
    setLoadingContacts(true);
    try {
      const { status } = await Contacts.requestPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Required', 'Please allow access to contacts to import customers');
        setContactsModalVisible(false);
        return;
      }

      const { data } = await Contacts.getContactsAsync({
        fields: [Contacts.Fields.Name, Contacts.Fields.PhoneNumbers],
      });

      if (data.length > 0) {
        const contactsWithPhones = data
          .filter(contact => contact.phoneNumbers && contact.phoneNumbers.length > 0)
          .map(contact => ({
            id: contact.id || Math.random().toString(),
            name: contact.name || 'Unknown',
            phoneNumber: formatPhoneNumber(contact.phoneNumbers![0].number || ''),
            selected: false,
          }));
        setPhoneContacts(contactsWithPhones);
      } else {
        Alert.alert('No Contacts', 'No contacts with phone numbers found');
      }
    } catch (error) {
      console.error('Error loading contacts:', error);
      Alert.alert('Error', 'Failed to load contacts');
    } finally {
      setLoadingContacts(false);
    }
  };

  const formatPhoneNumber = (phone: string, country?: Country) => {
    let cleaned = phone.replace(/\D/g, '');

    // If starts with 0, replace with country dial code
    if (cleaned.startsWith('0')) {
      const dial = (country || customerCountry).dial.replace('+', '');
      cleaned = dial + cleaned.substring(1);
    }

    // Add + if not present
    if (!cleaned.startsWith('+')) {
      cleaned = '+' + cleaned;
    }

    return cleaned;
  };

  const toggleContactSelection = (contactId: string) => {
    setPhoneContacts(phoneContacts.map(c =>
      c.id === contactId ? { ...c, selected: !c.selected } : c
    ));
  };

  const selectAllContacts = () => {
    const allSelected = filteredPhoneContacts.every(c => c.selected);
    setPhoneContacts(phoneContacts.map(c => ({
      ...c,
      selected: filteredPhoneContacts.some(fc => fc.id === c.id) ? !allSelected : c.selected
    })));
  };

  const importSelectedContacts = async () => {
    const selected = phoneContacts.filter(c => c.selected);
    if (selected.length === 0) {
      Alert.alert('No Selection', 'Please select contacts to import');
      return;
    }

    setImportingContacts(true);
    let imported = 0;
    let failed = 0;

    for (const contact of selected) {
      try {
        await apiClient.post('/customers', {
          name: contact.name,
          phone_number: contact.phoneNumber,
          notes: null,
          tags: ['New'],
        });
        imported++;
      } catch (error) {
        failed++;
      }
    }

    setImportingContacts(false);
    setContactsModalVisible(false);
    setPhoneContacts([]);
    fetchCustomers();

    Alert.alert(
      'Import Complete',
      `Successfully imported ${imported} contact${imported !== 1 ? 's' : ''}${failed > 0 ? `\n${failed} failed (may already exist)` : ''}`
    );
  };

  const filteredPhoneContacts = phoneContacts.filter(c =>
    c.name.toLowerCase().includes(contactSearch.toLowerCase()) ||
    c.phoneNumber.includes(contactSearch)
  );

  const selectedCount = phoneContacts.filter(c => c.selected).length;

  const openEditModal = (customer: Customer) => {
    setSelectedCustomer(customer);
    setNewName(customer.name);
    setNewPhone(customer.phone_number);
    setNewNotes(customer.notes || '');
    setNewTags(customer.tags);
    setEditModalVisible(true);
  };

  const filteredCustomers = customers.filter(c => {
    // If search query is a "command" (handled by backend), don't filter client-side
    const queryLower = searchQuery.toLowerCase();
    if (queryLower.includes('top') || queryLower.includes('best') ||
      queryLower.includes('highest') || queryLower.includes('vip') ||
      queryLower.includes('returning') || (queryLower.includes('new') && !queryLower.includes('news'))) { // simple check
      return true;
    }

    return c.name.toLowerCase().includes(queryLower) ||
      c.phone_number.includes(queryLower);
  });

  const toggleTag = (tag: string) => {
    if (newTags.includes(tag)) {
      setNewTags(newTags.filter(t => t !== tag));
    } else {
      setNewTags([...newTags, tag]);
    }
  };

  const handleWhatsApp = (customer: Customer) => {
    router.push({
      pathname: '/chat',
      params: {
        customerId: customer.id,
        customerName: customer.name,
        customerPhone: customer.phone_number,
      },
    });
  };

  const handleShowDraftMessage = async (customer: Customer, direction?: string) => {
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
      setDraftReason(response.data.reason || response.data.ai_reason || 'Based on your interaction history');
    } catch (error) {
      console.error('Error fetching draft message:', error);
      setDraftMessage(`Hi ${customer.name}, just checking in! How can I help you today?`);
      setDraftReason('Generic follow-up message');
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
    setCustomDirection('');
  };

  // Product picker handlers
  const handleOpenProductPicker = async (customer: Customer) => {
    setProductPickerCustomer(customer);
    setShowProductPicker(true);
    setLoadingProducts(true);
    setSelectedProductIds([]);
    try {
      const data = await productsAPI.getProducts();
      setPickerProducts(data.filter((p: any) => p.in_stock !== false));
    } catch (error) {
      console.error('Error fetching products:', error);
    } finally {
      setLoadingProducts(false);
    }
  };

  const toggleProductSelection = (productId: string) => {
    setSelectedProductIds(prev =>
      prev.includes(productId) ? prev.filter(id => id !== productId) : [...prev, productId]
    );
  };

  const handleSendProduct = async (product: any) => {
    if (!productPickerCustomer) return;
    setSendingProduct(product.id);
    try {
      await productsAPI.sendProductToCustomer(product.id, productPickerCustomer.id);
      Alert.alert('Sent!', `${product.name} sent to ${productPickerCustomer.name} via WhatsApp`);
      setShowProductPicker(false);
      setProductPickerCustomer(null);
    } catch (error: any) {
      // Fallback: navigate to chat with product message pre-filled
      const desc = product.description ? `\n${product.description}` : '';
      const text = `*${product.name}*\n${currency} ${product.price.toLocaleString()}${desc}\n\nInterested? Let me know!`;
      setShowProductPicker(false);
      router.push({
        pathname: '/chat',
        params: {
          customerId: productPickerCustomer.id,
          customerName: productPickerCustomer.name,
          customerPhone: productPickerCustomer.phone_number,
          prefill: text,
        },
      });
      setProductPickerCustomer(null);
    } finally {
      setSendingProduct(null);
    }
  };

  const handleSendCatalog = async () => {
    if (!productPickerCustomer || selectedProductIds.length === 0) return;
    setSendingCatalog(true);
    try {
      const result = await productsAPI.sendCatalog(productPickerCustomer.id, selectedProductIds);
      Alert.alert('Catalog Sent!', `${result.products_sent} products sent to ${productPickerCustomer.name} via WhatsApp. They can reply to order!`);
      setShowProductPicker(false);
      setProductPickerCustomer(null);
      setSelectedProductIds([]);
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to send catalog');
    } finally {
      setSendingCatalog(false);
    }
  };

  const handleCreateOrderFromProduct = async (product: any) => {
    if (!productPickerCustomer) return;
    try {
      await apiClient.post('/orders', {
        customer_id: productPickerCustomer.id,
        product: product.name,
        quantity: 1,
        price: product.price,
        total_amount: product.price,
      });
      Alert.alert('Order Created!', `Order for ${product.name} (${currency} ${product.price.toLocaleString()}) created for ${productPickerCustomer.name}`);
      setShowProductPicker(false);
      setProductPickerCustomer(null);
    } catch (error) {
      console.error('Error creating order:', error);
      Alert.alert('Error', 'Failed to create order');
    }
  };

  const handleSendDraftMessage = () => {
    if (!draftCustomer) return;

    const text = draftMessage || `Hi ${draftCustomer.name}, just checking in!`;

    setShowDraftModal(false);

    // Navigate to in-app chat with message pre-filled
    router.push({
      pathname: '/chat',
      params: {
        customerId: draftCustomer.id,
        customerName: draftCustomer.name,
        customerPhone: draftCustomer.phone_number,
        prefill: text,
      },
    });

    // Reset
    setDraftMessage('');
    setDraftReason('');
    setDraftCustomer(null);
    setCustomDirection('');
  };

  const TAG_COLORS: Record<string, string> = {
    VIP: '#FFD700',
    New: '#25D366',
    Returning: '#4A90D9',
    Wholesale: '#9B59B6',
  };

  const RotatingBadge = ({ tags, purchaseCount }: { tags: string[]; purchaseCount: number }) => {
    const items: { label: string; color: string }[] = [];
    tags.forEach(t => items.push({ label: t, color: TAG_COLORS[t] || '#8696A0' }));
    if (purchaseCount > 0) {
      items.push({ label: `${purchaseCount} ${purchaseCount === 1 ? 'Sale' : 'Sales'}`, color: '#00A884' });
    }

    const [index, setIndex] = useState(0);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
      if (items.length <= 1) return;
      timerRef.current = setInterval(() => {
        setIndex(prev => (prev + 1) % items.length);
      }, 2000);
      return () => { if (timerRef.current) clearInterval(timerRef.current); };
    }, [items.length]);

    if (items.length === 0) return null;
    const item = items[index % items.length];

    return (
      <View style={[styles.chatRowBadge, { backgroundColor: item.color }]}>
        <Text style={styles.chatRowBadgeText}>{item.label}</Text>
      </View>
    );
  };

  const formatLastContact = (dateStr: string | null) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return d.toLocaleDateString([], { weekday: 'short' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const renderCustomer = ({ item }: { item: Customer }) => (
    <TouchableOpacity
      style={styles.chatRow}
      onPress={() => handleWhatsApp(item)}
      onLongPress={() => openEditModal(item)}
      delayLongPress={400}
    >
      <View style={[styles.customerAvatar, item.tags.includes('VIP') && { backgroundColor: '#FFD700' }]}>
        <Text style={styles.avatarText}>{item.name.charAt(0).toUpperCase()}</Text>
      </View>
      <View style={styles.chatRowContent}>
        <View style={styles.chatRowTop}>
          <Text style={styles.chatRowName} numberOfLines={1}>{item.name}</Text>
          <Text style={styles.chatRowTime}>{formatLastContact(item.last_contacted)}</Text>
        </View>
        <View style={styles.chatRowBottom}>
          <Text style={styles.chatRowMessage} numberOfLines={1}>
            {item.last_message || item.notes || item.phone_number}
          </Text>
          <RotatingBadge tags={item.tags} purchaseCount={item.purchase_count} />
        </View>
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
            <View style={styles.phoneRow}>
              {!isEdit && (
                <CountryPicker
                  selectedCountry={customerCountry}
                  onSelect={setCustomerCountry}
                />
              )}
              <View style={{ flex: 1 }}>
                <TextInput
                  style={[styles.formInput, isEdit && styles.inputDisabled]}
                  value={newPhone}
                  onChangeText={setNewPhone}
                  placeholder="Phone number"
                  placeholderTextColor="#666"
                  keyboardType="phone-pad"
                  editable={!isEdit}
                />
              </View>
            </View>
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
              {[...new Set([...TAGS, ...newTags])].map((tag) => (
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
              {showTagInput ? (
                <View style={styles.addTagInputRow}>
                  <TextInput
                    style={styles.addTagInput}
                    value={newTagText}
                    onChangeText={setNewTagText}
                    placeholder="Tag name"
                    placeholderTextColor="#666"
                    autoFocus
                    onSubmitEditing={() => {
                      const t = newTagText.trim();
                      if (t && !newTags.includes(t)) setNewTags(prev => [...prev, t]);
                      setNewTagText('');
                      setShowTagInput(false);
                    }}
                    returnKeyType="done"
                  />
                  <TouchableOpacity onPress={() => {
                    const t = newTagText.trim();
                    if (t && !newTags.includes(t)) setNewTags(prev => [...prev, t]);
                    setNewTagText('');
                    setShowTagInput(false);
                  }}>
                    <Ionicons name="checkmark" size={18} color="#25D366" />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => { setShowTagInput(false); setNewTagText(''); }} style={{ marginLeft: 4 }}>
                    <Ionicons name="close" size={18} color="#666" />
                  </TouchableOpacity>
                </View>
              ) : (
                <TouchableOpacity style={styles.addTagButton} onPress={() => setShowTagInput(true)}>
                  <Ionicons name="add" size={16} color="#25D366" />
                  <Text style={styles.addTagButtonText}>Add Tag</Text>
                </TouchableOpacity>
              )}
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

      {/* Sorting Toggle */}
      <View style={styles.sortContainer}>
        <TouchableOpacity
          style={[styles.sortButton, sortBy === 'recently_contacted' && styles.sortButtonActive]}
          onPress={() => setSortBy('recently_contacted')}
        >
          <Ionicons
            name="chatbubble-outline"
            size={16}
            color={sortBy === 'recently_contacted' ? '#FFFFFF' : '#666'}
          />
          <Text style={[styles.sortText, sortBy === 'recently_contacted' && styles.sortTextActive]}>
            Recently Contacted
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.sortButton, sortBy === 'recently_added' && styles.sortButtonActive]}
          onPress={() => setSortBy('recently_added')}
        >
          <Ionicons
            name="time-outline"
            size={16}
            color={sortBy === 'recently_added' ? '#FFFFFF' : '#666'}
          />
          <Text style={[styles.sortText, sortBy === 'recently_added' && styles.sortTextActive]}>
            Recently Added
          </Text>
        </TouchableOpacity>
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

      {/* WhatsApp-style Floating Action Button with Menu */}
      <View style={[styles.fabContainer, { bottom: insets.bottom + 30 }]}>
        <TouchableOpacity
          style={styles.fabSecondary}
          onPress={() => {
            setContactsModalVisible(true);
            loadPhoneContacts();
          }}
          activeOpacity={0.8}
        >
          <Ionicons name="cloud-upload" size={22} color="#FFFFFF" />
          <Text style={styles.fabSecondaryText}>Import</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.fab}
          onPress={() => setModalVisible(true)}
          activeOpacity={0.8}
        >
          <Ionicons name="add" size={28} color="#FFFFFF" />
        </TouchableOpacity>
      </View>

      {renderModal(false)}
      {renderModal(true)}

      {/* AI Draft Message Modal */}
      <Modal
        visible={showDraftModal}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => {
          setShowDraftModal(false);
          setDraftMessage('');
          setDraftReason('');
        }}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => {
              setShowDraftModal(false);
              setDraftMessage('');
              setDraftReason('');
            }}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <View style={styles.aiModalTitleRow}>
              <Ionicons name="sparkles" size={20} color="#FFD700" />
              <Text style={styles.modalTitle}>AI Draft Message</Text>
            </View>
            <TouchableOpacity onPress={handleSendDraftMessage}>
              <Text style={styles.modalSave}>Send</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.draftModalContent}>
            {draftCustomer && (
              <View style={styles.draftCustomerInfo}>
                <View style={styles.customerAvatar}>
                  <Text style={styles.avatarText}>{draftCustomer.name.charAt(0).toUpperCase()}</Text>
                </View>
                <View>
                  <Text style={styles.draftCustomerName}>{draftCustomer.name}</Text>
                  <Text style={styles.draftCustomerPhone}>{draftCustomer.phone_number}</Text>
                </View>
              </View>
            )}

            {loadingDraft ? (
              <View style={styles.draftLoadingContainer}>
                <ActivityIndicator size="large" color="#25D366" />
                <Text style={styles.draftLoadingText}>AI is drafting your message...</Text>
              </View>
            ) : (
              <>
                <View style={styles.draftReasonContainer}>
                  <Ionicons name="bulb" size={20} color="#FFD700" />
                  <Text style={styles.draftReasonText}>{draftReason}</Text>
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

                <View style={styles.draftMessageContainer}>
                  <Text style={styles.draftLabel}>Message:</Text>
                  <TextInput
                    style={styles.draftMessageInput}
                    value={draftMessage}
                    onChangeText={setDraftMessage}
                    multiline
                    numberOfLines={8}
                    placeholder="Edit the AI-generated message..."
                    placeholderTextColor="#666"
                  />
                </View>

                <View style={styles.regenerateSection}>
                  <Text style={styles.draftLabel}>Give AI Direction (Optional):</Text>
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
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Product Picker Modal */}
      <Modal
        visible={showProductPicker}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => { setShowProductPicker(false); setProductPickerCustomer(null); }}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => { setShowProductPicker(false); setProductPickerCustomer(null); }}>
              <Text style={styles.modalCancel}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Send Product</Text>
            <View style={{ width: 50 }} />
          </View>

          {productPickerCustomer && (
            <View style={styles.pickerCustomerBar}>
              <Ionicons name="person-outline" size={16} color="#8899AA" />
              <Text style={styles.pickerCustomerName}>To: {productPickerCustomer.name}</Text>
              {selectedProductIds.length > 0 && (
                <View style={styles.pickerSelectedBadge}>
                  <Text style={styles.pickerSelectedText}>{selectedProductIds.length} selected</Text>
                </View>
              )}
            </View>
          )}

          {loadingProducts ? (
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
              <ActivityIndicator size="large" color="#25D366" />
              <Text style={{ color: '#8899AA', marginTop: 12 }}>Loading products...</Text>
            </View>
          ) : pickerProducts.length > 0 ? (
            <>
              <FlatList
                data={pickerProducts}
                keyExtractor={(item) => item.id}
                contentContainerStyle={{ padding: 16, paddingBottom: selectedProductIds.length > 0 ? 80 : 16 }}
                renderItem={({ item: product }) => {
                  const imageUri = product.image_url
                    ? (product.image_url.startsWith('http') ? product.image_url : `${process.env.EXPO_PUBLIC_BACKEND_URL}${product.image_url}`)
                    : null;
                  const isSending = sendingProduct === product.id;
                  const isSelected = selectedProductIds.includes(product.id);

                  return (
                    <TouchableOpacity
                      style={[styles.pickerProductCard, isSelected && styles.pickerProductCardSelected]}
                      onPress={() => toggleProductSelection(product.id)}
                      activeOpacity={0.7}
                    >
                      {/* Checkbox */}
                      <View style={[styles.pickerCheckbox, isSelected && styles.pickerCheckboxSelected]}>
                        {isSelected && <Ionicons name="checkmark" size={14} color="#FFF" />}
                      </View>
                      {imageUri ? (
                        <Image source={{ uri: imageUri }} style={styles.pickerProductImage} resizeMode="cover" />
                      ) : (
                        <View style={[styles.pickerProductImage, { justifyContent: 'center', alignItems: 'center', backgroundColor: '#1A2942' }]}>
                          <Ionicons name="image-outline" size={24} color="#3A4A5C" />
                        </View>
                      )}
                      <View style={styles.pickerProductInfo}>
                        <Text style={styles.pickerProductName} numberOfLines={1}>{product.name}</Text>
                        <Text style={styles.pickerProductPrice}>{currency} {product.price.toLocaleString()}</Text>
                        <Text style={styles.pickerProductCategory}>{product.category || 'Other'}</Text>
                      </View>
                      <View style={styles.pickerActions}>
                        <TouchableOpacity
                          style={styles.pickerSendBtn}
                          onPress={() => handleSendProduct(product)}
                          disabled={isSending}
                        >
                          {isSending ? (
                            <ActivityIndicator size="small" color="#FFF" />
                          ) : (
                            <>
                              <Ionicons name="send" size={14} color="#FFF" />
                              <Text style={styles.pickerSendText}>Send</Text>
                            </>
                          )}
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={styles.pickerOrderBtn}
                          onPress={() => handleCreateOrderFromProduct(product)}
                        >
                          <Ionicons name="cart-outline" size={14} color="#25D366" />
                          <Text style={styles.pickerOrderText}>Order</Text>
                        </TouchableOpacity>
                      </View>
                    </TouchableOpacity>
                  );
                }}
              />
              {/* Send Catalog floating bar */}
              {selectedProductIds.length > 0 && (
                <View style={styles.catalogBar}>
                  <TouchableOpacity style={styles.catalogClearBtn} onPress={() => setSelectedProductIds([])}>
                    <Ionicons name="close-circle" size={20} color="#8899AA" />
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.catalogSendBtn, sendingCatalog && { opacity: 0.6 }]}
                    onPress={handleSendCatalog}
                    disabled={sendingCatalog}
                  >
                    {sendingCatalog ? (
                      <ActivityIndicator size="small" color="#FFF" />
                    ) : (
                      <>
                        <Ionicons name="list-outline" size={18} color="#FFF" />
                        <Text style={styles.catalogSendText}>Send Catalog ({selectedProductIds.length})</Text>
                      </>
                    )}
                  </TouchableOpacity>
                </View>
              )}
            </>
          ) : (
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
              <Ionicons name="storefront-outline" size={48} color="#3A4A5C" />
              <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginTop: 12 }}>No products yet</Text>
              <Text style={{ color: '#8899AA', fontSize: 13, marginTop: 6, textAlign: 'center' }}>Add products in your Product Catalog first</Text>
            </View>
          )}
        </SafeAreaView>
      </Modal>

      {/* Import Contacts Modal */}
      <Modal
        visible={contactsModalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => {
          setContactsModalVisible(false);
          setPhoneContacts([]);
          setContactSearch('');
        }}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => {
              setContactsModalVisible(false);
              setPhoneContacts([]);
              setContactSearch('');
            }}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Import Contacts</Text>
            <TouchableOpacity onPress={importSelectedContacts} disabled={importingContacts || selectedCount === 0}>
              <Text style={[styles.modalSave, (importingContacts || selectedCount === 0) && styles.modalSaveDisabled]}>
                {importingContacts ? 'Importing...' : `Import (${selectedCount})`}
              </Text>
            </TouchableOpacity>
          </View>

          <View style={styles.contactsSearchContainer}>
            <Ionicons name="search" size={20} color="#666" style={styles.searchIcon} />
            <TextInput
              style={styles.searchInput}
              value={contactSearch}
              onChangeText={setContactSearch}
              placeholder="Search contacts..."
              placeholderTextColor="#666"
            />
          </View>

          <TouchableOpacity style={styles.selectAllButton} onPress={selectAllContacts}>
            <Ionicons
              name={filteredPhoneContacts.length > 0 && filteredPhoneContacts.every(c => c.selected) ? "checkbox" : "square-outline"}
              size={24}
              color="#25D366"
            />
            <Text style={styles.selectAllText}>Select All</Text>
            <Text style={styles.contactCount}>{filteredPhoneContacts.length} contacts</Text>
          </TouchableOpacity>

          {loadingContacts ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#25D366" />
              <Text style={styles.loadingText}>Loading contacts...</Text>
            </View>
          ) : (
            <FlatList
              data={filteredPhoneContacts}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={styles.contactItem}
                  onPress={() => toggleContactSelection(item.id)}
                >
                  <Ionicons
                    name={item.selected ? "checkbox" : "square-outline"}
                    size={24}
                    color={item.selected ? "#25D366" : "#666"}
                  />
                  <View style={styles.contactInfo}>
                    <Text style={styles.contactName}>{item.name}</Text>
                    <Text style={styles.contactPhone}>{item.phoneNumber}</Text>
                  </View>
                </TouchableOpacity>
              )}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.contactsList}
              ListEmptyComponent={
                <View style={styles.emptyContainer}>
                  <Ionicons name="people-outline" size={48} color="#666" />
                  <Text style={styles.emptyText}>No contacts found</Text>
                  <Text style={styles.emptySubtext}>
                    {Platform.OS === 'web'
                      ? 'Contact import is available on mobile devices only'
                      : 'Allow contact access to import'}
                  </Text>
                </View>
              }
            />
          )}
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
  sortContainer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 12,
    gap: 8,
  },
  sortButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1A2942',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 12,
    gap: 6,
  },
  sortButtonActive: {
    backgroundColor: '#25D366',
  },
  sortText: {
    fontSize: 13,
    fontWeight: '500',
    color: '#666',
  },
  sortTextActive: {
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
    paddingBottom: 150,
  },
  chatRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.04)',
  },
  customerAvatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  avatarText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  chatRowContent: {
    flex: 1,
  },
  chatRowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  chatRowName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    flex: 1,
    marginRight: 8,
  },
  chatRowTime: {
    fontSize: 12,
    color: '#8B9DC3',
  },
  chatRowBottom: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  chatRowMessage: {
    fontSize: 14,
    color: '#8B9DC3',
    flex: 1,
    marginRight: 8,
  },
  chatRowBadge: {
    borderRadius: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginLeft: 4,
  },
  chatRowBadgeText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#FFFFFF',
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
  phoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
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
    flexWrap: 'wrap',
    gap: 8,
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
  addTagButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: 'rgba(37,211,102,0.1)',
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#25D366',
    borderStyle: 'dashed',
  },
  addTagButtonText: {
    fontSize: 14,
    color: '#25D366',
    fontWeight: '500',
  },
  addTagInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: '#25D366',
    gap: 6,
  },
  addTagInput: {
    fontSize: 14,
    color: '#FFFFFF',
    minWidth: 80,
    paddingVertical: 0,
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
  fabContainer: {
    position: 'absolute',
    right: 24,
    alignItems: 'flex-end',
    gap: 12,
  },
  fabSecondary: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#4A90D9',
    borderRadius: 25,
    paddingHorizontal: 16,
    paddingVertical: 12,
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.25,
    shadowRadius: 6,
  },
  fabSecondaryText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 8,
  },
  regenerateSection: {
    marginTop: 8,
  },
  directionInput: {
    backgroundColor: '#1A2942',
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
  aiModalTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  draftModalContent: {
    flex: 1,
    padding: 20,
  },
  draftCustomerInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    padding: 16,
    borderRadius: 12,
    marginBottom: 20,
  },
  draftCustomerName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginLeft: 12,
  },
  draftCustomerPhone: {
    fontSize: 14,
    color: '#666',
    marginLeft: 12,
  },
  draftLoadingContainer: {
    alignItems: 'center',
    paddingVertical: 40,
  },
  draftLoadingText: {
    fontSize: 16,
    color: '#666',
    marginTop: 16,
  },
  draftReasonContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#1A2942',
    padding: 16,
    borderRadius: 12,
    marginBottom: 20,
  },
  draftReasonText: {
    flex: 1,
    fontSize: 14,
    color: '#FFD700',
    marginLeft: 12,
    lineHeight: 20,
  },
  draftMessageContainer: {
    marginBottom: 20,
  },
  draftLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  draftMessageInput: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: '#FFFFFF',
    minHeight: 150,
    textAlignVertical: 'top',
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
  contactsSearchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    marginHorizontal: 20,
    borderRadius: 12,
    paddingHorizontal: 16,
    marginBottom: 12,
  },
  selectAllButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  selectAllText: {
    flex: 1,
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginLeft: 12,
  },
  contactCount: {
    fontSize: 14,
    color: '#666',
  },
  loadingText: {
    fontSize: 14,
    color: '#666',
    marginTop: 12,
  },
  contactsList: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  contactItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  contactInfo: {
    flex: 1,
    marginLeft: 12,
  },
  contactName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  contactPhone: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },
  recentMessagesSection: {
    marginBottom: 20,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    overflow: 'hidden',
  },
  recentMessagesHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
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
    paddingHorizontal: 16,
    paddingBottom: 16,
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
  // Product Picker Styles
  pickerCustomerBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 20,
    paddingVertical: 10,
    backgroundColor: '#1A2942',
    borderBottomWidth: 1,
    borderBottomColor: '#2A3A52',
  },
  pickerCustomerName: {
    color: '#CCD6E0',
    fontSize: 14,
    fontWeight: '600',
  },
  pickerProductCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 10,
    marginBottom: 10,
    gap: 12,
  },
  pickerProductImage: {
    width: 56,
    height: 56,
    borderRadius: 10,
    backgroundColor: '#0D1B2A',
  },
  pickerProductInfo: {
    flex: 1,
  },
  pickerProductName: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  pickerProductPrice: {
    color: '#25D366',
    fontSize: 13,
    fontWeight: '700',
    marginTop: 2,
  },
  pickerProductCategory: {
    color: '#8899AA',
    fontSize: 11,
    marginTop: 2,
  },
  pickerActions: {
    gap: 6,
  },
  pickerSendBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#25D366',
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 8,
    gap: 4,
  },
  pickerSendText: {
    color: '#FFF',
    fontSize: 12,
    fontWeight: '600',
  },
  pickerOrderBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0D1B2A',
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 8,
    gap: 4,
    borderWidth: 1,
    borderColor: '#25D366',
  },
  pickerOrderText: {
    color: '#25D366',
    fontSize: 12,
    fontWeight: '600',
  },
  pickerProductCardSelected: {
    borderWidth: 1.5,
    borderColor: '#25D366',
  },
  pickerCheckbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#3A4A5C',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pickerCheckboxSelected: {
    backgroundColor: '#25D366',
    borderColor: '#25D366',
  },
  pickerSelectedBadge: {
    marginLeft: 'auto',
    backgroundColor: '#25D366',
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 12,
  },
  pickerSelectedText: {
    color: '#FFF',
    fontSize: 12,
    fontWeight: '700',
  },
  catalogBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0D1B2A',
    borderTopWidth: 1,
    borderTopColor: '#2A3A52',
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 12,
  },
  catalogClearBtn: {
    padding: 4,
  },
  catalogSendBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    paddingVertical: 12,
    borderRadius: 10,
    gap: 8,
  },
  catalogSendText: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '700',
  },
});
