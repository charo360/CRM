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
  ScrollView,
  Image,
  Platform,
} from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { apiClient, productsAPI, settingsAPI } from '../../context/api';
import { useRouter } from 'expo-router';

interface Customer {
  id: string;
  name: string;
  phone_number: string;
  tags: string[];
}

interface Broadcast {
  id: string;
  message: string;
  name?: string;
  filter_type: string;
  recipients_count: number;
  sent_count: number;
  status: string;
  image_url?: string;
  image_urls?: string[];
  scheduled_at?: string;
  created_at: string;
}

interface BroadcastPerformance {
  broadcast_id: string;
  sent_count: number;
  recipients_count: number;
  replies: number;
  reply_rate: number;
}

interface BroadcastAutomation {
  _id: string;
  type: 'auto_followup' | 'recurring';
  status: string;
  follow_up_message?: string;
  delay_days?: number;
  message?: string;
  recurrence?: string;
  send_hour?: number;
  runs: number;
  created_at: string;
}

interface BroadcastTemplate {
  id: string;
  name: string;
  message: string;
  image_url?: string;
  created_at: string;
}

const FILTERS = [
  { id: 'all', label: 'All Customers', icon: 'people' },
  { id: 'new', label: 'New Customers', icon: 'person-add' },
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

interface CustomerGroup {
  id: string;
  name: string;
  customer_ids: string[];
  count: number;
}

interface Product {
  id: string;
  name: string;
  price: number;
  image_url: string;
  images: string[];
  category: string;
}

export default function BroadcastScreen() {
  const router = useRouter();
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [templates, setTemplates] = useState<BroadcastTemplate[]>([]);
  const [groups, setGroups] = useState<CustomerGroup[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [viewingBroadcast, setViewingBroadcast] = useState<Broadcast | null>(null);
  const [currency, setCurrency] = useState('USD');
  const [broadcastSearch, setBroadcastSearch] = useState('');
  const [deletingBroadcast, setDeletingBroadcast] = useState(false);
  const [activeTab, setActiveTab] = useState<'broadcasts' | 'automations'>('broadcasts');
  const [automations, setAutomations] = useState<BroadcastAutomation[]>([]);
  const [performance, setPerformance] = useState<Record<string, BroadcastPerformance>>({});
  const [automationModalVisible, setAutomationModalVisible] = useState(false);
  const [automationType, setAutomationType] = useState<'auto_followup' | 'recurring'>('auto_followup');
  const [followUpMessage, setFollowUpMessage] = useState('');
  const [followUpDelayDays, setFollowUpDelayDays] = useState('2');
  const [selectedBroadcastForFollowUp, setSelectedBroadcastForFollowUp] = useState('');
  const [recurringMessage, setRecurringMessage] = useState('');
  const [recurringFilter, setRecurringFilter] = useState('all');
  const [recurrence, setRecurrence] = useState<'weekly' | 'monthly'>('weekly');
  const [sendHour, setSendHour] = useState('9');
  const [resending, setResending] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [generatingFollowUpAI, setGeneratingFollowUpAI] = useState(false);
  const [generatingRecurringAI, setGeneratingRecurringAI] = useState(false);
  const [followUpAIDirection, setFollowUpAIDirection] = useState('');
  const [recurringAIDirection, setRecurringAIDirection] = useState('');

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [aiModalVisible, setAiModalVisible] = useState(false);
  const [sending, setSending] = useState(false);
  const [generatingAI, setGeneratingAI] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollAttemptsRef = useRef(0);

  // New Modals
  const [createGroupModalVisible, setCreateGroupModalVisible] = useState(false);
  const [productModalVisible, setProductModalVisible] = useState(false);

  // Product Edit Modal
  const [editProductModalVisible, setEditProductModalVisible] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [editName, setEditName] = useState('');
  const [editPrice, setEditPrice] = useState('');
  const [editImages, setEditImages] = useState<string[]>([]);

  // Form state
  const [selectedFilter, setSelectedFilter] = useState('all');
  const [selectedGroup, setSelectedGroup] = useState(''); // For custom groups
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [broadcastName, setBroadcastName] = useState('');
  const [message, setMessage] = useState('');
  const [scheduledDate, setScheduledDate] = useState('');
  const [saveAsTemplate, setSaveAsTemplate] = useState(false);
  const [templateName, setTemplateName] = useState('');

  // Create Group State
  const [newGroupName, setNewGroupName] = useState('');
  const [selectedCustomerIds, setSelectedCustomerIds] = useState<Set<string>>(new Set());
  const [groupCustomerSearch, setGroupCustomerSearch] = useState('');

  // AI generation state
  const [aiPrompt, setAiPrompt] = useState('');
  const [businessType, setBusinessType] = useState('');

  // Image upload state
  // selectedImage (single) is deprecated in favor of selectedImages (list)
  // But keeping it synced for now to avoid breaking too much at once
  const [selectedImages, setSelectedImages] = useState<string[]>([]);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [viewingImage, setViewingImage] = useState<string | null>(null);

  // Gallery Selection State
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set());
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [tempDate, setTempDate] = useState<Date>(new Date());
  const [broadcastingCatalog, setBroadcastingCatalog] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [broadcastsRes, customersRes, templatesRes, groupsRes, productsRes, automationsRes] = await Promise.all([
        apiClient.get('/broadcasts'),
        apiClient.get('/customers'),
        apiClient.get('/broadcast-templates'),
        apiClient.get('/customer-groups'),
        apiClient.get('/products'),
        apiClient.get('/broadcasts/automations'),
      ]);
      setBroadcasts(broadcastsRes.data);
      setCustomers(customersRes.data);
      setTemplates(templatesRes.data);
      setGroups(groupsRes.data);
      setProducts(productsRes.data);
      setAutomations(automationsRes.data);
      // Load currency
      try {
        const settings = await settingsAPI.getSettings();
        if (settings.currency) setCurrency(settings.currency);
      } catch (e) {}
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const getFilteredCount = () => {
    if (selectedFilter === 'all') return customers.length;
    if (selectedFilter === 'new') {
      return customers.filter(c => c.tags.includes('New')).length;
    }
    if (selectedFilter === 'returning') {
      return customers.filter(c => c.tags.includes('Returning')).length;
    }
    if (selectedFilter === 'vip') {
      return customers.filter(c => c.tags.includes('VIP')).length;
    }
    if (selectedFilter === 'group' && selectedGroup) {
      const group = groups.find(g => g.id === selectedGroup);
      return group ? group.count : 0;
    }
    return 0;
  };

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      Alert.alert('Error', 'Please enter a group name');
      return;
    }
    if (selectedCustomerIds.size === 0) {
      Alert.alert('Error', 'Please select at least one customer');
      return;
    }

    try {
      const response = await apiClient.post('/customer-groups', {
        name: newGroupName,
        customer_ids: Array.from(selectedCustomerIds),
      });
      setGroups([response.data, ...groups]);
      setCreateGroupModalVisible(false);
      setNewGroupName('');
      setSelectedCustomerIds(new Set());
      setGroupCustomerSearch('');
      Alert.alert('Success', 'Group created!');
    } catch (error: any) {
      Alert.alert('Error', 'Failed to create group');
    }
  };

  const toggleCustomerSelection = (customerId: string) => {
    const newSelection = new Set(selectedCustomerIds);
    if (newSelection.has(customerId)) {
      newSelection.delete(customerId);
    } else {
      newSelection.add(customerId);
    }
    setSelectedCustomerIds(newSelection);
  };

  const handleSelectTemplate = (template: typeof TEMPLATES[0]) => {
    setSelectedTemplate(template.id);
    if (template.message) {
      setMessage(template.message);
    }
    // Clear images for standard templates
    setSelectedImages([]);
  };

  const handleSelectCustomTemplate = (template: BroadcastTemplate) => {
    setMessage(template.message);
    if (template.image_url) {
      // Replace current images with template image
      setSelectedImages([template.image_url]);
    } else {
      // Clear images if template has none
      setSelectedImages([]);
    }
  };

  // Toggles product selection in Gallery
  const handleToggleProductSelection = (product: Product) => {
    const newSelection = new Set(selectedProductIds);
    if (newSelection.has(product.id)) {
      newSelection.delete(product.id);
    } else {
      newSelection.add(product.id);
    }
    setSelectedProductIds(newSelection);
  };

  // Broadcast catalog to customers
  const handleBroadcastCatalog = async () => {
    if (selectedProductIds.size === 0) {
      Alert.alert('Error', 'Please select at least one product');
      return;
    }

    const recipientCount = getFilteredCount();
    if (recipientCount === 0) {
      Alert.alert('Error', 'No customers match this filter');
      return;
    }

    const productIds = Array.from(selectedProductIds);

    Alert.alert(
      'Broadcast Catalog',
      `Send ${productIds.length} product${productIds.length > 1 ? 's' : ''} as a catalog to ${recipientCount} customer${recipientCount > 1 ? 's' : ''}?\n\nCustomers can reply "Order 1" to place an order!`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Broadcast',
          onPress: async () => {
            setBroadcastingCatalog(true);
            try {
              let filterType = selectedFilter;
              let customerIds: string[] | undefined;

              if (selectedFilter === 'group' && selectedGroup) {
                const group = groups.find(g => g.id === selectedGroup);
                if (group) {
                  filterType = 'custom';
                  customerIds = group.customer_ids;
                }
              }

              const result = await productsAPI.broadcastCatalog(productIds, filterType, customerIds);
              setProductModalVisible(false);
              setSelectedProductIds(new Set());
              fetchData();
              Alert.alert(
                'Catalog Broadcast Sent!',
                `Sent to ${result.sent_count} customer${result.sent_count !== 1 ? 's' : ''} with ${result.products_in_catalog} products.\n\nCustomers can reply to order!`
              );
            } catch (error: any) {
              Alert.alert('Error', error.response?.data?.detail || 'Failed to broadcast catalog');
            } finally {
              setBroadcastingCatalog(false);
            }
          },
        },
      ]
    );
  };

  const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

  const toFullUrl = (url: string) => {
    if (!url) return url;
    if (url.startsWith('http://') || url.startsWith('https://')) return url;
    return `${BACKEND_URL}${url}`;
  };

  // Adds selected products' images to the broadcast
  const handleConfirmProductSelection = () => {
    const imagesToAdd: string[] = [];
    products.forEach(p => {
      if (selectedProductIds.has(p.id)) {
        if (p.images && p.images.length > 0) {
          imagesToAdd.push(...p.images.map(toFullUrl));
        } else if (p.image_url) {
          imagesToAdd.push(toFullUrl(p.image_url));
        }
      }
    });

    if (imagesToAdd.length === 0) {
      Alert.alert('Notice', 'No images found in selected products');
      return;
    }

    // Add unique images
    const currentImages = new Set(selectedImages);
    imagesToAdd.forEach(img => currentImages.add(img));
    setSelectedImages(Array.from(currentImages));

    setProductModalVisible(false);
    setSelectedProductIds(new Set());
  };

  const handleSelectProduct = (product: Product) => {
    // Legacy single select support: just add it
    if (product.image_url || (product.images && product.images.length > 0)) {
      const imgs = product.images?.length ? product.images : [product.image_url];
      setSelectedImages(prev => [...prev, ...imgs]);
      setProductModalVisible(false);
    } else {
      Alert.alert('Notice', 'This product has no image');
    }
  };

  // Prepare Edit Modal
  const openEditProduct = (product: Product) => {
    setEditingProduct(product);
    setEditName(product.name);
    setEditPrice(product.price.toString());
    setEditImages(product.images || (product.image_url ? [product.image_url] : []));
    setEditProductModalVisible(true);
  };

  const handleSaveProduct = async () => {
    if (!editingProduct) return;

    try {
      const response = await apiClient.put(`/products/${editingProduct.id}`, {
        name: editName,
        price: parseFloat(editPrice) || 0,
        images: editImages
      });

      // Update local list
      setProducts(products.map(p => p.id === editingProduct.id ? response.data : p));
      setEditProductModalVisible(false);
      setEditingProduct(null);
      Alert.alert('Success', 'Product updated!');
    } catch (error: any) {
      Alert.alert('Error', 'Failed to update product');
    }
  };

  const handleAddImageToProduct = async () => {
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') return;

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: false,
        quality: 0.8,
        base64: true,
      });

      if (!result.canceled && result.assets[0].base64) {
        const uploadRes = await apiClient.post('/upload-image', {
          base64_data: result.assets[0].base64,
          filename: result.assets[0].fileName || 'product_image.jpg',
        });
        setEditImages([...editImages, uploadRes.data.image_url]);
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to upload image');
    }
  };

  const handleGenerateAI = async () => {
    if (!aiPrompt.trim()) {
      Alert.alert('Error', 'Please enter a prompt');
      return;
    }

    setGeneratingAI(true);
    try {
      const response = await apiClient.post('/ai/generate-broadcast-message', {
        prompt: aiPrompt,
        business_type: businessType || undefined,
      });
      setMessage(response.data.message);
      setAiPrompt('');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to generate message');
    } finally {
      setGeneratingAI(false);
    }
  };

  const handleSaveTemplate = async () => {
    if (!templateName.trim() || !message.trim()) {
      Alert.alert('Error', 'Please enter template name and message');
      return;
    }

    try {
      const response = await apiClient.post('/broadcast-templates', {
        name: templateName,
        message: message,
        image_url: selectedImages.length > 0 ? selectedImages[0] : undefined,
      });
      setTemplates([response.data, ...templates]);
      Alert.alert('Success', 'Template saved!');
      setSaveAsTemplate(false);
      setTemplateName('');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to save template');
    }
  };

  const handleDeleteTemplate = async (templateId: string) => {
    Alert.alert(
      'Delete Template',
      'Are you sure you want to delete this template?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.delete(`/broadcast-templates/${templateId}`);
              setTemplates(templates.filter(t => t.id !== templateId));
            } catch (error: any) {
              Alert.alert('Error', 'Failed to delete template');
            }
          },
        },
      ]
    );
  };

  const handleDeleteGroup = async (groupId: string) => {
    Alert.alert(
      'Delete Group',
      'Delete this customer group?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.delete(`/customer-groups/${groupId}`);
              setGroups(groups.filter(g => g.id !== groupId));
              if (selectedGroup === groupId) {
                setSelectedGroup('');
                setSelectedFilter('all');
              }
            } catch (error: any) {
              Alert.alert('Error', 'Failed to delete group');
            }
          },
        },
      ]
    );
  };

  const pickImage = async () => {
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Required', 'Please allow access to your photo library to upload images.');
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: false,
        quality: 0.8,
        base64: true,
      });

      if (!result.canceled && result.assets[0]) {
        const asset = result.assets[0];

        // Auto-upload and create product
        if (asset.base64) {
          setUploadingImage(true);
          try {
            // 1. Upload Image
            const uploadRes = await apiClient.post('/upload-image', {
              base64_data: asset.base64,
              filename: asset.fileName || 'broadcast_image.jpg',
            });
            const newImageUrl = uploadRes.data.image_url;

            // 2. Create Product from Image
            const productRes = await apiClient.post('/products', {
              name: `Upload ${new Date().toLocaleTimeString()}`,
              price: 0,
              category: 'Uploads',
              image_url: newImageUrl,
              images: [newImageUrl]
            });

            // 3. Update products list
            setProducts([productRes.data, ...products]);

            // 4. Add to selection
            setSelectedImages(prev => [...prev, newImageUrl]);

            Alert.alert('Success', 'Image uploaded and added to products!');
          } catch (error: any) {
            Alert.alert('Upload Failed', error.response?.data?.detail || 'Failed to process image.');
          } finally {
            setUploadingImage(false);
          }
        }
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to pick image');
    }
  };

  const removeImage = (urlToRemove: string) => {
    setSelectedImages(selectedImages.filter(url => url !== urlToRemove));
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

    if (saveAsTemplate && templateName.trim()) {
      await handleSaveTemplate();
    }

    // Prepare payload
    const payload: any = {
      message: message,
      name: broadcastName.trim() || undefined,
      filter_type: selectedFilter,
      image_urls: selectedImages,
      image_url: selectedImages[0] || undefined,
      scheduled_at: scheduledDate || undefined,
    };

    // If using custom group, we need to pass the IDs manually
    if (selectedFilter === 'group' && selectedGroup) {
      const group = groups.find(g => g.id === selectedGroup);
      if (group) {
        payload.customer_ids = group.customer_ids;
        payload.filter_type = 'custom';
      }
    }

    const confirmMessage = scheduledDate
      ? `Schedule this message for ${new Date(scheduledDate).toLocaleString()} to ${recipientCount} customer${recipientCount > 1 ? 's' : ''}?`
      : `Send this message to ${recipientCount} customer${recipientCount > 1 ? 's' : ''}?`;

    Alert.alert(
      scheduledDate ? 'Schedule Broadcast' : 'Send Broadcast',
      confirmMessage,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: scheduledDate ? 'Schedule' : 'Send',
          onPress: async () => {
            setSending(true);
            try {
              const response = await apiClient.post('/broadcasts', payload);

              setBroadcasts(prev => [response.data, ...prev]);
              setModalVisible(false);
              resetForm();

              Alert.alert(
                'Success',
                scheduledDate
                  ? `Broadcast scheduled for ${new Date(scheduledDate).toLocaleString()}!`
                  : `Broadcast sent to ${response.data.recipients_count} customers!`
              );

              if (!scheduledDate) {
                startPolling(response.data.id);
              }
            } catch (error: any) {
              if (error?.response?.status === 429) {
                Alert.alert(
                  "You've reached your message limit",
                  'Upgrade your plan to send broadcasts and unlock more features.',
                  [
                    { text: 'Later', style: 'cancel' },
                    { text: 'Upgrade Now', onPress: () => router.push('/(tabs)/account') },
                  ]
                );
              } else {
                Alert.alert('Error', error.response?.data?.detail || 'Failed to send broadcast');
              }
            } finally {
              setSending(false);
            }
          },
        },
      ]
    );
  };

  const startPolling = useCallback((broadcastId: string) => {
    pollAttemptsRef.current = 0;
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    pollIntervalRef.current = setInterval(async () => {
      pollAttemptsRef.current += 1;
      try {
        const res = await apiClient.get('/broadcasts');
        setBroadcasts(res.data);
        const updated = res.data.find((b: Broadcast) => b.id === broadcastId);
        if (updated?.status === 'completed' || pollAttemptsRef.current >= 5) {
          clearInterval(pollIntervalRef.current!);
          pollIntervalRef.current = null;
        }
      } catch {
        clearInterval(pollIntervalRef.current!);
        pollIntervalRef.current = null;
      }
    }, 3000);
  }, []);

  const resetForm = () => {
    setSelectedFilter('all');
    setSelectedGroup('');
    setSelectedTemplate('');
    setBroadcastName('');
    setMessage('');
    setSelectedImages([]);
    setScheduledDate('');
    setSaveAsTemplate(false);
    setTemplateName('');
  };

  const handleCancelBroadcast = async (broadcast: Broadcast) => {
    Alert.alert(
      '⛔ Stop Broadcast',
      `Stop sending "${broadcast.name || 'this broadcast'}"? Messages already sent cannot be recalled.`,
      [
        { text: 'Keep Sending', style: 'cancel' },
        {
          text: 'Stop Now',
          style: 'destructive',
          onPress: async () => {
            setCancelling(broadcast.id);
            try {
              await apiClient.post(`/broadcasts/${broadcast.id}/cancel`);
              fetchData();
              Alert.alert('Stopped', 'Broadcast has been stopped. No more messages will be sent.');
            } catch (e: any) {
              Alert.alert('Error', e.response?.data?.detail || 'Failed to stop broadcast');
            } finally {
              setCancelling(null);
            }
          },
        },
      ]
    );
  };

  const handleResend = async (broadcast: Broadcast) => {
    const audienceLabel = broadcast.filter_type === 'all'
      ? 'all customers'
      : broadcast.filter_type === 'custom' || broadcast.filter_type === 'group'
        ? `the same ${broadcast.recipients_count} customer${broadcast.recipients_count !== 1 ? 's' : ''} from this broadcast`
        : `${broadcast.filter_type} customers`;
    const broadcastLabel = broadcast.name ? `"${broadcast.name}"` : 'this broadcast';
    Alert.alert(
      'Resend Broadcast',
      `Resend ${broadcastLabel} to ${audienceLabel} again?\n\n${broadcast.recipients_count} recipient${broadcast.recipients_count !== 1 ? 's' : ''} will receive this message.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Resend',
          onPress: async () => {
            setResending(broadcast.id);
            try {
              const res = await apiClient.post(`/broadcasts/${broadcast.id}/resend`);
              fetchData();
              Alert.alert('Resending!', `Message sent to ${res.data.recipients_count} customer${res.data.recipients_count !== 1 ? 's' : ''}.`);
            } catch (e: any) {
              Alert.alert('Error', e.response?.data?.detail || 'Failed to resend');
            } finally {
              setResending(null);
            }
          },
        },
      ]
    );
  };

  const fetchPerformance = async (broadcastId: string) => {
    if (performance[broadcastId]) return;
    try {
      const res = await apiClient.get(`/broadcasts/${broadcastId}/performance`);
      setPerformance(prev => ({ ...prev, [broadcastId]: res.data }));
    } catch (e) {}
  };

  const handleCreateAutomation = async () => {
    try {
      if (automationType === 'auto_followup') {
        if (!selectedBroadcastForFollowUp) { Alert.alert('Error', 'Select a broadcast'); return; }
        if (!followUpMessage.trim()) { Alert.alert('Error', 'Enter follow-up message'); return; }
        await apiClient.post('/broadcasts/auto-followup', {
          broadcast_id: selectedBroadcastForFollowUp,
          follow_up_message: followUpMessage,
          delay_days: parseInt(followUpDelayDays) || 2,
        });
      } else {
        if (!recurringMessage.trim()) { Alert.alert('Error', 'Enter message'); return; }
        await apiClient.post('/broadcasts/recurring', {
          message: recurringMessage,
          filter_type: recurringFilter,
          recurrence,
          send_hour: parseInt(sendHour) || 9,
        });
      }
      setAutomationModalVisible(false);
      setFollowUpMessage(''); setRecurringMessage(''); setSelectedBroadcastForFollowUp('');
      fetchData();
      Alert.alert('Success', 'Automation created!');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to create automation');
    }
  };

  const handleDeleteAutomation = async (id: string) => {
    Alert.alert('Delete Automation', 'Remove this automation?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive',
        onPress: async () => {
          try {
            await apiClient.delete(`/broadcasts/automations/${id}`);
            setAutomations(prev => prev.filter(a => a._id !== id));
          } catch (e) { Alert.alert('Error', 'Failed to delete'); }
        },
      },
    ]);
  };

  // Group products by category
  const productsByCategory = products.reduce((acc, product) => {
    const cat = product.category || 'Other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(product);
    return acc;
  }, {} as Record<string, Product[]>);

  // ImageViewer state
  const [viewImageModal, setViewImageModal] = useState(false);

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
      {/* ... Header & Stats ... */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Broadcast</Text>
          <Text style={styles.headerSubtitle}>Send promotions to customers</Text>
        </View>
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

      {/* Search Bar */}
      <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', borderRadius: 10, marginHorizontal: 16, marginBottom: 8, paddingHorizontal: 12 }}>
        <Ionicons name="search" size={16} color="#666" style={{ marginRight: 8 }} />
        <TextInput
          style={{ flex: 1, color: '#FFF', fontSize: 14, height: 40 }}
          value={broadcastSearch}
          onChangeText={setBroadcastSearch}
          placeholder="Search broadcasts..."
          placeholderTextColor="#666"
        />
        {broadcastSearch.length > 0 && (
          <TouchableOpacity onPress={() => setBroadcastSearch('')}>
            <Ionicons name="close-circle" size={16} color="#666" />
          </TouchableOpacity>
        )}
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', marginHorizontal: 16, marginBottom: 8, backgroundColor: '#1A2942', borderRadius: 10, padding: 4 }}>
        <TouchableOpacity
          style={{ flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: 8, backgroundColor: activeTab === 'broadcasts' ? '#25D366' : 'transparent' }}
          onPress={() => setActiveTab('broadcasts')}
        >
          <Text style={{ color: activeTab === 'broadcasts' ? '#FFF' : '#666', fontWeight: '600', fontSize: 13 }}>Broadcasts</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={{ flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: 8, backgroundColor: activeTab === 'automations' ? '#25D366' : 'transparent' }}
          onPress={() => setActiveTab('automations')}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Text style={{ color: activeTab === 'automations' ? '#FFF' : '#666', fontWeight: '600', fontSize: 13 }}>Automations</Text>
            {automations.length > 0 && (
              <View style={{ backgroundColor: '#F59E0B', borderRadius: 8, minWidth: 16, paddingHorizontal: 4, alignItems: 'center' }}>
                <Text style={{ color: '#FFF', fontSize: 10, fontWeight: 'bold' }}>{automations.length}</Text>
              </View>
            )}
          </View>
        </TouchableOpacity>
      </View>

      {activeTab === 'broadcasts' && (
        <FlatList
          data={broadcasts.filter(b => !broadcastSearch || b.message.toLowerCase().includes(broadcastSearch.toLowerCase()))}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={styles.broadcastCard}
              onPress={() => { setViewingBroadcast(item); fetchPerformance(item.id); }}
              activeOpacity={0.7}
            >
              <View style={styles.broadcastHeader}>
                <View style={styles.broadcastIcon}>
                  <Ionicons name="megaphone" size={20} color="#25D366" />
                </View>
                <View style={styles.broadcastInfo}>
                  {item.name ? (
                    <Text style={{ color: '#FFF', fontWeight: '700', fontSize: 14, marginBottom: 2 }} numberOfLines={1}>{item.name}</Text>
                  ) : null}
                  <View style={styles.statusRow}>
                    <Text style={styles.broadcastDate}>
                      {new Date(item.created_at).toLocaleDateString('en-KE', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </Text>
                    {item.scheduled_at && new Date(item.scheduled_at) > new Date() && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: '#3B82F6', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                        <Ionicons name="time-outline" size={12} color="#FFF" />
                        <Text style={{ color: '#FFF', fontSize: 10, marginLeft: 4, fontWeight: '600' }}>
                          {new Date(item.scheduled_at).toLocaleString('en-KE', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </Text>
                      </View>
                    )}
                  </View>
                  <View style={styles.statusRow}>
                    <View style={[styles.statusBadge, item.status === 'completed' && styles.statusCompleted, item.status === 'sending' && styles.statusSending, item.status === 'cancelled' && { backgroundColor: '#FF4A4A22' }]}>
                      <Text style={[styles.statusText, item.status === 'cancelled' && { color: '#FF4A4A' }]}>{item.status === 'completed' ? 'Sent' : item.status === 'cancelled' ? 'Stopped' : 'Sending...'}</Text>
                    </View>
                    <Text style={styles.recipientCount}>{item.sent_count}/{item.recipients_count} delivered</Text>
                  </View>
                </View>
                {item.status === 'sending' ? (
                  <TouchableOpacity
                    style={{ backgroundColor: '#FF4A4A22', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, marginLeft: 8, borderWidth: 1, borderColor: '#FF4A4A' }}
                    onPress={() => handleCancelBroadcast(item)}
                    disabled={cancelling === item.id}
                  >
                    {cancelling === item.id
                      ? <ActivityIndicator size="small" color="#FF4A4A" />
                      : <Ionicons name="stop-circle" size={18} color="#FF4A4A" />}
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity
                    style={{ backgroundColor: '#1E3A5F', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, marginLeft: 8 }}
                    onPress={() => handleResend(item)}
                    disabled={resending === item.id}
                  >
                    {resending === item.id
                      ? <ActivityIndicator size="small" color="#25D366" />
                      : <Ionicons name="refresh" size={16} color="#25D366" />}
                  </TouchableOpacity>
                )}
              </View>
              <Text style={styles.broadcastMessage} numberOfLines={2}>{item.message}</Text>
            </TouchableOpacity>
          )}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="megaphone-outline" size={64} color="#666" />
              <Text style={styles.emptyText}>No broadcasts yet</Text>
            </View>
          }
        />
      )}

      {activeTab === 'automations' && (
        <FlatList
          data={automations}
          keyExtractor={item => item._id}
          contentContainerStyle={styles.listContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />}
          renderItem={({ item }) => (
            <View style={styles.broadcastCard}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons
                    name={item.type === 'recurring' ? 'repeat' : 'chatbubble-ellipses'}
                    size={18}
                    color={item.type === 'recurring' ? '#8B5CF6' : '#F59E0B'}
                  />
                  <Text style={{ color: '#FFF', fontWeight: '700', fontSize: 14 }}>
                    {item.type === 'recurring' ? `${item.recurrence === 'weekly' ? 'Weekly' : 'Monthly'} Broadcast` : 'Auto Follow-up'}
                  </Text>
                  <View style={{ backgroundColor: item.status === 'active' ? '#25D36622' : '#FF4A4A22', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                    <Text style={{ color: item.status === 'active' ? '#25D366' : '#FF4A4A', fontSize: 11, fontWeight: '600' }}>{item.status}</Text>
                  </View>
                </View>
                <TouchableOpacity onPress={() => handleDeleteAutomation(item._id)}>
                  <Ionicons name="trash-outline" size={18} color="#FF4444" />
                </TouchableOpacity>
              </View>
              <Text style={{ color: '#CCD6E0', fontSize: 13, marginBottom: 8 }} numberOfLines={2}>
                {item.type === 'auto_followup' ? item.followup_message : item.message}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
                {item.type === 'auto_followup' && <Text style={{ color: '#666', fontSize: 12 }}>⏱ After {item.delay_days}d no reply</Text>}
                {item.type === 'recurring' && <Text style={{ color: '#666', fontSize: 12 }}>🕐 Every {item.recurrence} at {item.send_hour}:00</Text>}
                <Text style={{ color: '#666', fontSize: 12 }}>Runs: {item.runs || 0}</Text>
                {item.last_run
                  ? <Text style={{ color: '#25D366', fontSize: 12 }}>✓ Last ran {new Date(item.last_run).toLocaleDateString()}</Text>
                  : <Text style={{ color: '#F59E0B', fontSize: 12 }}>⏳ Not run yet</Text>
                }
              </View>
            </View>
          )}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="flash-outline" size={64} color="#666" />
              <Text style={styles.emptyText}>No automations yet</Text>
              <Text style={{ color: '#666', textAlign: 'center', marginTop: 8, paddingHorizontal: 20 }}>Tap + to create auto follow-ups or recurring broadcasts</Text>
            </View>
          }
        />
      )}

      {/* FAB */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => activeTab === 'broadcasts' ? setModalVisible(true) : setAutomationModalVisible(true)}
        activeOpacity={0.8}
      >
        <Ionicons name={activeTab === 'broadcasts' ? 'add' : 'flash'} size={22} color="#FFFFFF" />
      </TouchableOpacity>

      {/* Main Broadcast Modal */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setModalVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setModalVisible(false)}>
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
            {/* 0. Broadcast Name */}
            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Broadcast Name <Text style={{ color: '#666', fontWeight: '400' }}>(optional)</Text></Text>
              <TextInput
                style={styles.formInput}
                placeholder="e.g. January Sale, New Stock Alert..."
                placeholderTextColor="#666"
                value={broadcastName}
                onChangeText={setBroadcastName}
              />
            </View>

            {/* 1. Recipient Selection */}
            <View style={styles.formGroup}>
              <View style={styles.labelRow}>
                <Text style={styles.formLabel}>Send to</Text>
                <TouchableOpacity onPress={() => setCreateGroupModalVisible(true)}>
                  <Text style={styles.createGroupText}>+ New List</Text>
                </TouchableOpacity>
              </View>

              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filtersScroll}>
                {FILTERS.map((filter) => (
                  <TouchableOpacity
                    key={filter.id}
                    style={[
                      styles.filterOption,
                      selectedFilter === filter.id && styles.filterOptionSelected,
                    ]}
                    onPress={() => {
                      setSelectedFilter(filter.id);
                      setSelectedGroup('');
                    }}
                  >
                    <Ionicons
                      name={filter.icon as any}
                      size={18}
                      color={selectedFilter === filter.id ? '#FFFFFF' : '#666'}
                    />
                    <Text style={[
                      styles.filterOptionText,
                      selectedFilter === filter.id && styles.filterOptionTextSelected,
                    ]}>
                      {filter.label}
                    </Text>
                  </TouchableOpacity>
                ))}

                {groups.map((group) => (
                  <TouchableOpacity
                    key={group.id}
                    style={[
                      styles.filterOption,
                      selectedGroup === group.id && styles.filterOptionSelected,
                    ]}
                    onPress={() => {
                      setSelectedGroup(group.id);
                      setSelectedFilter('group');
                    }}
                    onLongPress={() => handleDeleteGroup(group.id)}
                  >
                    <Ionicons
                      name="people-circle"
                      size={18}
                      color={selectedGroup === group.id ? '#FFFFFF' : '#666'}
                    />
                    <Text style={[
                      styles.filterOptionText,
                      selectedGroup === group.id && styles.filterOptionTextSelected,
                    ]}>
                      {group.name}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
              <Text style={styles.recipientHint}>
                Targeting: {getFilteredCount()} customer(s)
              </Text>
            </View>

            {/* 2. Message Input */}
            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Message</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <TextInput
                  style={[styles.formInput, { flex: 1, marginBottom: 0 }]}
                  placeholder="Tell AI what to write, e.g. 20% off sale this weekend..."
                  placeholderTextColor="#555"
                  value={aiPrompt}
                  onChangeText={setAiPrompt}
                />
                <TouchableOpacity
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#1A2942', paddingHorizontal: 10, paddingVertical: 10, borderRadius: 8 }}
                  disabled={generatingAI}
                  onPress={handleGenerateAI}
                >
                  {generatingAI
                    ? <ActivityIndicator size="small" color="#FFD700" />
                    : <Ionicons name="sparkles" size={14} color="#FFD700" />}
                  <Text style={{ color: '#FFD700', fontSize: 12, fontWeight: '600' }}>
                    {generatingAI ? 'Writing...' : 'Draft'}
                  </Text>
                </TouchableOpacity>
              </View>
              <TextInput
                style={styles.messageInput}
                multiline
                placeholder="Type your message here..."
                placeholderTextColor="#666"
                value={message}
                onChangeText={setMessage}
                textAlignVertical="top"
              />
              <Text style={styles.charCount}>{message.length} chars</Text>

              {/* WhatsApp Warning */}
              {message.length > 0 && !selectedTemplate && (
                <View style={styles.warningBox}>
                  <Ionicons name="alert-circle" size={20} color="#FFD700" />
                  <Text style={styles.warningText}>
                    Note: For customers who haven't messaged you in 24h, you must use a template.
                  </Text>
                </View>
              )}
            </View>

            {/* 3. Image Selection */}
            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Message Image (Optional)</Text>

              <View style={styles.imageButtonsRow}>
                <TouchableOpacity
                  style={[styles.imagePickerButton, { flex: 1, marginRight: 8, padding: 12 }]}
                  onPress={pickImage}
                  disabled={uploadingImage}
                >
                  {uploadingImage ? (
                    <ActivityIndicator color="#25D366" />
                  ) : (
                    <>
                      <Ionicons name="scan-outline" size={20} color="#25D366" />
                      <Text style={[styles.imagePickerText, { marginTop: 4, fontSize: 12 }]}>Scan/Upload</Text>
                    </>
                  )}
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.imagePickerButton, { flex: 1, padding: 12 }]}
                  onPress={() => setProductModalVisible(true)}
                >
                  <Ionicons name="grid-outline" size={20} color="#3B82F6" />
                  <Text style={[styles.imagePickerText, { color: '#3B82F6', marginTop: 4, fontSize: 12 }]}>Product Gallery</Text>
                </TouchableOpacity>
              </View>

              {/* Selected Images List */}
              {selectedImages.length > 0 && (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.selectedImagesScroll}>
                  {selectedImages.map((imgUrl, index) => (
                    <View key={index} style={styles.selectedImageItem}>
                      <TouchableOpacity onPress={() => setViewingImage(imgUrl)}>
                        <Image source={{ uri: imgUrl }} style={styles.thumbnail} />
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={styles.removeImageBtn}
                        onPress={() => removeImage(imgUrl)}
                      >
                        <Ionicons name="close-circle" size={20} color="#FF4444" />
                      </TouchableOpacity>
                    </View>
                  ))}
                </ScrollView>
              )}
            </View>

            {/* 4. Templates */}
            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Templates</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                {TEMPLATES.map((t) => (
                  <TouchableOpacity key={t.id} style={styles.templateChip} onPress={() => handleSelectTemplate(t)}>
                    <Text style={styles.templateChipText}>{t.title}</Text>
                  </TouchableOpacity>
                ))}
                {templates.map((t) => (
                  <TouchableOpacity key={t.id} style={styles.templateChip} onPress={() => handleSelectCustomTemplate(t)}>
                    <Text style={styles.templateChipText}>{t.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>

            {/* 5. Schedule & Save */}
            <View style={styles.formGroup}>
              {/* Schedule Input */}
              <Text style={styles.formLabel}>Schedule (Optional)</Text>

              <View style={{ flexDirection: 'row', gap: 8 }}>
                {/* Date Picker Button */}
                <TouchableOpacity
                  style={[styles.formInput, { flex: 1 }]}
                  onPress={() => {
                    setTempDate(scheduledDate ? new Date(scheduledDate) : new Date());
                    setShowDatePicker(true);
                  }}
                >
                  <Ionicons name="calendar-outline" size={16} color="#666" style={{ marginRight: 8 }} />
                  <Text style={{ color: scheduledDate ? '#FFF' : '#666', flex: 1 }}>
                    {scheduledDate ? new Date(scheduledDate).toLocaleDateString() : 'Pick Date'}
                  </Text>
                </TouchableOpacity>

                {/* Time Picker Button */}
                <TouchableOpacity
                  style={[styles.formInput, { flex: 1 }]}
                  onPress={() => {
                    setTempDate(scheduledDate ? new Date(scheduledDate) : new Date());
                    setShowTimePicker(true);
                  }}
                >
                  <Ionicons name="time-outline" size={16} color="#666" style={{ marginRight: 8 }} />
                  <Text style={{ color: scheduledDate ? '#FFF' : '#666', flex: 1 }}>
                    {scheduledDate ? new Date(scheduledDate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Pick Time'}
                  </Text>
                </TouchableOpacity>
              </View>

              {scheduledDate && (
                <TouchableOpacity
                  onPress={() => setScheduledDate('')}
                  style={{ marginTop: 8, alignSelf: 'flex-start' }}
                >
                  <Text style={{ color: '#FF4444', fontSize: 12 }}>Clear Schedule</Text>
                </TouchableOpacity>
              )}

              {showDatePicker && (
                <DateTimePicker
                  value={tempDate}
                  mode="date"
                  display="default"
                  onChange={(event, selectedDate) => {
                    setShowDatePicker(false);
                    if (event.type === 'set' && selectedDate) {
                      // Preserve existing time if set, otherwise use current time
                      const currentScheduled = scheduledDate ? new Date(scheduledDate) : new Date();
                      selectedDate.setHours(currentScheduled.getHours());
                      selectedDate.setMinutes(currentScheduled.getMinutes());
                      setScheduledDate(selectedDate.toISOString());
                      setTempDate(selectedDate);
                    }
                  }}
                  minimumDate={new Date()}
                />
              )}

              {showTimePicker && (
                <DateTimePicker
                  value={tempDate}
                  mode="time"
                  display="default"
                  onChange={(event, selectedTime) => {
                    setShowTimePicker(false);
                    if (event.type === 'set' && selectedTime) {
                      // Preserve existing date if set, otherwise use today
                      const baseDate = scheduledDate ? new Date(scheduledDate) : new Date();
                      baseDate.setHours(selectedTime.getHours());
                      baseDate.setMinutes(selectedTime.getMinutes());
                      setScheduledDate(baseDate.toISOString());
                      setTempDate(baseDate);
                    }
                  }}
                />
              )}

              <View style={{ height: 16 }} />

              <TouchableOpacity
                style={styles.checkboxRow}
                onPress={() => setSaveAsTemplate(!saveAsTemplate)}
              >
                <Ionicons name={saveAsTemplate ? "checkbox" : "square-outline"} size={24} color="#25D366" />
                <Text style={styles.checkboxLabel}>Save as template</Text>
              </TouchableOpacity>

              {saveAsTemplate && (
                <TextInput
                  style={[styles.formInput, { marginTop: 8 }]}
                  value={templateName}
                  onChangeText={setTemplateName}
                  placeholder="Template Name"
                  placeholderTextColor="#666"
                />
              )}
            </View>

          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* View Broadcast Details Modal */}
      <Modal
        visible={!!viewingBroadcast}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setViewingBroadcast(null)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setViewingBroadcast(null)}>
              <Text style={styles.modalCancel}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle} numberOfLines={1}>
              {viewingBroadcast?.name || 'Broadcast Details'}
            </Text>
            <TouchableOpacity
              onPress={() => {
                if (!viewingBroadcast) return;
                Alert.alert(
                  'Delete Broadcast',
                  'Are you sure you want to delete this broadcast?',
                  [
                    { text: 'Cancel', style: 'cancel' },
                    {
                      text: 'Delete',
                      style: 'destructive',
                      onPress: async () => {
                        setDeletingBroadcast(true);
                        try {
                          await apiClient.delete(`/broadcasts/${viewingBroadcast.id}`);
                          setBroadcasts(prev => prev.filter(b => b.id !== viewingBroadcast.id));
                          setViewingBroadcast(null);
                        } catch (e: any) {
                          Alert.alert('Error', e.response?.data?.detail || 'Failed to delete');
                        } finally {
                          setDeletingBroadcast(false);
                        }
                      },
                    },
                  ]
                );
              }}
              disabled={deletingBroadcast}
            >
              {deletingBroadcast
                ? <ActivityIndicator size="small" color="#FF4444" />
                : <Ionicons name="trash-outline" size={22} color="#FF4444" />}
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalContent}>
            {viewingBroadcast && (
              <>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                  <View style={[styles.statusBadge,
                  { alignSelf: 'flex-start' },
                  viewingBroadcast.status === 'completed' && styles.statusCompleted,
                  viewingBroadcast.status === 'sending' && styles.statusSending,
                  ]}>
                    <Text style={styles.statusText}>
                      {viewingBroadcast.status === 'completed' ? 'Sent' : 'Sending...'}
                    </Text>
                  </View>

                  {viewingBroadcast.scheduled_at && new Date(viewingBroadcast.scheduled_at) > new Date() && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: '#3B82F6', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                      <Ionicons name="time-outline" size={14} color="#FFF" />
                      <Text style={{ color: '#FFF', fontSize: 11, marginLeft: 4, fontWeight: '600' }}>
                        Scheduled: {new Date(viewingBroadcast.scheduled_at).toLocaleString('en-KE', {
                          month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                        })}
                      </Text>
                    </View>
                  )}
                </View>

                <View style={styles.statsRow}>
                  <View style={styles.statCard}>
                    <Text style={styles.statValue}>{viewingBroadcast.sent_count}</Text>
                    <Text style={styles.statLabel}>Sent</Text>
                  </View>
                  <View style={styles.statCard}>
                    <Text style={styles.statValue}>{viewingBroadcast.recipients_count}</Text>
                    <Text style={styles.statLabel}>Total</Text>
                  </View>
                </View>

                <Text style={[styles.formLabel, { marginTop: 16 }]}>Message</Text>
                <View style={{ backgroundColor: '#1A2942', padding: 16, borderRadius: 12, marginBottom: 24 }}>
                  <Text style={{ color: '#FFF', fontSize: 16, lineHeight: 24 }}>{viewingBroadcast.message}</Text>
                </View>

                {(viewingBroadcast.image_urls || viewingBroadcast.image_url) && (
                  <View>
                    <Text style={styles.formLabel}>Images</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 24 }}>
                      {(viewingBroadcast.image_urls || [viewingBroadcast.image_url]).filter(Boolean).map((img, idx) => (
                        <Image key={idx} source={{ uri: img }} style={{ width: 200, height: 200, borderRadius: 12, marginRight: 12 }} />
                      ))}
                    </ScrollView>
                  </View>
                )}

                <Text style={styles.recipientHint}>
                  Sent on {new Date(viewingBroadcast.created_at).toLocaleString()}
                </Text>

                {/* Performance */}
                {performance[viewingBroadcast.id] && (
                  <View style={{ backgroundColor: '#0A1628', borderRadius: 12, padding: 16, marginBottom: 16 }}>
                    <Text style={[styles.formLabel, { marginBottom: 12 }]}>📊 Performance (3-day window)</Text>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-around' }}>
                      <View style={{ alignItems: 'center' }}>
                        <Text style={{ color: '#25D366', fontSize: 22, fontWeight: 'bold' }}>{performance[viewingBroadcast.id].replies}</Text>
                        <Text style={{ color: '#666', fontSize: 11 }}>Replies</Text>
                      </View>
                      <View style={{ alignItems: 'center' }}>
                        <Text style={{ color: '#F59E0B', fontSize: 22, fontWeight: 'bold' }}>{performance[viewingBroadcast.id].reply_rate}%</Text>
                        <Text style={{ color: '#666', fontSize: 11 }}>Reply Rate</Text>
                      </View>
                      <View style={{ alignItems: 'center' }}>
                        <Text style={{ color: '#4A90D9', fontSize: 22, fontWeight: 'bold' }}>{performance[viewingBroadcast.id].sent_count}</Text>
                        <Text style={{ color: '#666', fontSize: 11 }}>Delivered</Text>
                      </View>
                    </View>
                  </View>
                )}

                <View style={{ flexDirection: 'row', gap: 10, marginBottom: 10 }}>
                  <TouchableOpacity
                    style={[styles.generateButton, { flex: 1, backgroundColor: '#1E3A5F' }]}
                    onPress={() => {
                      setMessage(viewingBroadcast.message);
                      setBroadcastName(viewingBroadcast.name ? `${viewingBroadcast.name} (Copy)` : '');
                      if (viewingBroadcast.image_urls) setSelectedImages(viewingBroadcast.image_urls);
                      else if (viewingBroadcast.image_url) setSelectedImages([viewingBroadcast.image_url]);
                      setViewingBroadcast(null);
                      setModalVisible(true);
                    }}
                  >
                    <Text style={[styles.generateButtonText, { color: '#4A90D9' }]}>Reuse Message</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.generateButton, { flex: 1 }]}
                    onPress={() => { handleResend(viewingBroadcast); setViewingBroadcast(null); }}
                  >
                    <Text style={styles.generateButtonText}>🔁 Resend Now</Text>
                  </TouchableOpacity>
                </View>
                <TouchableOpacity
                  style={[styles.generateButton, { backgroundColor: '#F59E0B' }]}
                  onPress={() => {
                    setSelectedBroadcastForFollowUp(viewingBroadcast.id);
                    setAutomationType('auto_followup');
                    setViewingBroadcast(null);
                    setAutomationModalVisible(true);
                  }}
                >
                  <Text style={styles.generateButtonText}>⚡ Create Auto Follow-up</Text>
                </TouchableOpacity>
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* View Image Modal */}
      <Modal visible={!!viewingImage} transparent={true} onRequestClose={() => setViewingImage(null)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.9)', justifyContent: 'center', alignItems: 'center' }}>
          <TouchableOpacity
            style={{ position: 'absolute', top: 40, right: 20, zIndex: 10 }}
            onPress={() => setViewingImage(null)}
          >
            <Ionicons name="close" size={30} color="#FFF" />
          </TouchableOpacity>
          {viewingImage && (
            <Image
              source={{ uri: viewingImage }}
              style={{ width: '90%', height: '70%', resizeMode: 'contain' }}
            />
          )}
        </View>
      </Modal>

      {/* CREATE GROUP MODAL */}
      <Modal
        visible={createGroupModalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setCreateGroupModalVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setCreateGroupModalVisible(false)}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>New List</Text>
            <TouchableOpacity onPress={handleCreateGroup}>
              <Text style={styles.modalSave}>Save</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.modalContent}>
            <TextInput
              style={styles.formInput}
              value={newGroupName}
              onChangeText={setNewGroupName}
              placeholder="List Name (e.g., VIP Buyers)"
              placeholderTextColor="#666"
            />
            <Text style={[styles.formLabel, { marginTop: 16, marginBottom: 8 }]}>Select Customers ({selectedCustomerIds.size})</Text>

            <View style={[styles.formInput, { flexDirection: 'row', alignItems: 'center', marginBottom: 8, paddingVertical: 0 }]}>
              <Ionicons name="search" size={16} color="#666" style={{ marginRight: 8 }} />
              <TextInput
                style={{ flex: 1, color: '#FFF', fontSize: 14, height: 40 }}
                value={groupCustomerSearch}
                onChangeText={setGroupCustomerSearch}
                placeholder="Search customers..."
                placeholderTextColor="#666"
              />
              {groupCustomerSearch.length > 0 && (
                <TouchableOpacity onPress={() => setGroupCustomerSearch('')}>
                  <Ionicons name="close-circle" size={16} color="#666" />
                </TouchableOpacity>
              )}
            </View>

            <FlatList
              data={customers.filter(c =>
                c.name.toLowerCase().includes(groupCustomerSearch.toLowerCase()) ||
                c.phone_number.includes(groupCustomerSearch)
              )}
              keyExtractor={item => item.id}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={styles.customerSelectItem}
                  onPress={() => toggleCustomerSelection(item.id)}
                >
                  <View style={styles.customerSelectInfo}>
                    <Text style={styles.customerSelectName}>{item.name}</Text>
                    <Text style={styles.customerSelectPhone}>{item.phone_number}</Text>
                  </View>
                  {selectedCustomerIds.has(item.id) && (
                    <Ionicons name="checkmark-circle" size={24} color="#25D366" />
                  )}
                </TouchableOpacity>
              )}
            />
          </View>
        </SafeAreaView>
      </Modal>

      {/* PRODUCT GALLERY MODAL */}
      <Modal
        visible={productModalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setProductModalVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setProductModalVisible(false)}>
              <Text style={styles.modalCancel}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>
              {selectedProductIds.size > 0 ? `${selectedProductIds.size} Selected` : 'Select/Edit'}
            </Text>
            <TouchableOpacity onPress={handleConfirmProductSelection}>
              <Text style={[styles.modalSave, selectedProductIds.size === 0 && styles.modalSaveDisabled]}>
                {selectedProductIds.size > 0 ? 'Add' : ''}
              </Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalContent} contentContainerStyle={{ paddingBottom: selectedProductIds.size > 0 ? 80 : 20 }}>
            {Object.keys(productsByCategory).map((category) => (
              <View key={category} style={styles.categorySection}>
                <Text style={styles.categoryTitle}>{category}</Text>
                <View style={styles.productGrid}>
                  {productsByCategory[category].map((product) => {
                    const isSelected = selectedProductIds.has(product.id);
                    const imgUrl = product.image_url
                      ? (product.image_url.startsWith('http') ? product.image_url : `${process.env.EXPO_PUBLIC_BACKEND_URL}${product.image_url}`)
                      : null;
                    return (
                      <View key={product.id} style={[styles.productItem, isSelected && styles.productItemSelected]}>
                        <TouchableOpacity
                          style={styles.productTouchable}
                          onPress={() => handleToggleProductSelection(product)}
                        >
                          {imgUrl ? (
                            <Image source={{ uri: imgUrl }} style={styles.productImage} resizeMode="cover" />
                          ) : (
                            <View style={[styles.productImage, { backgroundColor: '#0D1B2A', justifyContent: 'center', alignItems: 'center' }]}>
                              <Ionicons name="image-outline" size={28} color="#3A4A5C" />
                            </View>
                          )}
                          <Text style={styles.productName} numberOfLines={1}>{product.name}</Text>
                          <Text style={styles.productPrice}>{currency} {product.price?.toLocaleString() || 0}</Text>
                        </TouchableOpacity>

                        {/* Edit Button Overlay */}
                        <TouchableOpacity
                          style={styles.editProductBtn}
                          onPress={() => openEditProduct(product)}
                        >
                          <Ionicons name="pencil" size={14} color="#FFF" />
                        </TouchableOpacity>

                        {/* Selection Indicator */}
                        {isSelected && (
                          <View style={styles.selectionBadge}>
                            <Ionicons name="checkmark" size={12} color="#FFF" />
                          </View>
                        )}
                      </View>
                    )
                  })}
                </View>
              </View>
            ))}
          </ScrollView>

          {/* Floating action bar when products are selected */}
          {selectedProductIds.size > 0 && (
            <View style={styles.broadcastCatalogBar}>
              <TouchableOpacity
                style={styles.broadcastCatalogAddBtn}
                onPress={handleConfirmProductSelection}
              >
                <Ionicons name="images-outline" size={18} color="#3B82F6" />
                <Text style={styles.broadcastCatalogAddText}>Add Images</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.broadcastCatalogSendBtn, broadcastingCatalog && { opacity: 0.6 }]}
                onPress={handleBroadcastCatalog}
                disabled={broadcastingCatalog}
              >
                {broadcastingCatalog ? (
                  <ActivityIndicator size="small" color="#FFF" />
                ) : (
                  <>
                    <Ionicons name="megaphone-outline" size={18} color="#FFF" />
                    <Text style={styles.broadcastCatalogSendText}>Broadcast Catalog ({selectedProductIds.size})</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          )}
        </SafeAreaView>
      </Modal>

      {/* EDIT PRODUCT MODAL */}
      <Modal
        visible={editProductModalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setEditProductModalVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setEditProductModalVisible(false)}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Edit Product</Text>
            <TouchableOpacity onPress={handleSaveProduct}>
              <Text style={styles.modalSave}>Save</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalContent}>
            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Product Name</Text>
              <TextInput
                style={styles.formInput}
                value={editName}
                onChangeText={setEditName}
                placeholder="Product Name"
                placeholderTextColor="#666"
              />
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Price ({currency})</Text>
              <TextInput
                style={styles.formInput}
                value={editPrice}
                onChangeText={setEditPrice}
                keyboardType="numeric"
                placeholder="0.00"
                placeholderTextColor="#666"
              />
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Images</Text>
              <View style={styles.modalImageGrid}>
                {editImages.map((img, idx) => (
                  <View key={idx} style={styles.modalImageItem}>
                    <Image source={{ uri: img }} style={styles.thumbnail} />
                    <TouchableOpacity
                      style={[styles.removeImageBtn, { right: -5, top: -5 }]}
                      onPress={() => setEditImages(editImages.filter((_, i) => i !== idx))}
                    >
                      <Ionicons name="close-circle" size={20} color="#FF4444" />
                    </TouchableOpacity>
                  </View>
                ))}
                <TouchableOpacity style={styles.addNewImageBtn} onPress={handleAddImageToProduct}>
                  <Ionicons name="add" size={24} color="#3B82F6" />
                </TouchableOpacity>
              </View>
            </View>
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Automation Modal */}
      <Modal
        visible={automationModalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setAutomationModalVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setAutomationModalVisible(false)}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>New Automation</Text>
            <TouchableOpacity onPress={handleCreateAutomation}>
              <Text style={styles.modalSave}>Save</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalContent}>
            {/* Type toggle */}
            <View style={{ flexDirection: 'row', backgroundColor: '#1A2942', borderRadius: 10, padding: 4, marginBottom: 20 }}>
              <TouchableOpacity
                style={{ flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: 8, backgroundColor: automationType === 'auto_followup' ? '#F59E0B' : 'transparent' }}
                onPress={() => setAutomationType('auto_followup')}
              >
                <Text style={{ color: automationType === 'auto_followup' ? '#FFF' : '#666', fontWeight: '600' }}>Auto Follow-up</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={{ flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: 8, backgroundColor: automationType === 'recurring' ? '#8B5CF6' : 'transparent' }}
                onPress={() => setAutomationType('recurring')}
              >
                <Text style={{ color: automationType === 'recurring' ? '#FFF' : '#666', fontWeight: '600' }}>Recurring</Text>
              </TouchableOpacity>
            </View>

            {automationType === 'auto_followup' && (
              <>
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Select Broadcast to Follow Up</Text>
                  <ScrollView style={{ maxHeight: 160, backgroundColor: '#1A2942', borderRadius: 8, padding: 4 }}>
                    {broadcasts.filter(b => b.status === 'completed').map(b => (
                      <TouchableOpacity
                        key={b.id}
                        style={{ flexDirection: 'row', alignItems: 'center', padding: 10, backgroundColor: selectedBroadcastForFollowUp === b.id ? '#1E3A5F' : 'transparent', borderRadius: 8, marginBottom: 4, borderWidth: selectedBroadcastForFollowUp === b.id ? 1 : 0, borderColor: '#25D366' }}
                        onPress={() => setSelectedBroadcastForFollowUp(b.id)}
                      >
                        <Ionicons name={selectedBroadcastForFollowUp === b.id ? 'radio-button-on' : 'radio-button-off'} size={18} color="#25D366" />
                        <View style={{ flex: 1, marginLeft: 10 }}>
                          {b.name ? (
                            <Text style={{ color: '#FFF', fontSize: 13, fontWeight: '600' }} numberOfLines={1}>{b.name}</Text>
                          ) : null}
                          <Text style={{ color: b.name ? '#888' : '#FFF', fontSize: b.name ? 11 : 13 }} numberOfLines={1}>{b.message}</Text>
                        </View>
                        <Text style={{ color: '#666', fontSize: 11, marginLeft: 6 }}>{new Date(b.created_at).toLocaleDateString()}</Text>
                      </TouchableOpacity>
                    ))}
                    {broadcasts.filter(b => b.status === 'completed').length === 0 && (
                      <Text style={{ color: '#666', padding: 10, textAlign: 'center' }}>No completed broadcasts yet</Text>
                    )}
                  </ScrollView>
                </View>
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Follow-up Message</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <TextInput
                      style={[styles.formInput, { flex: 1, marginBottom: 0 }]}
                      placeholder="Tell AI what to write, e.g. remind them about our 20% sale..."
                      placeholderTextColor="#555"
                      value={followUpAIDirection}
                      onChangeText={setFollowUpAIDirection}
                    />
                    <TouchableOpacity
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#1A2942', paddingHorizontal: 10, paddingVertical: 10, borderRadius: 8 }}
                      disabled={generatingFollowUpAI}
                      onPress={async () => {
                        const selectedB = broadcasts.find(b => b.id === selectedBroadcastForFollowUp);
                        const context = selectedB ? `for customers who didn't reply to our broadcast: "${selectedB.name || selectedB.message.slice(0, 60)}"` : `for customers who didn't reply to our broadcast`;
                        const direction = followUpAIDirection.trim();
                        setGeneratingFollowUpAI(true);
                        try {
                          const res = await apiClient.post('/ai/generate-broadcast-message', {
                            prompt: direction
                              ? `Write a short WhatsApp follow-up message ${context}. Direction: ${direction}. Keep it under 2 sentences, conversational, include {{name}}.`
                              : `Write a short, friendly WhatsApp follow-up message ${context}. Keep it under 2 sentences, conversational, include {{name}}.`,
                          });
                          setFollowUpMessage(res.data.message);
                        } catch (e: any) {
                          Alert.alert('Error', e.response?.data?.detail || 'Failed to generate');
                        } finally {
                          setGeneratingFollowUpAI(false);
                        }
                      }}
                    >
                      {generatingFollowUpAI
                        ? <ActivityIndicator size="small" color="#25D366" />
                        : <Ionicons name="sparkles" size={14} color="#25D366" />}
                      <Text style={{ color: '#25D366', fontSize: 12, fontWeight: '600' }}>
                        {generatingFollowUpAI ? 'Writing...' : 'Draft'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                  <TextInput
                    style={[styles.messageInput, { minHeight: 80 }]}
                    multiline
                    placeholder="e.g. Hey! Just checking if you saw our message 😊"
                    placeholderTextColor="#666"
                    value={followUpMessage}
                    onChangeText={setFollowUpMessage}
                  />
                </View>
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Send After (days of no reply)</Text>
                  <TextInput
                    style={styles.formInput}
                    keyboardType="numeric"
                    value={followUpDelayDays}
                    onChangeText={setFollowUpDelayDays}
                    placeholder="2"
                    placeholderTextColor="#666"
                  />
                  <Text style={{ color: '#666', fontSize: 12, marginTop: 4 }}>Customers who didn't reply after {followUpDelayDays} day(s) will get this message</Text>
                </View>
              </>
            )}

            {automationType === 'recurring' && (
              <>
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Message</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <TextInput
                      style={[styles.formInput, { flex: 1, marginBottom: 0 }]}
                      placeholder="Tell AI what to write, e.g. new arrivals, weekend sale..."
                      placeholderTextColor="#555"
                      value={recurringAIDirection}
                      onChangeText={setRecurringAIDirection}
                    />
                    <TouchableOpacity
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#1A2942', paddingHorizontal: 10, paddingVertical: 10, borderRadius: 8 }}
                      disabled={generatingRecurringAI}
                      onPress={async () => {
                        setGeneratingRecurringAI(true);
                        try {
                          const audience = recurringFilter === 'all' ? 'all customers' : `${recurringFilter} customers`;
                          const direction = recurringAIDirection.trim();
                          const res = await apiClient.post('/ai/generate-broadcast-message', {
                            prompt: direction
                              ? `Write a short WhatsApp broadcast message to ${audience}. Direction: ${direction}. Keep it under 3 sentences, friendly, include a call to action, include {{name}}.`
                              : `Write a short, engaging WhatsApp broadcast message for a ${recurrence} recurring message to ${audience}. Keep it under 3 sentences, friendly, include a call to action, include {{name}}.`,
                          });
                          setRecurringMessage(res.data.message);
                        } catch (e: any) {
                          Alert.alert('Error', e.response?.data?.detail || 'Failed to generate');
                        } finally {
                          setGeneratingRecurringAI(false);
                        }
                      }}
                    >
                      {generatingRecurringAI
                        ? <ActivityIndicator size="small" color="#8B5CF6" />
                        : <Ionicons name="sparkles" size={14} color="#8B5CF6" />}
                      <Text style={{ color: '#8B5CF6', fontSize: 12, fontWeight: '600' }}>
                        {generatingRecurringAI ? 'Writing...' : 'Draft'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                  <TextInput
                    style={[styles.messageInput, { minHeight: 80 }]}
                    multiline
                    placeholder="e.g. New stock just arrived! Reply to see what's new 🔥"
                    placeholderTextColor="#666"
                    value={recurringMessage}
                    onChangeText={setRecurringMessage}
                  />
                </View>
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Send To</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                    {FILTERS.map(f => (
                      <TouchableOpacity
                        key={f.id}
                        style={[styles.filterOption, recurringFilter === f.id && styles.filterOptionSelected]}
                        onPress={() => setRecurringFilter(f.id)}
                      >
                        <Text style={[styles.filterOptionText, recurringFilter === f.id && styles.filterOptionTextSelected]}>{f.label}</Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                </View>
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Frequency</Text>
                  <View style={{ flexDirection: 'row', gap: 10 }}>
                    {(['weekly', 'monthly'] as const).map(r => (
                      <TouchableOpacity
                        key={r}
                        style={{ flex: 1, paddingVertical: 12, alignItems: 'center', borderRadius: 8, backgroundColor: recurrence === r ? '#8B5CF6' : '#1A2942' }}
                        onPress={() => setRecurrence(r)}
                      >
                        <Text style={{ color: recurrence === r ? '#FFF' : '#666', fontWeight: '600' }}>{r === 'weekly' ? '📅 Weekly' : '🗓 Monthly'}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Send Hour (0–23)</Text>
                  <TextInput
                    style={styles.formInput}
                    keyboardType="numeric"
                    value={sendHour}
                    onChangeText={setSendHour}
                    placeholder="9"
                    placeholderTextColor="#666"
                  />
                  <Text style={{ color: '#666', fontSize: 12, marginTop: 4 }}>Will send at {sendHour}:00 every {recurrence === 'weekly' ? 'week' : 'month'}</Text>
                </View>
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>


    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A1628' },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { paddingHorizontal: 16, paddingVertical: 10 },
  headerTitle: { fontSize: 22, fontWeight: 'bold', color: '#FFFFFF' },
  headerSubtitle: { color: '#666', fontSize: 12 },
  statsRow: { flexDirection: 'row', paddingHorizontal: 16, gap: 8, marginBottom: 10 },
  statCard: { flex: 1, backgroundColor: '#1A2942', padding: 10, borderRadius: 10, alignItems: 'center' },
  statValue: { fontSize: 20, fontWeight: 'bold', color: '#25D366' },
  statLabel: { color: '#666', fontSize: 11 },
  listContent: { padding: 16 },
  broadcastCard: { backgroundColor: '#1A2942', padding: 12, borderRadius: 10, marginBottom: 10 },
  broadcastHeader: { flexDirection: 'row', marginBottom: 12 },
  broadcastIcon: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#0A1628', justifyContent: 'center', alignItems: 'center', marginRight: 10 },
  broadcastInfo: { flex: 1 },
  broadcastDate: { color: '#FFF', fontWeight: '600', marginBottom: 4 },
  statusRow: { flexDirection: 'row', alignItems: 'center' },
  statusBadge: { backgroundColor: '#2563EB', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, marginRight: 8 },
  statusCompleted: { backgroundColor: '#25D366' },
  statusSending: { backgroundColor: '#F59E0B' },
  statusText: { color: '#FFF', fontSize: 10, fontWeight: 'bold' },
  recipientCount: { color: '#666', fontSize: 12 },
  broadcastMessage: { color: '#CCD6E0' },
  fab: { position: 'absolute', bottom: 20, right: 16, width: 46, height: 46, borderRadius: 23, backgroundColor: '#25D366', justifyContent: 'center', alignItems: 'center', shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.25, shadowRadius: 4, elevation: 6 },

  // Modal Styles
  modalContainer: { flex: 1, backgroundColor: '#0A1628' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: '#1A2942', alignItems: 'center' },
  modalTitle: { fontSize: 18, fontWeight: 'bold', color: '#FFF' },
  modalCancel: { color: '#FF4444', fontSize: 16 },
  modalSave: { color: '#25D366', fontSize: 16, fontWeight: 'bold' },
  modalSaveDisabled: { opacity: 0.5 },
  modalContent: { padding: 16 },

  formGroup: { marginBottom: 18 },
  labelRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  formLabel: { color: '#FFF', fontSize: 14, fontWeight: '600', marginBottom: 6 },
  formInput: { backgroundColor: '#1A2942', borderRadius: 8, padding: 10, color: '#FFF', fontSize: 14 },
  messageInput: { backgroundColor: '#1A2942', borderRadius: 8, padding: 10, color: '#FFF', fontSize: 14, minHeight: 80 },
  charCount: { color: '#666', fontSize: 12, textAlign: 'right', marginTop: 4 },

  // Filters & Groups
  filtersScroll: { flexDirection: 'row', marginBottom: 8 },
  filterOption: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', padding: 8, borderRadius: 14, marginRight: 6 },
  filterOptionSelected: { backgroundColor: '#25D366' },
  filterOptionText: { color: '#666', marginLeft: 6, fontWeight: '500' },
  filterOptionTextSelected: { color: '#FFF' },
  createGroupText: { color: '#3B82F6', fontWeight: 'bold' },
  recipientHint: { color: '#666', fontSize: 12, marginTop: 4 },

  // Images
  imageButtonsRow: { flexDirection: 'row', gap: 12, marginBottom: 12 },
  imagePickerButton: { backgroundColor: '#1A2942', borderRadius: 12, padding: 16, alignItems: 'center', justifyContent: 'center', borderStyle: 'dashed', borderWidth: 1, borderColor: '#334155' },
  imagePickerText: { color: '#25D366', marginTop: 8, fontWeight: '600' },

  selectedImageRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', padding: 8, borderRadius: 12, borderWidth: 1, borderColor: '#334155' },
  thumbnail: { width: 44, height: 44, borderRadius: 8 },

  // Templates
  templateChip: { backgroundColor: '#1A2942', padding: 10, borderRadius: 8, marginRight: 8 },
  templateChipText: { color: '#FFF', fontSize: 14 },

  // Product Gallery
  categorySection: { marginBottom: 24 },
  categoryTitle: { color: '#666', fontSize: 14, fontWeight: 'bold', marginBottom: 12, textTransform: 'uppercase' },
  productGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  productItem: { width: '47%', backgroundColor: '#1A2942', borderRadius: 10, overflow: 'hidden', marginBottom: 4 },
  productImage: { width: '100%', height: 120, borderTopLeftRadius: 10, borderTopRightRadius: 10 },
  productName: { color: '#FFF', fontSize: 13, fontWeight: '500', paddingHorizontal: 8, paddingTop: 6 },
  productPrice: { color: '#25D366', fontSize: 13, fontWeight: 'bold', paddingHorizontal: 8, paddingBottom: 8 },

  // Customer Selection
  customerSelectItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#1A2942' },
  customerSelectInfo: { flex: 1 },
  customerSelectName: { color: '#FFF', fontSize: 16, fontWeight: '500' },
  customerSelectPhone: { color: '#666', fontSize: 14 },

  aiButton: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  aiButtonText: { color: '#FFD700', fontSize: 12, fontWeight: 'bold', marginLeft: 4 },
  checkboxRow: { flexDirection: 'row', alignItems: 'center', marginVertical: 8 },
  checkboxLabel: { color: '#FFF', marginLeft: 8, fontSize: 16 },

  warningBox: { flexDirection: 'row', backgroundColor: 'rgba(255, 215, 0, 0.1)', padding: 12, borderRadius: 8, marginTop: 16 },
  warningText: { color: '#FFD700', marginLeft: 8, flex: 1, fontSize: 12 },

  emptyContainer: { alignItems: 'center', padding: 40 },
  emptyText: { color: '#FFF', fontSize: 18, marginTop: 16, fontWeight: 'bold' },

  // Product Gallery Multi-select Styles
  productItemSelected: {
    borderColor: '#25D366',
    borderWidth: 2,
    borderRadius: 10,
  },
  productTouchable: {
    flex: 1,
  },
  editProductBtn: {
    position: 'absolute',
    top: 4,
    right: 4,
    backgroundColor: 'rgba(0,0,0,0.6)',
    padding: 6,
    borderRadius: 12,
  },
  selectionBadge: {
    position: 'absolute',
    top: 4,
    left: 4,
    backgroundColor: '#25D366',
    width: 20,
    height: 20,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },

  // Selected Images Horizontal List
  selectedImagesScroll: {
    flexDirection: 'row',
    marginTop: 8,
  },
  selectedImageItem: {
    marginRight: 10,
    position: 'relative',
  },
  removeImageBtn: {
    position: 'absolute',
    top: -6,
    right: -6,
    backgroundColor: '#fff',
    borderRadius: 10,
  },

  // Edit Modal Styles
  modalImageGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    backgroundColor: '#1A2942',
    padding: 10,
    borderRadius: 8,
  },
  modalImageItem: {
    position: 'relative',
  },
  addNewImageBtn: {
    width: 44,
    height: 44,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#3B82F6',
    borderStyle: 'dashed',
    justifyContent: 'center',
    alignItems: 'center',
  },
  generateButton: {
    backgroundColor: '#25D366',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginTop: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  generateButtonText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: 'bold',
  },
  // Broadcast Catalog Bar
  broadcastCatalogBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0D1B2A',
    borderTopWidth: 1,
    borderTopColor: '#2A3A52',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  broadcastCatalogAddBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1A2942',
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 10,
    gap: 6,
    borderWidth: 1,
    borderColor: '#3B82F6',
  },
  broadcastCatalogAddText: {
    color: '#3B82F6',
    fontSize: 13,
    fontWeight: '600',
  },
  broadcastCatalogSendBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    paddingVertical: 12,
    borderRadius: 10,
    gap: 8,
  },
  broadcastCatalogSendText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '700',
  },
});
