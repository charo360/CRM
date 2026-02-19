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
  Switch,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { apiClient, productsAPI, settingsAPI, suppliersAPI, classificationAPI, dashboardAPI, messageHelpers } from '../../context/api';
import { useRouter, useLocalSearchParams, useNavigation } from 'expo-router';
import * as Contacts from 'expo-contacts';
import CountryPicker, { Country, COUNTRIES } from '../../components/CountryPicker';

interface Customer {
  id: string;
  name: string;
  phone_number: string;
  notes: string | null;
  tags: string[];
  stage: string;
  purchase_count: number;
  total_spent: number;
  last_message: string | null;
  last_contacted: string | null;
  profile_picture: string | null;
  auto_reply: boolean;
  unread_count: number;
  created_at: string;
}

interface DashboardSummary {
  unread_messages: number;
  followups_today: number;
  sales_today: number;
  sales_count_today: number;
  total_customers: number;
}

const STAGES = ['all', 'lead', 'contacted', 'negotiating', 'won', 'lost'] as const;
const STAGE_COLORS: Record<string, string> = {
  lead: '#8696A0',
  contacted: '#4A90D9',
  negotiating: '#FF9800',
  won: '#25D366',
  lost: '#FF4444',
};
const STAGE_LABELS: Record<string, string> = {
  all: 'All',
  lead: 'Lead',
  contacted: 'Contacted',
  negotiating: 'Negotiating',
  won: 'Won',
  lost: 'Lost',
};

interface PhoneContact {
  id: string;
  name: string;
  phoneNumber: string;
  selected: boolean;
}

const TAGS = ['New', 'Returning', 'VIP'];

const CATEGORY_COLORS: Record<string, string> = {
  'Electronics': '#4A90D9',
  'Clothing': '#9B59B6',
  'Food & Beverage': '#E67E22',
  'Beauty & Health': '#E91E63',
  'Home & Garden': '#27AE60',
  'Automotive': '#607D8B',
  'Raw Materials': '#795548',
  'Packaging': '#00BCD4',
  'Stationery': '#FF9800',
  'Services': '#3F51B5',
  'Other': '#8696A0',
};

const CATEGORY_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  'Electronics': 'hardware-chip-outline',
  'Clothing': 'shirt-outline',
  'Food & Beverage': 'restaurant-outline',
  'Beauty & Health': 'heart-outline',
  'Home & Garden': 'home-outline',
  'Automotive': 'car-outline',
  'Raw Materials': 'cube-outline',
  'Packaging': 'gift-outline',
  'Stationery': 'pencil-outline',
  'Services': 'construct-outline',
  'Other': 'business-outline',
};

interface Message {
  id: string;
  direction: 'incoming' | 'outgoing';
  content: string;
  created_at: string;
}

