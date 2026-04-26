import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  StyleSheet, ActivityIndicator, Alert, Switch, RefreshControl,
  Modal, KeyboardAvoidingView, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { workflowsAPI } from '../context/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface WorkflowStep {
  id: string;
  action: string;
  params: Record<string, any>;
  delay_minutes: number;
}

interface Workflow {
  _id: string;
  name: string;
  description: string;
  trigger: { type: string; condition?: string };
  steps: WorkflowStep[];
  enabled: boolean;
  run_count: number;
  last_run_at?: string;
  created_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const TRIGGER_LABELS: Record<string, string> = {
  incoming_message: 'Incoming Message',
  intent_detected: 'Intent Detected',
  tag_added: 'Tag Added',
  customer_created: 'New Customer',
  pipeline_stage_changed: 'Stage Changed',
};

const ACTION_LABELS: Record<string, string> = {
  send_message: 'Send Message',
  tag_contact: 'Tag Contact',
  assign_owner: 'Assign Owner',
  notify_owner: 'Notify Owner',
  create_followup: 'Create Follow-up',
  move_pipeline_stage: 'Move Stage',
  escalate_to_human: 'Escalate',
  wait: 'Wait',
  if_no_reply: 'If No Reply',
};

const ACTION_ICONS: Record<string, string> = {
  send_message: 'chatbubble-outline',
  tag_contact: 'pricetag-outline',
  assign_owner: 'person-outline',
  notify_owner: 'notifications-outline',
  create_followup: 'alarm-outline',
  move_pipeline_stage: 'git-commit-outline',
  escalate_to_human: 'warning-outline',
  wait: 'time-outline',
  if_no_reply: 'checkmark-circle-outline',
};

function stepSummary(step: WorkflowStep): string {
  const a = step.action;
  const p = step.params || {};
  if (a === 'send_message') return `Send: "${(p.message || '').substring(0, 40)}${p.message?.length > 40 ? '...' : ''}"`;
  if (a === 'tag_contact') return `Tag as "${p.tag || ''}"`;
  if (a === 'assign_owner') return `Assign to ${p.member_name || 'team'}`;
  if (a === 'notify_owner') return `Alert: "${(p.message || '').substring(0, 40)}"`;
  if (a === 'create_followup') return `Follow-up: "${(p.note || '').substring(0, 40)}"`;
  if (a === 'move_pipeline_stage') return `Move to ${p.stage || ''} stage`;
  if (a === 'escalate_to_human') return `Escalate: ${p.reason || ''}`;
  if (a === 'wait') return `Wait ${p.hours || 1} hour${p.hours === 1 ? '' : 's'}`;
  if (a === 'if_no_reply') return `If customer hasn't replied`;
  return ACTION_LABELS[a] || a;
}

function triggerSummary(trigger: Workflow['trigger']): string {
  const label = TRIGGER_LABELS[trigger.type] || trigger.type;
  if (!trigger.condition || trigger.condition === 'always') return label;
  return `${label}: ${trigger.condition}`;
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function AutomationsScreen() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showBuilder, setShowBuilder] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await workflowsAPI.list();
      setWorkflows(data);
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Could not load automations');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, []);

  const handleToggle = async (wf: Workflow) => {
    const prev = wf.enabled;
    setWorkflows(ws => ws.map(w => w._id === wf._id ? { ...w, enabled: !prev } : w));
    try {
      await workflowsAPI.toggle(wf._id);
    } catch {
      setWorkflows(ws => ws.map(w => w._id === wf._id ? { ...w, enabled: prev } : w));
      Alert.alert('Error', 'Could not update automation');
    }
  };

