import React, { useState, useEffect, useCallback } from 'react';
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

    // Edit category state (for existing suppliers)
    const [editingCategoryId, setEditingCategoryId] = useState<string | null>(null);
    const [editCategory, setEditCategory] = useState('');
    const [editCustomCategory, setEditCustomCategory] = useState('');
    const [showEditCustomInput, setShowEditCustomInput] = useState(false);

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
            if (category) {
                await suppliersAPI.updateSupplier(id, { supplier_category: category });
            }
            setCategoryTarget(null);
            setAllCustomers(prev => prev.filter(c => (c._id || c.id) !== id));
            fetchData();
        } catch (error) {
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

    const handleSaveEditCategory = async (supplier: Supplier) => {
        const id = supplier._id || supplier.id;
        if (!id) return;
        const finalCategory = showEditCustomInput ? editCustomCategory.trim() : editCategory;
        if (!finalCategory) return;
        try {
            await suppliersAPI.updateSupplier(id, { supplier_category: finalCategory });
            setSuppliers(prev => prev.map(s =>
                (s._id || s.id) === id ? { ...s, supplier_category: finalCategory } : s
            ));
        } catch {
            Alert.alert('Error', 'Failed to update category');
        } finally {
            setEditingCategoryId(null);
        }
    };

    const startAddMode = () => {
        setViewMode('add');
        fetchAllCustomers();
    };

    const renderSupplierCard = (supplier: Supplier) => {
        const sid = supplier._id || supplier.id || '';
        const isEditing = editingCategoryId === sid;
        return (
            <View key={sid} style={styles.card}>
                <View style={styles.cardIcon}>
                    <Ionicons name="business" size={24} color="#4A90D9" />
                </View>
                <View style={styles.cardContent}>
                    <Text style={styles.cardTitle}>{supplier.name}</Text>
                    <Text style={styles.cardSubtitle}>{supplier.phone_number}</Text>
                    {isEditing ? (
                        <View style={{ marginTop: 8 }}>
                            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
                                <View style={{ flexDirection: 'row', gap: 6 }}>
                                    {PRESET_CATEGORIES.map(cat => (
                                        <TouchableOpacity
                                            key={cat}
                                            onPress={() => { setEditCategory(cat); setShowEditCustomInput(false); }}
                                            style={[styles.categoryChip, editCategory === cat && !showEditCustomInput && styles.categoryChipSelected]}
                                        >
                                            <Text style={[styles.categoryChipText, editCategory === cat && !showEditCustomInput && styles.categoryChipTextSelected]}>{cat}</Text>
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
                            <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
                                <TouchableOpacity style={styles.saveBtn} onPress={() => handleSaveEditCategory(supplier)}>
                                    <Text style={styles.saveBtnText}>Save</Text>
                                </TouchableOpacity>
                                <TouchableOpacity style={styles.cancelBtn} onPress={() => setEditingCategoryId(null)}>
                                    <Text style={styles.cancelBtnText}>Cancel</Text>
                                </TouchableOpacity>
                            </View>
                        </View>
                    ) : (
                        <TouchableOpacity
                            onPress={() => {
                                setEditingCategoryId(sid);
                                setEditCategory(supplier.supplier_category || '');
                                setEditCustomCategory('');
                                setShowEditCustomInput(false);
                            }}
                            style={styles.categoryBadge}
                        >
                            <Ionicons name="pricetag-outline" size={11} color="#4A90D9" />
                            <Text style={styles.categoryBadgeText}>
                                {supplier.supplier_category && supplier.supplier_category !== 'Other' ? supplier.supplier_category : 'Set category'}
                            </Text>
                            <Ionicons name="pencil" size={10} color="#4A90D9" />
                        </TouchableOpacity>
                    )}
                </View>
                <TouchableOpacity style={styles.cardAction}>
                    <Ionicons name="chatbubble-ellipses-outline" size={20} color="#666" />
                </TouchableOpacity>
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
                onPress={() => handleAddSupplier(customer)}
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
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#1A2942',
        borderRadius: 12,
        padding: 16,
        marginBottom: 10,
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
