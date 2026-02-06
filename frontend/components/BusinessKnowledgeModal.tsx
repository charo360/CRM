import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    Modal,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    TextInput,
    Alert,
    ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { settingsAPI } from '../context/api';

interface BusinessKnowledgeModalProps {
    visible: boolean;
    onClose: () => void;
}

// Helper: convert newline-separated string to array of items
const stringToItems = (str: string): string[] => {
    if (!str) return [];
    return str.split('\n').filter((s) => s.trim() !== '');
};

// Helper: convert array of items to newline-separated string
const itemsToString = (items: string[]): string => {
    return items.filter((s) => s.trim() !== '').join('\n');
};

// Reusable list field with + button
function ListField({
    items,
    onUpdate,
    placeholder,
    icon,
}: {
    items: string[];
    onUpdate: (items: string[]) => void;
    placeholder: string;
    icon: string;
}) {
    const addItem = () => {
        onUpdate([...items, '']);
    };

    const updateItem = (index: number, text: string) => {
        const updated = [...items];
        updated[index] = text;
        onUpdate(updated);
    };

    const removeItem = (index: number) => {
        const updated = items.filter((_, i) => i !== index);
        onUpdate(updated);
    };

    return (
        <View>
            {items.map((item, index) => (
                <View key={index} style={styles.listItemRow}>
                    <Ionicons name={icon as any} size={16} color="#4A90D9" style={{ marginTop: 12 }} />
                    <TextInput
                        style={styles.listItemInput}
                        placeholder={placeholder}
                        placeholderTextColor="#555"
                        value={item}
                        onChangeText={(text) => updateItem(index, text)}
                        multiline
                    />
                    <TouchableOpacity onPress={() => removeItem(index)} style={styles.removeButton}>
                        <Ionicons name="close-circle" size={20} color="#FF6B6B" />
                    </TouchableOpacity>
                </View>
            ))}
            <TouchableOpacity style={styles.addButton} onPress={addItem}>
                <Ionicons name="add-circle" size={20} color="#25D366" />
                <Text style={styles.addButtonText}>Add {placeholder.toLowerCase()}</Text>
            </TouchableOpacity>
        </View>
    );
}

// FAQ list with Q & A pairs
function FAQField({
    faqs,
    onAdd,
    onUpdate,
    onRemove,
}: {
    faqs: { question: string; answer: string }[];
    onAdd: () => void;
    onUpdate: (index: number, field: 'question' | 'answer', text: string) => void;
    onRemove: (index: number) => void;
}) {
    return (
        <View>
            {faqs.map((faq, index) => (
                <View key={`faq-${index}`} style={styles.faqCard}>
                    <View style={styles.faqHeader}>
                        <Text style={styles.faqNumber}>#{index + 1}</Text>
                        <TouchableOpacity onPress={() => onRemove(index)} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                            <Ionicons name="close-circle" size={22} color="#FF6B6B" />
                        </TouchableOpacity>
                    </View>
                    <View style={styles.faqRow}>
                        <Text style={styles.faqLabel}>Q</Text>
                        <TextInput
                            style={styles.faqInput}
                            placeholder="Customer's question"
                            placeholderTextColor="#555"
                            value={faq.question}
                            onChangeText={(text) => onUpdate(index, 'question', text)}
                            multiline
                        />
                    </View>
                    <View style={styles.faqRow}>
                        <Text style={[styles.faqLabel, { color: '#25D366' }]}>A</Text>
                        <TextInput
                            style={styles.faqInput}
                            placeholder="Your answer"
                            placeholderTextColor="#555"
                            value={faq.answer}
                            onChangeText={(text) => onUpdate(index, 'answer', text)}
                            multiline
                        />
                    </View>
                </View>
            ))}
            <TouchableOpacity style={styles.addButton} onPress={onAdd}>
                <Ionicons name="add-circle" size={20} color="#25D366" />
                <Text style={styles.addButtonText}>Add question & answer</Text>
            </TouchableOpacity>
        </View>
    );
}