  const handleDelete = (wf: Workflow) => {
    Alert.alert(
      'Delete Automation',
      `Delete "${wf.name}"? This cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete', style: 'destructive',
          onPress: async () => {
            try {
              await workflowsAPI.delete(wf._id);
              setWorkflows(ws => ws.filter(w => w._id !== wf._id));
            } catch {
              Alert.alert('Error', 'Could not delete automation');
            }
          },
        },
      ]
    );
  };

  const handleBuilderSave = (wf: Workflow) => {
    setWorkflows(ws => {
      const exists = ws.find(w => w._id === wf._id);
      return exists ? ws.map(w => w._id === wf._id ? wf : w) : [wf, ...ws];
    });
    setShowBuilder(false);
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#25D366" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#FFF" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Automations</Text>
          <Text style={styles.headerSub}>Workflows that run in the background for you</Text>
        </View>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowBuilder(true)}>
          <Ionicons name="add" size={22} color="#FFF" />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 80 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#25D366" />}
      >
        {/* Build with AI banner */}
        <TouchableOpacity style={styles.aiBanner} onPress={() => setShowBuilder(true)} activeOpacity={0.85}>
          <Ionicons name="sparkles" size={20} color="#FFF" style={{ marginRight: 10 }} />
          <View style={{ flex: 1 }}>
            <Text style={styles.aiBannerTitle}>Build with AI</Text>
            <Text style={styles.aiBannerSub}>Describe what you want in plain English</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color="rgba(255,255,255,0.7)" />
        </TouchableOpacity>

        {/* Empty state */}
        {workflows.length === 0 && (
          <View style={styles.emptyState}>
            <Ionicons name="git-network-outline" size={48} color="#1A2942" />
            <Text style={styles.emptyTitle}>No automations yet</Text>
            <Text style={styles.emptySub}>
              Create your first automation to run background tasks, send follow-ups, tag leads, and more.
            </Text>
            <TouchableOpacity style={styles.emptyBtn} onPress={() => setShowBuilder(true)}>
              <Text style={styles.emptyBtnText}>Create Automation</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Workflow list */}
        {workflows.map(wf => (
          <WorkflowCard
            key={wf._id}
            workflow={wf}
            expanded={expandedId === wf._id}
            onExpand={() => setExpandedId(expandedId === wf._id ? null : wf._id)}
            onToggle={() => handleToggle(wf)}
            onDelete={() => handleDelete(wf)}
          />
        ))}

        {/* Example templates */}
        {workflows.length === 0 && (
          <ExampleTemplates onUse={(desc) => { setShowBuilder(true); }} />
        )}
      </ScrollView>

      {/* AI Builder Modal */}
      <WorkflowBuilderModal
        visible={showBuilder}
        onClose={() => setShowBuilder(false)}
        onSave={handleBuilderSave}
      />
    </View>
  );
}

// ── Workflow card ─────────────────────────────────────────────────────────────

function WorkflowCard({
  workflow: wf, expanded, onExpand, onToggle, onDelete,
}: {
  workflow: Workflow;
  expanded: boolean;
  onExpand: () => void;
  onToggle: () => void;
  onDelete: () => void;
}) {
  return (
    <View style={styles.card}>
      <TouchableOpacity onPress={onExpand} activeOpacity={0.8} style={styles.cardHeader}>
        <View style={[styles.triggerPill]}>
          <Text style={styles.triggerPillText}>{TRIGGER_LABELS[wf.trigger.type] || wf.trigger.type}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>{wf.name}</Text>
          {wf.description ? <Text style={styles.cardDesc}>{wf.description}</Text> : null}
        </View>
        <View style={styles.cardRight}>
          <Switch
            value={wf.enabled}
            onValueChange={onToggle}
            trackColor={{ false: '#1A2942', true: '#25D366' }}
            thumbColor="#FFF"
            style={{ transform: [{ scaleX: 0.85 }, { scaleY: 0.85 }] }}
          />
          <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color="#666" style={{ marginTop: 4 }} />
        </View>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.cardBody}>
          {/* Trigger condition */}
          <View style={styles.triggerRow}>
            <Ionicons name="flash-outline" size={14} color="#F59E0B" style={{ marginRight: 6 }} />
            <Text style={styles.triggerText}>{triggerSummary(wf.trigger)}</Text>
          </View>

          {/* Steps */}
          {wf.steps.map((step, i) => (
            <View key={step.id} style={styles.stepRow}>
              <View style={styles.stepLine}>
                {i < wf.steps.length - 1 && <View style={styles.stepConnector} />}
              </View>
              <View style={styles.stepDot}>
                <Ionicons name={(ACTION_ICONS[step.action] as any) || 'ellipse-outline'} size={12} color="#25D366" />
              </View>
              <Text style={styles.stepText}>{stepSummary(step)}</Text>
            </View>
          ))}

          {/* Stats + delete */}
          <View style={styles.cardFooter}>
            <Text style={styles.runCount}>{wf.run_count} run{wf.run_count !== 1 ? 's' : ''}</Text>
            <TouchableOpacity onPress={onDelete} style={styles.deleteBtn}>
              <Ionicons name="trash-outline" size={14} color="#EF4444" />
              <Text style={styles.deleteBtnText}>Delete</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
}

// ── Example templates ─────────────────────────────────────────────────────────

const TEMPLATES = [
  "When a customer asks about price, wait 2 hours, if they haven't replied, send a follow-up message",
  "When a new customer messages, tag them as 'new_lead' and notify me",
  "When a complaint is detected, escalate to human immediately and notify the owner",
  "When an order intent is detected, create a follow-up reminder for 24 hours",
];

function ExampleTemplates({ onUse }: { onUse: (desc: string) => void }) {
  return (
    <View style={{ padding: 16 }}>
      <Text style={styles.sectionLabel}>Example automations</Text>
      {TEMPLATES.map((t, i) => (
        <TouchableOpacity key={i} style={styles.templateCard} onPress={() => onUse(t)} activeOpacity={0.85}>
          <Text style={styles.templateText}>{t}</Text>
          <Ionicons name="arrow-forward-circle-outline" size={18} color="#25D366" />
        </TouchableOpacity>
      ))}
    </View>
  );
}

// ── AI Builder Modal ──────────────────────────────────────────────────────────

function WorkflowBuilderModal({
  visible, onClose, onSave,
}: {
  visible: boolean;
  onClose: () => void;
  onSave: (wf: Workflow) => void;
}) {
  const [step, setStep] = useState<'input' | 'preview' | 'saving'>('input');
  const [description, setDescription] = useState('');
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState('');
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setStep('input');
    setDescription('');
    setPreview(null);
    setError('');
    setGenerating(false);
    setSaving(false);
  };

  const handleClose = () => { reset(); onClose(); };

  const handleGenerate = async () => {
    if (!description.trim() || description.trim().length < 10) {
      setError('Please describe your automation in more detail.');
      return;
    }
    setError('');
    setGenerating(true);
    try {
      const result = await workflowsAPI.buildFromDescription(description.trim());
      setPreview(result);
      setStep('preview');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not generate automation. Try rephrasing.');
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if (!preview) return;
    setSaving(true);
    try {
      const saved = await workflowsAPI.create(preview);
      onSave(saved);
      reset();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not save automation.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={handleClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={styles.modalContainer}>
          {/* Modal header */}
          <View style={styles.modalHeader}>
            {step === 'preview' ? (
              <TouchableOpacity onPress={() => setStep('input')} style={styles.backBtn}>
                <Ionicons name="arrow-back" size={20} color="#FFF" />
              </TouchableOpacity>
            ) : (
              <TouchableOpacity onPress={handleClose} style={styles.backBtn}>
                <Ionicons name="close" size={20} color="#FFF" />
              </TouchableOpacity>
            )}
            <Text style={styles.modalTitle}>
              {step === 'input' ? 'Describe Your Automation' : 'Preview Automation'}
            </Text>
            <View style={{ width: 36 }} />
          </View>

          <ScrollView contentContainerStyle={styles.modalBody} keyboardShouldPersistTaps="handled">
            {step === 'input' && (
              <>
                <Text style={styles.modalHint}>
                  Describe what you want to happen in plain English. The AI will turn it into a live automation.
                </Text>

                <Text style={styles.fieldLabel}>What should this automation do?</Text>
                <TextInput
                  style={styles.textArea}
                  multiline
                  numberOfLines={5}
                  placeholder="e.g. When a customer asks about price, wait 2 hours, then if they haven't replied, send a follow-up message"
                  placeholderTextColor="#4A5568"
                  value={description}
                  onChangeText={setDescription}
                  autoFocus
                />

                {error ? <Text style={styles.errorText}>{error}</Text> : null}

                <TouchableOpacity
                  style={[styles.primaryBtn, generating && styles.btnDisabled]}
                  onPress={handleGenerate}
                  disabled={generating}
                  activeOpacity={0.85}
                >
                  {generating ? (
                    <ActivityIndicator color="#FFF" size="small" />
                  ) : (
                    <>
                      <Ionicons name="sparkles" size={16} color="#FFF" style={{ marginRight: 8 }} />
                      <Text style={styles.primaryBtnText}>Generate Automation</Text>
                    </>
                  )}
                </TouchableOpacity>

                <Text style={styles.sectionLabel}>Tap an example to try it</Text>
                {TEMPLATES.map((t, i) => (
                  <TouchableOpacity
                    key={i}
                    style={styles.templateCard}
                    onPress={() => setDescription(t)}
                    activeOpacity={0.85}
                  >
                    <Text style={styles.templateText}>{t}</Text>
                  </TouchableOpacity>
                ))}
              </>
            )}

            {step === 'preview' && preview && (
              <>
                <View style={styles.previewCard}>
                  <Text style={styles.previewName}>{preview.name}</Text>
                  {preview.description ? (
                    <Text style={styles.previewDesc}>{preview.description}</Text>
                  ) : null}

                  {/* Trigger */}
                  <View style={styles.previewSection}>
                    <Text style={styles.previewSectionLabel}>TRIGGER</Text>
                    <View style={styles.previewTrigger}>
                      <Ionicons name="flash" size={14} color="#F59E0B" style={{ marginRight: 6 }} />
                      <Text style={styles.previewTriggerText}>
                        {TRIGGER_LABELS[preview.trigger?.type] || preview.trigger?.type}
                        {preview.trigger?.condition && preview.trigger.condition !== 'always'
                          ? `: ${preview.trigger.condition}` : ''}
                      </Text>
                    </View>
                  </View>

                  {/* Steps */}
                  <View style={styles.previewSection}>
                    <Text style={styles.previewSectionLabel}>STEPS</Text>
                    {(preview.steps || []).map((step: WorkflowStep, i: number) => (
                      <View key={i} style={styles.previewStep}>
                        <View style={styles.previewStepNum}>
                          <Text style={styles.previewStepNumText}>{i + 1}</Text>
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.previewStepAction}>{ACTION_LABELS[step.action] || step.action}</Text>
                          <Text style={styles.previewStepDetail}>{stepSummary(step)}</Text>
                        </View>
                      </View>
                    ))}
                  </View>
                </View>

                {error ? <Text style={styles.errorText}>{error}</Text> : null}

                <TouchableOpacity
                  style={[styles.primaryBtn, saving && styles.btnDisabled]}
                  onPress={handleSave}
                  disabled={saving}
                  activeOpacity={0.85}
                >
                  {saving ? (
                    <ActivityIndicator color="#FFF" size="small" />
                  ) : (
                    <>
                      <Ionicons name="checkmark-circle" size={16} color="#FFF" style={{ marginRight: 8 }} />
                      <Text style={styles.primaryBtnText}>Activate Automation</Text>
                    </>
                  )}
                </TouchableOpacity>

                <TouchableOpacity style={styles.secondaryBtn} onPress={() => setStep('input')}>
                  <Text style={styles.secondaryBtnText}>Edit Description</Text>
                </TouchableOpacity>
              </>
            )}
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#060E1E' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#060E1E' },

  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingTop: Platform.OS === 'ios' ? 52 : 40,
    paddingHorizontal: 16, paddingBottom: 16,
    backgroundColor: '#0A1628',
    borderBottomWidth: 1, borderBottomColor: '#1A2942',
  },
  backBtn: { width: 36, height: 36, justifyContent: 'center', alignItems: 'center', marginRight: 8 },
  headerTitle: { color: '#FFF', fontSize: 18, fontWeight: '700' },
  headerSub: { color: '#64748B', fontSize: 12, marginTop: 2 },
  addBtn: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: '#25D366', justifyContent: 'center', alignItems: 'center',
  },

  aiBanner: {
    margin: 16, borderRadius: 12, padding: 16,
    backgroundColor: '#1A1042',
    borderWidth: 1, borderColor: '#6B21A8',
    flexDirection: 'row', alignItems: 'center',
  },
  aiBannerTitle: { color: '#FFF', fontWeight: '700', fontSize: 14 },
  aiBannerSub: { color: '#A78BFA', fontSize: 12, marginTop: 2 },

  emptyState: { alignItems: 'center', paddingTop: 48, paddingHorizontal: 32 },
  emptyTitle: { color: '#FFF', fontSize: 18, fontWeight: '700', marginTop: 16 },
  emptySub: { color: '#64748B', fontSize: 14, textAlign: 'center', marginTop: 8, lineHeight: 20 },
  emptyBtn: {
    marginTop: 20, backgroundColor: '#25D366', borderRadius: 10,
    paddingVertical: 12, paddingHorizontal: 24,
  },
  emptyBtnText: { color: '#FFF', fontWeight: '700', fontSize: 14 },

  sectionLabel: { color: '#64748B', fontSize: 11, fontWeight: '700', letterSpacing: 1, marginBottom: 8, marginTop: 8 },

  card: {
    marginHorizontal: 16, marginBottom: 10, borderRadius: 12,
    backgroundColor: '#0D1B2E', borderWidth: 1, borderColor: '#1A2942',
    overflow: 'hidden',
  },
  cardHeader: { padding: 14, flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  triggerPill: {
    backgroundColor: '#0F2D19', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3,
    alignSelf: 'flex-start',
  },
  triggerPillText: { color: '#25D366', fontSize: 10, fontWeight: '600' },
  cardTitle: { color: '#FFF', fontWeight: '700', fontSize: 14, flex: 1 },
  cardDesc: { color: '#64748B', fontSize: 12, marginTop: 2 },
  cardRight: { alignItems: 'flex-end', gap: 2 },

  cardBody: { paddingHorizontal: 14, paddingBottom: 14, borderTopWidth: 1, borderTopColor: '#1A2942' },
  triggerRow: { flexDirection: 'row', alignItems: 'center', marginTop: 10, marginBottom: 6 },
  triggerText: { color: '#F59E0B', fontSize: 12 },

  stepRow: { flexDirection: 'row', alignItems: 'center', marginVertical: 3, paddingLeft: 4 },
  stepLine: { width: 16, alignItems: 'center' },
  stepConnector: { position: 'absolute', width: 1, backgroundColor: '#1A2942', top: 16, bottom: -10, left: 7 },
  stepDot: {
    width: 20, height: 20, borderRadius: 10,
    backgroundColor: '#0F2D19', justifyContent: 'center', alignItems: 'center', marginRight: 8,
  },
  stepText: { color: '#94A3B8', fontSize: 12, flex: 1 },

  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 },
  runCount: { color: '#64748B', fontSize: 11 },
  deleteBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  deleteBtnText: { color: '#EF4444', fontSize: 12 },

  templateCard: {
    backgroundColor: '#0D1B2E', borderWidth: 1, borderColor: '#1A2942',
    borderRadius: 10, padding: 12, marginBottom: 8,
    flexDirection: 'row', alignItems: 'center', gap: 10,
  },
  templateText: { color: '#94A3B8', fontSize: 13, flex: 1, lineHeight: 18 },

  // Modal
  modalContainer: { flex: 1, backgroundColor: '#060E1E' },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingTop: Platform.OS === 'ios' ? 52 : 40, paddingHorizontal: 16, paddingBottom: 16,
    backgroundColor: '#0A1628', borderBottomWidth: 1, borderBottomColor: '#1A2942',
  },
  modalTitle: { color: '#FFF', fontWeight: '700', fontSize: 16 },
  modalBody: { padding: 16, paddingBottom: 60 },
  modalHint: { color: '#64748B', fontSize: 13, lineHeight: 19, marginBottom: 20 },

  fieldLabel: { color: '#94A3B8', fontSize: 12, fontWeight: '600', marginBottom: 6 },
  textArea: {
    backgroundColor: '#0D1B2E', borderRadius: 10, borderWidth: 1, borderColor: '#1A2942',
    color: '#FFF', padding: 14, fontSize: 14, minHeight: 120, textAlignVertical: 'top',
    lineHeight: 20,
  },
  errorText: { color: '#EF4444', fontSize: 12, marginTop: 8 },

  primaryBtn: {
    backgroundColor: '#25D366', borderRadius: 10, paddingVertical: 14,
    flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginTop: 16,
  },
  primaryBtnText: { color: '#FFF', fontWeight: '700', fontSize: 15 },
  btnDisabled: { opacity: 0.6 },
  secondaryBtn: {
    borderRadius: 10, paddingVertical: 13, alignItems: 'center', marginTop: 10,
    borderWidth: 1, borderColor: '#1A2942',
  },
  secondaryBtnText: { color: '#94A3B8', fontWeight: '600', fontSize: 14 },

  // Preview
  previewCard: {
    backgroundColor: '#0D1B2E', borderRadius: 12, borderWidth: 1, borderColor: '#1A2942', padding: 16,
  },
  previewName: { color: '#FFF', fontWeight: '700', fontSize: 16, marginBottom: 4 },
  previewDesc: { color: '#64748B', fontSize: 13, marginBottom: 12 },
  previewSection: { marginTop: 14 },
  previewSectionLabel: { color: '#64748B', fontSize: 10, fontWeight: '700', letterSpacing: 1.2, marginBottom: 8 },
  previewTrigger: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#0F1F10', borderRadius: 8, padding: 10,
  },
  previewTriggerText: { color: '#F59E0B', fontSize: 13, flex: 1 },
  previewStep: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 8,
  },
  previewStepNum: {
    width: 22, height: 22, borderRadius: 11, backgroundColor: '#0F2D19',
    justifyContent: 'center', alignItems: 'center',
  },
  previewStepNumText: { color: '#25D366', fontSize: 11, fontWeight: '700' },
  previewStepAction: { color: '#FFF', fontSize: 13, fontWeight: '600' },
  previewStepDetail: { color: '#64748B', fontSize: 11, marginTop: 2 },
});
