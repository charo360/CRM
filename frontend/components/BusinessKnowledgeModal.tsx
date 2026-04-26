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
            }
        } catch (error) {
            console.error('Error fetching business knowledge:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await settingsAPI.updateBusinessKnowledge(knowledge);
            Alert.alert('Success', 'Business knowledge updated!', [
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
                        <Ionicons name="arrow-back" size={24} color="#333" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Business Knowledge</Text>
                    <TouchableOpacity
                        onPress={handleSave}
                        disabled={saving}
                        style={styles.saveButton}
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
                    <ScrollView style={styles.content}>
                        <Text style={styles.description}>
                            Help the AI understand your business better. This information will be
                            used to generate smarter, more accurate responses to customers.
                        </Text>

                        <View style={styles.field}>
                            <Text style={styles.label}>Business Description</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="What makes your business unique?"
                                value={knowledge.business_description}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, business_description: text })
                                }
                                multiline
                                numberOfLines={3}
                            />
                        </View>

                        <View style={styles.field}>
                            <Text style={styles.label}>Products & Services</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="What do you sell or offer?"
                                value={knowledge.products_services}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, products_services: text })
                                }
                                multiline
                                numberOfLines={3}
                            />
                        </View>

                        <View style={styles.field}>
                            <Text style={styles.label}>Pricing Information</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="Price ranges, payment methods accepted"
                                value={knowledge.pricing_info}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, pricing_info: text })
                                }
                                multiline
                                numberOfLines={2}
                            />
                        </View>

                        <View style={styles.field}>
                            <Text style={styles.label}>Business Hours</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="When are you available?"
                                value={knowledge.business_hours}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, business_hours: text })
                                }
                            />
                        </View>

                        <View style={styles.field}>
                            <Text style={styles.label}>Delivery Information</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="Areas served, costs, timing"
                                value={knowledge.delivery_info}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, delivery_info: text })
                                }
                                multiline
                                numberOfLines={2}
                            />
                        </View>

                        <View style={styles.field}>
                            <Text style={styles.label}>FAQs</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="Common questions and answers"
                                value={knowledge.faqs}
                                onChangeText={(text) => setKnowledge({ ...knowledge, faqs: text })}
                                multiline
                                numberOfLines={4}
                            />
                        </View>

                        <View style={styles.field}>
                            <Text style={styles.label}>Special Offers</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="Current promotions or deals"
                                value={knowledge.special_offers}
                                onChangeText={(text) =>
                                    setKnowledge({ ...knowledge, special_offers: text })
                                }
                                multiline
                                numberOfLines={2}
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
        backgroundColor: '#F5F5F5',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 16,
        paddingVertical: 12,
        backgroundColor: '#FFFFFF',
        borderBottomWidth: 1,
        borderBottomColor: '#E0E0E0',
    },
    backButton: {
        padding: 4,
    },
    headerTitle: {
        fontSize: 18,
        fontWeight: '600',
        color: '#333',
    },
    saveButton: {
        paddingHorizontal: 12,
        paddingVertical: 6,
    },
    saveButtonText: {
        fontSize: 16,
        fontWeight: '600',
        color: '#25D366',
    },
    loader: {
        marginTop: 40,
    },
    content: {
        flex: 1,
        padding: 16,
    },
    description: {
        fontSize: 14,
        color: '#666',
        marginBottom: 20,
        lineHeight: 20,
    },
    field: {
        marginBottom: 20,
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        color: '#333',
        marginBottom: 8,
    },
    input: {
        backgroundColor: '#FFFFFF',
        borderWidth: 1,
        borderColor: '#E0E0E0',
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 10,
        fontSize: 14,
        color: '#333',
        textAlignVertical: 'top',
    },
    bottomPadding: {
        height: 40,
    },
});
