import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
  Modal,
  Image,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { apiClient, whatsappAPI, messagesAPI, productsAPI } from '../context/api';

interface Message {
  id: string;
  content: string;
  direction: 'incoming' | 'outgoing';
  created_at: string;
  status?: string;
}

export default function ChatScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    customerId: string;
    customerName: string;
    customerPhone: string;
    prefill: string;
  }>();

  const customerId = params.customerId || '';
  const customerName = params.customerName || 'Customer';
  const customerPhone = params.customerPhone || '';
  const prefill = params.prefill || '';

  const insets = useSafeAreaInsets();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [showProducts, setShowProducts] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [products, setProducts] = useState<any[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [sendingProduct, setSendingProduct] = useState<string | null>(null);
  const [currency, setCurrency] = useState('USD');
  const flatListRef = useRef<FlatList>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [showToast, setShowToast] = useState(false);

  useEffect(() => {
    if (showToast) {
      const timer = setTimeout(() => setShowToast(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [showToast]);

  // Fetch initial auto-reply state
  useEffect(() => {
    if (!customerId) return;
    const loadAutoReplyState = async () => {
      try {
        const [cRes, sRes] = await Promise.all([
          apiClient.get(`/customers/${customerId}`),
          apiClient.get('/settings')
        ]);
        const custVal = cRes.data.auto_reply;
        const globalVal = sRes.data.auto_reply_enabled || false;
        // If customer has explicit setting, use it. Otherwise use global.
        // Note: backend returns null if not set, or boolean if set.
        setAutoReplyEnabled(custVal !== null && custVal !== undefined ? custVal : globalVal);
      } catch (e) {
        console.error('Failed to load auto-reply state', e);
      }
    };
    loadAutoReplyState();
  }, [customerId]);

  const toggleAutoReply = async () => {
    const newVal = !autoReplyEnabled;
    setAutoReplyEnabled(newVal); // Optimistic update
    setToastMessage(newVal ? 'Auto-Reply Enabled' : 'Auto-Reply Disabled');
    setShowToast(true);
    try {
      await apiClient.put(`/customers/${customerId}`, { auto_reply: newVal });
    } catch (e) {
      setAutoReplyEnabled(!newVal); // Revert on failure
      console.error('Failed to toggle auto-reply', e);
      Alert.alert('Error', 'Failed to update auto-reply setting');
    }
  };

  // Pre-fill input text if navigated with a message
  useEffect(() => {
    if (prefill) setInputText(prefill);
  }, [prefill]);

  const fetchMessages = useCallback(async (isPolling = false) => {
    if (!customerId) {
      setLoading(false);
      return;
    }
    try {
      const data = await messagesAPI.getMessages(customerId);
      const newMessages = data || [];
      if (isPolling) {
        // Only update if message count changed or latest message is different
        setMessages(prev => {
          if (prev.length !== newMessages.length ||
            (newMessages.length > 0 && prev.length > 0 && newMessages[0].id !== prev[0].id)) {
            return newMessages;
          }
          return prev;
        });
      } else {
        setMessages(newMessages);
      }
    } catch (error) {
      console.error('Error fetching messages:', error);
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    fetchMessages();
    // Poll for new messages every 5 seconds
    pollRef.current = setInterval(() => fetchMessages(true), 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchMessages]);

  const handleAIDraft = async () => {
    if (!customerId || drafting) return;
    setDrafting(true);
    try {
      const direction = inputText.trim();
      const res = await apiClient.post('/ai/draft-message', {
        customer_id: customerId,
        ...(direction ? { custom_instructions: direction } : {}),
      });
      const msg = res.data.message || res.data.drafted_message || '';
      if (msg) setInputText(msg);
    } catch (error) {
      Alert.alert('Error', 'Failed to generate AI draft');
    } finally {
      setDrafting(false);
    }
  };

  const handleOpenProducts = async () => {
    setShowProducts(true);
    setLoadingProducts(true);
    try {
      const [prodsRes, settingsRes] = await Promise.all([
        apiClient.get('/products'),
        apiClient.get('/settings'),
      ]);
      setProducts(prodsRes.data || []);
      if (settingsRes.data?.currency) setCurrency(settingsRes.data.currency);
    } catch (error) {
      console.error('Error loading products:', error);
    } finally {
      setLoadingProducts(false);
    }
  };

  const handleSendProduct = async (product: any) => {
    setSendingProduct(product.id);
    try {
      await productsAPI.sendProductToCustomer(product.id, customerId);
      Alert.alert('Sent!', `${product.name} sent to ${customerName}`);
      setShowProducts(false);
    } catch (error) {
      const desc = product.description ? `\n${product.description}` : '';
      const text = `*${product.name}*\n${currency} ${product.price.toLocaleString()}${desc}\n\nInterested? Let me know!`;
      setShowProducts(false);
      setInputText(text);
    } finally {
      setSendingProduct(null);
    }
  };

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text || sending) return;

    setSending(true);
    setInputText('');

    // Optimistic UI: add message immediately
    const tempId = `temp_${Date.now()}`;
    const optimisticMsg: Message = {
      id: tempId,
      content: text,
      direction: 'outgoing',
      created_at: new Date().toISOString(),
      status: 'sending',
    };
    setMessages(prev => [optimisticMsg, ...prev]);

    try {
      const result = await whatsappAPI.sendMessage(customerPhone, text, customerName);

      // Replace optimistic message with real one
      setMessages(prev =>
        prev.map(m =>
          m.id === tempId
            ? { ...m, id: result.message_id || tempId, status: 'sent' }
            : m
        )
      );
    } catch (error: any) {
      console.error('Send error:', error);
      // Show friendly error for rate limits
      if (error?.response?.status === 429) {
        const detail = error.response?.data?.detail || 'Message limit reached. Please upgrade your plan.';
        Alert.alert('Message Limit', detail);
      } else {
        Alert.alert('Send Failed', 'Could not send message. Please try again.');
      }
      // Mark as failed
      setMessages(prev =>
        prev.map(m =>
          m.id === tempId ? { ...m, status: 'failed' } : m
        )
      );
    } finally {
      setSending(false);
    }
  };

  const renderMessage = ({ item }: { item: Message }) => {
    const isOutgoing = item.direction === 'outgoing';
    return (
      <View
        style={[
          styles.messageBubble,
          isOutgoing ? styles.outgoing : styles.incoming,
        ]}
      >
        <Text style={[styles.messageText, isOutgoing ? styles.outgoingText : styles.incomingText]}>
          {item.content}
        </Text>
        <View style={styles.messageFooter}>
          <Text style={styles.messageTime}>
            {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </Text>
          {isOutgoing && item.status === 'sending' && (
            <Ionicons name="time-outline" size={12} color="#8B9DC3" style={{ marginLeft: 4 }} />
          )}
          {isOutgoing && item.status === 'pending' && (
            <Ionicons name="time-outline" size={12} color="#8B9DC3" style={{ marginLeft: 4 }} />
          )}
          {isOutgoing && item.status === 'sent' && (
            <Ionicons name="checkmark" size={14} color="#8B9DC3" style={{ marginLeft: 4 }} />
          )}
          {isOutgoing && item.status === 'delivered' && (
            <Ionicons name="checkmark-done" size={14} color="#8B9DC3" style={{ marginLeft: 4 }} />
          )}
          {isOutgoing && item.status === 'read' && (
            <Ionicons name="checkmark-done" size={14} color="#53BDEB" style={{ marginLeft: 4 }} />
          )}
          {isOutgoing && item.status === 'failed' && (
            <Ionicons name="alert-circle" size={12} color="#FF4444" style={{ marginLeft: 4 }} />
          )}
          {isOutgoing && !item.status && (
            <Ionicons name="checkmark" size={14} color="#8B9DC3" style={{ marginLeft: 4 }} />
          )}
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.headerInfo}
          onPress={() => router.push({
            pathname: '/customer-profile',
            params: { customerId, customerName, customerPhone },
          })}
          activeOpacity={0.7}
        >
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {customerName.charAt(0).toUpperCase()}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.headerName}>{customerName}</Text>
            <Text style={styles.headerPhone}>{customerPhone}</Text>
          </View>
        </TouchableOpacity>
      </View>

      {/* Toast Notification */}
      {showToast && (
        <View style={styles.toastContainer}>
          <Text style={styles.toastText}>{toastMessage}</Text>
        </View>
      )}

      {/* Messages */}
      <KeyboardAvoidingView
        style={styles.chatArea}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
      >
        {loading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#25D366" />
          </View>
        ) : (
          <FlatList
            ref={flatListRef}
            inverted
            data={messages}
            keyExtractor={(item) => item.id}
            renderItem={renderMessage}
            contentContainerStyle={styles.messagesList}
            ListEmptyComponent={
              <View style={styles.emptyContainer}>
                <Ionicons name="chatbubbles-outline" size={48} color="#8B9DC3" />
                <Text style={styles.emptyText}>No messages yet</Text>
                <Text style={styles.emptySubtext}>Send a message to start the conversation</Text>
              </View>
            }
          />
        )}

        {/* Attach menu (above input) */}
        {showAttachMenu && (
          <View style={styles.attachMenu}>
            <TouchableOpacity style={styles.attachOption} onPress={() => { setShowAttachMenu(false); /* TODO: camera */ }}>
              <View style={[styles.attachIconCircle, { backgroundColor: '#25D366' }]}>
                <Ionicons name="camera" size={22} color="#FFFFFF" />
              </View>
              <Text style={styles.attachLabel}>Camera</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.attachOption} onPress={() => { setShowAttachMenu(false); /* TODO: gallery */ }}>
              <View style={[styles.attachIconCircle, { backgroundColor: '#7C4DFF' }]}>
                <Ionicons name="image" size={22} color="#FFFFFF" />
              </View>
              <Text style={styles.attachLabel}>Gallery</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.attachOption} onPress={() => { setShowAttachMenu(false); /* TODO: file picker */ }}>
              <View style={[styles.attachIconCircle, { backgroundColor: '#4A90D9' }]}>
                <Ionicons name="document" size={22} color="#FFFFFF" />
              </View>
              <Text style={styles.attachLabel}>Document</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Input bar — WhatsApp style */}
        <View style={[styles.inputBar, { paddingBottom: Math.max(insets.bottom, 6) }]}>
          {/* Auto-Reply Toggle (Left of input) */}
          <TouchableOpacity
            onPress={toggleAutoReply}
            style={{
              marginRight: 8,
              padding: 8,
              justifyContent: 'center',
              alignItems: 'center'
            }}
          >
            <Ionicons
              name={autoReplyEnabled ? "flash" : "flash-off"}
              size={20}
              color={autoReplyEnabled ? "#FFD700" : "#8B9DC3"}
            />
          </TouchableOpacity>

          <View style={styles.inputPill}>
            <TouchableOpacity style={styles.pillIcon} onPress={() => setShowAttachMenu(!showAttachMenu)}>
              <Ionicons name="attach" size={24} color="#8B9DC3" />
            </TouchableOpacity>
            <TextInput
              style={styles.pillInput}
              value={inputText}
              onChangeText={(text) => { setInputText(text); if (text.length > 0) setShowAttachMenu(false); }}
              placeholder="Message"
              placeholderTextColor="#8B9DC3"
              multiline
              maxLength={4096}
            />
            <TouchableOpacity style={styles.pillIcon} onPress={handleAIDraft} disabled={drafting}>
              {drafting ? (
                <ActivityIndicator size="small" color="#FFD700" />
              ) : (
                <Ionicons name="sparkles" size={22} color="#FFD700" />
              )}
            </TouchableOpacity>
            {!inputText.trim() && (
              <TouchableOpacity style={styles.pillIcon} onPress={handleOpenProducts}>
                <Ionicons name="storefront-outline" size={22} color="#8B9DC3" />
              </TouchableOpacity>
            )}
          </View>
          <TouchableOpacity
            style={[styles.sendCircle, (!inputText.trim() || sending) && styles.sendCircleDisabled]}
            onPress={handleSend}
            disabled={!inputText.trim() || sending}
          >
            {sending ? (
              <ActivityIndicator size="small" color="#FFFFFF" />
            ) : (
              <Ionicons name="send" size={20} color="#FFFFFF" />
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>

      {/* Product Picker Modal */}
      <Modal
        visible={showProducts}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowProducts(false)}
      >
        <SafeAreaView style={styles.container}>
          <View style={styles.productModalHeader}>
            <TouchableOpacity onPress={() => setShowProducts(false)}>
              <Ionicons name="close" size={24} color="#FFFFFF" />
            </TouchableOpacity>
            <Text style={styles.productModalTitle}>Send Product</Text>
            <View style={{ width: 24 }} />
          </View>
          {loadingProducts ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#25D366" />
            </View>
          ) : products.length > 0 ? (
            <FlatList
              data={products}
              keyExtractor={(item) => item.id}
              contentContainerStyle={{ padding: 16 }}
              renderItem={({ item: product }) => {
                const imageUri = product.image_url
                  ? (product.image_url.startsWith('http') ? product.image_url : `${process.env.EXPO_PUBLIC_BACKEND_URL}${product.image_url}`)
                  : null;
                const isSending = sendingProduct === product.id;
                return (
                  <TouchableOpacity
                    style={styles.productRow}
                    onPress={() => handleSendProduct(product)}
                    disabled={isSending}
                  >
                    {imageUri ? (
                      <Image source={{ uri: imageUri }} style={styles.productImage} resizeMode="cover" />
                    ) : (
                      <View style={[styles.productImage, { justifyContent: 'center', alignItems: 'center', backgroundColor: '#1A2A4A' }]}>
                        <Ionicons name="image-outline" size={20} color="#3A4A5C" />
                      </View>
                    )}
                    <View style={{ flex: 1, marginLeft: 12 }}>
                      <Text style={{ color: '#FFFFFF', fontSize: 15, fontWeight: '600' }} numberOfLines={1}>{product.name}</Text>
                      <Text style={{ color: '#25D366', fontSize: 14, marginTop: 2 }}>{currency} {product.price?.toLocaleString()}</Text>
                    </View>
                    {isSending ? (
                      <ActivityIndicator size="small" color="#25D366" />
                    ) : (
                      <Ionicons name="send" size={18} color="#25D366" />
                    )}
                  </TouchableOpacity>
                );
              }}
            />
          ) : (
            <View style={styles.loadingContainer}>
              <Ionicons name="storefront-outline" size={48} color="#3A4A5C" />
              <Text style={{ color: '#8B9DC3', fontSize: 16, marginTop: 12 }}>No products yet</Text>
            </View>
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0B141A',
  },
  // ── Header (WhatsApp dark green bar) ──
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 8,
    backgroundColor: '#1F2C34',
  },
  backButton: {
    padding: 8,
  },
  headerInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginLeft: 4,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#25D366',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  avatarText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  headerName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#E9EDEF',
  },
  headerPhone: {
    fontSize: 12,
    color: '#8696A0',
    marginTop: 1,
  },
  // ── Chat area ──
  chatArea: {
    flex: 1,
    backgroundColor: '#0B141A',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  messagesList: {
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  // ── Bubbles ──
  messageBubble: {
    maxWidth: '80%',
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 6,
    borderRadius: 10,
    marginBottom: 3,
  },
  outgoing: {
    alignSelf: 'flex-end',
    backgroundColor: '#005C4B',
    borderTopRightRadius: 2,
  },
  incoming: {
    alignSelf: 'flex-start',
    backgroundColor: '#1F2C34',
    borderTopLeftRadius: 2,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 20,
  },
  outgoingText: {
    color: '#E9EDEF',
  },
  incomingText: {
    color: '#E9EDEF',
  },
  messageFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    marginTop: 2,
  },
  messageTime: {
    fontSize: 11,
    color: 'rgba(233,237,239,0.5)',
  },
  // ── Empty state ──
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
  },
  emptyText: {
    fontSize: 16,
    color: '#8696A0',
    marginTop: 12,
  },
  emptySubtext: {
    fontSize: 13,
    color: '#8696A0',
    marginTop: 4,
  },
  // ── Attach menu (above input) ──
  attachMenu: {
    flexDirection: 'row',
    justifyContent: 'space-evenly',
    paddingVertical: 16,
    paddingHorizontal: 16,
    backgroundColor: '#1F2C34',
    borderRadius: 16,
    marginHorizontal: 8,
    marginBottom: 4,
  },
  attachOption: {
    alignItems: 'center',
    gap: 8,
  },
  attachIconCircle: {
    width: 52,
    height: 52,
    borderRadius: 26,
    justifyContent: 'center',
    alignItems: 'center',
  },
  attachLabel: {
    fontSize: 12,
    color: '#8696A0',
    fontWeight: '500',
  },
  // ── Input bar ──
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 6,
    paddingTop: 4,
  },
  inputPill: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: '#1F2C34',
    borderRadius: 24,
    paddingHorizontal: 4,
    paddingVertical: 4,
    marginRight: 6,
    minHeight: 48,
  },
  pillIcon: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  pillInput: {
    flex: 1,
    fontSize: 16,
    color: '#E9EDEF',
    paddingVertical: 8,
    paddingHorizontal: 4,
    maxHeight: 120,
  },
  sendCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#00A884',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendCircleDisabled: {
    backgroundColor: '#1D3D35',
  },
  // ── Product modal ──
  productModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    backgroundColor: '#1F2C34',
  },
  productModalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#E9EDEF',
  },
  productRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2C34',
    borderRadius: 12,
    padding: 12,
    marginBottom: 10,
  },
  productImage: {
    width: 48,
    height: 48,
    borderRadius: 10,
    backgroundColor: '#0B141A',
  },
  // ── Toast ──
  toastContainer: {
    position: 'absolute',
    top: 70,
    alignSelf: 'center',
    backgroundColor: 'rgba(31, 44, 52, 0.95)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 24,
    zIndex: 1000,
    shadowColor: "#000",
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
    elevation: 5,
  },
  toastText: {
    color: '#E9EDEF',
    fontSize: 14,
    fontWeight: '500',
  },
});
