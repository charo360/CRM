import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { apiClient, messageHelpers } from '../context/api';
import LoyaltyCard from './components/LoyaltyCard';
import CustomerFeedbackModal from './components/CustomerFeedbackModal';
import { useBusiness } from '../context/BusinessContext';

const TAGS = ['New', 'VIP', 'Returning', 'Wholesale'];

export default function CustomerProfileScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    customerId: string;
    customerName: string;
    customerPhone: string;
  }>();

  const customerId = params.customerId || '';
  const initialName = params.customerName || '';
  const customerPhone = params.customerPhone || '';

  const { isServiceBusiness, businessType: bizType } = useBusiness();
  const [name, setName] = useState(initialName);
  const [notes, setNotes] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [purchaseCount, setPurchaseCount] = useState(0);
  const [totalSpent, setTotalSpent] = useState(0);
  const [bookingCount, setBookingCount] = useState(0);
  const [currency, setCurrency] = useState('USD');
  const [profilePicture, setProfilePicture] = useState<string | null>(null);
  const [imgError, setImgError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showTagInput, setShowTagInput] = useState(false);
  const [newTagText, setNewTagText] = useState('');
  const scrollRef = useRef<ScrollView>(null);
  const [activeTab, setActiveTab] = useState<'info' | 'timeline' | 'loyalty' | 'feedback'>('info');
  const [feedbackVisible, setFeedbackVisible] = useState(false);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [loadingTimeline, setLoadingTimeline] = useState(false);

  useEffect(() => {
    fetchCustomer();
  }, [customerId]);

  const fetchCustomer = async () => {
    if (!customerId) { setLoading(false); return; }
    try {
      const [custRes, settingsRes] = await Promise.all([
        apiClient.get(`/customers/${customerId}`),
        apiClient.get('/settings'),
      ]);
      const c = custRes.data;
      setName(c.name || initialName);
      setNotes(c.notes || '');
      setTags(c.tags || []);
      setPurchaseCount(c.purchase_count || 0);
      setTotalSpent(c.total_spent || 0);
      // Fetch booking count for service businesses
      try {
        const bkRes = await apiClient.get(`/bookings?customer_id=${customerId}`);
        setBookingCount(Array.isArray(bkRes.data) ? bkRes.data.length : 0);
      } catch (_) {}
      setProfilePicture(c.profile_picture || null);
      setImgError(false);
      if (settingsRes.data?.currency) setCurrency(settingsRes.data.currency);
    } catch (error) {
      console.error('Error fetching customer:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTimeline = async () => {
    if (!customerId) return;
    setLoadingTimeline(true);
    try {
      const data = await messageHelpers.getTimeline(customerId);
      setTimeline(data || []);
    } catch (error) {
      console.error('Error fetching timeline:', error);
    } finally {
      setLoadingTimeline(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'timeline' && timeline.length === 0) {
      fetchTimeline();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'feedback') setFeedbackVisible(true);
  }, [activeTab]);

  const toggleTag = (tag: string) => {
    setTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);
  };

  const addCustomTag = () => {
    const t = newTagText.trim();
    if (!t) return;
    if (!tags.includes(t)) setTags(prev => [...prev, t]);
    setNewTagText('');
    setShowTagInput(false);
  };

  const handleSave = async () => {
    if (!name.trim()) {
      Alert.alert('Error', 'Name is required');
      return;
    }
    setSaving(true);
    try {
      await apiClient.put(`/customers/${customerId}`, {
        name: name.trim(),
        notes: notes || null,
        tags,
      });
      Alert.alert('Saved', 'Customer updated successfully');
      router.back();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to update customer');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = () => {
    Alert.alert(
      'Delete Customer',
      `Are you sure you want to delete ${name}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.delete(`/customers/${customerId}`);
              router.dismiss(2);
            } catch (error) {
              Alert.alert('Error', 'Failed to delete customer');
            }
          },
        },
      ]
    );
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#00A884" />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#E9EDEF" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Contact Info</Text>
        <TouchableOpacity onPress={handleSave} disabled={saving}>
          <Text style={[styles.saveText, saving && { opacity: 0.5 }]}>
            {saving ? 'Saving...' : 'Save'}
          </Text>
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
      <ScrollView ref={scrollRef} style={styles.content} keyboardShouldPersistTaps="handled">
        {/* Avatar + Name */}
        <View style={styles.profileSection}>
          {profilePicture && !imgError ? (
            <Image
              source={{ uri: profilePicture }}
              style={styles.avatarLargeImage}
              onError={() => setImgError(true)}
            />
          ) : (
            <View style={styles.avatarLarge}>
              <Text style={styles.avatarLargeText}>{name.charAt(0).toUpperCase()}</Text>
            </View>
          )}
          <Text style={styles.phoneText}>{customerPhone}</Text>
          {isServiceBusiness ? (
            bookingCount > 0 && (
              <Text style={styles.statsText}>
                {bookingCount} {bookingCount === 1
                  ? (bizType === 'tech' ? 'demo' : bizType === 'creator' ? 'collab' : bizType === 'restaurant' ? 'reservation' : bizType === 'fitness' ? 'session' : bizType === 'rental' ? 'booking' : 'appointment')
                  : (bizType === 'tech' ? 'demos' : bizType === 'creator' ? 'collabs' : bizType === 'restaurant' ? 'reservations' : bizType === 'fitness' ? 'sessions' : bizType === 'rental' ? 'bookings' : 'appointments')}
              </Text>
            )
          ) : (
            purchaseCount > 0 && (
              <Text style={styles.statsText}>
                {purchaseCount} {purchaseCount === 1 ? 'sale' : 'sales'} · {currency} {totalSpent.toLocaleString()}
              </Text>
            )
          )}
        </View>

        {/* Tab Switcher */}
        <View style={styles.tabBar}>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'info' && styles.tabActive]}
            onPress={() => setActiveTab('info')}
          >
            <Ionicons name="information-circle" size={18} color={activeTab === 'info' ? '#00A884' : '#8696A0'} />
            <Text style={[styles.tabText, activeTab === 'info' && styles.tabTextActive]}>Info</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'timeline' && styles.tabActive]}
            onPress={() => setActiveTab('timeline')}
          >
            <Ionicons name="time" size={18} color={activeTab === 'timeline' ? '#00A884' : '#8696A0'} />
            <Text style={[styles.tabText, activeTab === 'timeline' && styles.tabTextActive]}>Timeline</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'loyalty' && styles.tabActive]}
            onPress={() => setActiveTab('loyalty')}
          >
            <Ionicons name="trophy" size={18} color={activeTab === 'loyalty' ? '#00A884' : '#8696A0'} />
            <Text style={[styles.tabText, activeTab === 'loyalty' && styles.tabTextActive]}>Loyalty</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'feedback' && styles.tabActive]}
            onPress={() => setActiveTab('feedback')}
          >
            <Ionicons name="chatbubbles" size={18} color={activeTab === 'feedback' ? '#00A884' : '#8696A0'} />
            <Text style={[styles.tabText, activeTab === 'feedback' && styles.tabTextActive]}>Feedback</Text>
          </TouchableOpacity>
        </View>

        {activeTab === 'info' && (
          <>
            {/* Name */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Name</Text>
          <TextInput
            style={styles.fieldInput}
            value={name}
            onChangeText={setName}
            placeholder="Customer name"
            placeholderTextColor="#8696A0"
          />
        </View>

        {/* Notes */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Notes</Text>
          <TextInput
            style={[styles.fieldInput, styles.fieldTextarea]}
            value={notes}
            onChangeText={setNotes}
            placeholder="e.g., Asked for size 32, Budget 3k"
            placeholderTextColor="#8696A0"
            multiline
            numberOfLines={3}
          />
        </View>

        {/* Tags */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Tags</Text>
          <View style={styles.tagsRow}>
            {[...new Set([...TAGS, ...tags])].map((tag) => (
              <TouchableOpacity
                key={tag}
                style={[styles.tagChip, tags.includes(tag) && styles.tagChipActive]}
                onPress={() => toggleTag(tag)}
              >
                <Text style={[styles.tagChipText, tags.includes(tag) && styles.tagChipTextActive]}>
                  {tag}
                </Text>
              </TouchableOpacity>
            ))}
            {showTagInput ? (
              <View style={styles.addTagInputRow}>
                <TextInput
                  style={styles.addTagInput}
                  value={newTagText}
                  onChangeText={setNewTagText}
                  placeholder="Tag name"
                  placeholderTextColor="#8696A0"
                  autoFocus
                  onSubmitEditing={addCustomTag}
                  returnKeyType="done"
                />
                <TouchableOpacity onPress={addCustomTag} style={styles.addTagConfirm}>
                  <Ionicons name="checkmark" size={18} color="#00A884" />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => { setShowTagInput(false); setNewTagText(''); }} style={styles.addTagCancel}>
                  <Ionicons name="close" size={18} color="#8696A0" />
                </TouchableOpacity>
              </View>
            ) : (
              <TouchableOpacity style={styles.addTagChip} onPress={() => { setShowTagInput(true); setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 300); }}>
                <Ionicons name="add" size={16} color="#00A884" />
                <Text style={styles.addTagChipText}>Add Tag</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Delete */}
        <TouchableOpacity style={styles.deleteButton} onPress={handleDelete}>
          <Ionicons name="trash-outline" size={20} color="#FF4444" />
          <Text style={styles.deleteText}>Delete Customer</Text>
        </TouchableOpacity>
          </>
        )}

        {activeTab === 'timeline' && (
          <>
            {/* Timeline Tab */}
            {loadingTimeline ? (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color="#00A884" />
              </View>
            ) : timeline.length > 0 ? (
              <View style={{ paddingHorizontal: 20, paddingTop: 16 }}>
                {timeline.map((item, index) => (
                  <View key={index} style={styles.timelineItem}>
                    <View style={[styles.timelineIcon, { backgroundColor: 
                      item.type === 'message' ? '#4A90D9' : 
                      item.type === 'sale' ? '#25D366' : '#FF9800' 
                    }]}>
                      <Ionicons 
                        name={
                          item.type === 'message' ? 'chatbubble' : 
                          item.type === 'sale' ? 'cash' : 'alarm'
                        } 
                        size={14} 
                        color="#FFFFFF" 
                      />
                    </View>
                    <View style={styles.timelineContent}>
                      <Text style={styles.timelineText}>{item.content}</Text>
                      <Text style={styles.timelineDate}>
                        {new Date(item.created_at).toLocaleDateString()} {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </Text>
                    </View>
                  </View>
                ))}
              </View>
            ) : (
              <View style={styles.loadingContainer}>
                <Ionicons name="time-outline" size={48} color="#8696A0" />
                <Text style={{ color: '#8696A0', fontSize: 16, marginTop: 12 }}>No activity yet</Text>
              </View>
            )}
          </>
        )}

        {activeTab === 'loyalty' && (
          <>
            <LoyaltyCard customerId={customerId} />
          </>
        )}

        {activeTab === 'feedback' && (
          <>
            <View style={{ paddingHorizontal: 20, paddingTop: 16 }}>
              <Text style={{ color: '#E9EDEF', fontSize: 16, fontWeight: '700', marginBottom: 8 }}>Customer Feedback</Text>
              <Text style={{ color: '#8696A0', marginBottom: 12 }}>Send a survey link to the customer or view their past responses.</Text>
              <TouchableOpacity style={[styles.actionButton, { marginTop: 4 }]} onPress={() => setFeedbackVisible(true)}>
                <Ionicons name="send" size={18} color="#00A884" />
                <Text style={[styles.actionButtonText, { marginLeft: 8 }]}>Open Feedback</Text>
              </TouchableOpacity>
            </View>
            <CustomerFeedbackModal customerId={customerId} visible={feedbackVisible} onClose={() => setFeedbackVisible(false)} />
          </>
        )}

      </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0B141A',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 8,
    paddingVertical: 10,
    backgroundColor: '#1F2C34',
  },
  backButton: {
    padding: 8,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#E9EDEF',
  },
  saveText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#00A884',
    paddingHorizontal: 8,
  },
  content: {
    flex: 1,
    paddingBottom: 40,
  },
  profileSection: {
    alignItems: 'center',
    paddingVertical: 28,
    borderBottomWidth: 8,
    borderBottomColor: '#1F2C34',
  },
  avatarLarge: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#00A884',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  avatarLargeText: {
    fontSize: 34,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  avatarLargeImage: {
    width: 80,
    height: 80,
    borderRadius: 40,
    marginBottom: 12,
    backgroundColor: '#1A2332',
  },
  phoneText: {
    fontSize: 16,
    color: '#8696A0',
    marginTop: 4,
  },
  statsText: {
    fontSize: 14,
    color: '#00A884',
    marginTop: 6,
  },
  fieldGroup: {
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(134,150,160,0.15)',
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '500',
    color: '#00A884',
    marginBottom: 8,
  },
  fieldInput: {
    fontSize: 16,
    color: '#E9EDEF',
    backgroundColor: '#1F2C34',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  fieldTextarea: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tagChip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#1F2C34',
    borderRadius: 20,
  },
  tagChipActive: {
    backgroundColor: '#00A884',
  },
  tagChipText: {
    fontSize: 14,
    color: '#8696A0',
    fontWeight: '500',
  },
  tagChipTextActive: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  addTagChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: 'rgba(0,168,132,0.1)',
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#00A884',
    borderStyle: 'dashed',
  },
  addTagChipText: {
    fontSize: 14,
    color: '#00A884',
    fontWeight: '500',
  },
  addTagInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2C34',
    borderRadius: 20,
    paddingLeft: 14,
    paddingRight: 4,
    height: 36,
    borderWidth: 1,
    borderColor: '#00A884',
  },
  addTagInput: {
    fontSize: 14,
    color: '#E9EDEF',
    minWidth: 80,
    paddingVertical: 0,
  },
  addTagConfirm: {
    padding: 6,
  },
  addTagCancel: {
    padding: 6,
  },
  deleteButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginTop: 30,
    marginHorizontal: 20,
    paddingVertical: 14,
    backgroundColor: 'rgba(255,68,68,0.1)',
    borderRadius: 12,
  },
  deleteText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FF4444',
  },
  // Tab Bar
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(134,150,160,0.15)',
    marginBottom: 16,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 12,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: {
    borderBottomColor: '#00A884',
  },
  tabText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#8696A0',
  },
  tabTextActive: {
    color: '#00A884',
    fontWeight: '600',
  },
  actionButton: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  actionButtonText: { color: '#00A884', fontWeight: '600', marginLeft: 6 },
  // Timeline
  timelineItem: {
    flexDirection: 'row',
    marginBottom: 20,
  },
  timelineIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  timelineContent: {
    flex: 1,
    backgroundColor: '#1F2C34',
    borderRadius: 10,
    padding: 12,
  },
  timelineText: {
    fontSize: 14,
    color: '#E9EDEF',
    marginBottom: 6,
  },
  timelineDate: {
    fontSize: 11,
    color: '#8696A0',
  },
});