export default function CustomersScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string }>();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'recently_added' | 'recently_contacted'>('recently_added');
  const [modalVisible, setModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);

  // Suppliers mode state
  const [viewMode, setViewMode] = useState<'customers' | 'suppliers'>('customers');
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [supplierCategories, setSupplierCategories] = useState<string[]>([]);
  const [selectedSupplierCategory, setSelectedSupplierCategory] = useState<string | null>(null);
  const [loadingSupplierData, setLoadingSupplierData] = useState(false);
  const [supplierDetailVisible, setSupplierDetailVisible] = useState(false);
  const [selectedSupplier, setSelectedSupplier] = useState<any | null>(null);
  const [editingSupplierCategory, setEditingSupplierCategory] = useState('Other');
  const [editingPaymentTerms, setEditingPaymentTerms] = useState('');
  const [editingLeadTime, setEditingLeadTime] = useState('');
  const [editingRating, setEditingRating] = useState(0);
  const [savingSupplier, setSavingSupplier] = useState(false);

  // AI Classification
  const [pendingClassifications, setPendingClassifications] = useState<any[]>([]);
  const [scanningContacts, setScanningContacts] = useState(false);

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
  const [newAutoReply, setNewAutoReply] = useState(false);

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
  const [aiModel, setAiModel] = useState('standard');
  const [showModelSelector, setShowModelSelector] = useState(false);
  const [selectedStage, setSelectedStage] = useState<string>('all');
  const [dashboardSummary, setDashboardSummary] = useState<DashboardSummary | null>(null);

  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const navigation = useNavigation();

  const loadSettings = async () => {
    try {
      const settings = await settingsAPI.getSettings();
      if (settings.currency) setCurrency(settings.currency);
      if (settings.ai_model) setAiModel(settings.ai_model);
    } catch (e) { }
  };

  const fetchDashboard = async () => {
    try {
      const data = await dashboardAPI.getSummary();
      setDashboardSummary(data);
    } catch (e) { }
  };

  useEffect(() => {
    loadSettings();
    fetchDashboard();
  }, []);

  const getModelShortName = (modelId: string) => {
    switch (modelId) {
      case 'standard': return 'GPT-4o Mini';
      case 'premium': return 'GPT-4o';
      case 'gpt-5': return 'GPT-5';
      case 'claude-3.5': return 'Claude 3.5';
      case 'sonnet-4.5': return 'Sonnet 4.5';
      case 'grok': return 'Grok 4.1';
      case 'deepseek': return 'DeepSeek';
      default: return 'AI';
    }
  };

  React.useLayoutEffect(() => {
    navigation.setOptions({
      headerTitle: () => (
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Text style={{ color: '#FFFFFF', fontSize: 20, fontWeight: 'bold' }}>Customers</Text>
          <TouchableOpacity
            onPress={() => setShowModelSelector(true)}
            style={{
              marginLeft: 16,
              backgroundColor: aiModel === 'standard' ? 'rgba(255,255,255,0.1)' : '#25D366',
              paddingHorizontal: 8,
              paddingVertical: 4,
              borderRadius: 12,
              flexDirection: 'row',
              alignItems: 'center'
            }}
          >
            <Ionicons name="hardware-chip" size={12} color={aiModel === 'standard' ? '#8B9DC3' : '#FFFFFF'} style={{ marginRight: 4 }} />
            <Text style={{ color: aiModel === 'standard' ? '#8B9DC3' : '#FFFFFF', fontSize: 12, fontWeight: '600' }}>
              {getModelShortName(aiModel)}
            </Text>
          </TouchableOpacity>
        </View>
      ),
    });
  }, [navigation, aiModel]);

  const handleModelSelect = async (model: string) => {
    setAiModel(model);
    setShowModelSelector(false);
    try {
      await settingsAPI.updateSettings({ ai_model: model });
    } catch (error) {
      console.error('Failed to update AI model');
    }
  };

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
    // Debounce search to prevent too many API calls
    const timeoutId = setTimeout(() => {
      fetchCustomers();
    }, 500);
    return () => clearTimeout(timeoutId);
  }, [fetchCustomers]);



  // Handle route param from account tab
  useEffect(() => {
    if (params.mode === 'suppliers') {
      setViewMode('suppliers');
    }
  }, [params.mode]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchCustomers();
    fetchPendingClassifications();
    fetchDashboard();
    if (viewMode === 'suppliers') {
      fetchSupplierData();
    }
  };

  const fetchSupplierData = useCallback(async () => {
    setLoadingSupplierData(true);
    try {
      const suppliersData = await suppliersAPI.getSuppliers();
      setSuppliers(suppliersData);
      setSupplierCategories(Object.keys(CATEGORY_COLORS));
    } catch (error) {
      console.error('Error fetching supplier data:', error);
    } finally {
      setLoadingSupplierData(false);
    }
  }, []);

  const openSupplierDetail = (supplier: any) => {
    setSelectedSupplier(supplier);
    setEditingSupplierCategory(supplier.supplier_category || 'Other');
    setEditingPaymentTerms(supplier.payment_terms || '');
    setEditingLeadTime(supplier.lead_time || '');
    setEditingRating(supplier.rating || 0);
    setSupplierDetailVisible(true);
  };

  const saveSupplierDetails = async () => {
    if (!selectedSupplier) return;
    setSavingSupplier(true);
    try {
      await suppliersAPI.updateSupplier(selectedSupplier.id || selectedSupplier._id, {
        supplier_category: editingSupplierCategory,
        payment_terms: editingPaymentTerms,
        lead_time: editingLeadTime,
        rating: editingRating,
      });
      setSupplierDetailVisible(false);
      fetchSupplierData();
    } catch (error) {
      Alert.alert('Error', 'Failed to save supplier details');
    } finally {
      setSavingSupplier(false);
    }
  };

  const removeSupplier = async (supplierId: string) => {
    Alert.alert('Remove Supplier', 'This will remove the supplier tag. The contact will remain as a customer.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove', style: 'destructive', onPress: async () => {
          try {
            await suppliersAPI.removeSupplier(supplierId);
            setSupplierDetailVisible(false);
            fetchSupplierData();
            fetchCustomers();
          } catch (error) {
            Alert.alert('Error', 'Failed to remove supplier');
          }
        }
      }
    ]);
  };

  // AI Classification functions
  const fetchPendingClassifications = useCallback(async () => {
    try {
      const data = await classificationAPI.getPending();
      setPendingClassifications(data || []);
    } catch (error) {
      console.error('Error fetching pending classifications:', error);
    }
  }, []);

  const scanAllContacts = async () => {
    setScanningContacts(true);
    try {
      await classificationAPI.scanContacts();
      await fetchPendingClassifications();
    } catch (error) {
      console.error('Error scanning contacts:', error);
    } finally {
      setScanningContacts(false);
    }
  };

  useEffect(() => {
    fetchPendingClassifications();
  }, [fetchPendingClassifications]);

  const confirmClassification = async (customerId: string, type: 'customer' | 'supplier') => {
    try {
      await classificationAPI.confirm(customerId, 'approve', type);
      setPendingClassifications(prev => prev.filter(p => p.customer_id !== customerId));
      fetchCustomers();
      if (type === 'supplier') fetchSupplierData();
    } catch (error) {
      Alert.alert('Error', 'Failed to confirm classification');
    }
  };

  const dismissClassification = async (customerId: string) => {
    try {
      await classificationAPI.dismiss(customerId);
      setPendingClassifications(prev => prev.filter(p => p.customer_id !== customerId));
    } catch (error) {
      console.error('Error dismissing classification:', error);
    }
  };

  const filteredSuppliers = suppliers.filter(s => {
    const matchesSearch = !searchQuery || s.name.toLowerCase().includes(searchQuery.toLowerCase()) || s.phone_number.includes(searchQuery);
    const matchesCategory = !selectedSupplierCategory || s.supplier_category === selectedSupplierCategory;
    return matchesSearch && matchesCategory;
  });

  const supplierCategoryCounts = suppliers.reduce((acc: Record<string, number>, s: any) => {
    const cat = s.supplier_category || 'Other';
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  // Fetch supplier data when mode changes
  useEffect(() => {
    if (viewMode === 'suppliers') {
      fetchSupplierData();
      setNewTags(['Supplier', 'New']);
    } else {
      setNewTags(['New']);
    }
  }, [viewMode, fetchSupplierData]);

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
      // If we are in suppliers mode, refresh supplier data too
      if (viewMode === 'suppliers') {
        fetchSupplierData();
      }
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
        auto_reply: newAutoReply,
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
    setNewTags(viewMode === 'suppliers' ? ['Supplier', 'New'] : ['New']);
    setNewAutoReply(false);
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

    const isSupplierImport = viewMode === 'suppliers';
    setImportingContacts(true);
    let imported = 0;
    let failed = 0;

    for (const contact of selected) {
      try {
        const tags = isSupplierImport ? ['Supplier'] : ['New'];
        const res = await apiClient.post('/customers', {
          name: contact.name,
          phone_number: contact.phoneNumber,
          notes: isSupplierImport ? 'Imported as supplier from contacts' : null,
          tags,
        });
        // If importing as supplier, also mark classification as confirmed
        if (isSupplierImport && res.data?.id) {
          try {
            await apiClient.put(`/customers/${res.data.id}`, {
              classification_confirmed: true,
              classification_type: 'supplier',
            });
          } catch (_) { }
        }
        imported++;
      } catch (error) {
        failed++;
      }
    }

    setImportingContacts(false);
    setContactsModalVisible(false);
    setPhoneContacts([]);
    fetchCustomers();
    if (isSupplierImport) fetchSupplierData();

    const label = isSupplierImport ? 'supplier' : 'contact';
    Alert.alert(
      'Import Complete',
      `Successfully imported ${imported} ${label}${imported !== 1 ? 's' : ''}${failed > 0 ? `\n${failed} failed (may already exist)` : ''}`
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
    setNewAutoReply(customer.auto_reply || false);
    setEditModalVisible(true);
  };

  const filteredCustomers = customers.filter(c => {
    // Stage filter
    if (selectedStage !== 'all' && (c.stage || 'lead') !== selectedStage) return false;

    const queryLower = searchQuery.toLowerCase();
    if (queryLower.includes('top') || queryLower.includes('best') ||
      queryLower.includes('highest') || queryLower.includes('vip') ||
      queryLower.includes('returning') || (queryLower.includes('new') && !queryLower.includes('news'))) {
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

  const CustomerAvatar = ({ customer }: { customer: Customer }) => {
    const [imgError, setImgError] = React.useState(false);
    if (customer.profile_picture && !imgError) {
      return (
        <Image
          source={{ uri: customer.profile_picture }}
          style={[styles.customerAvatar, styles.avatarImage]}
          onError={() => setImgError(true)}
        />
      );
    }
    return (
      <View style={[styles.customerAvatar, customer.tags.includes('VIP') && { backgroundColor: '#FFD700' }]}>
        <Text style={styles.avatarText}>{customer.name.charAt(0).toUpperCase()}</Text>
      </View>
    );
  };

  const renderCustomer = ({ item }: { item: Customer }) => (
    <TouchableOpacity
      style={styles.chatRow}
      onPress={() => handleWhatsApp(item)}
      onLongPress={() => openEditModal(item)}
      delayLongPress={400}
    >
      <View>
        <CustomerAvatar customer={item} />
        {item.unread_count > 0 && (
          <View style={styles.unreadBadge}>
            <Text style={styles.unreadBadgeText}>{item.unread_count > 9 ? '9+' : item.unread_count}</Text>
          </View>
        )}
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
          <Text style={styles.modalTitle}>
            {isEdit
              ? (viewMode === 'suppliers' ? 'Edit Supplier' : 'Edit Customer')
              : (viewMode === 'suppliers' ? 'Add Supplier' : 'Add Customer')}
          </Text>
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

          {isEdit && (
            <View style={styles.formGroup}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={styles.formLabel}>AI Auto-Reply</Text>
                <Switch
                  value={newAutoReply}
                  onValueChange={setNewAutoReply}
                  trackColor={{ false: "#767577", true: "#25D366" }}
                  thumbColor={newAutoReply ? "#ffffff" : "#f4f3f4"}
                />
              </View>
              <Text style={{ color: '#8899AA', fontSize: 12, marginTop: 4 }}>
                {newAutoReply
                  ? 'Auto-reply is ENABLED for this customer.'
                  : 'Auto-reply is DISABLED for this customer.'}
              </Text>
            </View>
          )}

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

      {/* Customers / Suppliers Toggle */}
      <View style={styles.viewToggle}>
        <TouchableOpacity
          style={[styles.toggleButton, viewMode === 'customers' && styles.toggleButtonActive]}
          onPress={() => setViewMode('customers')}
        >
          <Ionicons
            name="people"
            size={18}
            color={viewMode === 'customers' ? '#FFFFFF' : '#666'}
          />
          <Text style={[styles.toggleText, viewMode === 'customers' && styles.toggleTextActive]}>Customers</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.toggleButton, viewMode === 'suppliers' && styles.toggleButtonActive]}
          onPress={() => setViewMode('suppliers')}
        >
          <Ionicons
            name="business"
            size={18}
            color={viewMode === 'suppliers' ? '#FFFFFF' : '#666'}
          />
          <Text style={[styles.toggleText, viewMode === 'suppliers' && styles.toggleTextActive]}>Suppliers</Text>
        </TouchableOpacity>
      </View>

      {/* ===== AI PENDING APPROVALS ===== */}
      {pendingClassifications.length > 0 && (
        <View style={styles.pendingBanner}>
          <View style={styles.pendingHeader}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name="sparkles" size={16} color="#FFD700" />
              <Text style={styles.pendingTitle}>AI Detected ({pendingClassifications.length})</Text>
            </View>
            <TouchableOpacity onPress={scanAllContacts} disabled={scanningContacts}>
              <Ionicons name="refresh" size={16} color="#8899AA" />
            </TouchableOpacity>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {pendingClassifications.slice(0, 10).map((item: any) => (
              <View key={item.customer_id} style={styles.pendingCard}>
                <View style={styles.pendingCardTop}>
                  <View style={[styles.pendingTypeBadge, { backgroundColor: item.suggested_type === 'supplier' ? '#4A90D920' : '#25D36620' }]}>
                    <Ionicons
                      name={item.suggested_type === 'supplier' ? 'business' : 'person'}
                      size={10}
                      color={item.suggested_type === 'supplier' ? '#4A90D9' : '#25D366'}
                    />
                    <Text style={[styles.pendingTypeText, { color: item.suggested_type === 'supplier' ? '#4A90D9' : '#25D366' }]}>
                      {item.suggested_type === 'supplier' ? 'Supplier' : 'Customer'}
                    </Text>
                  </View>
                  <Text style={styles.pendingConfidence}>{Math.round((item.confidence || 0) * 100)}%</Text>
                </View>
                <Text style={styles.pendingName} numberOfLines={1}>{item.contact_name}</Text>
                <Text style={styles.pendingReason} numberOfLines={2}>{item.reason}</Text>
                <View style={styles.pendingActions}>
                  <TouchableOpacity
                    style={styles.pendingConfirmBtn}
                    onPress={() => confirmClassification(item.customer_id, item.suggested_type)}
                  >
                    <Ionicons name="checkmark" size={14} color="#FFF" />
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.pendingDismissBtn}
                    onPress={() => dismissClassification(item.customer_id)}
                  >
                    <Ionicons name="close" size={14} color="#FF4444" />
                  </TouchableOpacity>
                  {item.suggested_type === 'supplier' && (
                    <TouchableOpacity
                      style={styles.pendingSwapBtn}
                      onPress={() => confirmClassification(item.customer_id, 'customer')}
                    >
                      <Text style={styles.pendingSwapText}>Keep as Customer</Text>
                    </TouchableOpacity>
                  )}
                  {item.suggested_type === 'customer' && (
                    <TouchableOpacity
                      style={styles.pendingSwapBtn}
                      onPress={() => confirmClassification(item.customer_id, 'supplier')}
                    >
                      <Text style={styles.pendingSwapText}>Make Supplier</Text>
                    </TouchableOpacity>
                  )}
                </View>
              </View>
            ))}
          </ScrollView>
        </View>
      )}

      {/* ===== SUPPLIER MODE ===== */}
      {viewMode === 'suppliers' ? (
        <>
          {/* Scan button when no pending classifications */}
          {pendingClassifications.length === 0 && (
            <TouchableOpacity style={styles.scanButton} onPress={scanAllContacts} disabled={scanningContacts}>
              {scanningContacts ? (
                <ActivityIndicator size="small" color="#FFD700" />
              ) : (
                <>
                  <Ionicons name="sparkles" size={14} color="#FFD700" />
                  <Text style={styles.scanButtonText}>Scan Chats to Classify Contacts</Text>
                </>
              )}
            </TouchableOpacity>
          )}

          {/* Supplier Stats Bar */}
          <View style={styles.supplierStatsBar}>
            <View style={styles.supplierStatItem}>
              <Text style={styles.supplierStatValue}>{suppliers.length}</Text>
              <Text style={styles.supplierStatLabel}>Total</Text>
            </View>
            <View style={styles.supplierStatDivider} />
            <View style={styles.supplierStatItem}>
              <Text style={styles.supplierStatValue}>{Object.keys(supplierCategoryCounts).length}</Text>
              <Text style={styles.supplierStatLabel}>Categories</Text>
            </View>
            <View style={styles.supplierStatDivider} />
            <View style={styles.supplierStatItem}>
              <Text style={[styles.supplierStatValue, { color: '#FFD700' }]}>
                {suppliers.filter(s => s.rating >= 4).length}
              </Text>
              <Text style={styles.supplierStatLabel}>Top Rated</Text>
            </View>
          </View>

          {/* Search */}
          <View style={styles.searchContainer}>
            <Ionicons name="search" size={20} color="#666" style={styles.searchIcon} />
            <TextInput
              style={styles.searchInput}
              value={searchQuery}
              onChangeText={setSearchQuery}
              placeholder="Search suppliers..."
              placeholderTextColor="#666"
            />
          </View>

          {/* Category Filter Chips */}
          <View style={{ height: 38, marginBottom: 8 }}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 4, gap: 6, alignItems: 'center' }}>
              <TouchableOpacity
                style={[styles.filterChip, !selectedSupplierCategory && styles.filterChipActive]}
                onPress={() => setSelectedSupplierCategory(null)}
              >
                <Text style={[styles.filterText, !selectedSupplierCategory && styles.filterTextActive]}>All</Text>
              </TouchableOpacity>
              {Object.entries(supplierCategoryCounts).map(([cat, count]) => (
                <TouchableOpacity
                  key={cat}
                  style={[styles.filterChip, selectedSupplierCategory === cat && styles.filterChipActive]}
                  onPress={() => setSelectedSupplierCategory(selectedSupplierCategory === cat ? null : cat)}
                >
                  <Text style={[styles.filterText, selectedSupplierCategory === cat && styles.filterTextActive]}>
                    {cat} ({count})
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          {/* Supplier List */}
          {loadingSupplierData ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#25D366" />
            </View>
          ) : (
            <FlatList
              data={filteredSuppliers}
              keyExtractor={(item) => item.id || item._id}
              contentContainerStyle={styles.listContent}
              refreshControl={
                <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
              }
              renderItem={({ item }) => (
                <TouchableOpacity style={styles.supplierCard} onPress={() => openSupplierDetail(item)}>
                  <View style={styles.supplierCardLeft}>
                    <View style={[styles.supplierAvatar, { backgroundColor: CATEGORY_COLORS[item.supplier_category] || '#4A90D9' }]}>
                      <Ionicons name={CATEGORY_ICONS[item.supplier_category] || ('business' as keyof typeof Ionicons.glyphMap)} size={18} color="#FFF" />
                    </View>
                    <View style={styles.supplierCardInfo}>
                      <Text style={styles.supplierCardName} numberOfLines={1}>{item.name}</Text>
                      <Text style={styles.supplierCardPhone}>{item.phone_number}</Text>
                      <View style={styles.supplierCardMeta}>
                        <View style={[styles.supplierCategoryBadge, { backgroundColor: (CATEGORY_COLORS[item.supplier_category] || '#4A90D9') + '30' }]}>
                          <Text style={[styles.supplierCategoryText, { color: CATEGORY_COLORS[item.supplier_category] || '#4A90D9' }]}>{item.supplier_category || 'Other'}</Text>
                        </View>
                        {item.rating > 0 && (
                          <View style={styles.supplierRatingRow}>
                            {[1, 2, 3, 4, 5].map(star => (
                              <Ionicons key={star} name={star <= item.rating ? 'star' : 'star-outline'} size={12} color="#FFD700" />
                            ))}
                          </View>
                        )}
                      </View>
                    </View>
                  </View>
                  <TouchableOpacity
                    style={styles.supplierWhatsappBtn}
                    onPress={(e) => {
                      e.stopPropagation();
                      router.push({ pathname: '/chat', params: { customerId: item.id || item._id, customerName: item.name, customerPhone: item.phone_number } });
                    }}
                  >
                    <Ionicons name="chatbubble-ellipses" size={18} color="#25D366" />
                  </TouchableOpacity>
                </TouchableOpacity>
              )}
              ListEmptyComponent={
                <View style={styles.emptyContainer}>
                  <Ionicons name="business-outline" size={64} color="#4A90D9" />
                  <Text style={styles.emptyText}>No suppliers yet</Text>
                  <Text style={styles.emptySubtext}>Add suppliers from your contacts to track who you buy from</Text>
                </View>
              }
            />
          )}

          {/* Supplier FABs */}
          <View style={[styles.fabContainer, { bottom: 20 }]}>
            <TouchableOpacity
              style={styles.fabSecondary}
              onPress={() => {
                setContactsModalVisible(true);
                loadPhoneContacts();
              }}
              activeOpacity={0.8}
            >
              <Ionicons name="people" size={18} color="#FFFFFF" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.fab}
              onPress={() => setModalVisible(true)}
              activeOpacity={0.8}
            >
              <Ionicons name="add" size={22} color="#FFFFFF" />
            </TouchableOpacity>
          </View>

          {/* Supplier Detail Modal */}
          <Modal
            visible={supplierDetailVisible}
            animationType="slide"
            presentationStyle="pageSheet"
            onRequestClose={() => setSupplierDetailVisible(false)}
          >
            <SafeAreaView style={styles.modalContainer}>
              <View style={styles.modalHeader}>
                <TouchableOpacity onPress={() => setSupplierDetailVisible(false)}>
                  <Text style={styles.modalCancel}>Close</Text>
                </TouchableOpacity>
                <Text style={styles.modalTitle}>Supplier Details</Text>
                <TouchableOpacity onPress={saveSupplierDetails} disabled={savingSupplier}>
                  <Text style={[styles.modalSave, savingSupplier && styles.modalSaveDisabled]}>
                    {savingSupplier ? 'Saving...' : 'Save'}
                  </Text>
                </TouchableOpacity>
              </View>
              <ScrollView style={styles.modalBody} keyboardShouldPersistTaps="handled">
                {selectedSupplier && (
                  <>
                    {/* Supplier Header */}
                    <View style={styles.supplierDetailHeader}>
                      <View style={[styles.supplierDetailAvatar, { backgroundColor: CATEGORY_COLORS[editingSupplierCategory] || '#4A90D9' }]}>
                        <Text style={styles.supplierDetailAvatarText}>{selectedSupplier.name?.charAt(0)?.toUpperCase()}</Text>
                      </View>
                      <Text style={styles.supplierDetailName}>{selectedSupplier.name}</Text>
                      <Text style={styles.supplierDetailPhone}>{selectedSupplier.phone_number}</Text>
                    </View>

                    {/* Category */}
                    <View style={styles.supplierDetailSection}>
                      <Text style={styles.supplierDetailLabel}>Category</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                        {supplierCategories.map(cat => (
                          <TouchableOpacity
                            key={cat}
                            style={[styles.supplierCatChip, editingSupplierCategory === cat && styles.supplierCatChipActive]}
                            onPress={() => setEditingSupplierCategory(cat)}
                          >
                            <Ionicons name={CATEGORY_ICONS[cat] || ('business' as keyof typeof Ionicons.glyphMap)} size={14} color={editingSupplierCategory === cat ? '#FFF' : '#888'} />
                            <Text style={[styles.supplierCatChipText, editingSupplierCategory === cat && styles.supplierCatChipTextActive]}>{cat}</Text>
                          </TouchableOpacity>
                        ))}
                      </ScrollView>
                    </View>

                    {/* Rating */}
                    <View style={styles.supplierDetailSection}>
                      <Text style={styles.supplierDetailLabel}>Rating</Text>
                      <View style={styles.ratingRow}>
                        {[1, 2, 3, 4, 5].map(star => (
                          <TouchableOpacity key={star} onPress={() => setEditingRating(star === editingRating ? 0 : star)}>
                            <Ionicons name={star <= editingRating ? 'star' : 'star-outline'} size={28} color="#FFD700" style={{ marginRight: 6 }} />
                          </TouchableOpacity>
                        ))}
                        {editingRating > 0 && <Text style={styles.ratingLabel}>{editingRating}/5</Text>}
                      </View>
                    </View>

                    {/* Payment Terms */}
                    <View style={styles.supplierDetailSection}>
                      <Text style={styles.supplierDetailLabel}>Payment Terms</Text>
                      <TextInput
                        style={styles.supplierDetailInput}
                        value={editingPaymentTerms}
                        onChangeText={setEditingPaymentTerms}
                        placeholder="e.g. Net 30, Cash on delivery, 50% upfront"
                        placeholderTextColor="#555"
                      />
                    </View>

                    {/* Lead Time */}
                    <View style={styles.supplierDetailSection}>
                      <Text style={styles.supplierDetailLabel}>Lead Time</Text>
                      <TextInput
                        style={styles.supplierDetailInput}
                        value={editingLeadTime}
                        onChangeText={setEditingLeadTime}
                        placeholder="e.g. 3-5 days, Same day, 2 weeks"
                        placeholderTextColor="#555"
                      />
                    </View>

                    {/* Quick Actions */}
                    <View style={styles.supplierDetailSection}>
                      <Text style={styles.supplierDetailLabel}>Quick Actions</Text>
                      <TouchableOpacity
                        style={styles.supplierActionBtn}
                        onPress={() => {
                          setSupplierDetailVisible(false);
                          router.push({ pathname: '/chat', params: { customerId: selectedSupplier.id || selectedSupplier._id, customerName: selectedSupplier.name, customerPhone: selectedSupplier.phone_number } });
                        }}
                      >
                        <Ionicons name="chatbubble-ellipses" size={20} color="#25D366" />
                        <Text style={styles.supplierActionBtnText}>Message on WhatsApp</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.supplierActionBtn, { borderColor: '#FF4444' }]}
                        onPress={() => removeSupplier(selectedSupplier.id || selectedSupplier._id)}
                      >
                        <Ionicons name="trash-outline" size={20} color="#FF4444" />
                        <Text style={[styles.supplierActionBtnText, { color: '#FF4444' }]}>Remove Supplier</Text>
                      </TouchableOpacity>
                    </View>
                  </>
                )}
              </ScrollView>
            </SafeAreaView>
          </Modal>
        </>
      ) : (
        <>
          {/* ===== CUSTOMER MODE ===== */}
          {/* Dashboard Summary Card */}
          {dashboardSummary && (
            <View style={styles.dashboardCard}>
              <TouchableOpacity style={styles.dashboardItem} onPress={() => {}}>
                <View style={[styles.dashboardIcon, { backgroundColor: '#25D36620' }]}>
                  <Ionicons name="chatbubble-ellipses" size={14} color="#25D366" />
                </View>
                <View style={styles.dashboardInfo}>
                  <Text style={styles.dashboardValue} numberOfLines={1}>{dashboardSummary.unread_messages}</Text>
                  <Text style={styles.dashboardLabel}>Unread</Text>
                </View>
              </TouchableOpacity>
              <View style={styles.dashboardDivider} />
              <TouchableOpacity style={styles.dashboardItem} onPress={() => router.push('/(tabs)/followups')}>
                <View style={[styles.dashboardIcon, { backgroundColor: '#FF980020' }]}>
                  <Ionicons name="alarm" size={14} color="#FF9800" />
                </View>
                <View style={styles.dashboardInfo}>
                  <Text style={styles.dashboardValue} numberOfLines={1}>{dashboardSummary.followups_today}</Text>
                  <Text style={styles.dashboardLabel}>Follow-ups</Text>
                </View>
              </TouchableOpacity>
              <View style={styles.dashboardDivider} />
              <TouchableOpacity style={styles.dashboardItem} onPress={() => router.push('/(tabs)/sales')}>
                <View style={[styles.dashboardIcon, { backgroundColor: '#4A90D920' }]}>
                  <Ionicons name="cash" size={14} color="#4A90D9" />
                </View>
                <View style={styles.dashboardInfo}>
                  <Text style={styles.dashboardValue} numberOfLines={1} adjustsFontSizeToFit>{currency} {dashboardSummary.sales_today.toLocaleString()}</Text>
                  <Text style={styles.dashboardLabel}>Sales</Text>
                </View>
              </TouchableOpacity>
            </View>
          )}

          {/* Pipeline Stage Pills */}
          <View style={{ height: 38, marginBottom: 8 }}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 4, gap: 6 }}>
              {STAGES.map((stage) => (
                <TouchableOpacity
                  key={stage}
                  style={[
                    styles.stageChip,
                    selectedStage === stage && styles.stageChipActive,
                    selectedStage === stage && stage !== 'all' && { backgroundColor: STAGE_COLORS[stage] }
                  ]}
                  onPress={() => setSelectedStage(stage)}
                >
                  <Text style={[styles.stageChipText, selectedStage === stage && styles.stageChipTextActive]}>
                    {STAGE_LABELS[stage]}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
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
          <View style={[styles.fabContainer, { bottom: 20 }]}>
            <TouchableOpacity
              style={styles.fabSecondary}
              onPress={() => {
                setContactsModalVisible(true);
                loadPhoneContacts();
              }}
              activeOpacity={0.8}
            >
              <Ionicons name="people" size={18} color="#FFFFFF" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.fab}
              onPress={() => setModalVisible(true)}
              activeOpacity={0.8}
            >
              <Ionicons name="add" size={22} color="#FFFFFF" />
            </TouchableOpacity>
          </View>
        </>
      )}

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
            <Text style={styles.modalTitle}>{viewMode === 'suppliers' ? 'Import Suppliers' : 'Import Contacts'}</Text>
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
      {/* AI Model Selector Modal */}
      <Modal
        visible={showModelSelector}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setShowModelSelector(false)}
      >
        <TouchableOpacity
          style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-start', paddingTop: 100, alignItems: 'center' }}
          activeOpacity={1}
          onPress={() => setShowModelSelector(false)}
        >
          <View style={{ backgroundColor: '#1E1E1E', borderRadius: 12, padding: 8, width: 200, shadowColor: "#000", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.25, shadowRadius: 3.84, elevation: 5 }}>
            {[
              { id: 'standard', name: 'GPT-4o Mini' },
              { id: 'premium', name: 'GPT-4o' },
              { id: 'gpt-5', name: 'GPT-5' },
              { id: 'sonnet-4.5', name: 'Sonnet 4.5' },
              { id: 'grok', name: 'Grok 4.1' },
              { id: 'deepseek', name: 'DeepSeek' },
            ].map((model) => (
              <TouchableOpacity
                key={model.id}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  paddingVertical: 12,
                  paddingHorizontal: 16,
                  backgroundColor: aiModel === model.id ? 'rgba(37,211,102,0.1)' : 'transparent',
                  borderRadius: 8,
                }}
                onPress={() => handleModelSelect(model.id)}
              >
                <Text style={{ color: aiModel === model.id ? '#25D366' : '#FFFFFF', fontSize: 14, fontWeight: aiModel === model.id ? '600' : '400', flex: 1 }}>
                  {model.name}
                </Text>
                {aiModel === model.id && (
                  <Ionicons name="checkmark" size={16} color="#25D366" />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </TouchableOpacity>
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
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  headerTitle: {
    fontSize: 22,
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
    marginHorizontal: 16,
    borderRadius: 10,
    paddingHorizontal: 12,
    marginBottom: 8,
  },
  searchIcon: {
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    height: 38,
    fontSize: 14,
    color: '#FFFFFF',
  },
  sortContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    marginBottom: 8,
    gap: 6,
  },
  sortButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1A2942',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    gap: 4,
  },
  sortButtonActive: {
    backgroundColor: '#25D366',
  },
  sortText: {
    fontSize: 11,
    fontWeight: '500',
    color: '#666',
  },
  sortTextActive: {
    color: '#FFFFFF',
  },
  filterContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    marginBottom: 10,
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
  avatarImage: {
    backgroundColor: '#1A2332',
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
  },
  fabContainer: {
    position: 'absolute',
    right: 16,
    alignItems: 'flex-end',
    gap: 10,
  },
  fabSecondary: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: '#4A90D9',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
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
  // Suppliers mode styles
  viewToggle: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginTop: 8,
    marginBottom: 8,
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 3,
  },
  toggleButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 7,
    paddingHorizontal: 10,
    borderRadius: 8,
    gap: 4,
  },
  toggleButtonActive: {
    backgroundColor: '#25D366',
  },
  toggleText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#666',
  },
  toggleTextActive: {
    color: '#FFFFFF',
  },
  // Supplier Stats Bar
  supplierStatsBar: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: '#1A2942',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    alignItems: 'center',
  },
  supplierStatItem: {
    flex: 1,
    alignItems: 'center',
  },
  supplierStatValue: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  supplierStatLabel: {
    fontSize: 10,
    color: '#8899AA',
    marginTop: 2,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  supplierStatDivider: {
    width: 1,
    height: 24,
    backgroundColor: '#2A3F5F',
  },
  // Supplier Card
  supplierCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1A2942',
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 10,
    padding: 12,
  },
  supplierCardLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  supplierAvatar: {
    width: 38,
    height: 38,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  supplierCardInfo: {
    flex: 1,
  },
  supplierCardName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 1,
  },
  supplierCardPhone: {
    fontSize: 12,
    color: '#8899AA',
    marginBottom: 4,
  },
  supplierCardMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  supplierCategoryBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  supplierCategoryText: {
    fontSize: 10,
    fontWeight: '600',
  },
  supplierRatingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 1,
  },
  supplierWhatsappBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(37, 211, 102, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  // Supplier Detail Modal
  modalBody: {
    flex: 1,
    padding: 20,
  },
  supplierDetailHeader: {
    alignItems: 'center',
    marginBottom: 24,
  },
  supplierDetailAvatar: {
    width: 60,
    height: 60,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
  },
  supplierDetailAvatarText: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  supplierDetailName: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 2,
  },
  supplierDetailPhone: {
    fontSize: 14,
    color: '#8899AA',
  },
  supplierDetailSection: {
    marginBottom: 20,
  },
  supplierDetailLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#8899AA',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  supplierDetailInput: {
    backgroundColor: '#1A2942',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: '#FFFFFF',
    fontSize: 14,
    borderWidth: 1,
    borderColor: '#2A3F5F',
  },
  supplierCatChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#1A2942',
    borderWidth: 1,
    borderColor: '#2A3F5F',
    gap: 4,
  },
  supplierCatChipActive: {
    backgroundColor: '#25D366',
    borderColor: '#25D366',
  },
  supplierCatChipText: {
    fontSize: 12,
    color: '#888',
    fontWeight: '500',
  },
  supplierCatChipTextActive: {
    color: '#FFFFFF',
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  ratingLabel: {
    color: '#FFD700',
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 8,
  },
  supplierActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#25D366',
    marginBottom: 10,
  },
  supplierActionBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#25D366',
  },
  // AI Pending Approvals
  pendingBanner: {
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 10,
    borderLeftWidth: 3,
    borderLeftColor: '#FFD700',
  },
  pendingHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  pendingTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#FFD700',
  },
  pendingCard: {
    width: 160,
    backgroundColor: '#0F1D32',
    borderRadius: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: '#2A3F5F',
  },
  pendingCardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  pendingTypeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    gap: 3,
  },
  pendingTypeText: {
    fontSize: 9,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  pendingConfidence: {
    fontSize: 10,
    fontWeight: '600',
    color: '#8899AA',
  },
  pendingName: {
    fontSize: 13,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 2,
  },
  pendingReason: {
    fontSize: 10,
    color: '#8899AA',
    marginBottom: 8,
    lineHeight: 14,
  },
  pendingActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  pendingConfirmBtn: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pendingDismissBtn: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: '#FF444420',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pendingSwapBtn: {
    paddingHorizontal: 6,
    paddingVertical: 4,
    borderRadius: 4,
    backgroundColor: '#2A3F5F',
  },
  pendingSwapText: {
    fontSize: 9,
    color: '#8899AA',
    fontWeight: '500',
  },
  scanButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginHorizontal: 16,
    marginBottom: 8,
    paddingVertical: 8,
    backgroundColor: '#1A2942',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#FFD70040',
  },
  scanButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#FFD700',
  },
  // Dashboard Summary Card
  dashboardCard: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 16,
    marginTop: 6,
    marginBottom: 8,
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 8,
  },
  dashboardItem: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dashboardIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  dashboardInfo: {
    flex: 1,
    minWidth: 0,
  },
  dashboardValue: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  dashboardLabel: {
    fontSize: 10,
    color: '#8B9DC3',
    marginTop: 1,
  },
  dashboardDivider: {
    width: 1,
    height: 28,
    backgroundColor: 'rgba(255,255,255,0.1)',
    marginHorizontal: 6,
  },
  // Pipeline Stage Chips
  stageChip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    backgroundColor: '#1A2942',
    borderRadius: 16,
  },
  stageChipActive: {
    backgroundColor: '#25D366',
  },
  stageChipText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#8B9DC3',
  },
  stageChipTextActive: {
    color: '#FFFFFF',
  },
  // Unread Badge
  unreadBadge: {
    position: 'absolute',
    top: -2,
    right: -2,
    backgroundColor: '#25D366',
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 5,
    borderWidth: 2,
    borderColor: '#0A1628',
  },
  unreadBadgeText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});
