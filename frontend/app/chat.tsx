import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  Pressable,
  FlatList,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
  Modal,
  Image,
  Dimensions,
  Linking,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { apiClient, whatsappAPI, messagesAPI, productsAPI, messageHelpers } from '../context/api';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

interface Message {
  id: string;
  content: string;
  direction: 'incoming' | 'outgoing';
  created_at: string;
  status?: string;
  message_type?: string;
  image_url?: string;
  file_name?: string;
  evo_message_id?: string | null;
  remote_jid?: string | null;
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
  const [selectedProducts, setSelectedProducts] = useState<string[]>([]);
  const [sendingBatch, setSendingBatch] = useState(false);
  const [currency, setCurrency] = useState('USD');
  const flatListRef = useRef<FlatList>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [isPersonal, setIsPersonal] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [showToast, setShowToast] = useState(false);
  const [viewerImage, setViewerImage] = useState<string | null>(null);
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Message[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);

  useEffect(() => {
    if (showToast) {
      const timer = setTimeout(() => setShowToast(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [showToast]);

  // Fetch initial auto-reply state + preload products
  useEffect(() => {
    if (!customerId) return;
    const loadInitialData = async () => {
      try {
        const [cRes, sRes, prodsRes] = await Promise.all([
          apiClient.get(`/customers/${customerId}`),
          apiClient.get('/settings'),
          apiClient.get('/products'),
        ]);
        const custVal = cRes.data.auto_reply;
        const globalVal = sRes.data.auto_reply_enabled || false;
        setAutoReplyEnabled(custVal !== null && custVal !== undefined ? custVal : globalVal);
        setIsPersonal(cRes.data.is_personal || false);
        if (sRes.data?.currency) setCurrency(sRes.data.currency);
        setProducts(prodsRes.data || []);
      } catch (e) {
        console.error('Failed to load initial data', e);
      }
    };
    loadInitialData();
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

  const togglePersonal = async () => {
    const newVal = !isPersonal;
    setIsPersonal(newVal); // Optimistic update
    setToastMessage(newVal ? 'Marked as Personal' : 'Marked as Business');
    setShowToast(true);
    try {
      await apiClient.put(`/customers/${customerId}`, { is_personal: newVal });
    } catch (e) {
      setIsPersonal(!newVal); // Revert on failure
      console.error('Failed to toggle personal status', e);
      Alert.alert('Error', 'Failed to update contact status');
    }
  };

  // Pre-fill input text if navigated with a message
  useEffect(() => {
    if (prefill) setInputText(prefill);
  }, [prefill]);

  const sendingRef = useRef(false);

  const fetchMessages = useCallback(async (isPolling = false) => {
    if (!customerId) {
      setLoading(false);
      return;
    }
    try {
      const data = await messagesAPI.getMessages(customerId);
      const newMessages = data || [];

      // Mark messages as read when opening chat (only on initial load, not polling)
      if (!isPolling && newMessages.length > 0) {
        messageHelpers.markRead(customerId).catch(e => console.error('Failed to mark read:', e));
      }
      if (isPolling) {
        // Skip poll update while a send is in flight — prevents optimistic msg from disappearing
        if (sendingRef.current) return;
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

  const handleOpenProducts = () => {
    setSelectedProducts([]);
    setShowProducts(true);
  };

  const toggleProductSelection = (productId: string) => {
    setSelectedProducts(prev =>
      prev.includes(productId)
        ? prev.filter(id => id !== productId)
        : [...prev, productId]
    );
  };

  const handleSendSelectedProducts = async () => {
    const ids = [...selectedProducts];
    if (ids.length === 0) return;
    setSendingBatch(true);
    try {
      if (ids.length === 1) {
        await productsAPI.sendProductToCustomer(ids[0], customerId);
      } else {
        await productsAPI.sendCatalog(customerId, ids);
      }
      const count = ids.length;
      setToastMessage(`${count} product${count > 1 ? 's' : ''} sent!`);
      setShowToast(true);
      setShowProducts(false);
      setSelectedProducts([]);
      // Refresh messages to show sent products
      setTimeout(() => fetchMessages(true), 1500);
    } catch (error) {
      // Fallback: paste as text
      const selected = products.filter(p => ids.includes(p.id));
      const text = selected.map(p => {
        const desc = p.description ? `\n${p.description}` : '';
        return `*${p.name}*\n${currency} ${p.price?.toLocaleString()}${desc}`;
      }).join('\n\n');
      setShowProducts(false);
      setInputText(text + '\n\nInterested? Let me know!');
    } finally {
      setSendingBatch(false);
    }
  };

  const sendMediaFile = async (uri: string, fileName: string, mimeType: string) => {
    setSending(true);
    const tempId = `temp_${Date.now()}`;
    const isImage = mimeType.startsWith('image/');
    const optimisticMsg: Message = {
      id: tempId,
      content: isImage ? '' : `📎 ${fileName}`,
      direction: 'outgoing',
      created_at: new Date().toISOString(),
      status: 'sending',
      message_type: isImage ? 'image' : 'document',
      image_url: isImage ? uri : undefined,
      file_name: !isImage ? fileName : undefined,
    };
    setMessages(prev => [optimisticMsg, ...prev]);
    try {
      const caption = inputText.trim();
      const result = await whatsappAPI.sendMedia(customerPhone, uri, fileName, mimeType, caption, customerName);
      if (caption) setInputText('');
      setMessages(prev =>
        prev.map(m =>
          m.id === tempId ? { ...m, id: result.message_id || tempId, status: 'sent' } : m
        )
      );
      setToastMessage(isImage ? 'Photo sent!' : 'Document sent!');
      setShowToast(true);
    } catch (error: any) {
      console.error('Send media error:', error);
      if (error?.response?.status === 429) {
        Alert.alert('Message Limit', error.response?.data?.detail || 'Message limit reached.');
      } else {
        Alert.alert('Send Failed', 'Could not send file. Please try again.');
      }
      setMessages(prev =>
        prev.map(m => (m.id === tempId ? { ...m, status: 'failed' } : m))
      );
    } finally {
      setSending(false);
    }
  };

  const handleCamera = async () => {
    setShowAttachMenu(false);
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Required', 'Camera access is needed to take photos.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      quality: 0.7,
    });
    if (result.canceled || !result.assets?.length) return;
    const asset = result.assets[0];
    const fileName = asset.fileName || `photo_${Date.now()}.jpg`;
    const mimeType = asset.mimeType || 'image/jpeg';
    await sendMediaFile(asset.uri, fileName, mimeType);
  };

  const handleGallery = async () => {
    setShowAttachMenu(false);
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Required', 'Gallery access is needed to select photos.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.7,
      allowsMultipleSelection: true,
    });
    if (result.canceled || !result.assets?.length) return;
    for (const asset of result.assets) {
      const fileName = asset.fileName || `image_${Date.now()}.jpg`;
      const mimeType = asset.mimeType || 'image/jpeg';
      await sendMediaFile(asset.uri, fileName, mimeType);
    }
  };

  const handleDocument = async () => {
    setShowAttachMenu(false);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: true,
        multiple: true,
      });
      if (result.canceled || !result.assets?.length) return;
      // Send each file one by one (sequential to avoid shared-state race conditions)
      for (const asset of result.assets) {
        const fileName = asset.name || `document_${Date.now()}`;
        const mimeType = asset.mimeType || 'application/octet-stream';
        await sendMediaFile(asset.uri, fileName, mimeType);
      }
    } catch (error) {
      console.error('Document picker error:', error);
    }
  };

  const handleOpenDocument = async (url: string) => {
    try {
      const fileName = url.split('/').pop() || 'document';
      const localUri = `${FileSystem.cacheDirectory}${fileName}`;
      const { uri } = await FileSystem.downloadAsync(url, localUri);
      const canShare = await Sharing.isAvailableAsync();
      if (canShare) {
        await Sharing.shareAsync(uri);
      } else {
        await Linking.openURL(url);
      }
    } catch (error) {
      console.error('Open document error:', error);
      // Fallback: open URL in browser
      try { await Linking.openURL(url); } catch { }
    }
  };

  const handleSearch = async (query: string) => {
    setSearchQuery(query);
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const results = await messageHelpers.search(customerId, query);
      setSearchResults(results || []);
    } catch (error) {
      console.error('Search error:', error);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text || sending) return;

    setSending(true);
    sendingRef.current = true;
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
      sendingRef.current = false;
    }
  };

  const handleDeleteMessage = (item: Message) => {
    const canDeleteForEveryone = item.direction === 'outgoing' && !!item.evo_message_id && !!item.remote_jid;

    const doDeleteLocal = async () => {
      try {
        await apiClient.delete(`/messages/${item.id}`);
        setMessages(prev => prev.filter(m => m.id !== item.id));
      } catch (e) {
        Alert.alert('Error', 'Failed to delete message');
      } finally {
        setSelectedMessageId(null);
      }
    };

    const doDeleteForEveryone = async () => {
      try {
        await apiClient.delete(`/messages/${item.id}/for-everyone`);
        setMessages(prev => prev.filter(m => m.id !== item.id));
        setToastMessage('Deleted for everyone');
        setShowToast(true);
      } catch (e: any) {
        const detail = e?.response?.data?.detail || 'Failed to delete for everyone';
        Alert.alert('Could Not Delete', detail);
      } finally {
        setSelectedMessageId(null);
      }
    };

    const buttons: any[] = [
      { text: 'Cancel', style: 'cancel', onPress: () => setSelectedMessageId(null) },
      { text: 'Delete for Me', style: 'destructive', onPress: doDeleteLocal },
    ];
    if (canDeleteForEveryone) {
      buttons.splice(1, 0, { text: 'Delete for Everyone', onPress: doDeleteForEveryone });
    }

    Alert.alert(
      'Delete Message',
      canDeleteForEveryone
        ? 'Delete just for yourself, or delete for everyone on WhatsApp?'
        : 'Remove this message from your CRM?',
      buttons
    );
  };

  const renderMessage = ({ item }: { item: Message }) => {
    const isOutgoing = item.direction === 'outgoing';
    const isDocument = item.message_type === 'document';
    const hasImage = !isDocument && (item.message_type === 'image' || item.image_url);
    const backendUrl = process.env.EXPO_PUBLIC_BACKEND_URL || 'http://localhost:8000';
    let imageUri = item.image_url
      ? (item.image_url.startsWith('http') || item.image_url.startsWith('file://') ? item.image_url : `${backendUrl}${item.image_url}`)
      : null;
    // Fix Docker-internal URLs that the phone can't resolve
    if (imageUri && imageUri.includes('host.docker.internal')) {
      const backendHost = backendUrl.replace(/^https?:\/\//, '').replace(/:\d+$/, '');
      imageUri = imageUri.replace('host.docker.internal', backendHost);
    }

    // Extract filename and extension from URL for documents
    // Only use URL-derived name if it looks like a real filename (not a UUID)
    const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
    const rawFromUrl = isDocument && imageUri
      ? decodeURIComponent(imageUri.split('/').pop() || '')
      : null;
    const rawDocName = rawFromUrl && !uuidPattern.test(rawFromUrl) ? rawFromUrl : null;
    // Priority: stored file_name > stripped content (if not a fallback string) > real URL name > fallback
    const cleanContent = item.content?.replace(/^📎\s*/, '').trim() || '';
    const isFallbackContent = !cleanContent || cleanContent === 'Received document' || cleanContent === 'Document';
    const docDisplayName = item.file_name || (!isFallbackContent ? cleanContent : null) || rawDocName || 'Document';
    const docExt = docDisplayName.includes('.') ? docDisplayName.split('.').pop()?.toUpperCase() : null;
    const docFileName = docDisplayName;

    const isSelected = selectedMessageId === item.id;

    return (
      <TouchableOpacity
        activeOpacity={0.85}
        onLongPress={() => setSelectedMessageId(isSelected ? null : item.id)}
        delayLongPress={400}
        style={{ alignSelf: isOutgoing ? 'flex-end' : 'flex-start' }}
      >
      <View
        style={[
          styles.messageBubble,
          isOutgoing ? styles.outgoing : styles.incoming,
          isSelected && { opacity: 0.75 },
        ]}
      >
        {hasImage && imageUri && (
          <Pressable
            onPress={() => { if (!isSelected) setViewerImage(imageUri); else setSelectedMessageId(null); }}
            onLongPress={() => setSelectedMessageId(isSelected ? null : item.id)}
            delayLongPress={300}
          >
            <Image
              source={{ uri: imageUri }}
              style={[styles.messageImage, isSelected && { opacity: 0.7 }]}
              resizeMode="cover"
              onError={() => { }}
            />
          </Pressable>
        )}
        {isDocument && imageUri && (
          <TouchableOpacity activeOpacity={0.7} onPress={() => handleOpenDocument(imageUri)} onLongPress={() => setSelectedMessageId(isSelected ? null : item.id)} delayLongPress={400}>
            <View style={styles.documentBubble}>
              <View style={styles.docIconWrap}>
                <Ionicons name="document-text" size={26} color="#FFFFFF" />
                {docExt && <Text style={styles.docExtBadge}>{docExt}</Text>}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.docFileName} numberOfLines={2}>{docFileName}</Text>
                <Text style={styles.docOpenHint}>📂 Tap to open</Text>
              </View>
              <Ionicons name="arrow-down-circle" size={22} color={isOutgoing ? '#DCF8C6' : '#25D366'} />
            </View>
          </TouchableOpacity>
        )}
        {isDocument && !imageUri && (
          <View style={styles.documentBubble}>
            <View style={styles.docIconWrap}>
              <Ionicons name="document-text" size={26} color="#FFFFFF" />
              {docExt && <Text style={styles.docExtBadge}>{docExt}</Text>}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.docFileName} numberOfLines={2}>{docFileName}</Text>
              <Text style={styles.docOpenHint}>No preview available</Text>
            </View>
          </View>
        )}
        {!isDocument && item.content && (
          <Text style={[styles.messageText, isOutgoing ? styles.outgoingText : styles.incomingText]}>
            {item.content}
          </Text>
        )}
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
      {isSelected && (
        <TouchableOpacity
          onPress={() => handleDeleteMessage(item)}
          style={[
            styles.deleteBtn,
            isOutgoing ? { alignSelf: 'flex-end' } : { alignSelf: 'flex-start' },
          ]}
        >
          <Ionicons name="trash-outline" size={13} color="#FF4444" />
          <Text style={styles.deleteBtnText}>Delete</Text>
        </TouchableOpacity>
      )}
      </TouchableOpacity>
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

        {/* Search Icon */}
        <TouchableOpacity onPress={() => setShowSearch(!showSearch)} style={styles.headerIcon}>
          <Ionicons name="search" size={22} color="#FFFFFF" />
        </TouchableOpacity>

        {/* Toggle Personal Mode */}
        <TouchableOpacity
          onPress={togglePersonal}
          style={[
            styles.personalBadge,
            isPersonal && styles.personalBadgeActive
          ]}
        >
          <Ionicons
            name={isPersonal ? "heart" : "heart-outline"}
            size={16}
            color={isPersonal ? "#FFFFFF" : "#8696A0"}
          />
          <Text style={[
            styles.personalBadgeText,
            isPersonal && styles.personalBadgeTextActive
          ]}>
            {isPersonal ? "Personal" : "Business"}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Search Bar */}
      {showSearch && (
        <View style={styles.searchBar}>
          <Ionicons name="search" size={18} color="#8B9DC3" style={{ marginRight: 8 }} />
          <TextInput
            style={styles.searchInput}
            placeholder="Search messages..."
            placeholderTextColor="#8B9DC3"
            value={searchQuery}
            onChangeText={handleSearch}
            autoFocus
          />
          {searching && <ActivityIndicator size="small" color="#25D366" />}
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => { setSearchQuery(''); setSearchResults([]); }}>
              <Ionicons name="close-circle" size={20} color="#8B9DC3" />
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* Search Results */}
      {showSearch && searchResults.length > 0 && (
        <View style={styles.searchResults}>
          <Text style={styles.searchResultsTitle}>{searchResults.length} result{searchResults.length !== 1 ? 's' : ''}</Text>
          <FlatList
            data={searchResults}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => (
              <TouchableOpacity
                style={styles.searchResultItem}
                onPress={() => {
                  setShowSearch(false);
                  setSearchQuery('');
                  setSearchResults([]);
                }}
              >
                <Text style={styles.searchResultText} numberOfLines={2}>{item.content}</Text>
                <Text style={styles.searchResultDate}>
                  {new Date(item.created_at).toLocaleDateString()}
                </Text>
              </TouchableOpacity>
            )}
            style={{ maxHeight: 200 }}
          />
        </View>
      )}

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
            <TouchableOpacity style={styles.attachOption} onPress={handleCamera}>
              <View style={[styles.attachIconCircle, { backgroundColor: '#25D366' }]}>
                <Ionicons name="camera" size={22} color="#FFFFFF" />
              </View>
              <Text style={styles.attachLabel}>Camera</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.attachOption} onPress={handleGallery}>
              <View style={[styles.attachIconCircle, { backgroundColor: '#7C4DFF' }]}>
                <Ionicons name="image" size={22} color="#FFFFFF" />
              </View>
              <Text style={styles.attachLabel}>Gallery</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.attachOption} onPress={handleDocument}>
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
            <Text style={styles.productModalTitle}>
              {selectedProducts.length > 0 ? `${selectedProducts.length} selected` : 'Select Products'}
            </Text>
            {selectedProducts.length > 0 ? (
              <TouchableOpacity onPress={() => setSelectedProducts([])}>
                <Text style={{ color: '#8696A0', fontSize: 14 }}>Clear</Text>
              </TouchableOpacity>
            ) : (
              <View style={{ width: 40 }} />
            )}
          </View>
          {products.length > 0 ? (
            <FlatList
              data={products}
              keyExtractor={(item) => item.id}
              contentContainerStyle={{ padding: 16, paddingBottom: selectedProducts.length > 0 ? 90 : 16 }}
              renderItem={({ item: product }) => {
                const imageUri = product.image_url
                  ? (product.image_url.startsWith('http') ? product.image_url : `${process.env.EXPO_PUBLIC_BACKEND_URL}${product.image_url}`)
                  : null;
                const isSelected = selectedProducts.includes(product.id);
                return (
                  <TouchableOpacity
                    style={[styles.productRow, isSelected && { borderColor: '#25D366', borderWidth: 1.5 }]}
                    onPress={() => toggleProductSelection(product.id)}
                    activeOpacity={0.7}
                  >
                    {/* Checkbox */}
                    <View style={{
                      width: 24, height: 24, borderRadius: 12,
                      borderWidth: 2, borderColor: isSelected ? '#25D366' : '#3A4A5C',
                      backgroundColor: isSelected ? '#25D366' : 'transparent',
                      justifyContent: 'center', alignItems: 'center', marginRight: 10,
                    }}>
                      {isSelected && <Ionicons name="checkmark" size={16} color="#FFFFFF" />}
                    </View>
                    {imageUri ? (
                      <Image
                        source={{ uri: imageUri }}
                        style={styles.productImage}
                        resizeMode="cover"
                        onError={() => { }}
                      />
                    ) : (
                      <View style={[styles.productImage, { justifyContent: 'center', alignItems: 'center', backgroundColor: '#1A2A4A' }]}>
                        <Ionicons name="image-outline" size={20} color="#3A4A5C" />
                      </View>
                    )}
                    <View style={{ flex: 1, marginLeft: 12 }}>
                      <Text style={{ color: '#FFFFFF', fontSize: 15, fontWeight: '600' }} numberOfLines={1}>{product.name}</Text>
                      <Text style={{ color: '#25D366', fontSize: 14, marginTop: 2 }}>{currency} {product.price?.toLocaleString()}</Text>
                    </View>
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
          {/* Floating Send Button */}
          {selectedProducts.length > 0 && (
            <View style={styles.sendSelectedBar}>
              <TouchableOpacity
                style={[styles.sendSelectedButton, sendingBatch && { opacity: 0.6 }]}
                onPress={handleSendSelectedProducts}
                disabled={sendingBatch}
              >
                {sendingBatch ? (
                  <ActivityIndicator size="small" color="#FFFFFF" />
                ) : (
                  <>
                    <Ionicons name="send" size={18} color="#FFFFFF" style={{ marginRight: 8 }} />
                    <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600' }}>
                      Send {selectedProducts.length} Product{selectedProducts.length > 1 ? 's' : ''}
                    </Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          )}
        </SafeAreaView>
      </Modal>

      {/* Full-screen Image Viewer */}
      <Modal visible={!!viewerImage} transparent animationType="fade" onRequestClose={() => setViewerImage(null)}>
        <View style={styles.imageViewerOverlay}>
          <TouchableOpacity style={styles.imageViewerClose} onPress={() => setViewerImage(null)}>
            <Ionicons name="close" size={28} color="#FFFFFF" />
          </TouchableOpacity>
          {viewerImage && (
            <Image
              source={{ uri: viewerImage }}
              style={styles.imageViewerImage}
              resizeMode="contain"
            />
          )}
        </View>
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
    borderWidth: 1.5,
    borderColor: 'transparent',
  },
  sendSelectedBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    padding: 16,
    paddingBottom: 32,
    backgroundColor: 'rgba(11, 20, 26, 0.95)',
  },
  sendSelectedButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    borderRadius: 24,
    paddingVertical: 14,
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
  personalBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#3A4A5C',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    marginRight: 8,
  },
  personalBadgeActive: {
    backgroundColor: '#E91E63',
    borderColor: '#E91E63',
  },
  personalBadgeText: {
    fontSize: 11,
    color: '#8696A0',
    fontWeight: '600',
    marginLeft: 4,
  },
  personalBadgeTextActive: {
    color: '#FFFFFF',
  },
  messageImage: {
    width: 200,
    height: 200,
    borderRadius: 8,
    marginBottom: 6,
    backgroundColor: '#1A2A4A',
  },
  documentBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.2)',
    borderRadius: 10,
    padding: 12,
    marginBottom: 6,
    gap: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    minWidth: 220,
  },
  docIconWrap: {
    width: 48,
    height: 48,
    borderRadius: 10,
    backgroundColor: '#4A90D9',
    justifyContent: 'center',
    alignItems: 'center',
  },
  docExtBadge: {
    fontSize: 8,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 0.5,
    marginTop: 1,
  },
  docFileName: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 3,
  },
  docOpenHint: {
    fontSize: 11,
    color: '#8B9DC3',
  },
  documentName: {
    flex: 1,
    fontSize: 13,
    fontWeight: '500',
  },
  imageViewerOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.95)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  imageViewerClose: {
    position: 'absolute',
    top: 50,
    right: 20,
    zIndex: 10,
    padding: 8,
  },
  imageViewerImage: {
    width: Dimensions.get('window').width,
    height: Dimensions.get('window').height * 0.75,
  },
  // Search
  headerIcon: {
    padding: 8,
    marginLeft: 4,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2C34',
    marginHorizontal: 12,
    marginVertical: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
  },
  searchInput: {
    flex: 1,
    fontSize: 15,
    color: '#E9EDEF',
    paddingVertical: 0,
  },
  searchResults: {
    backgroundColor: '#1F2C34',
    marginHorizontal: 12,
    marginBottom: 8,
    borderRadius: 8,
    padding: 8,
  },
  searchResultsTitle: {
    fontSize: 12,
    fontWeight: '600',
    color: '#8B9DC3',
    marginBottom: 8,
    paddingHorizontal: 8,
  },
  searchResultItem: {
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.05)',
  },
  searchResultText: {
    fontSize: 14,
    color: '#E9EDEF',
    marginBottom: 4,
  },
  searchResultDate: {
    fontSize: 11,
    color: '#8B9DC3',
  },
  deleteBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginTop: 2,
    marginBottom: 4,
    backgroundColor: 'rgba(255,68,68,0.12)',
    borderRadius: 8,
  },
  deleteBtnText: {
    fontSize: 12,
    color: '#FF4444',
    fontWeight: '600',
  },
});
