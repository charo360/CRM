import React, { useState, useEffect } from 'react';
import {
    View, Text, Modal, StyleSheet, TouchableOpacity,
    ScrollView, TextInput, Alert, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiClient } from '../context/api';

interface ProductAction {
    label: string;
    action_type: string;
    index: number;
    ai_prompt: string;
}

interface Props {
    visible: boolean;
    onClose: () => void;
}

const ACTION_TYPE_LABELS: Record<string, string> = {
    order:       '🛒 Order Now',
    add_to_cart: '🛍️ Add to Cart',
    ask:         '💬 Ask a Question',
    book:        '📅 Book Appointment',
    subscribe:   '⭐ Subscribe',
    quote:       '💰 Request Quote',
    test_drive:  '🚗 Test Drive',
    info:        'ℹ️ More Info',
    custom:      '✏️ Custom (AI Prompt)',
};

const ACTION_TYPE_KEYS = Object.keys(ACTION_TYPE_LABELS);

const PRESETS: { name: string; icon: string; desc: string; actions: ProductAction[] }[] = [
    {
        name: 'Shop / E-commerce',
        icon: '🛒',
        desc: 'Sell products online',
        actions: [
            { label: 'Order Now',      action_type: 'order',       index: 1, ai_prompt: '' },
            { label: 'Add to Cart',    action_type: 'add_to_cart', index: 2, ai_prompt: '' },
            { label: 'Ask a Question', action_type: 'ask',         index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Car Dealership',
        icon: '🚗',
        desc: 'Sell vehicles',
        actions: [
            { label: 'Schedule Test Drive', action_type: 'test_drive', index: 1, ai_prompt: '' },
            { label: 'Get a Quote',         action_type: 'quote',      index: 2, ai_prompt: '' },
            { label: 'Ask a Question',      action_type: 'ask',        index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Salon / Beauty',
        icon: '💅',
        desc: 'Beauty & wellness',
        actions: [
            { label: 'Book Appointment', action_type: 'book', index: 1, ai_prompt: '' },
            { label: 'View Services',    action_type: 'info', index: 2, ai_prompt: '' },
            { label: 'Ask a Question',   action_type: 'ask',  index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Subscription',
        icon: '⭐',
        desc: 'Plans & subscriptions',
        actions: [
            { label: 'Subscribe Now',  action_type: 'subscribe', index: 1, ai_prompt: '' },
            { label: 'Learn More',     action_type: 'info',      index: 2, ai_prompt: '' },
            { label: 'Ask a Question', action_type: 'ask',       index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Restaurant',
        icon: '🍽️',
        desc: 'Food & dining',
        actions: [
            { label: 'Order Now',        action_type: 'order', index: 1, ai_prompt: '' },
            { label: 'Make Reservation', action_type: 'book',  index: 2, ai_prompt: '' },
            { label: 'View Menu',        action_type: 'info',  index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Real Estate',
        icon: '🏠',
        desc: 'Property listings',
        actions: [
            { label: 'Book a Viewing', action_type: 'book',  index: 1, ai_prompt: '' },
            { label: 'Get a Quote',    action_type: 'quote', index: 2, ai_prompt: '' },
            { label: 'Ask a Question', action_type: 'ask',   index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Fitness / Gym',
        icon: '🏋️',
        desc: 'Classes & memberships',
        actions: [
            { label: 'Join / Enroll',    action_type: 'order',     index: 1, ai_prompt: '' },
            { label: 'Book a Class',     action_type: 'book',      index: 2, ai_prompt: '' },
            { label: 'Ask a Question',   action_type: 'ask',       index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Healthcare',
        icon: '🏥',
        desc: 'Clinic & medical',
        actions: [
            { label: 'Book Appointment', action_type: 'book',  index: 1, ai_prompt: '' },
            { label: 'Get a Quote',      action_type: 'quote', index: 2, ai_prompt: '' },
            { label: 'Ask a Question',   action_type: 'ask',   index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Rental / Airbnb',
        icon: '🏡',
        desc: 'Short-stay rentals',
        actions: [
            { label: 'Check Availability', action_type: 'book',  index: 1, ai_prompt: '' },
            { label: 'Get a Quote',        action_type: 'quote', index: 2, ai_prompt: '' },
            { label: 'Ask a Question',     action_type: 'ask',   index: 3, ai_prompt: '' },
        ],
    },
    {
        name: 'Tech / SaaS',
        icon: '💻',
        desc: 'Software & platforms',
        actions: [
            { label: 'Start Free Trial', action_type: 'subscribe', index: 1, ai_prompt: '' },
            { label: 'Book a Demo',      action_type: 'book',      index: 2, ai_prompt: '' },
            { label: 'Ask a Question',   action_type: 'ask',       index: 3, ai_prompt: '' },
        ],
    },
];

const DEFAULT_ACTIONS: ProductAction[] = [
    { label: 'Order Now',      action_type: 'order',       index: 1, ai_prompt: '' },
    { label: 'Add to Cart',    action_type: 'add_to_cart', index: 2, ai_prompt: '' },
    { label: 'Ask a Question', action_type: 'ask',         index: 3, ai_prompt: '' },
];

export default function ProductActionsModal({ visible, onClose }: Props) {
    const [actions, setActions] = useState<ProductAction[]>(DEFAULT_ACTIONS);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
    const [showTypePicker, setShowTypePicker] = useState<number | null>(null);

    useEffect(() => {
        if (visible) loadActions();
    }, [visible]);

    const loadActions = async () => {
        setLoading(true);
        try {
            const res = await apiClient.get('/settings/product-actions');
            if (res.data?.actions?.length) setActions(res.data.actions);
        } catch (e) {
            console.error('Load product actions failed', e);
        } finally {
            setLoading(false);
        }
    };

    const applyPreset = (preset: typeof PRESETS[0]) => {
        setActions(preset.actions);
        setExpandedIdx(null);
    };

    const updateAction = (idx: number, field: keyof ProductAction, value: string) => {
        setActions(prev => prev.map((a, i) => i === idx ? { ...a, [field]: value } : a));
    };

    const addAction = () => {
        if (actions.length >= 3) return;
        setActions(prev => [
            ...prev,
            { label: '', action_type: 'ask', index: prev.length + 1, ai_prompt: '' },
        ]);
        setExpandedIdx(actions.length);
    };

    const removeLastAction = () => {
        if (actions.length <= 1) return;
        setActions(prev => prev.slice(0, -1));
        setExpandedIdx(null);
    };

    const save = async () => {
        const valid = actions.filter(a => a.label.trim());
        if (!valid.length) {
            Alert.alert('Error', 'At least one action with a label is required.');
            return;
        }
        setSaving(true);
        try {
            await apiClient.put('/settings/product-actions', { actions: valid });
            Alert.alert(
                '✅ Saved!',
                'Customers will see these options the next time you send them a product on WhatsApp.'
            );
            onClose();
        } catch (e) {
            Alert.alert('Error', 'Failed to save. Please try again.');
        } finally {
            setSaving(false);
        }
    };

    const replyHint = () => {
        const n = actions.length;
        if (n === 1) return 'Reply with 1';
        if (n === 2) return 'Reply with 1 or 2';
        return 'Reply with 1, 2 or 3';
    };

    return (
        <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
            <SafeAreaView style={styles.container}>
                {/* Header */}
                <View style={styles.header}>
                    <TouchableOpacity onPress={onClose} style={styles.headerBtn}>
                        <Ionicons name="close" size={22} color="#374151" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Product Actions</Text>
                    <TouchableOpacity onPress={save} disabled={saving} style={styles.headerBtn}>
                        {saving
                            ? <ActivityIndicator size="small" color="#6366f1" />
                            : <Text style={styles.saveText}>Save</Text>}
                    </TouchableOpacity>
                </View>

                {loading
                    ? <ActivityIndicator size="large" color="#6366f1" style={{ marginTop: 60 }} />
                    : (
                        <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
                            {/* Info */}
                            <View style={styles.infoBox}>
                                <Ionicons name="chatbubble-ellipses-outline" size={18} color="#6366f1" />
                                <Text style={styles.infoText}>
                                    When you send a product on WhatsApp, customers see these numbered options. Customise them to match your business.
                                </Text>
                            </View>

                            {/* Presets */}
                            <Text style={styles.sectionLabel}>Quick Presets</Text>
                            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.presetsRow}>
                                {PRESETS.map(p => (
                                    <TouchableOpacity key={p.name} style={styles.presetCard} onPress={() => applyPreset(p)}>
                                        <Text style={styles.presetEmoji}>{p.icon}</Text>
                                        <Text style={styles.presetName}>{p.name}</Text>
                                        <Text style={styles.presetDesc}>{p.desc}</Text>
                                    </TouchableOpacity>
                                ))}
                            </ScrollView>

                            {/* Live Preview */}
                            <Text style={styles.sectionLabel}>Live Preview</Text>
                            <View style={styles.previewBubble}>
                                <Text style={styles.previewHeader}>*What would you like to do?*</Text>
                                {actions.map((a, i) => (
                                    <Text key={i} style={styles.previewLine}>
                                        {i + 1}️⃣  {a.label || '…'}
                                    </Text>
                                ))}
                                <Text style={styles.previewHint}>_{replyHint()}_</Text>
                            </View>

                            {/* Editor */}
                            <Text style={styles.sectionLabel}>Customise (up to 3)</Text>
                            {actions.map((action, idx) => (
                                <View key={idx} style={styles.card}>
                                    <TouchableOpacity
                                        style={styles.cardHeader}
                                        onPress={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
                                        activeOpacity={0.7}
                                    >
                                        <View style={styles.cardLeft}>
                                            <View style={styles.badge}>
                                                <Text style={styles.badgeText}>{idx + 1}</Text>
                                            </View>
                                            <View>
                                                <Text style={styles.cardTitle}>{action.label || 'Untitled action'}</Text>
                                                <Text style={styles.cardSub}>{ACTION_TYPE_LABELS[action.action_type] ?? action.action_type}</Text>
                                            </View>
                                        </View>
                                        <Ionicons
                                            name={expandedIdx === idx ? 'chevron-up' : 'chevron-down'}
                                            size={18} color="#9ca3af"
                                        />
                                    </TouchableOpacity>

                                    {expandedIdx === idx && (
                                        <View style={styles.cardBody}>
                                            <Text style={styles.fieldLabel}>Button Label</Text>
                                            <TextInput
                                                style={styles.input}
                                                value={action.label}
                                                onChangeText={v => updateAction(idx, 'label', v)}
                                                placeholder="e.g. Book Appointment"
                                                maxLength={30}
                                            />

                                            <Text style={styles.fieldLabel}>What happens when tapped?</Text>
                                            <TouchableOpacity
                                                style={styles.typeBtn}
                                                onPress={() => setShowTypePicker(showTypePicker === idx ? null : idx)}
                                            >
                                                <Text style={styles.typeBtnText}>
                                                    {ACTION_TYPE_LABELS[action.action_type] ?? action.action_type}
                                                </Text>
                                                <Ionicons name="chevron-down" size={16} color="#6b7280" />
                                            </TouchableOpacity>

                                            {showTypePicker === idx && (
                                                <View style={styles.dropdown}>
                                                    {ACTION_TYPE_KEYS.map(k => (
                                                        <TouchableOpacity
                                                            key={k}
                                                            style={[
                                                                styles.dropdownItem,
                                                                action.action_type === k && styles.dropdownItemActive,
                                                            ]}
                                                            onPress={() => {
                                                                updateAction(idx, 'action_type', k);
                                                                setShowTypePicker(null);
                                                            }}
                                                        >
                                                            <Text style={[
                                                                styles.dropdownText,
                                                                action.action_type === k && styles.dropdownTextActive,
                                                            ]}>
                                                                {ACTION_TYPE_LABELS[k]}
                                                            </Text>
                                                            {action.action_type === k && (
                                                                <Ionicons name="checkmark" size={16} color="#6366f1" />
                                                            )}
                                                        </TouchableOpacity>
                                                    ))}
                                                </View>
                                            )}

                                            {action.action_type === 'custom' && (
                                                <>
                                                    <Text style={styles.fieldLabel}>
                                                        AI Prompt{' '}
                                                        <Text style={styles.fieldHint}>
                                                            (use {'{product}'} and {'{name}'})
                                                        </Text>
                                                    </Text>
                                                    <TextInput
                                                        style={[styles.input, styles.inputTall]}
                                                        value={action.ai_prompt}
                                                        onChangeText={v => updateAction(idx, 'ai_prompt', v)}
                                                        placeholder="e.g. I'd like to enquire about {product}, my name is {name}"
                                                        multiline
                                                        maxLength={200}
                                                    />
                                                    <Text style={styles.charCount}>{(action.ai_prompt || '').length}/200</Text>
                                                </>
                                            )}
                                        </View>
                                    )}
                                </View>
                            ))}

                            <View style={styles.actionRow}>
                                {actions.length < 3 && (
                                    <TouchableOpacity style={styles.addBtn} onPress={addAction}>
                                        <Ionicons name="add-circle-outline" size={18} color="#6366f1" />
                                        <Text style={styles.addBtnText}>Add Action</Text>
                                    </TouchableOpacity>
                                )}
                                {actions.length > 1 && (
                                    <TouchableOpacity style={styles.removeBtn} onPress={removeLastAction}>
                                        <Ionicons name="remove-circle-outline" size={18} color="#ef4444" />
                                        <Text style={styles.removeBtnText}>Remove Last</Text>
                                    </TouchableOpacity>
                                )}
                            </View>

                            <TouchableOpacity style={styles.saveFullBtn} onPress={save} disabled={saving}>
                                {saving
                                    ? <ActivityIndicator size="small" color="#fff" />
                                    : <Text style={styles.saveFullText}>Save Changes</Text>}
                            </TouchableOpacity>

                            <View style={{ height: 40 }} />
                        </ScrollView>
                    )}
            </SafeAreaView>
        </Modal>
    );
}

const styles = StyleSheet.create({
    container:          { flex: 1, backgroundColor: '#f9fafb' },
    header:             { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
    headerBtn:          { minWidth: 40, alignItems: 'center' },
    headerTitle:        { fontSize: 17, fontWeight: '700', color: '#111827' },
    saveText:           { fontSize: 16, fontWeight: '700', color: '#6366f1' },
    scroll:             { flex: 1, paddingHorizontal: 16 },
    infoBox:            { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: '#ede9fe', borderRadius: 12, padding: 12, marginTop: 16, marginBottom: 4 },
    infoText:           { flex: 1, fontSize: 13, color: '#4b5563', lineHeight: 19 },
    sectionLabel:       { fontSize: 12, fontWeight: '700', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: 0.6, marginTop: 22, marginBottom: 10 },
    presetsRow:         { paddingBottom: 4, gap: 10 },
    presetCard:         { backgroundColor: '#fff', borderRadius: 14, padding: 14, width: 130, alignItems: 'center', borderWidth: 1, borderColor: '#e5e7eb' },
    presetEmoji:        { fontSize: 26, marginBottom: 6 },
    presetName:         { fontSize: 13, fontWeight: '700', color: '#111827', textAlign: 'center' },
    presetDesc:         { fontSize: 11, color: '#9ca3af', textAlign: 'center', marginTop: 3 },
    previewBubble:      { backgroundColor: '#d1fae5', borderRadius: 14, padding: 14, marginBottom: 4 },
    previewHeader:      { fontSize: 15, fontWeight: '700', color: '#065f46', marginBottom: 8 },
    previewLine:        { fontSize: 14, color: '#065f46', marginBottom: 4 },
    previewHint:        { fontSize: 12, color: '#059669', fontStyle: 'italic', marginTop: 4 },
    card:               { backgroundColor: '#fff', borderRadius: 14, marginBottom: 10, borderWidth: 1, borderColor: '#e5e7eb', overflow: 'hidden' },
    cardHeader:         { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14 },
    cardLeft:           { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
    badge:              { width: 30, height: 30, borderRadius: 15, backgroundColor: '#6366f1', alignItems: 'center', justifyContent: 'center' },
    badgeText:          { color: '#fff', fontWeight: '800', fontSize: 14 },
    cardTitle:          { fontSize: 15, fontWeight: '600', color: '#111827' },
    cardSub:            { fontSize: 12, color: '#6b7280', marginTop: 1 },
    cardBody:           { paddingHorizontal: 14, paddingBottom: 14, paddingTop: 4, borderTopWidth: 1, borderTopColor: '#f3f4f6' },
    fieldLabel:         { fontSize: 13, fontWeight: '600', color: '#374151', marginTop: 12, marginBottom: 5 },
    fieldHint:          { fontWeight: '400', color: '#9ca3af', fontSize: 12 },
    input:              { backgroundColor: '#f9fafb', borderRadius: 10, borderWidth: 1, borderColor: '#d1d5db', paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, color: '#111827' },
    inputTall:          { minHeight: 80, textAlignVertical: 'top', paddingTop: 10 },
    charCount:          { fontSize: 11, color: '#9ca3af', textAlign: 'right', marginTop: 4 },
    typeBtn:            { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#f9fafb', borderRadius: 10, borderWidth: 1, borderColor: '#d1d5db', paddingHorizontal: 12, paddingVertical: 10 },
    typeBtnText:        { fontSize: 15, color: '#111827' },
    dropdown:           { backgroundColor: '#fff', borderRadius: 10, borderWidth: 1, borderColor: '#d1d5db', marginTop: 6, overflow: 'hidden' },
    dropdownItem:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
    dropdownItemActive: { backgroundColor: '#ede9fe' },
    dropdownText:       { fontSize: 14, color: '#374151' },
    dropdownTextActive: { color: '#6366f1', fontWeight: '700' },
    actionRow:          { flexDirection: 'row', gap: 10, marginTop: 6, marginBottom: 4 },
    addBtn:             { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 12, borderWidth: 1.5, borderColor: '#6366f1', borderStyle: 'dashed' },
    addBtnText:         { fontSize: 14, fontWeight: '600', color: '#6366f1' },
    removeBtn:          { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 12, borderWidth: 1.5, borderColor: '#fca5a5', borderStyle: 'dashed' },
    removeBtnText:      { fontSize: 14, fontWeight: '600', color: '#ef4444' },
    saveFullBtn:        { backgroundColor: '#6366f1', borderRadius: 14, paddingVertical: 15, alignItems: 'center', marginTop: 16 },
    saveFullText:       { color: '#fff', fontSize: 16, fontWeight: '700' },
});
