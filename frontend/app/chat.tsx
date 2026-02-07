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
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { apiClient, whatsappAPI, messagesAPI } from '../context/api';

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
  const flatListRef = useRef<FlatList>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Pre-fill input text if navigated with a message
  useEffect(() => {
    if (prefill) setInputText(prefill);
  }, [prefill]);

  const fetchMessages = useCallback(async () => {
    if (!customerId) {
      setLoading(false);
      return;
    }
    try {
      const data = await messagesAPI.getMessages(customerId);
      setMessages(data || []);
    } catch (error) {
      console.error('Error fetching messages:', error);
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    fetchMessages();
    // Poll for new messages every 5 seconds
    pollRef.current = setInterval(fetchMessages, 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchMessages]);

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
    setMessages(prev => [...prev, optimisticMsg]);

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
          {isOutgoing && item.status === 'sent' && (
            <Ionicons name="checkmark-done" size={12} color="#25D366" style={{ marginLeft: 4 }} />
          )}
          {isOutgoing && item.status === 'failed' && (
            <Ionicons name="alert-circle" size={12} color="#FF4444" style={{ marginLeft: 4 }} />
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
        <View style={styles.headerInfo}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {customerName.charAt(0).toUpperCase()}
            </Text>
          </View>
          <View>
            <Text style={styles.headerName}>{customerName}</Text>
            <Text style={styles.headerPhone}>{customerPhone}</Text>
          </View>
        </View>
      </View>

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
            data={messages}
            keyExtractor={(item) => item.id}
            renderItem={renderMessage}
            contentContainerStyle={styles.messagesList}
            onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
            ListEmptyComponent={
              <View style={styles.emptyContainer}>
                <Ionicons name="chatbubbles-outline" size={48} color="#8B9DC3" />
                <Text style={styles.emptyText}>No messages yet</Text>
                <Text style={styles.emptySubtext}>Send a message to start the conversation</Text>
              </View>
            }
          />
        )}

        {/* Input */}
        <View style={[styles.inputContainer, { paddingBottom: Math.max(insets.bottom, 10) }]}>
          <TextInput
            style={styles.input}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Type a message..."
            placeholderTextColor="#666"
            multiline
            maxLength={4096}
          />
          <TouchableOpacity
            style={[styles.sendButton, (!inputText.trim() || sending) && styles.sendButtonDisabled]}
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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#0F1F3D',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.08)',
  },
  backButton: {
    marginRight: 12,
    padding: 4,
  },
  headerInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#25D366',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  avatarText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  headerName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  headerPhone: {
    fontSize: 12,
    color: '#8B9DC3',
    marginTop: 1,
  },
  chatArea: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  messagesList: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    flexGrow: 1,
    justifyContent: 'flex-end',
  },
  messageBubble: {
    maxWidth: '78%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
    marginBottom: 8,
  },
  outgoing: {
    alignSelf: 'flex-end',
    backgroundColor: '#25D366',
    borderBottomRightRadius: 4,
  },
  incoming: {
    alignSelf: 'flex-start',
    backgroundColor: '#1A2A4A',
    borderBottomLeftRadius: 4,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 20,
  },
  outgoingText: {
    color: '#FFFFFF',
  },
  incomingText: {
    color: '#E0E0E0',
  },
  messageFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    marginTop: 4,
  },
  messageTime: {
    fontSize: 10,
    color: 'rgba(255,255,255,0.5)',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
  },
  emptyText: {
    fontSize: 16,
    color: '#8B9DC3',
    marginTop: 12,
  },
  emptySubtext: {
    fontSize: 13,
    color: '#5A6B8A',
    marginTop: 4,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#0F1F3D',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.08)',
  },
  input: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    color: '#FFFFFF',
    maxHeight: 100,
    marginRight: 10,
  },
  sendButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: '#25D366',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#1A3A2A',
  },
});
