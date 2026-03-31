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
import { settingsAPI, apiClient } from '../context/api';
import { useBusiness } from '../context/BusinessContext';

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

const GLOBAL_TO_BK_TYPE: Record<string, string> = {
    retail: 'retail', restaurant: 'restaurant', creator: 'creator',
    salon: 'salon', services: 'services', fitness: 'fitness', healthcare: 'healthcare',
    rental: 'rental', tech: 'tech',
    '': 'general',
};

const BK_TYPE_LABELS: Record<string, string> = {
    general: 'General', retail: 'Retail', creator: 'Creator',
    restaurant: 'Restaurant', salon: 'Salon / Beauty', services: 'Services',
    fitness: 'Fitness / Gym', healthcare: 'Healthcare / Clinic', rental: 'Rental / Airbnb',
    tech: 'Tech / SaaS / Fintech',
};

const PLATFORMS = ['Instagram', 'TikTok', 'YouTube', 'Twitter/X', 'Facebook', 'Snapchat', 'LinkedIn', 'Podcast'];

export default function BusinessKnowledgeModal({
    visible,
    onClose,
}: BusinessKnowledgeModalProps) {
    const { businessType: globalBT, isServiceBusiness, config } = useBusiness();
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [businessType, setBusinessType] = useState(() => GLOBAL_TO_BK_TYPE[globalBT] || 'general');
    const [knowledge, setKnowledge] = useState({
        business_description: '',
        products_services: '',
        pricing_info: '',
        business_hours: '',
        delivery_info: '',
        faqs: '',
        special_offers: '',
        booking_process: '',
        cancellation_policy: '',
        staff_info: '',
    });
    const [creator, setCreator] = useState({
        creator_niche: '',
        creator_platforms: '',
        creator_audience_size: '',
        creator_collab_types: '',
        creator_rate_card: '',
        creator_whats_included: '',
        creator_turnaround: '',
        creator_booking_process: '',
        creator_min_budget: '',
        creator_blacklisted_niches: '',
        creator_fan_dm_response: '',
        creator_media_kit_link: '',
    });
    const [fitness, setFitness] = useState({
        fitness_class_types: '',
        fitness_class_schedule: '',
        fitness_trainers: '',
        fitness_membership_tiers: '',
        fitness_trial_offer: '',
        fitness_class_capacity: '',
        fitness_cancellation_policy: '',
        fitness_equipment: '',
    });
    const [healthcare, setHealthcare] = useState({
        healthcare_providers: '',
        healthcare_specialties: '',
        healthcare_appointment_types: '',
        healthcare_insurance: '',
        healthcare_consultation_fee: '',
        healthcare_patient_prep: '',
        healthcare_languages: '',
    });
    const [restaurant, setRestaurant] = useState({
        restaurant_cuisine: '',
        restaurant_menu_highlights: '',
        restaurant_dietary_options: '',
        restaurant_price_range: '',
        restaurant_seating: '',
        restaurant_reservation_policy: '',
        restaurant_parking: '',
        restaurant_dress_code: '',
    });
    const [salon, setSalon] = useState({
        salon_stylists: '',
        salon_services_menu: '',
        salon_deposit_policy: '',
        salon_cancellation_policy: '',
        salon_walk_ins: '',
        salon_products_used: '',
    });
    const [retail, setRetail] = useState({
        retail_return_policy: '',
        retail_discount_tiers: '',
        retail_delivery_areas: '',
        retail_warranty: '',
        retail_exchange_policy: '',
        retail_min_order: '',
    });
    const [rental, setRental] = useState({
        rental_check_in_time: '',
        rental_house_rules: '',
        rental_amenities: '',
        rental_min_stay: '',
        rental_security_deposit: '',
        rental_cancellation_policy: '',
        rental_pet_policy: '',
    });
    const [tech, setTech] = useState({
        tech_product_description: '',
        tech_target_customers: '',
        tech_pricing_plans: '',
        tech_free_trial: '',
        tech_key_features: '',
        tech_integrations: '',
        tech_demo_process: '',
        tech_onboarding: '',
        tech_support_channels: '',
        tech_compliance: '',
        tech_contract_terms: '',
        tech_case_studies: '',
    });
    const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);

    // Payment methods state
    const [paymentMethods, setPaymentMethods] = useState<{name:string;details?:string;fields?:{label:string;value:string}[]}[]>([]);
    const [addingPayment, setAddingPayment] = useState(false);
    const [newPmName, setNewPmName] = useState('');
    const [newPmDetails, setNewPmDetails] = useState('');

    // List states (derived from string fields)
    const [productItems, setProductItems] = useState<string[]>([]);
    const [deliveryItems, setDeliveryItems] = useState<string[]>([]);
    const [faqList, setFaqList] = useState<{ question: string; answer: string }[]>([]);
    const [offerItems, setOfferItems] = useState<string[]>([]);

    // Sync internal type from global context whenever modal opens
    useEffect(() => {
        if (visible) {
            setBusinessType(GLOBAL_TO_BK_TYPE[globalBT] || 'general');
            fetchKnowledge();
        }
    }, [visible, globalBT]);

    const fetchKnowledge = async () => {
        setLoading(true);
        try {
            const data = await settingsAPI.getBusinessKnowledge();
            if (data) {
                setKnowledge({
                    business_description: data.business_description || '',
                    products_services: data.products_services || '',
                    pricing_info: data.pricing_info || '',
                    business_hours: data.business_hours || '',
                    delivery_info: data.delivery_info || '',
                    faqs: data.faqs || '',
                    special_offers: data.special_offers || '',
                    booking_process: data.booking_process || '',
                    cancellation_policy: data.cancellation_policy || '',
                    staff_info: data.staff_info || '',
                });
                // Always use global type mapping, ignoring any stale saved BK type
                setBusinessType(GLOBAL_TO_BK_TYPE[globalBT] || data.business_type || 'general');
                setCreator({
                    creator_niche: data.creator_niche || '',
                    creator_platforms: data.creator_platforms || '',
                    creator_audience_size: data.creator_audience_size || '',
                    creator_collab_types: data.creator_collab_types || '',
                    creator_rate_card: data.creator_rate_card || '',
                    creator_whats_included: data.creator_whats_included || '',
                    creator_turnaround: data.creator_turnaround || '',
                    creator_booking_process: data.creator_booking_process || '',
                    creator_min_budget: data.creator_min_budget || '',
                    creator_blacklisted_niches: data.creator_blacklisted_niches || '',
                    creator_fan_dm_response: data.creator_fan_dm_response || '',
                    creator_media_kit_link: data.creator_media_kit_link || '',
                });
                setSelectedPlatforms(
                    data.creator_platforms ? data.creator_platforms.split(',').map((s: string) => s.trim()).filter(Boolean) : []
                );
                setFitness({
                    fitness_class_types: data.fitness_class_types || '',
                    fitness_class_schedule: data.fitness_class_schedule || '',
                    fitness_trainers: data.fitness_trainers || '',
                    fitness_membership_tiers: data.fitness_membership_tiers || '',
                    fitness_trial_offer: data.fitness_trial_offer || '',
                    fitness_class_capacity: data.fitness_class_capacity || '',
                    fitness_cancellation_policy: data.fitness_cancellation_policy || '',
                    fitness_equipment: data.fitness_equipment || '',
                });
                setHealthcare({
                    healthcare_providers: data.healthcare_providers || '',
                    healthcare_specialties: data.healthcare_specialties || '',
                    healthcare_appointment_types: data.healthcare_appointment_types || '',
                    healthcare_insurance: data.healthcare_insurance || '',
                    healthcare_consultation_fee: data.healthcare_consultation_fee || '',
                    healthcare_patient_prep: data.healthcare_patient_prep || '',
                    healthcare_languages: data.healthcare_languages || '',
                });
                setRestaurant({
                    restaurant_cuisine: data.restaurant_cuisine || '',
                    restaurant_menu_highlights: data.restaurant_menu_highlights || '',
                    restaurant_dietary_options: data.restaurant_dietary_options || '',
                    restaurant_price_range: data.restaurant_price_range || '',
                    restaurant_seating: data.restaurant_seating || '',
                    restaurant_reservation_policy: data.restaurant_reservation_policy || '',
                    restaurant_parking: data.restaurant_parking || '',
                    restaurant_dress_code: data.restaurant_dress_code || '',
                });
                setSalon({
                    salon_stylists: data.salon_stylists || '',
                    salon_services_menu: data.salon_services_menu || '',
                    salon_deposit_policy: data.salon_deposit_policy || '',
                    salon_cancellation_policy: data.salon_cancellation_policy || '',
                    salon_walk_ins: data.salon_walk_ins || '',
                    salon_products_used: data.salon_products_used || '',
                });
                setRetail({
                    retail_return_policy: data.retail_return_policy || '',
                    retail_discount_tiers: data.retail_discount_tiers || '',
                    retail_delivery_areas: data.retail_delivery_areas || '',
                    retail_warranty: data.retail_warranty || '',
                    retail_exchange_policy: data.retail_exchange_policy || '',
                    retail_min_order: data.retail_min_order || '',
                });
                setRental({
                    rental_check_in_time: data.rental_check_in_time || '',
                    rental_house_rules: data.rental_house_rules || '',
                    rental_amenities: data.rental_amenities || '',
                    rental_min_stay: data.rental_min_stay || '',
                    rental_security_deposit: data.rental_security_deposit || '',
                    rental_cancellation_policy: data.rental_cancellation_policy || '',
                    rental_pet_policy: data.rental_pet_policy || '',
                });
                setTech({
                    tech_product_description: data.tech_product_description || '',
                    tech_target_customers: data.tech_target_customers || '',
                    tech_pricing_plans: data.tech_pricing_plans || '',
                    tech_free_trial: data.tech_free_trial || '',
                    tech_key_features: data.tech_key_features || '',
                    tech_integrations: data.tech_integrations || '',
                    tech_demo_process: data.tech_demo_process || '',
                    tech_onboarding: data.tech_onboarding || '',
                    tech_support_channels: data.tech_support_channels || '',
                    tech_compliance: data.tech_compliance || '',
                    tech_contract_terms: data.tech_contract_terms || '',
                    tech_case_studies: data.tech_case_studies || '',
                });
                // Load payment methods — keep all entries that have a name
                if (data.payment_methods && data.payment_methods.length > 0) {
                    const loaded = data.payment_methods
                        .map((m: any) => typeof m === 'string' ? { name: m } : m)
                        .filter((m: any) => m.name && String(m.name).trim());
                    setPaymentMethods(loaded);
                }
                setProductItems(stringToItems(data.products_services));
                setDeliveryItems(stringToItems(data.delivery_info));
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

    const togglePlatform = (platform: string) => {
        const updated = selectedPlatforms.includes(platform)
            ? selectedPlatforms.filter(p => p !== platform)
            : [...selectedPlatforms, platform];
        setSelectedPlatforms(updated);
        setCreator(c => ({ ...c, creator_platforms: updated.join(', ') }));
    };

    const getMethodSummary = (pm: {name:string;details?:string;fields?:{label:string;value:string}[]}) => {
        if (pm.fields && pm.fields.length > 0) {
            return pm.fields.filter(f => f.value).map(f => `${f.label}: ${f.value}`).join('  ·  ');
        }
        return pm.details || '';
    };

    const resetAddForm = () => {
        setAddingPayment(false);
        setNewPmName('');
        setNewPmDetails('');
    };

    const handleSave = async () => {
        setSaving(true);
        const updatedKnowledge = {
            ...knowledge,
            products_services: itemsToString(productItems),
            delivery_info: itemsToString(deliveryItems),
            faqs: faqList.map(f => `Q: ${f.question}\nA: ${f.answer}`).join('\n'),
            special_offers: itemsToString(offerItems),
            business_type: businessType,
            ...creator,
            creator_platforms: selectedPlatforms.join(', '),
            ...fitness,
            ...healthcare,
            ...restaurant,
            ...salon,
            ...retail,
            ...rental,
            ...tech,
        };
        try {
            await settingsAPI.updateBusinessKnowledge({
                ...updatedKnowledge,
                payment_methods: paymentMethods,
            });
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

    const isCreator = businessType === 'creator';
    const isFitness = businessType === 'fitness';
    const isHealthcare = businessType === 'healthcare';
    const isRestaurant = businessType === 'restaurant';
    const isSalon = businessType === 'salon';
    const isRetail = businessType === 'retail';
    const isRental = businessType === 'rental';
    const isGenericService = businessType === 'services';
    const isTech = businessType === 'tech';
    const isService = isFitness || isHealthcare || isSalon || isGenericService;
    const itemLabel = config.catalogItemLabel;

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
                                The AI uses this to answer customers accurately. Select your business type to unlock the right fields.
                            </Text>
                        </View>

                        {/* Business Type — read-only, driven by Account Settings */}
                        <View style={[styles.field, { flexDirection: 'row', alignItems: 'center', gap: 10 }]}>
                            <Ionicons name="storefront-outline" size={18} color="#25D366" />
                            <View style={{ flex: 1 }}>
                                <Text style={styles.label}>Business Type</Text>
                                <Text style={[styles.hint, { marginTop: 2 }]}>
                                    {BK_TYPE_LABELS[businessType] || businessType}  ·  Change in Account Settings
                                </Text>
                            </View>
                        </View>

                        {/* About */}
                        <View style={styles.field}>
                            <Text style={styles.label}>{isCreator ? 'About You' : 'About Your Business'}</Text>
                            <Text style={styles.hint}>
                                {isCreator
                                    ? 'e.g. "I\'m a lifestyle creator based in Nairobi, I create content on fashion, travel and daily life."'
                                    : isFitness
                                    ? 'e.g. "We\'re a fitness studio in Karen offering HIIT, yoga and pilates classes for all levels."'
                                    : isHealthcare
                                    ? 'e.g. "We\'re a family clinic offering GP, dental and physiotherapy services in Westlands."'
                                    : isRestaurant
                                    ? 'e.g. "We serve authentic Kenyan cuisine — famous for our nyama choma and fresh juices."'
                                    : isSalon
                                    ? 'e.g. "We\'re a natural hair salon specializing in braids, locs and protective styles."'
                                    : isRetail
                                    ? 'e.g. "We sell handmade jewellery and accessories. We specialize in custom orders."'
                                    : isRental
                                    ? 'e.g. "We offer a fully-furnished 2BR Airbnb in Westlands with pool and gym access."'
                                    : isTech
                                    ? 'e.g. "We build cloud accounting software that automates invoicing and VAT filing for SMEs."'
                                    : isGenericService
                                    ? 'e.g. "We provide professional plumbing and electrical services across Nairobi — fast, reliable, affordable."'
                                    : 'e.g. "We sell fresh cakes and pastries. We specialize in custom birthday cakes."'}
                            </Text>
                            <TextInput
                                style={styles.input}
                                placeholder={isCreator ? 'Who are you and what do you create?' : 'What does your business do?'}
                                placeholderTextColor="#555"
                                value={knowledge.business_description}
                                onChangeText={(text) => setKnowledge({ ...knowledge, business_description: text })}
                                multiline
                                numberOfLines={3}
                            />
                        </View>

                        {/* ── CREATOR FIELDS ── */}
                        {isCreator && (
                            <>
                                {/* Divider */}
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="star" size={16} color="#FFD700" />
                                    <Text style={styles.sectionDividerText}>Creator Profile</Text>
                                </View>

                                {/* Niche */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Content Niche</Text>
                                    <Text style={styles.hint}>e.g. "Fashion, Lifestyle, Travel, Tech Reviews"</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="What topics do you cover?"
                                        placeholderTextColor="#555"
                                        value={creator.creator_niche}
                                        onChangeText={(text) => setCreator({ ...creator, creator_niche: text })}
                                    />
                                </View>

                                {/* Platforms */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Platforms</Text>
                                    <Text style={styles.hint}>Select all platforms where you create content</Text>
                                    <View style={styles.platformGrid}>
                                        {PLATFORMS.map(p => (
                                            <TouchableOpacity
                                                key={p}
                                                style={[styles.platformChip, selectedPlatforms.includes(p) && styles.platformChipActive]}
                                                onPress={() => togglePlatform(p)}
                                            >
                                                <Text style={[styles.platformChipText, selectedPlatforms.includes(p) && styles.platformChipTextActive]}>
                                                    {p}
                                                </Text>
                                            </TouchableOpacity>
                                        ))}
                                    </View>
                                </View>

                                {/* Audience Size */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Audience Size</Text>
                                    <Text style={styles.hint}>e.g. "50K Instagram, 20K TikTok"</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="Your follower/subscriber counts"
                                        placeholderTextColor="#555"
                                        value={creator.creator_audience_size}
                                        onChangeText={(text) => setCreator({ ...creator, creator_audience_size: text })}
                                    />
                                </View>

                                {/* Collab Types */}
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="megaphone-outline" size={18} color="#25D366" />
                                        <Text style={styles.label}>Collaboration Types</Text>
                                    </View>
                                    <Text style={styles.hint}>e.g. "Sponsored post, Story mention, Reel, Brand ambassador, Product review"</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="What types of collabs do you offer?"
                                        placeholderTextColor="#555"
                                        value={creator.creator_collab_types}
                                        onChangeText={(text) => setCreator({ ...creator, creator_collab_types: text })}
                                        multiline
                                        numberOfLines={2}
                                    />
                                </View>

                                {/* Rate Card */}
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="pricetag-outline" size={18} color="#25D366" />
                                        <Text style={styles.label}>Rate Card</Text>
                                    </View>
                                    <Text style={styles.hint}>e.g. "1 Reel: $300, 3 Stories: $150, Full package (Reel + 3 Stories): $400"</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="Your pricing per deliverable"
                                        placeholderTextColor="#555"
                                        value={creator.creator_rate_card}
                                        onChangeText={(text) => setCreator({ ...creator, creator_rate_card: text })}
                                        multiline
                                        numberOfLines={3}
                                    />
                                </View>

                                {/* What's Included */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>What's Included</Text>
                                    <Text style={styles.hint}>e.g. "1 reel + 3 stories + link in bio for 24hrs + performance report after 7 days"</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="What does a brand get when they work with you?"
                                        placeholderTextColor="#555"
                                        value={creator.creator_whats_included}
                                        onChangeText={(text) => setCreator({ ...creator, creator_whats_included: text })}
                                        multiline
                                        numberOfLines={2}
                                    />
                                </View>

                                {/* Turnaround */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Turnaround Time</Text>
                                    <Text style={styles.hint}>e.g. "Content delivered within 5 business days of brief approval"</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="How long to deliver content?"
                                        placeholderTextColor="#555"
                                        value={creator.creator_turnaround}
                                        onChangeText={(text) => setCreator({ ...creator, creator_turnaround: text })}
                                    />
                                </View>

                                {/* Booking Process */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Booking Process</Text>
                                    <Text style={styles.hint}>e.g. "50% deposit upfront, balance before posting. Brief must be approved before production starts."</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="How should brands book you?"
                                        placeholderTextColor="#555"
                                        value={creator.creator_booking_process}
                                        onChangeText={(text) => setCreator({ ...creator, creator_booking_process: text })}
                                        multiline
                                        numberOfLines={2}
                                    />
                                </View>

                                {/* Min Budget */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Minimum Budget</Text>
                                    <Text style={styles.hint}>e.g. "Minimum collab budget is $200"</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="What's the lowest budget you accept?"
                                        placeholderTextColor="#555"
                                        value={creator.creator_min_budget}
                                        onChangeText={(text) => setCreator({ ...creator, creator_min_budget: text })}
                                    />
                                </View>

                                {/* Blacklisted Niches */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Brands I Don't Work With</Text>
                                    <Text style={styles.hint}>e.g. "Alcohol, gambling, competitor brands, adult content"</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="Industries or topics you decline"
                                        placeholderTextColor="#555"
                                        value={creator.creator_blacklisted_niches}
                                        onChangeText={(text) => setCreator({ ...creator, creator_blacklisted_niches: text })}
                                    />
                                </View>

                                {/* Media Kit Link */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Media Kit Link</Text>
                                    <Text style={styles.hint}>Share this link with brands who ask for your stats</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="https://drive.google.com/... or Linktree URL"
                                        placeholderTextColor="#555"
                                        value={creator.creator_media_kit_link}
                                        onChangeText={(text) => setCreator({ ...creator, creator_media_kit_link: text })}
                                        autoCapitalize="none"
                                        keyboardType="url"
                                    />
                                </View>

                                {/* Fan DM Response */}
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="heart-outline" size={18} color="#FF6B6B" />
                                        <Text style={styles.label}>Fan DM Response</Text>
                                    </View>
                                    <Text style={styles.hint}>Default warm reply for fans who DM (not brands). The AI uses this for non-business messages.</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder='e.g. "Hey! Thanks so much for the love, means everything! Stay tuned for more content"'
                                        placeholderTextColor="#555"
                                        value={creator.creator_fan_dm_response}
                                        onChangeText={(text) => setCreator({ ...creator, creator_fan_dm_response: text })}
                                        multiline
                                        numberOfLines={3}
                                    />
                                </View>

                                <View style={styles.sectionDivider}>
                                    <Ionicons name="storefront-outline" size={16} color="#6B7D99" />
                                    <Text style={[styles.sectionDividerText, { color: '#6B7D99' }]}>General Info</Text>
                                </View>
                            </>
                        )}

                        {/* ── FITNESS FIELDS ── */}
                        {isFitness && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="barbell-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Fitness / Gym Details</Text>
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Classes Offered *</Text>
                                    <Text style={styles.hint}>e.g. "Yoga, HIIT, Pilates, Spin, Zumba"</Text>
                                    <TextInput style={styles.input} placeholder="What classes do you offer?" placeholderTextColor="#555" value={fitness.fitness_class_types} onChangeText={t => setFitness({...fitness, fitness_class_types: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Class Schedule *</Text>
                                    <Text style={styles.hint}>e.g. "Mon/Wed/Fri 6am HIIT · Tue/Thu 7pm Yoga · Sat 9am Pilates"</Text>
                                    <TextInput style={styles.input} placeholder="Days, times, and class names" placeholderTextColor="#555" value={fitness.fitness_class_schedule} onChangeText={t => setFitness({...fitness, fitness_class_schedule: t})} multiline numberOfLines={3} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Membership & Pricing *</Text>
                                    <Text style={styles.hint}>e.g. "Monthly KES 3,500 · 10-class pack KES 3,000 · Drop-in KES 500"</Text>
                                    <TextInput style={styles.input} placeholder="Membership tiers and prices" placeholderTextColor="#555" value={fitness.fitness_membership_tiers} onChangeText={t => setFitness({...fitness, fitness_membership_tiers: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Trainers / Instructors</Text>
                                    <Text style={styles.hint}>e.g. "Jane (Yoga, Pilates) · Mike (HIIT, Strength) · Amina (Zumba)"</Text>
                                    <TextInput style={styles.input} placeholder="Names and their specialties" placeholderTextColor="#555" value={fitness.fitness_trainers} onChangeText={t => setFitness({...fitness, fitness_trainers: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Trial Offer</Text>
                                    <Text style={styles.hint}>e.g. "First class free" or "1-week trial KES 500"</Text>
                                    <TextInput style={styles.input} placeholder="Any intro/trial offer?" placeholderTextColor="#555" value={fitness.fitness_trial_offer} onChangeText={t => setFitness({...fitness, fitness_trial_offer: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Class Capacity</Text>
                                    <Text style={styles.hint}>e.g. "Max 15 per class — book in advance to secure your spot"</Text>
                                    <TextInput style={styles.input} placeholder="Max students per class" placeholderTextColor="#555" value={fitness.fitness_class_capacity} onChangeText={t => setFitness({...fitness, fitness_class_capacity: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Cancellation Policy</Text>
                                    <Text style={styles.hint}>e.g. "Cancel 2hrs before or forfeit the class"</Text>
                                    <TextInput style={styles.input} placeholder="Cancellation & no-show policy" placeholderTextColor="#555" value={fitness.fitness_cancellation_policy} onChangeText={t => setFitness({...fitness, fitness_cancellation_policy: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Equipment / What to Bring</Text>
                                    <Text style={styles.hint}>e.g. "Mats provided · Bring water bottle and towel · Lockers available"</Text>
                                    <TextInput style={styles.input} placeholder="What should members bring?" placeholderTextColor="#555" value={fitness.fitness_equipment} onChangeText={t => setFitness({...fitness, fitness_equipment: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="calendar-outline" size={18} color="#25D366" />
                                        <Text style={styles.label}>How to Book a Class *</Text>
                                    </View>
                                    <Text style={styles.hint}>e.g. "Book via WhatsApp or our app at least 2hrs before · Walk-ins welcome if space available"</Text>
                                    <TextInput style={styles.input} placeholder="How do members reserve their spot?" placeholderTextColor="#555" value={knowledge.booking_process} onChangeText={t => setKnowledge({...knowledge, booking_process: t})} multiline numberOfLines={2} />
                                </View>
                            </>
                        )}

                        {/* ── HEALTHCARE FIELDS ── */}
                        {isHealthcare && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="medical-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Healthcare / Clinic Details</Text>
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Doctors / Providers *</Text>
                                    <Text style={styles.hint}>e.g. "Dr. Kamau (GP) · Dr. Njoki (Dermatology) · Dr. Omondi (Dentist)"</Text>
                                    <TextInput style={styles.input} placeholder="Names and specialties" placeholderTextColor="#555" value={healthcare.healthcare_providers} onChangeText={t => setHealthcare({...healthcare, healthcare_providers: t})} multiline numberOfLines={3} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Specialties Offered *</Text>
                                    <Text style={styles.hint}>e.g. "General Practice, Dermatology, Dentistry, Physiotherapy"</Text>
                                    <TextInput style={styles.input} placeholder="What medical services do you offer?" placeholderTextColor="#555" value={healthcare.healthcare_specialties} onChangeText={t => setHealthcare({...healthcare, healthcare_specialties: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Consultation Fees *</Text>
                                    <Text style={styles.hint}>e.g. "GP KES 1,500 · Specialist KES 3,000 · Follow-up KES 800"</Text>
                                    <TextInput style={styles.input} placeholder="Fees per appointment type" placeholderTextColor="#555" value={healthcare.healthcare_consultation_fee} onChangeText={t => setHealthcare({...healthcare, healthcare_consultation_fee: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Insurance Accepted</Text>
                                    <Text style={styles.hint}>e.g. "NHIF, AAR, Jubilee, Britam, Madison, CIC"</Text>
                                    <TextInput style={styles.input} placeholder="Which insurance schemes do you accept?" placeholderTextColor="#555" value={healthcare.healthcare_insurance} onChangeText={t => setHealthcare({...healthcare, healthcare_insurance: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Appointment Types</Text>
                                    <Text style={styles.hint}>e.g. "New patient consult, Follow-up, Procedure, Lab tests, X-ray"</Text>
                                    <TextInput style={styles.input} placeholder="Types of appointments available" placeholderTextColor="#555" value={healthcare.healthcare_appointment_types} onChangeText={t => setHealthcare({...healthcare, healthcare_appointment_types: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Patient Preparation Notes</Text>
                                    <Text style={styles.hint}>e.g. "Bring previous prescriptions · Fast 8hrs before blood tests · Bring ID"</Text>
                                    <TextInput style={styles.input} placeholder="What should patients bring or do before their visit?" placeholderTextColor="#555" value={healthcare.healthcare_patient_prep} onChangeText={t => setHealthcare({...healthcare, healthcare_patient_prep: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Languages Spoken</Text>
                                    <Text style={styles.hint}>e.g. "English, Swahili, Kikuyu, Luo"</Text>
                                    <TextInput style={styles.input} placeholder="Languages your staff speaks" placeholderTextColor="#555" value={healthcare.healthcare_languages} onChangeText={t => setHealthcare({...healthcare, healthcare_languages: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Booking Process</Text>
                                    <Text style={styles.hint}>e.g. "Walk-ins welcome · Or book via WhatsApp for guaranteed slot"</Text>
                                    <TextInput style={styles.input} placeholder="How do patients book?" placeholderTextColor="#555" value={knowledge.booking_process} onChangeText={t => setKnowledge({...knowledge, booking_process: t})} multiline numberOfLines={2} />
                                </View>
                            </>
                        )}

                        {/* ── RESTAURANT FIELDS ── */}
                        {isRestaurant && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="restaurant-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Restaurant Details</Text>
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Cuisine Type *</Text>
                                    <Text style={styles.hint}>e.g. "Kenyan, Indian fusion, Continental, BBQ"</Text>
                                    <TextInput style={styles.input} placeholder="What type of food do you serve?" placeholderTextColor="#555" value={restaurant.restaurant_cuisine} onChangeText={t => setRestaurant({...restaurant, restaurant_cuisine: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Menu Highlights *</Text>
                                    <Text style={styles.hint}>e.g. "Nyama choma, biryani, tilapia, fresh juices, wood-fired pizza"</Text>
                                    <TextInput style={styles.input} placeholder="Your most popular or signature dishes" placeholderTextColor="#555" value={restaurant.restaurant_menu_highlights} onChangeText={t => setRestaurant({...restaurant, restaurant_menu_highlights: t})} multiline numberOfLines={3} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Price Range *</Text>
                                    <Text style={styles.hint}>e.g. "KES 500–2,000 per person" or "$$$ (upscale)"</Text>
                                    <TextInput style={styles.input} placeholder="Typical spend per person" placeholderTextColor="#555" value={restaurant.restaurant_price_range} onChangeText={t => setRestaurant({...restaurant, restaurant_price_range: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Dietary Options</Text>
                                    <Text style={styles.hint}>e.g. "Vegan menu available · Halal certified · Gluten-free options"</Text>
                                    <TextInput style={styles.input} placeholder="Any special dietary menus?" placeholderTextColor="#555" value={restaurant.restaurant_dietary_options} onChangeText={t => setRestaurant({...restaurant, restaurant_dietary_options: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Seating Options</Text>
                                    <Text style={styles.hint}>e.g. "Indoor 80 pax · Outdoor terrace 40 pax · Private room 20 pax"</Text>
                                    <TextInput style={styles.input} placeholder="Indoor, outdoor, private dining?" placeholderTextColor="#555" value={restaurant.restaurant_seating} onChangeText={t => setRestaurant({...restaurant, restaurant_seating: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Reservation Policy</Text>
                                    <Text style={styles.hint}>e.g. "Walk-ins welcome · Reservations required Fri-Sat · KES 500 deposit for groups 6+"</Text>
                                    <TextInput style={styles.input} placeholder="How should customers book a table?" placeholderTextColor="#555" value={restaurant.restaurant_reservation_policy} onChangeText={t => setRestaurant({...restaurant, restaurant_reservation_policy: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Parking</Text>
                                    <Text style={styles.hint}>e.g. "Free parking on premises · Street parking available"</Text>
                                    <TextInput style={styles.input} placeholder="Is parking available?" placeholderTextColor="#555" value={restaurant.restaurant_parking} onChangeText={t => setRestaurant({...restaurant, restaurant_parking: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Dress Code</Text>
                                    <Text style={styles.hint}>e.g. "Smart casual · No slippers or shorts in evenings"</Text>
                                    <TextInput style={styles.input} placeholder="Any dress code?" placeholderTextColor="#555" value={restaurant.restaurant_dress_code} onChangeText={t => setRestaurant({...restaurant, restaurant_dress_code: t})} />
                                </View>
                            </>
                        )}

                        {/* ── SALON FIELDS ── */}
                        {isSalon && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="cut-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Salon / Beauty Details</Text>
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Stylists / Staff *</Text>
                                    <Text style={styles.hint}>e.g. "Amina (braids, locs, natural hair) · Lisa (color, cuts, relaxers)"</Text>
                                    <TextInput style={styles.input} placeholder="Names and what each person specializes in" placeholderTextColor="#555" value={salon.salon_stylists} onChangeText={t => setSalon({...salon, salon_stylists: t})} multiline numberOfLines={3} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Services & Prices *</Text>
                                    <Text style={styles.hint}>e.g. "Box braids KES 2,500 · Silk press KES 1,800 · Color KES 3,500+"</Text>
                                    <TextInput style={styles.input} placeholder="List your services with prices" placeholderTextColor="#555" value={salon.salon_services_menu} onChangeText={t => setSalon({...salon, salon_services_menu: t})} multiline numberOfLines={4} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Deposit Policy</Text>
                                    <Text style={styles.hint}>e.g. "50% deposit required to confirm booking"</Text>
                                    <TextInput style={styles.input} placeholder="Do you require a deposit?" placeholderTextColor="#555" value={salon.salon_deposit_policy} onChangeText={t => setSalon({...salon, salon_deposit_policy: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Cancellation Policy</Text>
                                    <Text style={styles.hint}>e.g. "Cancel 24hrs before or lose deposit · Reschedule once free"</Text>
                                    <TextInput style={styles.input} placeholder="Cancellation & rescheduling rules" placeholderTextColor="#555" value={salon.salon_cancellation_policy} onChangeText={t => setSalon({...salon, salon_cancellation_policy: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Walk-ins</Text>
                                    <Text style={styles.hint}>e.g. "Walk-ins welcome Mon–Thu if space available · Weekends by appointment only"</Text>
                                    <TextInput style={styles.input} placeholder="Do you accept walk-in clients?" placeholderTextColor="#555" value={salon.salon_walk_ins} onChangeText={t => setSalon({...salon, salon_walk_ins: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Products Used</Text>
                                    <Text style={styles.hint}>e.g. "OGX, Cantu, SheaMoisture · Natural/organic products on request"</Text>
                                    <TextInput style={styles.input} placeholder="What brands or products do you use?" placeholderTextColor="#555" value={salon.salon_products_used} onChangeText={t => setSalon({...salon, salon_products_used: t})} />
                                </View>
                            </>
                        )}

                        {/* ── RETAIL FIELDS ── */}
                        {isRetail && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="bag-handle-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Retail Details</Text>
                                </View>
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="pricetag-outline" size={18} color="#25D366" />
                                        <Text style={styles.label}>Products & Prices *</Text>
                                    </View>
                                    <Text style={styles.hint}>Add each product with its price</Text>
                                    <ListField items={productItems} onUpdate={setProductItems} placeholder="Product - price" icon="cart-outline" />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Return Policy *</Text>
                                    <Text style={styles.hint}>e.g. "7-day returns with receipt · Item must be unused and in original packaging"</Text>
                                    <TextInput style={styles.input} placeholder="Can customers return items?" placeholderTextColor="#555" value={retail.retail_return_policy} onChangeText={t => setRetail({...retail, retail_return_policy: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Exchange Policy</Text>
                                    <Text style={styles.hint}>e.g. "Exchanges within 14 days · Item must be unworn with tags attached"</Text>
                                    <TextInput style={styles.input} placeholder="Exchange rules" placeholderTextColor="#555" value={retail.retail_exchange_policy} onChangeText={t => setRetail({...retail, retail_exchange_policy: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Discount Tiers</Text>
                                    <Text style={styles.hint}>e.g. "Buy 3+ items get 5% off · Orders over KES 5,000 get 10% off"</Text>
                                    <TextInput style={styles.input} placeholder="Bulk or loyalty discounts" placeholderTextColor="#555" value={retail.retail_discount_tiers} onChangeText={t => setRetail({...retail, retail_discount_tiers: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Delivery Areas & Costs</Text>
                                    <Text style={styles.hint}>e.g. "Same-day Nairobi CBD KES 200 · Next-day countrywide KES 350"</Text>
                                    <ListField items={deliveryItems} onUpdate={setDeliveryItems} placeholder="Area - delivery cost" icon="location-outline" />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Minimum Order</Text>
                                    <Text style={styles.hint}>e.g. "Minimum order KES 500 for delivery"</Text>
                                    <TextInput style={styles.input} placeholder="Any minimum order amount?" placeholderTextColor="#555" value={retail.retail_min_order} onChangeText={t => setRetail({...retail, retail_min_order: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Warranty</Text>
                                    <Text style={styles.hint}>e.g. "6-month warranty on electronics · 1-year on appliances"</Text>
                                    <TextInput style={styles.input} placeholder="Any product warranties?" placeholderTextColor="#555" value={retail.retail_warranty} onChangeText={t => setRetail({...retail, retail_warranty: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Payment & Order Notes</Text>
                                    <Text style={styles.hint}>e.g. "Cash on delivery available · Pay before dispatch for new customers · M-Pesa accepted"</Text>
                                    <TextInput style={styles.input} placeholder="Any important payment or order notes?" placeholderTextColor="#555" value={knowledge.pricing_info} onChangeText={t => setKnowledge({...knowledge, pricing_info: t})} multiline numberOfLines={2} />
                                </View>
                            </>
                        )}

                        {/* ── RENTAL FIELDS ── */}
                        {isRental && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="home-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Rental / Listing Details</Text>
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Listing Name / Description *</Text>
                                    <Text style={styles.hint}>e.g. "Luxury 2BR with pool in Westlands · Sleeps 4 · Full kitchen"</Text>
                                    <TextInput style={styles.input} placeholder="What are you renting out?" placeholderTextColor="#555" value={knowledge.products_services} onChangeText={t => setKnowledge({...knowledge, products_services: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Nightly Rate / Pricing *</Text>
                                    <Text style={styles.hint}>e.g. "Weekday KES 8,000/night · Weekend KES 10,000/night · Weekly discount 15% off"</Text>
                                    <TextInput style={styles.input} placeholder="Your rates per night or period" placeholderTextColor="#555" value={knowledge.pricing_info} onChangeText={t => setKnowledge({...knowledge, pricing_info: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Check-in / Check-out Times *</Text>
                                    <Text style={styles.hint}>e.g. "Check-in from 2pm · Check-out by 11am"</Text>
                                    <TextInput style={styles.input} placeholder="Check-in and check-out times" placeholderTextColor="#555" value={rental.rental_check_in_time} onChangeText={t => setRental({...rental, rental_check_in_time: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Amenities *</Text>
                                    <Text style={styles.hint}>e.g. "WiFi, pool, full kitchen, parking, generator, Smart TV"</Text>
                                    <TextInput style={styles.input} placeholder="What's included in the listing?" placeholderTextColor="#555" value={rental.rental_amenities} onChangeText={t => setRental({...rental, rental_amenities: t})} multiline numberOfLines={3} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>House Rules *</Text>
                                    <Text style={styles.hint}>e.g. "No smoking indoors · No pets · Max 4 guests · Quiet hours after 10pm"</Text>
                                    <TextInput style={styles.input} placeholder="Rules guests must follow" placeholderTextColor="#555" value={rental.rental_house_rules} onChangeText={t => setRental({...rental, rental_house_rules: t})} multiline numberOfLines={3} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Minimum Stay</Text>
                                    <Text style={styles.hint}>e.g. "Minimum 2 nights · Weekly discount available (7+ nights)"</Text>
                                    <TextInput style={styles.input} placeholder="Minimum booking duration" placeholderTextColor="#555" value={rental.rental_min_stay} onChangeText={t => setRental({...rental, rental_min_stay: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Security Deposit</Text>
                                    <Text style={styles.hint}>e.g. "KES 5,000 refundable deposit collected on arrival"</Text>
                                    <TextInput style={styles.input} placeholder="Is there a security deposit?" placeholderTextColor="#555" value={rental.rental_security_deposit} onChangeText={t => setRental({...rental, rental_security_deposit: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Cancellation Policy</Text>
                                    <Text style={styles.hint}>e.g. "Free cancellation 7 days before · 50% refund within 7 days · No refund within 24hrs"</Text>
                                    <TextInput style={styles.input} placeholder="Refund and cancellation rules" placeholderTextColor="#555" value={rental.rental_cancellation_policy} onChangeText={t => setRental({...rental, rental_cancellation_policy: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Pet Policy</Text>
                                    <Text style={styles.hint}>e.g. "Pets allowed with prior approval · KES 500 cleaning fee applies"</Text>
                                    <TextInput style={styles.input} placeholder="Are pets allowed?" placeholderTextColor="#555" value={rental.rental_pet_policy} onChangeText={t => setRental({...rental, rental_pet_policy: t})} />
                                </View>
                            </>
                        )}

                        {/* ── GENERIC SERVICES FIELDS ── */}
                        {/* ── TECH / SAAS / FINTECH FIELDS ── */}
                        {isTech && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="laptop-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Tech / SaaS / Fintech Details</Text>
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>What Your Product Does *</Text>
                                    <Text style={styles.hint}>e.g. "Cloud accounting software for SMEs — automates invoicing, payroll and VAT filing"</Text>
                                    <TextInput style={styles.input} placeholder="Describe your product or platform in 1-2 sentences" placeholderTextColor="#555" value={tech.tech_product_description} onChangeText={t => setTech({...tech, tech_product_description: t})} multiline numberOfLines={3} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Target Customers *</Text>
                                    <Text style={styles.hint}>e.g. "SMEs, accountants, NGOs, retail chains, restaurants"</Text>
                                    <TextInput style={styles.input} placeholder="Who is this for?" placeholderTextColor="#555" value={tech.tech_target_customers} onChangeText={t => setTech({...tech, tech_target_customers: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Key Features *</Text>
                                    <Text style={styles.hint}>e.g. "Invoicing, M-Pesa integration, payroll, expense tracking, VAT filing, multi-user"</Text>
                                    <TextInput style={styles.input} placeholder="Your most important features" placeholderTextColor="#555" value={tech.tech_key_features} onChangeText={t => setTech({...tech, tech_key_features: t})} multiline numberOfLines={3} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Pricing Plans *</Text>
                                    <Text style={styles.hint}>e.g. "Starter $29/mo · Pro $79/mo · Enterprise custom · 20% off annual"</Text>
                                    <TextInput style={styles.input} placeholder="Your plan tiers and prices" placeholderTextColor="#555" value={tech.tech_pricing_plans} onChangeText={t => setTech({...tech, tech_pricing_plans: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Free Trial</Text>
                                    <Text style={styles.hint}>e.g. "14-day free trial, no credit card required"</Text>
                                    <TextInput style={styles.input} placeholder="Do you offer a trial or freemium plan?" placeholderTextColor="#555" value={tech.tech_free_trial} onChangeText={t => setTech({...tech, tech_free_trial: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Integrations</Text>
                                    <Text style={styles.hint}>e.g. "M-Pesa, Stripe, QuickBooks, Xero, Shopify, Slack, Zapier"</Text>
                                    <TextInput style={styles.input} placeholder="What does your product connect with?" placeholderTextColor="#555" value={tech.tech_integrations} onChangeText={t => setTech({...tech, tech_integrations: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Demo Booking Process</Text>
                                    <Text style={styles.hint}>e.g. "Book a 30-min live demo via Calendly — link sent on request" or "Reply to schedule a call"</Text>
                                    <TextInput style={styles.input} placeholder="How do prospects book a demo or trial?" placeholderTextColor="#555" value={tech.tech_demo_process} onChangeText={t => setTech({...tech, tech_demo_process: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Onboarding</Text>
                                    <Text style={styles.hint}>e.g. "Self-serve setup in 15 mins · Dedicated onboarding call for Pro+ · Data migration included for Enterprise"</Text>
                                    <TextInput style={styles.input} placeholder="How do new customers get started?" placeholderTextColor="#555" value={tech.tech_onboarding} onChangeText={t => setTech({...tech, tech_onboarding: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Support Channels</Text>
                                    <Text style={styles.hint}>e.g. "Email (24hr response) · In-app chat Mon-Fri 9am-6pm · WhatsApp for Enterprise"</Text>
                                    <TextInput style={styles.input} placeholder="How do customers get help?" placeholderTextColor="#555" value={tech.tech_support_channels} onChangeText={t => setTech({...tech, tech_support_channels: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Compliance & Security</Text>
                                    <Text style={styles.hint}>e.g. "PCI-DSS compliant · GDPR ready · KRA-approved for VAT · ISO 27001 certified"</Text>
                                    <TextInput style={styles.input} placeholder="Any certifications or compliance standards?" placeholderTextColor="#555" value={tech.tech_compliance} onChangeText={t => setTech({...tech, tech_compliance: t})} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Contract Terms</Text>
                                    <Text style={styles.hint}>e.g. "Month-to-month, cancel anytime · 20% discount on annual plans · No setup fees"</Text>
                                    <TextInput style={styles.input} placeholder="Billing cycle, lock-in, cancellation policy" placeholderTextColor="#555" value={tech.tech_contract_terms} onChangeText={t => setTech({...tech, tech_contract_terms: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <Text style={styles.label}>Customers / Case Studies</Text>
                                    <Text style={styles.hint}>e.g. "Used by 500+ businesses including Naivas, Java House, KPLC · Reduced invoicing time by 80%"</Text>
                                    <TextInput style={styles.input} placeholder="Notable customers or results you can share" placeholderTextColor="#555" value={tech.tech_case_studies} onChangeText={t => setTech({...tech, tech_case_studies: t})} multiline numberOfLines={2} />
                                </View>
                            </>
                        )}

                        {isGenericService && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="briefcase-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Service Details</Text>
                                </View>
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="list-outline" size={18} color="#25D366" />
                                        <Text style={styles.label}>Services & Pricing *</Text>
                                    </View>
                                    <Text style={styles.hint}>Add each service with its price and estimated duration</Text>
                                    <ListField items={productItems} onUpdate={setProductItems} placeholder="Service - price - duration" icon="timer-outline" />
                                </View>
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="location-outline" size={18} color="#25D366" />
                                        <Text style={styles.label}>Service Area *</Text>
                                    </View>
                                    <Text style={styles.hint}>e.g. "We cover Nairobi and surroundings within 20km · Travel fee applies outside CBD"</Text>
                                    <TextInput style={styles.input} placeholder="Where do you provide services?" placeholderTextColor="#555" value={knowledge.delivery_info} onChangeText={t => setKnowledge({...knowledge, delivery_info: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="people-outline" size={18} color="#25D366" />
                                        <Text style={styles.label}>Team / Specialists</Text>
                                    </View>
                                    <Text style={styles.hint}>e.g. "James - senior plumber (10 yrs exp) · Grace - electrician, solar specialist"</Text>
                                    <TextInput style={styles.input} placeholder="Who does the work and their specialties?" placeholderTextColor="#555" value={knowledge.staff_info} onChangeText={t => setKnowledge({...knowledge, staff_info: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="calendar-outline" size={18} color="#25D366" />
                                        <Text style={styles.label}>Booking Process *</Text>
                                    </View>
                                    <Text style={styles.hint}>e.g. "Book via WhatsApp · We confirm within 1 hour · Free quote given before any work starts"</Text>
                                    <TextInput style={styles.input} placeholder="How do clients book and what happens next?" placeholderTextColor="#555" value={knowledge.booking_process} onChangeText={t => setKnowledge({...knowledge, booking_process: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="flash-outline" size={18} color="#FF9800" />
                                        <Text style={styles.label}>Emergency / Same-Day Service</Text>
                                    </View>
                                    <Text style={styles.hint}>e.g. "Emergency callouts available 24/7 · Extra charge applies after 6pm and weekends"</Text>
                                    <TextInput style={styles.input} placeholder="Do you offer urgent or same-day service?" placeholderTextColor="#555" value={knowledge.pricing_info} onChangeText={t => setKnowledge({...knowledge, pricing_info: t})} multiline numberOfLines={2} />
                                </View>
                                <View style={styles.field}>
                                    <View style={styles.sectionHeader}>
                                        <Ionicons name="close-circle-outline" size={18} color="#FF9800" />
                                        <Text style={styles.label}>Cancellation Policy</Text>
                                    </View>
                                    <Text style={styles.hint}>e.g. "Cancel at least 24hrs before · Late cancellations charged 50% of job fee"</Text>
                                    <TextInput style={styles.input} placeholder="Your cancellation & rescheduling policy" placeholderTextColor="#555" value={knowledge.cancellation_policy} onChangeText={t => setKnowledge({...knowledge, cancellation_policy: t})} multiline numberOfLines={2} />
                                </View>
                            </>
                        )}

                        {/* Business Hours */}
                        <View style={styles.field}>
                            <Text style={styles.label}>
                                {isCreator ? 'Response Hours' : isRestaurant ? 'Opening Hours' : isRental ? 'Check-in Support Hours' : isFitness ? 'Studio Hours' : isHealthcare ? 'Clinic Hours' : 'Business Hours'}
                            </Text>
                            <Text style={styles.hint}>
                                {isCreator
                                    ? 'e.g. "I check DMs Mon-Fri 9am-5pm EAT"'
                                    : isRestaurant
                                    ? 'e.g. "Mon-Thu 11am-10pm · Fri-Sat 11am-midnight · Sun 12pm-9pm"'
                                    : isRental
                                    ? 'e.g. "Check-in support available 8am-10pm daily · Emergency line 24/7"'
                                    : isFitness
                                    ? 'e.g. "Mon-Fri 5:30am-9pm · Sat 7am-5pm · Sun 8am-2pm"'
                                    : isHealthcare
                                    ? 'e.g. "Mon-Fri 8am-6pm · Sat 9am-1pm · Closed Sunday"'
                                    : 'e.g. "Mon-Sat 8am-6pm · Sunday closed"'}
                            </Text>
                            <TextInput
                                style={styles.input}
                                placeholder={isCreator ? 'When do you respond to DMs?' : 'When are you open?'}
                                placeholderTextColor="#555"
                                value={knowledge.business_hours}
                                onChangeText={(text) => setKnowledge({ ...knowledge, business_hours: text })}
                            />
                        </View>

                        {/* Delivery - restaurant and general only; not for service/creator/retail(has own)/rental/tech */}
                        {(isRestaurant || (!isCreator && !isService && !isRetail && !isRental && !isTech)) && (
                            <View style={styles.field}>
                                <View style={styles.sectionHeader}>
                                    <Ionicons name="bicycle-outline" size={18} color="#25D366" />
                                    <Text style={styles.label}>{isRestaurant ? 'Food Delivery Areas & Costs' : 'Delivery Zones'}</Text>
                                </View>
                                <Text style={styles.hint}>
                                    {isRestaurant
                                        ? 'e.g. "CBD - KES 150 · Westlands - KES 200 · Karen - KES 350"'
                                        : 'Add each delivery area with cost'}
                                </Text>
                                <ListField
                                    items={deliveryItems}
                                    onUpdate={setDeliveryItems}
                                    placeholder={isRestaurant ? 'Area - delivery cost' : 'Area - delivery cost'}
                                    icon="location-outline"
                                />
                            </View>
                        )}

                        {/* Payment Methods */}
                        <View style={styles.field}>
                            <View style={styles.sectionHeader}>
                                <Ionicons name="wallet-outline" size={18} color="#25D366" />
                                <Text style={styles.label}>Payment Methods</Text>
                            </View>
                            <Text style={styles.hint}>Add how customers can pay you — include the actual number, email or account details</Text>

                            {/* Existing methods */}
                            {paymentMethods.map((pm, i) => {
                                const summary = getMethodSummary(pm);
                                const iconName = pm.name.toLowerCase().includes('mpesa') || pm.name.toLowerCase().includes('m-pesa') || pm.name.toLowerCase().includes('airtel') || pm.name.toLowerCase().includes('mtn') || pm.name.toLowerCase().includes('wave') || pm.name.toLowerCase().includes('mobile') ? 'phone-portrait' : pm.name.toLowerCase().includes('paypal') ? 'logo-paypal' : pm.name.toLowerCase().includes('bank') ? 'business' : pm.name.toLowerCase().includes('card') || pm.name.toLowerCase().includes('visa') || pm.name.toLowerCase().includes('stripe') ? 'card' : pm.name.toLowerCase().includes('bitcoin') || pm.name.toLowerCase().includes('crypto') ? 'logo-bitcoin' : 'cash';
                                return (
                                    <View key={i} style={styles.pmRow}>
                                        <View style={styles.pmRowIcon}>
                                            <Ionicons name={iconName as any} size={16} color="#25D366" />
                                        </View>
                                        <View style={{ flex: 1 }}>
                                            <Text style={styles.pmRowName}>{pm.name}</Text>
                                            {summary ? (
                                                <Text style={styles.pmRowDetails}>{summary}</Text>
                                            ) : (
                                                <Text style={[styles.pmRowDetails, { color: '#444', fontStyle: 'italic' }]}>No details added</Text>
                                            )}
                                        </View>
                                        <TouchableOpacity onPress={() => setPaymentMethods(paymentMethods.filter((_, idx) => idx !== i))}>
                                            <Ionicons name="close-circle" size={20} color="#FF6B6B" />
                                        </TouchableOpacity>
                                    </View>
                                );
                            })}

                            {/* Add form */}
                            {addingPayment ? (
                                <View style={styles.pmAddBox}>
                                    <Text style={styles.pmFieldLabel}>Payment Method Name</Text>
                                    <TextInput
                                        style={[styles.pmInput, { marginBottom: 10 }]}
                                        value={newPmName}
                                        onChangeText={setNewPmName}
                                        placeholder="e.g. M-Pesa, Bank Transfer, PayPal, Cash"
                                        placeholderTextColor="#555"
                                        autoCapitalize="words"
                                    />
                                    <Text style={styles.pmFieldLabel}>Payment Details</Text>
                                    <TextInput
                                        style={[styles.pmInput, { minHeight: 60, textAlignVertical: 'top' }]}
                                        value={newPmDetails}
                                        onChangeText={setNewPmDetails}
                                        placeholder="e.g. Send to 0712 345 678 (John) / Account: 1234567890, Equity Bank"
                                        placeholderTextColor="#555"
                                        multiline
                                        autoCapitalize="none"
                                    />
                                    <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
                                        <TouchableOpacity style={styles.pmCancelBtn} onPress={resetAddForm}>
                                            <Text style={{ color: '#888', fontSize: 14, fontWeight: '600' }}>Cancel</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={styles.pmSaveBtn}
                                            onPress={() => {
                                                const name = newPmName.trim();
                                                if (!name) return;
                                                if (paymentMethods.find(m => m.name.toLowerCase() === name.toLowerCase())) return;
                                                setPaymentMethods([...paymentMethods, { name, details: newPmDetails.trim() }]);
                                                resetAddForm();
                                            }}
                                        >
                                            <Text style={{ color: '#fff', fontSize: 14, fontWeight: '600' }}>Add</Text>
                                        </TouchableOpacity>
                                    </View>
                                </View>
                            ) : (
                                <TouchableOpacity style={styles.addButton} onPress={() => setAddingPayment(true)}>
                                    <Ionicons name="add-circle" size={20} color="#25D366" />
                                    <Text style={styles.addButtonText}>Add payment method</Text>
                                </TouchableOpacity>
                            )}
                        </View>

                        {/* FAQs */}
                        <View style={styles.field}>
                            <View style={styles.sectionHeader}>
                                <Ionicons name="chatbubble-ellipses-outline" size={18} color="#25D366" />
                                <Text style={styles.label}>Common Questions</Text>
                            </View>
                            <Text style={styles.hint}>
                                {isCreator
                                    ? 'e.g. "Do you do gifting collabs? / Do you negotiate rates?"'
                                    : isFitness
                                    ? 'e.g. "Do I need to book in advance? / What should I bring? / Can I pause my membership?"'
                                    : isHealthcare
                                    ? 'e.g. "Do you accept walk-ins? / How long is a consultation? / Do you accept NHIF?"'
                                    : isRestaurant
                                    ? 'e.g. "Can I make a group reservation? / Do you have parking? / Is there a kids menu?"'
                                    : isSalon
                                    ? 'e.g. "How far in advance should I book? / Do you do natural hair? / Can I walk in?"'
                                    : isRetail
                                    ? 'e.g. "Do you deliver countrywide? / Can I return an item? / How long does delivery take?"'
                                    : isRental
                                    ? 'e.g. "Is parking available? / How do I check in? / Is the pool heated?"'
                                    : isTech
                                    ? 'e.g. "Is there a free trial? / Do you offer training? / How do I cancel my plan?"'
                                    : isGenericService
                                    ? 'e.g. "Do you offer emergency callouts? / How soon can you come? / Do you give free quotes?"'
                                    : 'Add questions customers always ask and your answers'}
                            </Text>
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

                        {/* Offers */}
                        <View style={styles.field}>
                            <View style={styles.sectionHeader}>
                                <Ionicons name="gift-outline" size={18} color="#25D366" />
                                <Text style={styles.label}>{isCreator ? 'Current Packages / Promotions' : 'Current Offers'}</Text>
                            </View>
                            <Text style={styles.hint}>
                                {isCreator
                                    ? 'e.g. "Q1 bundle: Reel + 5 stories for $500 (limited spots)"'
                                    : isFitness
                                    ? 'e.g. "First month 50% off, 2-month deal, refer a friend and get 1 free class"'
                                    : isHealthcare
                                    ? 'e.g. "Free BMI check for new patients, 20% off dental cleanings this month"'
                                    : isRestaurant
                                    ? 'e.g. "Happy hour 4–7pm 50% off drinks, lunch special KES 600 (main + drink)"'
                                    : isSalon
                                    ? 'e.g. "New client 20% off first visit, refer a friend and get a free deep condition"'
                                    : isRetail
                                    ? 'e.g. "Buy 2 get 1 free, 15% off orders over KES 5,000, free delivery this week"'
                                    : isRental
                                    ? 'e.g. "7-night stay: 15% discount, last-minute weekend deal available now"'
                                    : isTech
                                    ? 'e.g. "2 months free on annual plan, free onboarding for teams of 5+"'
                                    : isGenericService
                                    ? 'e.g. "10% off first callout, free quote this week, seasonal tune-up special"'
                                    : 'Add active promotions or deals'}
                            </Text>
                            <ListField
                                items={offerItems}
                                onUpdate={setOfferItems}
                                placeholder={isCreator ? 'Package or promotion' : 'Offer or promotion'}
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
    // Payment methods
    pmRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#1A2942',
        borderRadius: 10,
        padding: 12,
        marginBottom: 8,
        gap: 10,
        borderWidth: 1,
        borderColor: '#2A3952',
    },
    pmRowIcon: {
        width: 34,
        height: 34,
        borderRadius: 8,
        backgroundColor: '#0F2D1A',
        justifyContent: 'center',
        alignItems: 'center',
    },
    pmRowName: {
        fontSize: 14,
        fontWeight: '600',
        color: '#FFFFFF',
        marginBottom: 2,
    },
    pmRowDetails: {
        fontSize: 12,
        color: '#8B9DC3',
    },
    pmAddBox: {
        backgroundColor: '#1A2942',
        borderRadius: 12,
        padding: 14,
        borderWidth: 1,
        borderColor: '#2A3952',
        marginTop: 4,
    },
    pmPresetLabel: {
        fontSize: 11,
        color: '#6B7D99',
        fontWeight: '600',
        marginBottom: 8,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    pmChipRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 7,
        marginBottom: 12,
    },
    pmChip: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingVertical: 5,
        paddingHorizontal: 10,
        borderRadius: 16,
        borderWidth: 1.5,
        borderColor: '#2A3952',
        backgroundColor: '#0F1D32',
    },
    pmChipActive: {
        borderColor: '#25D366',
        backgroundColor: '#0F2D1A',
    },
    pmChipText: {
        fontSize: 12,
        color: '#6B7D99',
        fontWeight: '500',
    },
    pmInput: {
        backgroundColor: '#0F1D32',
        borderWidth: 1,
        borderColor: '#2A3952',
        borderRadius: 9,
        paddingHorizontal: 12,
        paddingVertical: 10,
        fontSize: 14,
        color: '#FFFFFF',
    },
    pmFieldLabel: {
        fontSize: 12,
        color: '#8B9DC3',
        fontWeight: '600',
        marginBottom: 4,
    },
    pmCancelBtn: {
        flex: 1,
        paddingVertical: 10,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: '#2A3952',
        alignItems: 'center',
    },
    pmSaveBtn: {
        flex: 1,
        paddingVertical: 10,
        borderRadius: 8,
        backgroundColor: '#25D366',
        alignItems: 'center',
    },
    // Business type selector
    typeGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 10,
        marginTop: 4,
    },
    typeCard: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 12,
        paddingHorizontal: 14,
        borderRadius: 12,
        borderWidth: 1.5,
        borderColor: '#2A3952',
        backgroundColor: '#1A2942',
        minWidth: 90,
        gap: 6,
    },
    typeCardActive: {
        borderColor: '#25D366',
        backgroundColor: '#0F2D1A',
    },
    typeLabel: {
        fontSize: 12,
        fontWeight: '500',
        color: '#6B7D99',
    },
    typeLabelActive: {
        color: '#25D366',
        fontWeight: '700',
    },
    // Platform chips
    platformGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
        marginTop: 4,
    },
    platformChip: {
        paddingVertical: 7,
        paddingHorizontal: 14,
        borderRadius: 20,
        borderWidth: 1.5,
        borderColor: '#2A3952',
        backgroundColor: '#1A2942',
    },
    platformChipActive: {
        borderColor: '#25D366',
        backgroundColor: '#0F2D1A',
    },
    platformChipText: {
        fontSize: 13,
        color: '#6B7D99',
        fontWeight: '500',
    },
    platformChipTextActive: {
        color: '#25D366',
        fontWeight: '700',
    },
    // Section divider
    sectionDivider: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        marginBottom: 20,
        marginTop: 4,
        paddingVertical: 10,
        paddingHorizontal: 14,
        backgroundColor: '#1A2942',
        borderRadius: 10,
        borderLeftWidth: 3,
        borderLeftColor: '#FFD700',
    },
    sectionDividerText: {
        fontSize: 13,
        fontWeight: '700',
        color: '#FFD700',
        letterSpacing: 0.5,
        textTransform: 'uppercase',
    },
});