export default function BusinessKnowledgeModal({
    visible,
    onClose,
}: BusinessKnowledgeModalProps) {
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [knowledge, setKnowledge] = useState({
        business_description: '',
        products_services: '',
        pricing_info: '',
        business_hours: '',
        delivery_info: '',
        faqs: '',
        special_offers: '',
    });

    // List states (derived from string fields)
    const [productItems, setProductItems] = useState<string[]>([]);
    const [deliveryItems, setDeliveryItems] = useState<string[]>([]);
    const [faqList, setFaqList] = useState<{ question: string; answer: string }[]>([]);
    const [offerItems, setOfferItems] = useState<string[]>([]);

    useEffect(() => {
        if (visible) {
            fetchKnowledge();
        }
    }, [visible]);

    const fetchKnowledge = async () => {
        setLoading(true);
        try {
            const data = await settingsAPI.getBusinessKnowledge();
            if (data) {
                setKnowledge(data);
                setProductItems(stringToItems(data.products_services));
                setDeliveryItems(stringToItems(data.delivery_info));
                // Parse FAQ strings into Q&A objects
                const faqLines = stringToItems(data.faqs);
                const parsed: { question: string; answer: string }[] = [];
                for (let i = 0; i < faqLines.length; i++) {
                    const line = faqLines[i];
                    if (line.startsWith('Q: ') || line.startsWith('q: ')) {
                        const q = line.replace(/^[Qq]: /, '');
                        let a = '';
                        if (i + 1 < faqLines.length && (faqLines[i + 1].startsWith('A: ') || faqLines[i + 1].startsWith('a: '))) {
                            a = faqLines[i + 1].replace(/^[Aa]: /, '');
                            i++;
                        }
                        parsed.push({ question: q, answer: a });
                    } else if (line.trim()) {
                        parsed.push({ question: line, answer: '' });
                    }
                }
                setFaqList(parsed);
                setOfferItems(stringToItems(data.special_offers));
            }
        } catch (error) {
            console.error('Error fetching business knowledge:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        // Sync list states back to knowledge strings
        const updatedKnowledge = {
            ...knowledge,
            products_services: itemsToString(productItems),
            delivery_info: itemsToString(deliveryItems),
            faqs: faqList.map(f => `Q: ${f.question}\nA: ${f.answer}`).join('\n'),
            special_offers: itemsToString(offerItems),
        };
        try {
            await settingsAPI.updateBusinessKnowledge(updatedKnowledge);
            Alert.alert('Saved', 'Business knowledge updated!', [
                { text: 'OK', onPress: onClose },
            ]);
        } catch (error) {
            console.error('Error saving business knowledge:', error);
            Alert.alert('Error', 'Failed to save business knowledge');
        } finally {
            setSaving(false);
        }
    };

    return (
        <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
            <SafeAreaView style={styles.container}>
                {/* Header */}
                <View style={styles.header}>
                    <TouchableOpacity onPress={onClose} style={styles.backButton}>
                        <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Business Knowledge</Text>
                    <TouchableOpacity
                        onPress={handleSave}
                        disabled={saving}
                        style={[styles.saveButton, saving && { opacity: 0.6 }]}
                    >
                        <Text style={styles.saveButtonText}>
                            {saving ? 'Saving...' : 'Save'}
                        </Text>
                    </TouchableOpacity>
                </View>

                {/* Content */}
                {loading ? (
                    <ActivityIndicator size="large" color="#25D366" style={styles.loader} />
                ) : (
                    <ScrollView style={styles.content} keyboardShouldPersistTaps="handled">
                        <View style={styles.tipCard}>
                            <Ionicons name="bulb-outline" size={20} color="#FFD700" />
                            <Text style={styles.tipText}>
                                The AI uses this to answer customers accurately. It also learns from your past conversations!
                            </Text>
                        </View>

                        {/* About */}
                        <View style={styles.field}>
                            <Text style={styles.label}>About Your Business</Text>
                            <Text style={styles.hint}>e.g. "We sell fresh cakes and pastries. We specialize in custom birthday cakes."</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="What does your business do?"
                                placeholderTextColor="#555"
                                value={knowledge.business_description}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, business_description: text })
                                }
                                multiline
                                numberOfLines={3}
                            />
                        </View>

                        {/* Products & Prices - List */}
                        <View style={styles.field}>
                            <View style={styles.sectionHeader}>
                                <Ionicons name="pricetag-outline" size={18} color="#25D366" />
                                <Text style={styles.label}>Products & Prices</Text>
                            </View>
                            <Text style={styles.hint}>Add each product with its price</Text>
                            <ListField
                                items={productItems}
                                onUpdate={setProductItems}
                                placeholder="Product - price"
                                icon="cart-outline"
                            />
                        </View>

                        {/* Payment Methods */}
                        <View style={styles.field}>
                            <Text style={styles.label}>Payment Methods</Text>
                            <Text style={styles.hint}>e.g. "Mobile money, Cash on delivery, Bank transfer"</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="How can customers pay?"
                                placeholderTextColor="#555"
                                value={knowledge.pricing_info}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, pricing_info: text })
                                }
                                multiline
                                numberOfLines={2}
                            />
                        </View>

                        {/* Business Hours */}
                        <View style={styles.field}>
                            <Text style={styles.label}>Business Hours</Text>
                            <Text style={styles.hint}>e.g. "Mon-Sat 8am-6pm, Sunday closed"</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="When are you open?"
                                placeholderTextColor="#555"
                                value={knowledge.business_hours}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, business_hours: text })
                                }
                            />
                        </View>

                        {/* Delivery - List */}
                        <View style={styles.field}>
                            <View style={styles.sectionHeader}>
                                <Ionicons name="bicycle-outline" size={18} color="#25D366" />
                                <Text style={styles.label}>Delivery Zones</Text>
                            </View>
                            <Text style={styles.hint}>Add each delivery area with cost</Text>
                            <ListField
                                items={deliveryItems}
                                onUpdate={setDeliveryItems}
                                placeholder="Area - delivery cost"
                                icon="location-outline"
                            />
                        </View>

                        {/* FAQs - Q&A pairs */}
                        <View style={styles.field}>
                            <View style={styles.sectionHeader}>
                                <Ionicons name="chatbubble-ellipses-outline" size={18} color="#25D366" />
                                <Text style={styles.label}>Common Questions</Text>
                            </View>
                            <Text style={styles.hint}>Add questions customers always ask and your answers</Text>
                            <FAQField
                                faqs={faqList}
                                onAdd={() => setFaqList([...faqList, { question: '', answer: '' }])}
                                onUpdate={(index, field, text) => {
                                    const updated = [...faqList];
                                    updated[index] = { ...updated[index], [field]: text };
                                    setFaqList(updated);
                                }}
                                onRemove={(index) => {
                                    setFaqList(faqList.filter((_, i) => i !== index));
                                }}
                            />
                        </View>

                        {/* Offers - List */}
                        <View style={styles.field}>
                            <View style={styles.sectionHeader}>
                                <Ionicons name="gift-outline" size={18} color="#25D366" />
                                <Text style={styles.label}>Current Offers</Text>
                            </View>
                            <Text style={styles.hint}>Add active promotions or deals</Text>
                            <ListField
                                items={offerItems}
                                onUpdate={setOfferItems}
                                placeholder="Offer or promotion"
                                icon="flash-outline"
                            />
                        </View>

                        <View style={styles.bottomPadding} />
                    </ScrollView>
                )}
            </SafeAreaView>
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
        paddingHorizontal: 16,
        paddingVertical: 12,
        backgroundColor: '#0A1628',
        borderBottomWidth: 1,
        borderBottomColor: '#1A2942',
    },
    backButton: {
        padding: 4,
    },
    headerTitle: {
        fontSize: 18,
        fontWeight: '600',
        color: '#FFFFFF',
    },
    saveButton: {
        paddingHorizontal: 16,
        paddingVertical: 8,
        backgroundColor: '#25D366',
        borderRadius: 8,
    },
    saveButtonText: {
        fontSize: 14,
        fontWeight: '600',
        color: '#FFFFFF',
    },
    loader: {
        marginTop: 40,
    },
    content: {
        flex: 1,
        padding: 16,
    },
    tipCard: {
        flexDirection: 'row',
        backgroundColor: '#1A2942',
        borderRadius: 12,
        padding: 14,
        marginBottom: 20,
        gap: 10,
        alignItems: 'flex-start',
        borderLeftWidth: 3,
        borderLeftColor: '#FFD700',
    },
    tipText: {
        flex: 1,
        fontSize: 13,
        color: '#8B9DC3',
        lineHeight: 19,
    },
    field: {
        marginBottom: 24,
    },
    sectionHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        marginBottom: 4,
    },
    label: {
        fontSize: 15,
        fontWeight: '600',
        color: '#FFFFFF',
    },
    hint: {
        fontSize: 12,
        color: '#6B7D99',
        marginBottom: 10,
        lineHeight: 17,
        fontStyle: 'italic',
    },
    input: {
        backgroundColor: '#1A2942',
        borderWidth: 1,
        borderColor: '#2A3952',
        borderRadius: 10,
        paddingHorizontal: 14,
        paddingVertical: 12,
        fontSize: 14,
        color: '#FFFFFF',
        textAlignVertical: 'top',
    },
    // List items
    listItemRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: 8,
        marginBottom: 8,
    },
    listItemInput: {
        flex: 1,
        backgroundColor: '#1A2942',
        borderWidth: 1,
        borderColor: '#2A3952',
        borderRadius: 10,
        paddingHorizontal: 14,
        paddingVertical: 10,
        fontSize: 14,
        color: '#FFFFFF',
        textAlignVertical: 'top',
    },
    removeButton: {
        marginTop: 10,
        padding: 2,
    },
    addButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        paddingVertical: 10,
        paddingHorizontal: 4,
    },
    addButtonText: {
        fontSize: 14,
        color: '#25D366',
        fontWeight: '500',
    },
    // FAQ cards
    faqCard: {
        backgroundColor: '#1A2942',
        borderRadius: 10,
        padding: 12,
        marginBottom: 10,
        borderWidth: 1,
        borderColor: '#2A3952',
    },
    faqHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 8,
    },
    faqNumber: {
        fontSize: 12,
        color: '#6B7D99',
        fontWeight: '600',
    },
    faqRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: 8,
        marginBottom: 6,
    },
    faqLabel: {
        fontSize: 14,
        fontWeight: '700',
        color: '#4A90D9',
        marginTop: 10,
        width: 18,
    },
    faqInput: {
        flex: 1,
        backgroundColor: '#0F1D32',
        borderWidth: 1,
        borderColor: '#2A3952',
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 8,
        fontSize: 14,
        color: '#FFFFFF',
        textAlignVertical: 'top',
    },
    bottomPadding: {
        height: 40,
    },
});
