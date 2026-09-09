import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Switch,
  ActivityIndicator,
  Alert,
  RefreshControl,
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import {
  groupScoutAPI,
  type SocialScoutSettings,
  type ScoutQueueItem,
} from '../context/api';

export default function GroupScoutScreen() {
  const router = useRouter();

  const [settings, setSettings] = useState<SocialScoutSettings | null>(null);
  const [keywordsText, setKeywordsText] = useState('');
  const [leads, setLeads] = useState<ScoutQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [actioningId, setActioningId] = useState<string | null>(null);

  // Edit-reply modal state
  const [editItem, setEditItem] = useState<ScoutQueueItem | null>(null);
  const [editText, setEditText] = useState('');

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(async (isRefresh = false) => {
    try {
      const [s, q] = await Promise.all([
        groupScoutAPI.getSettings(),
        groupScoutAPI.getQueue(),
      ]);
      setSettings(s);
      setKeywordsText((s.keywords || []).join(', '));
      // Only show genuine pending leads from the monitor pipeline
      setLeads((q || []).filter((i) => i.status === 'pending'));
    } catch (e) {
      console.error('[GroupScout] load failed', e);
      if (!isRefresh) {
        Alert.alert('Error', 'Could not load Group Scout. Pull to retry.');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    // Refresh the lead list every 15s while screen is open
    pollRef.current = setInterval(() => {
      groupScoutAPI
        .getQueue()
        .then((q) => setLeads((q || []).filter((i) => i.status === 'pending')))
        .catch(() => {});
    }, 15000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadAll]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadAll(true);
  };

  const persist = async (next: SocialScoutSettings) => {
    setSaving(true);
    try {
      // Send the full object so we don't clobber other fields server-side
      await groupScoutAPI.saveSettings(next);
      setSettings(next);
    } catch (e) {
      console.error('[GroupScout] save failed', e);
      Alert.alert('Error', 'Failed to save settings');
      // Reload to reflect the true server state
      loadAll(true);
    } finally {
      setSaving(false);
    }
  };

  const handleToggleMonitor = (value: boolean) => {
    if (!settings) return;
    const next = { ...settings, group_monitor_enabled: value };
    setSettings(next); // optimistic
    persist(next);
  };

  const handleSaveKeywords = () => {
    if (!settings) return;
    const keywords = keywordsText
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean);
    persist({ ...settings, keywords });
    Alert.alert('Saved', 'Your scout keywords were updated.');
  };

  const applyAction = async (
    item: ScoutQueueItem,
    action: 'approve' | 'skip',
    editedContent?: string,
  ) => {
    setActioningId(item._id);
    // optimistic removal
    setLeads((prev) => prev.filter((l) => l._id !== item._id));
    try {
      await groupScoutAPI.queueAction(item._id, action, editedContent);
    } catch (e) {
      console.error('[GroupScout] action failed', e);
      Alert.alert('Error', `Failed to ${action}. Restoring item.`);
      loadAll(true);
    } finally {
      setActioningId(null);
    }
  };

  const openEdit = (item: ScoutQueueItem) => {
    setEditItem(item);
    setEditText(item.draft_content || '');
  };

  const renderLead = (item: ScoutQueueItem) => {
    const meta = item.metadata || {};
    const busy = actioningId === item._id;
    return (
      <View key={item._id} style={styles.leadCard}>
        <View style={styles.leadHeader}>
          <View style={styles.groupBadge}>
            <Ionicons name="people" size={12} color="#25D366" />
            <Text style={styles.groupBadgeText} numberOfLines={1}>
              {meta.group_name || meta.platform || 'WhatsApp group'}
            </Text>
          </View>
          {!!meta.keyword && (
            <View style={styles.keywordPill}>
              <Text style={styles.keywordPillText}>{meta.keyword}</Text>
            </View>
          )}
        </View>

        <Text style={styles.leadAuthor}>{meta.author || 'Someone'}</Text>
        <Text style={styles.leadSnippet}>{meta.snippet || item.title}</Text>

        <View style={styles.draftBox}>
          <View style={styles.draftLabelRow}>
            <Ionicons name="sparkles" size={13} color="#FFD700" />
            <Text style={styles.draftLabel}>Suggested reply</Text>
          </View>
          <Text style={styles.draftText}>{item.draft_content}</Text>
        </View>

        <View style={styles.leadActions}>
          <TouchableOpacity
            style={[styles.actionBtn, styles.skipBtn]}
            onPress={() => applyAction(item, 'skip')}
            disabled={busy}
          >
            <Ionicons name="close" size={16} color="#8B9DC3" />
            <Text style={styles.skipBtnText}>Skip</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.actionBtn, styles.editBtn]}
            onPress={() => openEdit(item)}
            disabled={busy}
          >
            <Ionicons name="create-outline" size={16} color="#4A90E2" />
            <Text style={styles.editBtnText}>Edit</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.actionBtn, styles.approveBtn]}
            onPress={() => applyAction(item, 'approve')}
            disabled={busy}
          >
            {busy ? (
              <ActivityIndicator size="small" color="#FFFFFF" />
            ) : (
              <>
                <Ionicons name="send" size={15} color="#FFFFFF" />
                <Text style={styles.approveBtnText}>Approve</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  const monitorOn = !!settings?.group_monitor_enabled;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Group Scout</Text>
          <Text style={styles.headerSubtitle}>AI leads from your WhatsApp groups</Text>
        </View>
      </View>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#25D366" />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
          }
        >
          {/* Monitor toggle */}
          <View style={styles.card}>
            <View style={styles.toggleRow}>
              <View style={{ flex: 1, paddingRight: 12 }}>
                <Text style={styles.cardTitle}>Monitor my WhatsApp groups</Text>
                <Text style={styles.cardHint}>
                  When on, the AI reads group messages and flags people who look ready to buy.
                </Text>
              </View>
              <Switch
                value={monitorOn}
                onValueChange={handleToggleMonitor}
                disabled={saving}
                trackColor={{ false: '#2A3A52', true: '#1D6B45' }}
                thumbColor={monitorOn ? '#25D366' : '#8B9DC3'}
              />
            </View>
          </View>

          {/* Keywords */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Keywords to watch for</Text>
            <Text style={styles.cardHint}>
              Comma-separated. Leave blank to use your business type. Common buy phrases
              (&quot;looking for&quot;, &quot;anyone recommend&quot;) are always detected.
            </Text>
            <TextInput
              style={styles.keywordInput}
              value={keywordsText}
              onChangeText={setKeywordsText}
              placeholder="e.g. plumber, catering, website design"
              placeholderTextColor="#5A6B82"
              multiline
            />
            <TouchableOpacity
              style={[styles.saveKeywordsBtn, saving && { opacity: 0.6 }]}
              onPress={handleSaveKeywords}
              disabled={saving}
            >
              {saving ? (
                <ActivityIndicator size="small" color="#FFFFFF" />
              ) : (
                <Text style={styles.saveKeywordsText}>Save keywords</Text>
              )}
            </TouchableOpacity>
          </View>

          {/* Leads */}
          <View style={styles.leadsHeaderRow}>
            <Text style={styles.sectionTitle}>Detected leads</Text>
            {leads.length > 0 && (
              <View style={styles.countBadge}>
                <Text style={styles.countBadgeText}>{leads.length}</Text>
              </View>
            )}
          </View>

          {leads.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons
                name={monitorOn ? 'search' : 'notifications-off-outline'}
                size={40}
                color="#3A4A5C"
              />
              <Text style={styles.emptyText}>
                {monitorOn
                  ? 'No leads yet. New buying signals from your groups will show up here.'
                  : 'Turn on monitoring above to start finding leads in your groups.'}
              </Text>
            </View>
          ) : (
            leads.map(renderLead)
          )}
        </ScrollView>
      )}

      {/* Edit reply modal */}
      <Modal
        visible={!!editItem}
        animationType="slide"
        transparent
        onRequestClose={() => setEditItem(null)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Edit reply</Text>
            <TextInput
              style={styles.modalInput}
              value={editText}
              onChangeText={setEditText}
              multiline
              autoFocus
              placeholder="Your reply…"
              placeholderTextColor="#5A6B82"
            />
            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[styles.actionBtn, styles.skipBtn, { flex: 1 }]}
                onPress={() => setEditItem(null)}
              >
                <Text style={styles.skipBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, styles.approveBtn, { flex: 1 }]}
                onPress={() => {
                  if (editItem) {
                    applyAction(editItem, 'approve', editText);
                    setEditItem(null);
                  }
                }}
              >
                <Ionicons name="send" size={15} color="#FFFFFF" />
                <Text style={styles.approveBtnText}>Send</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
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
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: '#0A1628',
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  backButton: {
    padding: 8,
    marginRight: 4,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  headerSubtitle: {
    fontSize: 12,
    color: '#8B9DC3',
    marginTop: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 60,
  },
  card: {
    backgroundColor: '#0F2038',
    borderRadius: 14,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: '#1A2942',
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  cardHint: {
    fontSize: 12,
    color: '#8B9DC3',
    marginTop: 4,
    lineHeight: 17,
  },
  keywordInput: {
    backgroundColor: '#0A1628',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1A2942',
    color: '#E9EDEF',
    fontSize: 14,
    padding: 12,
    marginTop: 12,
    minHeight: 60,
    textAlignVertical: 'top',
  },
  saveKeywordsBtn: {
    backgroundColor: '#25D366',
    borderRadius: 10,
    paddingVertical: 11,
    alignItems: 'center',
    marginTop: 12,
  },
  saveKeywordsText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 14,
  },
  leadsHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 6,
    marginBottom: 10,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  countBadge: {
    backgroundColor: '#25D366',
    borderRadius: 10,
    minWidth: 20,
    paddingHorizontal: 7,
    paddingVertical: 1,
    marginLeft: 8,
    alignItems: 'center',
  },
  countBadgeText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 50,
    paddingHorizontal: 30,
  },
  emptyText: {
    color: '#8B9DC3',
    fontSize: 14,
    textAlign: 'center',
    marginTop: 14,
    lineHeight: 20,
  },
  leadCard: {
    backgroundColor: '#0F2038',
    borderRadius: 14,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1A2942',
  },
  leadHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  groupBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    flex: 1,
    marginRight: 8,
  },
  groupBadgeText: {
    color: '#25D366',
    fontSize: 12,
    fontWeight: '600',
    flexShrink: 1,
  },
  keywordPill: {
    backgroundColor: 'rgba(74,144,226,0.15)',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  keywordPillText: {
    color: '#4A90E2',
    fontSize: 11,
    fontWeight: '600',
  },
  leadAuthor: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  leadSnippet: {
    color: '#C7D2DE',
    fontSize: 14,
    marginTop: 4,
    lineHeight: 19,
  },
  draftBox: {
    backgroundColor: '#0A1628',
    borderRadius: 10,
    padding: 11,
    marginTop: 12,
    borderWidth: 1,
    borderColor: '#1A2942',
  },
  draftLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginBottom: 5,
  },
  draftLabel: {
    color: '#FFD700',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  draftText: {
    color: '#E9EDEF',
    fontSize: 14,
    lineHeight: 19,
  },
  leadActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    paddingVertical: 10,
    borderRadius: 10,
  },
  skipBtn: {
    backgroundColor: 'rgba(139,157,195,0.12)',
    paddingHorizontal: 14,
  },
  skipBtnText: {
    color: '#8B9DC3',
    fontSize: 13,
    fontWeight: '600',
  },
  editBtn: {
    backgroundColor: 'rgba(74,144,226,0.12)',
    paddingHorizontal: 14,
  },
  editBtnText: {
    color: '#4A90E2',
    fontSize: 13,
    fontWeight: '600',
  },
  approveBtn: {
    backgroundColor: '#25D366',
    flex: 1,
  },
  approveBtnText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: '#0F2038',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    paddingBottom: 36,
  },
  modalTitle: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '700',
    marginBottom: 12,
  },
  modalInput: {
    backgroundColor: '#0A1628',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1A2942',
    color: '#E9EDEF',
    fontSize: 15,
    padding: 12,
    minHeight: 110,
    textAlignVertical: 'top',
  },
  modalActions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
  },
});
