import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    Modal,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    Alert,
    FlatList,
    TextInput
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { suppliersAPI, apiClient } from '../context/api';

const PRESET_CATEGORIES = [
    'Electronics', 'Clothing', 'Food & Beverage', 'Beauty & Health',
    'Home & Garden', 'Automotive', 'Raw Materials', 'Packaging',
    'Stationery', 'Services', 'Agriculture', 'Construction',
    'Pharmacy', 'Furniture', 'Printing', 'Other',
];

interface Supplier {
    _id: string;
    id?: string;
    name: string;
    phone_number: string;
    tags: string[];
    supplier_category?: string;
    payment_terms?: string;
    lead_time?: string;
    rating?: number;
}

interface RestockSuggestion {
    type: string;
    product_name: string;
    current_stock: number;
    suggested_action: string;
    priority: string;
}

interface SupplierListModalProps {
    visible: boolean;
    onClose: () => void;
}

export default function SupplierListModal({ visible, onClose }: SupplierListModalProps) {
    const router = useRouter();
    const [suppliers, setSuppliers] = useState<Supplier[]>([]);
    const [potentialSuppliers, setPotentialSuppliers] = useState<Supplier[]>([]);
    const [restockSuggestions, setRestockSuggestions] = useState<RestockSuggestion[]>([]);
    const [loading, setLoading] = useState(false);
    const [viewMode, setViewMode] = useState<'list' | 'add'>('list');

    // Add Mode State
    const [allCustomers, setAllCustomers] = useState<Supplier[]>([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [addingIds, setAddingIds] = useState<string[]>([]);

    // Category picker state
    const [categoryTarget, setCategoryTarget] = useState<Supplier | null>(null); // supplier being categorised
    const [selectedCategory, setSelectedCategory] = useState('');
    const [customCategory, setCustomCategory] = useState('');
    const [showCustomInput, setShowCustomInput] = useState(false);

    // Expanded card edit state
    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [editCategory, setEditCategory] = useState('');
    const [editCustomCategory, setEditCustomCategory] = useState('');
    const [showEditCustomInput, setShowEditCustomInput] = useState(false);
    const [editPaymentTerms, setEditPaymentTerms] = useState('');
    const [editLeadTime, setEditLeadTime] = useState('');
    const [editRating, setEditRating] = useState(0);
    const [savingId, setSavingId] = useState<string | null>(null);

    useEffect(() => {
        if (visible) {
            fetchData();
            setViewMode('list');
        }
    }, [visible]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [suppliersData, insightsData] = await Promise.all([
                suppliersAPI.getSuppliers(),
                suppliersAPI.getInsights()
            ]);
            setSuppliers(suppliersData);
            setPotentialSuppliers(insightsData.potential_suppliers || []);
            setRestockSuggestions(insightsData.restock_suggestions || []);
        } catch (error) {
            console.error('Error fetching supplier data:', error);
            Alert.alert('Error', 'Failed to load suppliers');
        } finally {
            setLoading(false);
        }
    };

    const fetchAllCustomers = async () => {
        setLoading(true);
        try {
            const response = await apiClient.get('/customers');
            // Filter out existing suppliers
            const currentSupplierIds = new Set(suppliers.map(s => s._id || s.id));
            const available = response.data.filter((c: any) => !currentSupplierIds.has(c.id));
            setAllCustomers(available);
        } catch (error) {
            console.error('Error fetching customers:', error);
        } finally {
            setLoading(false);
        }
    };

    const openCategoryPicker = (customer: Supplier) => {
        setCategoryTarget(customer);
        setSelectedCategory('');
        setCustomCategory('');
        setShowCustomInput(false);
    };

    const handleAddSupplier = async (customer: Supplier, category?: string) => {
        const id = customer._id || customer.id;
        if (!id) return;
        setAddingIds(prev => [...prev, id]);
        try {
            await suppliersAPI.tagSupplier(id);
            if (category) await suppliersAPI.updateSupplier(id, { supplier_category: category });
            setCategoryTarget(null);
            setAllCustomers(prev => prev.filter(c => (c._id || c.id) !== id));
            setPotentialSuppliers(prev => prev.filter(c => (c._id || c.id) !== id));
            fetchData();
        } catch {
            Alert.alert('Error', 'Failed to add supplier');
        } finally {
            setAddingIds(prev => prev.filter(pid => pid !== id));
        }
    };

    const handleConfirmCategory = () => {
        if (!categoryTarget) return;
        const finalCategory = showCustomInput ? customCategory.trim() : selectedCategory;
        handleAddSupplier(categoryTarget, finalCategory || undefined);
    };

    const handleRemoveSupplier = (supplier: Supplier) => {
        const id = supplier._id || supplier.id || '';
        Alert.alert(
            'Remove Supplier',
            `Remove ${supplier.name} as a supplier? Their contact will remain.`,
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Remove', style: 'destructive',
                    onPress: async () => {
                        try {
                            await suppliersAPI.removeSupplier(id);
                            setSuppliers(prev => prev.filter(s => (s._id || s.id) !== id));
                            if (expandedId === id) setExpandedId(null);
                        } catch {
                            Alert.alert('Error', 'Failed to remove supplier');
                        }
                    }
                }
            ]
        );
    };

    const handleOpenExpand = (supplier: Supplier) => {
        const id = supplier._id || supplier.id || '';
        if (expandedId === id) { setExpandedId(null); return; }
        setExpandedId(id);
        const cat = supplier.supplier_category || '';
        const isPreset = PRESET_CATEGORIES.includes(cat);
        setEditCategory(isPreset ? cat : '');
        setEditCustomCategory(!isPreset && cat ? cat : '');
        setShowEditCustomInput(!isPreset && !!cat);
        setEditPaymentTerms(supplier.payment_terms || '');
        setEditLeadTime(supplier.lead_time || '');
        setEditRating(supplier.rating || 0);
    };

    const handleSaveDetails = async (supplier: Supplier) => {
        const id = supplier._id || supplier.id;
        if (!id) return;
        const finalCategory = showEditCustomInput ? editCustomCategory.trim() : editCategory;
        setSavingId(id);
        try {
            await suppliersAPI.updateSupplier(id, {
                ...(finalCategory ? { supplier_category: finalCategory } : {}),
                ...(editPaymentTerms.trim() ? { payment_terms: editPaymentTerms.trim() } : {}),
                ...(editLeadTime.trim() ? { lead_time: editLeadTime.trim() } : {}),
                ...(editRating ? { rating: editRating } : {}),
            });
            setSuppliers(prev => prev.map(s =>
                (s._id || s.id) === id
                    ? { ...s, supplier_category: finalCategory || s.supplier_category, payment_terms: editPaymentTerms.trim(), lead_time: editLeadTime.trim(), rating: editRating }
                    : s
            ));
            setExpandedId(null);
        } catch {
            Alert.alert('Error', 'Failed to save details');
        } finally {
            setSavingId(null);
        }
    };

    const handleChatSupplier = (supplier: Supplier) => {
        onClose();
        router.push({
            pathname: '/chat',
            params: {
                customerId: supplier._id || supplier.id || '',
                customerName: supplier.name,
                customerPhone: supplier.phone_number,
            },
        });
    };

    const startAddMode = () => {
        setViewMode('add');
        fetchAllCustomers();
    };

    const renderStars = (rating: number, onPress?: (r: number) => void) => (
        <View style={{ flexDirection: 'row', gap: 3 }}>
            {[1, 2, 3, 4, 5].map(star => (
                <TouchableOpacity key={star} onPress={() => onPress?.(star)} disabled={!onPress}>
                    <Ionicons
                        name={star <= rating ? 'star' : 'star-outline'}
                        size={18}
                        color={star <= rating ? '#FFB800' : '#3A4F6A'}
                    />
                </TouchableOpacity>
            ))}
        </View>
    );

    const renderSupplierCard = (supplier: Supplier) => {
        const sid = supplier._id || supplier.id || '';
        const isExpanded = expandedId === sid;
        const isSaving = savingId === sid;
        const cat = supplier.supplier_category;
        const displayCat = cat && cat !== 'Other' ? cat : null;

        return (
            <View key={sid} style={styles.card}>
                {/* Header row — tap to expand */}
                <TouchableOpacity
                    style={styles.cardHeader}
                    onPress={() => handleOpenExpand(supplier)}
                    activeOpacity={0.75}
                >
                    <View style={styles.cardIcon}>
                        <Ionicons name="business" size={22} color="#4A90D9" />
                    </View>
                    <View style={styles.cardContent}>
                        <Text style={styles.cardTitle}>{supplier.name}</Text>
                        <Text style={styles.cardSubtitle}>{supplier.phone_number}</Text>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
                            {displayCat ? (
                                <View style={styles.categoryBadge}>
                                    <Ionicons name="pricetag-outline" size={10} color="#4A90D9" />
                                    <Text style={styles.categoryBadgeText}>{displayCat}</Text>
                                </View>
                            ) : (
                                <Text style={styles.setCategoryHint}>Tap to set category</Text>
                            )}
                            {!!supplier.rating && renderStars(supplier.rating)}
                        </View>
                        {supplier.payment_terms ? (
                            <Text style={styles.detailHint}>💳 {supplier.payment_terms}</Text>
                        ) : null}
                        {supplier.lead_time ? (
                            <Text style={styles.detailHint}>⏱ {supplier.lead_time}</Text>
                        ) : null}
                    </View>
                    <View style={{ alignItems: 'center', gap: 6 }}>
                        <TouchableOpacity style={styles.cardAction} onPress={() => handleChatSupplier(supplier)}>
                            <Ionicons name="chatbubble-ellipses-outline" size={20} color="#25D366" />
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.cardAction} onPress={() => handleRemoveSupplier(supplier)}>
                            <Ionicons name="trash-outline" size={18} color="#FF6B6B" />
                        </TouchableOpacity>
                    </View>
                </TouchableOpacity>

                {/* Expanded edit panel */}
                {isExpanded && (
                    <View style={styles.expandPanel}>
                        {/* Category chips */}
                        <Text style={styles.expandLabel}>Category</Text>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
                            <View style={{ flexDirection: 'row', gap: 6 }}>
                                {PRESET_CATEGORIES.map(c => (
                                    <TouchableOpacity
                                        key={c}
                                        onPress={() => { setEditCategory(c); setShowEditCustomInput(false); }}
                                        style={[styles.categoryChip, editCategory === c && !showEditCustomInput && styles.categoryChipSelected]}
                                    >
                                        <Text style={[styles.categoryChipText, editCategory === c && !showEditCustomInput && styles.categoryChipTextSelected]}>{c}</Text>
                                    </TouchableOpacity>
                                ))}
                                <TouchableOpacity
                                    onPress={() => { setShowEditCustomInput(true); setEditCategory(''); }}
                                    style={[styles.categoryChip, showEditCustomInput && styles.categoryChipSelected]}
                                >
                                    <Text style={[styles.categoryChipText, showEditCustomInput && styles.categoryChipTextSelected]}>✏️ Custom</Text>
                                </TouchableOpacity>
                            </View>
                        </ScrollView>
                        {showEditCustomInput && (
                            <TextInput
                                style={styles.customInput}
                                placeholder="Type your category..."
                                placeholderTextColor="#556"
                                value={editCustomCategory}
                                onChangeText={setEditCustomCategory}
                                autoFocus
                            />
                        )}

                        {/* Payment terms */}
                        <Text style={styles.expandLabel}>Payment Terms</Text>
                        <TextInput
                            style={styles.customInput}
                            placeholder="e.g. Net 30, Cash on delivery..."
                            placeholderTextColor="#556"
                            value={editPaymentTerms}
                            onChangeText={setEditPaymentTerms}
                        />

                        {/* Lead time */}
                        <Text style={styles.expandLabel}>Lead Time</Text>
                        <TextInput
                            style={styles.customInput}
                            placeholder="e.g. 3-5 days, 2 weeks..."
                            placeholderTextColor="#556"
                            value={editLeadTime}
                            onChangeText={setEditLeadTime}
                        />

                        {/* Rating */}
                        <Text style={styles.expandLabel}>Rating</Text>
                        {renderStars(editRating, setEditRating)}

                        {/* Actions */}
                        <View style={{ flexDirection: 'row', gap: 10, marginTop: 14 }}>
                            <TouchableOpacity style={styles.cancelBtn} onPress={() => setExpandedId(null)}>
                                <Text style={styles.cancelBtnText}>Cancel</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={[styles.saveBtn, { flex: 1 }]}
                                onPress={() => handleSaveDetails(supplier)}
                                disabled={isSaving}
                            >
                                {isSaving
                                    ? <ActivityIndicator size="small" color="#0A1628" />
                                    : <Text style={styles.saveBtnText}>Save</Text>
                                }
                            </TouchableOpacity>
                        </View>
                    </View>
                )}
            </View>
        );
    };

    const renderRestockCard = (item: RestockSuggestion, index: number) => (
        <View key={index} style={[styles.suggestionCard, item.priority === 'High' ? styles.borderRed : styles.borderOrange]}>
            <View style={styles.suggestionHeader}>
                <Ionicons name="alert-circle" size={20} color={item.priority === 'High' ? '#FF6B6B' : '#FF9F43'} />
                <Text style={[styles.suggestionTitle, { color: item.priority === 'High' ? '#FF6B6B' : '#FF9F43' }]}>
                    {item.priority} Priority
                </Text>
            </View>
            <Text style={styles.suggestionText}>
                <Text style={{ fontWeight: 'bold' }}>{item.product_name}</Text> is low ({item.current_stock} left).
            </Text>
            <Text style={styles.suggestionAction}>{item.suggested_action}</Text>
        </View>
    );

    const renderPotentialSupplier = (customer: Supplier) => (
        <View key={customer._id || customer.id} style={styles.potentialCard}>
            <View>
                <Text style={styles.potentialName}>{customer.name}</Text>
                <Text style={styles.potentialReason}>AI detected supplier signals in chat</Text>
            </View>
            <TouchableOpacity
                style={styles.addButton}
                onPress={() => openCategoryPicker(customer)}
                disabled={addingIds.includes(customer._id || customer.id || '')}
            >
                {addingIds.includes(customer._id || customer.id || '') ? (
                    <ActivityIndicator color="#FFF" size="small" />
                ) : (
                    <Text style={styles.addButtonText}>Add</Text>
                )}
            </TouchableOpacity>
        </View>
    );

    const filteredCustomers = allCustomers.filter(c =>
        c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.phone_number.includes(searchQuery)
    );

    // ── Category picker modal (shown when adding a supplier) ──
    const renderCategoryPicker = () => (
        <Modal visible={!!categoryTarget} animationType="slide" transparent onRequestClose={() => setCategoryTarget(null)}>
            <View style={styles.pickerOverlay}>
                <View style={styles.pickerSheet}>
                    <Text style={styles.pickerTitle}>Choose a Category</Text>
                    <Text style={styles.pickerSubtitle}>for {categoryTarget?.name}</Text>
                    <ScrollView style={{ maxHeight: 280 }} showsVerticalScrollIndicator={false}>
                        <View style={styles.chipGrid}>
                            {PRESET_CATEGORIES.map(cat => (
                                <TouchableOpacity
                                    key={cat}
                                    onPress={() => { setSelectedCategory(cat); setShowCustomInput(false); }}
                                    style={[styles.categoryChip, selectedCategory === cat && !showCustomInput && styles.categoryChipSelected]}
                                >
                                    <Text style={[styles.categoryChipText, selectedCategory === cat && !showCustomInput && styles.categoryChipTextSelected]}>{cat}</Text>
                                </TouchableOpacity>
                            ))}
                            <TouchableOpacity
                                onPress={() => { setShowCustomInput(true); setSelectedCategory(''); }}
                                style={[styles.categoryChip, showCustomInput && styles.categoryChipSelected]}
                            >
                                <Text style={[styles.categoryChipText, showCustomInput && styles.categoryChipTextSelected]}>✏️ Custom</Text>
                            </TouchableOpacity>
                        </View>
                    </ScrollView>
                    {showCustomInput && (
                        <TextInput
                            style={styles.customInput}
                            placeholder="e.g. Spare Parts, Fabrics, Chemicals..."
                            placeholderTextColor="#556"
                            value={customCategory}
                            onChangeText={setCustomCategory}
                            autoFocus
                        />
                    )}
                    <View style={styles.pickerActions}>
                        <TouchableOpacity style={styles.cancelBtn} onPress={() => setCategoryTarget(null)}>
                            <Text style={styles.cancelBtnText}>Skip</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={[styles.saveBtn, { flex: 1 }]}
                            onPress={handleConfirmCategory}
                        >
                            <Text style={styles.saveBtnText}>Add Supplier</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </View>
        </Modal>
    );

    return (
        <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
            <SafeAreaView style={styles.container}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => viewMode === 'add' ? setViewMode('list') : onClose()}>
                        <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>
                        {viewMode === 'add' ? 'Add Supplier' : 'Smart Sourcing'}
                    </Text>
                    {viewMode === 'list' && (
                        <TouchableOpacity onPress={startAddMode}>
                            <Ionicons name="add-circle" size={28} color="#25D366" />
                        </TouchableOpacity>
                    )}
                </View>

                {loading && viewMode === 'list' ? (
                    <View style={styles.loadingContainer}>
                        <ActivityIndicator size="large" color="#25D366" />
                    </View>
                ) : viewMode === 'list' ? (
                    <ScrollView style={styles.content}>
                        {/* Restock Suggestions */}
                        {restockSuggestions.length > 0 && (
                            <View style={styles.section}>
                                <Text style={styles.sectionTitle}>Restock Alerts</Text>
                                {restockSuggestions.map(renderRestockCard)}
                            </View>
                        )}

                        {/* Potential Suppliers */}
                        {potentialSuppliers.length > 0 && (
                            <View style={styles.section}>
                                <Text style={styles.sectionTitle}>Potential Suppliers Found</Text>
                                {potentialSuppliers.map(renderPotentialSupplier)}
                            </View>
                        )}

                        {/* Supplier List */}
                        <View style={styles.section}>
                            <Text style={styles.sectionTitle}>My Suppliers ({suppliers.length})</Text>
                            {suppliers.length === 0 ? (
                                <View style={styles.emptyState}>
                                    <Text style={styles.emptyText}>No suppliers yet.</Text>
                                    <Text style={styles.emptySubtext}>Add suppliers from your contacts to track orders.</Text>
                                </View>
                            ) : (
                                suppliers.map(renderSupplierCard)
                            )}
                        </View>
                    </ScrollView>
                ) : (
                    <View style={styles.addModeContainer}>
                        <View style={styles.searchBar}>
                            <Ionicons name="search" size={20} color="#8899AA" />
                            <TextInput
                                style={styles.searchInput}
                                placeholder="Search contacts..."
                                placeholderTextColor="#666"
                                value={searchQuery}
                                onChangeText={setSearchQuery}
                            />
                        </View>
                        <FlatList
                            data={filteredCustomers}
                            keyExtractor={(item) => item._id || item.id || Math.random().toString()}
                            renderItem={({ item }) => (
                                <View style={styles.contactRow}>
                                    <View>
                                        <Text style={styles.contactName}>{item.name}</Text>
                                        <Text style={styles.contactPhone}>{item.phone_number}</Text>
                                    </View>
                                    <TouchableOpacity
                                        style={styles.addButtonSmall}
                                        onPress={() => openCategoryPicker(item)}
                                        disabled={addingIds.includes(item._id || item.id || '')}
                                    >
                                        {addingIds.includes(item._id || item.id || '') ? (
                                            <ActivityIndicator size="small" color="#25D366" />
                                        ) : (
                                            <Text style={styles.addButtonText}>Add</Text>
                                        )}
                                    </TouchableOpacity>
                                </View>
                            )}
                            ListEmptyComponent={
                                <Text style={styles.emptyListText}>No contacts found</Text>
                            }
                        />
                    </View>
                )}
            </SafeAreaView>
            {renderCategoryPicker()}
        </Modal>
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
        justifyContent: 'space-between',
        paddingHorizontal: 20,
        paddingVertical: 14,
        borderBottomWidth: 1,
        borderBottomColor: '#1A2942',
    },
    headerTitle: {
        fontSize: 20,
        fontWeight: '700',
        color: '#FFFFFF',
    },
    loadingContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    content: {
        flex: 1,
        padding: 20,
    },
    section: {
        marginBottom: 24,
    },
    sectionTitle: {
        fontSize: 16,
        fontWeight: '600',
        color: '#8899AA',
        marginBottom: 12,
        textTransform: 'uppercase',
        letterSpacing: 1,
    },
    // Cards
    card: {
        flexDirection: 'column',
        backgroundColor: '#1A2942',
        borderRadius: 12,
        marginBottom: 10,
        overflow: 'hidden',
    },
    cardHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 14,
    },
    expandPanel: {
        paddingHorizontal: 16,
        paddingBottom: 16,
        borderTopWidth: 1,
        borderTopColor: '#243550',
    },
    expandLabel: {
        fontSize: 11,
        fontWeight: '700',
        color: '#8899AA',
        textTransform: 'uppercase',
        letterSpacing: 0.8,
        marginTop: 12,
        marginBottom: 6,
    },
    setCategoryHint: {
        fontSize: 12,
        color: '#4A90D9',
        fontStyle: 'italic',
    },
    detailHint: {
        fontSize: 12,
        color: '#8899AA',
        marginTop: 2,
    },
    cardIcon: {
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: 'rgba(74, 144, 217, 0.1)',
        justifyContent: 'center',
        alignItems: 'center',
        marginRight: 12,
    },
    cardContent: {
        flex: 1,
    },
    cardTitle: {
        fontSize: 16,
        fontWeight: '600',
        color: '#FFFFFF',
        marginBottom: 2,
    },
    cardSubtitle: {
        fontSize: 14,
        color: '#8899AA',
    },
    cardAction: {
        padding: 8,
    },
    // Restock
    suggestionCard: {
        backgroundColor: '#1A2942',
        borderRadius: 12,
        padding: 16,
        marginBottom: 10,
        borderLeftWidth: 4,
    },
    borderRed: { borderLeftColor: '#FF6B6B' },
    borderOrange: { borderLeftColor: '#FF9F43' },
    suggestionHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 8,
        gap: 6,
    },
    suggestionTitle: {
        fontWeight: 'bold',
        fontSize: 14,
    },
    suggestionText: {
        color: '#FFFFFF',
        fontSize: 15,
        marginBottom: 8,
    },
    suggestionAction: {
        color: '#4A90D9',
        fontWeight: '600',
    },
    // Potential
    potentialCard: {
        backgroundColor: 'rgba(37, 211, 102, 0.1)',
        borderRadius: 12,
        padding: 16,
        marginBottom: 10,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: 'rgba(37, 211, 102, 0.3)',
    },
    potentialName: {
        color: '#FFFFFF',
        fontWeight: 'bold',
        fontSize: 16,
        marginBottom: 4,
    },
    potentialReason: {
        color: '#25D366',
        fontSize: 12,
    },
    addButton: {
        backgroundColor: '#25D366',
        paddingHorizontal: 16,
        paddingVertical: 8,
        borderRadius: 20,
    },
    addButtonText: {
        color: '#0A1628',
        fontWeight: 'bold',
        fontSize: 14,
    },
    // Empty
    emptyState: {
        alignItems: 'center',
        paddingVertical: 20,
        opacity: 0.7,
    },
    emptyText: {
        color: '#FFF',
        fontSize: 16,
        fontWeight: '600',
        marginBottom: 4,
    },
    emptySubtext: {
        color: '#8899AA',
        textAlign: 'center',
    },
    // Add Mode
    addModeContainer: {
        flex: 1,
        padding: 20,
    },
    searchBar: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#1A2942',
        borderRadius: 12,
        paddingHorizontal: 12,
        paddingVertical: 10,
        marginBottom: 16,
    },
    searchInput: {
        flex: 1,
        color: '#FFF',
        marginLeft: 8,
        fontSize: 16,
    },
    contactRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: 14,
        borderBottomWidth: 1,
        borderBottomColor: '#1A2942',
    },
    contactName: {
        color: '#FFF',
        fontSize: 16,
        fontWeight: '500',
    },
    contactPhone: {
        color: '#8899AA',
        fontSize: 14,
    },
    addButtonSmall: {
        backgroundColor: '#1A2942',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: '#25D366',
    },
    emptyListText: {
        color: '#666',
        textAlign: 'center',
        marginTop: 20,
    },
    categoryBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        marginTop: 4,
    },
    categoryBadgeText: {
        fontSize: 12,
        color: '#4A90D9',
        fontWeight: '500',
    },
    chipGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
        paddingVertical: 4,
    },
    categoryChip: {
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 16,
        backgroundColor: '#1A2942',
        borderWidth: 1,
        borderColor: '#2A3F5F',
    },
    categoryChipSelected: {
        backgroundColor: '#4A90D9',
        borderColor: '#4A90D9',
    },
    categoryChipText: {
        fontSize: 13,
        color: '#8899AA',
        fontWeight: '500',
    },
    categoryChipTextSelected: {
        color: '#FFFFFF',
    },
    customInput: {
        backgroundColor: '#1A2942',
        borderRadius: 10,
        paddingHorizontal: 14,
        paddingVertical: 10,
        color: '#FFF',
        fontSize: 15,
        marginTop: 10,
        borderWidth: 1,
        borderColor: '#4A90D9',
    },
    pickerOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.6)',
        justifyContent: 'flex-end',
    },
    pickerSheet: {
        backgroundColor: '#0D1F35',
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        padding: 24,
        paddingBottom: 36,
    },
    pickerTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#FFF',
        marginBottom: 2,
    },
    pickerSubtitle: {
        fontSize: 13,
        color: '#8899AA',
        marginBottom: 16,
    },
    pickerActions: {
        flexDirection: 'row',
        gap: 10,
        marginTop: 16,
    },
    saveBtn: {
        backgroundColor: '#25D366',
        paddingVertical: 10,
        paddingHorizontal: 16,
        borderRadius: 10,
        alignItems: 'center',
    },
    saveBtnText: {
        color: '#0A1628',
        fontWeight: '700',
        fontSize: 14,
    },
    cancelBtn: {
        backgroundColor: '#1A2942',
        paddingVertical: 10,
        paddingHorizontal: 16,
        borderRadius: 10,
        alignItems: 'center',
    },
    cancelBtnText: {
        color: '#8899AA',
        fontWeight: '600',
        fontSize: 14,
    },
});
