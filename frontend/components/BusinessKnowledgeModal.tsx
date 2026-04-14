import React, { useState, useEffect, useRef } from 'react';
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
    Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { settingsAPI, apiClient } from '../context/api';

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

const BUSINESS_TYPES = [
    { key: 'retail',      label: 'Retail / Shop',        icon: 'cart-outline' },
    { key: 'wholesale',   label: 'Wholesale / B2B',      icon: 'cube-outline' },
    { key: 'restaurant',  label: 'Restaurant / Café',    icon: 'restaurant-outline' },
    { key: 'food',        label: 'Food Delivery',        icon: 'fast-food-outline' },
    { key: 'bakery',      label: 'Bakery',               icon: 'cafe-outline' },
    { key: 'grocery',     label: 'Grocery',              icon: 'basket-outline' },
    { key: 'salon',       label: 'Salon & Beauty',       icon: 'color-palette-outline' },
    { key: 'spa',         label: 'Spa & Wellness',       icon: 'flower-outline' },
    { key: 'services',    label: 'Services / Freelance', icon: 'construct-outline' },
    { key: 'repair',      label: 'Repair',               icon: 'build-outline' },
    { key: 'cleaning',    label: 'Cleaning',             icon: 'water-outline' },
    { key: 'fitness',     label: 'Gym & Fitness',        icon: 'barbell-outline' },
    { key: 'events',      label: 'Events & Photos',      icon: 'camera-outline' },
    { key: 'healthcare',  label: 'Healthcare',           icon: 'medkit-outline' },
    { key: 'rental',      label: 'Rental / Airbnb',      icon: 'home-outline' },
    { key: 'creator',     label: 'Creator / Digital',    icon: 'videocam-outline' },
    { key: 'general',     label: 'General / Other',      icon: 'storefront-outline' },
];

const getTypeConfig = (type: string) => {
    const configs: Record<string, any> = {
        retail:     { servicesLabel: 'Products & Prices',            servicesPlaceholder: 'Product - price (e.g. T-shirt - $15)',              servicesIcon: 'cart-outline',        showDelivery: true,  deliveryLabel: 'Delivery Zones',    deliveryPlaceholder: 'Area - delivery cost',          hoursLabel: 'Business Hours',     aboutLabel: 'About Your Shop' },
        wholesale:  { servicesLabel: 'Products & Wholesale Prices',  servicesPlaceholder: 'Product - min qty - price (e.g. T-shirts - 12pcs - $60)', servicesIcon: 'cube-outline',   showDelivery: true,  deliveryLabel: 'Delivery Zones',    deliveryPlaceholder: 'Area - delivery cost',          hoursLabel: 'Business Hours',     aboutLabel: 'About Your Wholesale Business' },
        restaurant: { servicesLabel: 'Menu Items & Prices',          servicesPlaceholder: 'Item - price (e.g. Burger - $8)',                  servicesIcon: 'restaurant-outline',  showDelivery: true,  deliveryLabel: 'Delivery Zones',    deliveryPlaceholder: 'Area - delivery fee',           hoursLabel: 'Opening Hours',      aboutLabel: 'About Your Restaurant' },
        food:       { servicesLabel: 'Menu Items & Prices',          servicesPlaceholder: 'Item - price (e.g. Rice & Stew - $5)',             servicesIcon: 'fast-food-outline',   showDelivery: true,  deliveryLabel: 'Delivery Areas',    deliveryPlaceholder: 'Area - delivery fee',           hoursLabel: 'Operating Hours',    aboutLabel: 'About Your Food Business' },
        bakery:     { servicesLabel: 'Products & Prices',            servicesPlaceholder: 'Item - price (e.g. Birthday Cake - $30)',          servicesIcon: 'cafe-outline',        showDelivery: true,  deliveryLabel: 'Delivery Zones',    deliveryPlaceholder: 'Area - delivery fee',           hoursLabel: 'Bakery Hours',       aboutLabel: 'About Your Bakery' },
        grocery:    { servicesLabel: 'Products & Prices',            servicesPlaceholder: 'Product - price (e.g. 1kg Sugar - $1.50)',         servicesIcon: 'basket-outline',      showDelivery: true,  deliveryLabel: 'Delivery Areas',    deliveryPlaceholder: 'Area - delivery fee',           hoursLabel: 'Store Hours',        aboutLabel: 'About Your Store' },
        salon:      { servicesLabel: 'Services & Prices',            servicesPlaceholder: 'Service - price (e.g. Haircut - $20)',             servicesIcon: 'cut-outline',         showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Business Hours',     aboutLabel: 'About Your Salon' },
        spa:        { servicesLabel: 'Treatments & Prices',          servicesPlaceholder: 'Treatment - duration - price (e.g. Massage - 60min - $70)', servicesIcon: 'flower-outline', showDelivery: false, deliveryLabel: '',             deliveryPlaceholder: '',                              hoursLabel: 'Spa Hours',          aboutLabel: 'About Your Spa' },
        services:   { servicesLabel: 'Services & Rates',             servicesPlaceholder: 'Service - rate (e.g. Web design - $500)',          servicesIcon: 'construct-outline',   showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Working Hours',      aboutLabel: 'About Your Business' },
        repair:     { servicesLabel: 'Services & Rates',             servicesPlaceholder: 'Service - rate (e.g. Phone screen repair - $40)',  servicesIcon: 'build-outline',       showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Working Hours',      aboutLabel: 'About Your Repair Business' },
        cleaning:   { servicesLabel: 'Packages & Prices',            servicesPlaceholder: 'Package - price (e.g. 2BR Deep Clean - $80)',      servicesIcon: 'water-outline',       showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Operating Hours',    aboutLabel: 'About Your Cleaning Business' },
        fitness:    { servicesLabel: 'Classes & Memberships',        servicesPlaceholder: 'Class / plan - price (e.g. Monthly membership - $40)', servicesIcon: 'barbell-outline', showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Gym / Studio Hours', aboutLabel: 'About Your Fitness Business' },
        events:     { servicesLabel: 'Packages & Rates',             servicesPlaceholder: 'Package - price (e.g. Wedding Photography - $800)', servicesIcon: 'camera-outline',     showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Availability',       aboutLabel: 'About Your Business' },
        healthcare: { servicesLabel: 'Consultations & Fees',         servicesPlaceholder: 'Consultation - fee (e.g. General Consult - $50)',  servicesIcon: 'medkit-outline',      showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Clinic Hours',       aboutLabel: 'About Your Practice' },
        rental:     { servicesLabel: 'Properties / Items & Rates',   servicesPlaceholder: 'Item - rate (e.g. 2BR Apt - $80/night)',           servicesIcon: 'home-outline',        showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Availability Hours', aboutLabel: 'About Your Rental Business' },
        creator:    { servicesLabel: '',                             servicesPlaceholder: '',                                                 servicesIcon: '',                    showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Response Hours',     aboutLabel: 'About You' },
        general:    { servicesLabel: 'Services or Products',         servicesPlaceholder: 'Service or product - price',                       servicesIcon: 'storefront-outline',  showDelivery: false, deliveryLabel: '',                  deliveryPlaceholder: '',                              hoursLabel: 'Business Hours',     aboutLabel: 'About Your Business' },
    };
    return configs[type] ?? configs.general;
};

const PLATFORMS = ['Instagram', 'TikTok', 'YouTube', 'Twitter/X', 'Facebook', 'Snapchat', 'LinkedIn', 'Podcast'];

export default function BusinessKnowledgeModal({
    visible,
    onClose,
}: BusinessKnowledgeModalProps) {
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [isGeneratingAbout, setIsGeneratingAbout] = useState(false);
    
    // Ref for about TextInput to control scroll position
    const aboutInputRef = useRef<TextInput>(null);
    const [businessType, setBusinessType] = useState('general');
    const [knowledge, setKnowledge] = useState({
        business_description: '',
        business_location: '',
        products_services: '',
        pricing_info: '',
        business_hours: '',
        delivery_info: '',
        faqs: '',
        special_offers: '',
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
    const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);

    // Payment methods state
    const [paymentMethods, setPaymentMethods] = useState<{name:string;details:string}[]>([]);
    const [addingPayment, setAddingPayment] = useState(false);
    const [newPmName, setNewPmName] = useState('');
    const [newPmDetails, setNewPmDetails] = useState('');
    const [customPmName, setCustomPmName] = useState('');

    // Restaurant-specific state
    const [restaurantModes, setRestaurantModes] = useState({ dine_in: true, delivery: true, takeout: true });
    const [restaurantTableRange, setRestaurantTableRange] = useState('');
    const [restaurantAvgWait, setRestaurantAvgWait] = useState('');
    const [restaurantMinDelivery, setRestaurantMinDelivery] = useState('');

    // Retail delivery state
    const [retailHasDelivery, setRetailHasDelivery] = useState(true);
    const [retailHasPickup, setRetailHasPickup] = useState(true);
    const [retailDeliveryFee, setRetailDeliveryFee] = useState('');
    const [retailFreeDeliveryAbove, setRetailFreeDeliveryAbove] = useState('');

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
            const [data, settings] = await Promise.all([
                settingsAPI.getBusinessKnowledge(),
                settingsAPI.getSettings(),
            ]);
            if (data) {
                setKnowledge({
                    business_description: data.business_description || '',
                    business_location: data.business_location || '',
                    products_services: data.products_services || '',
                    pricing_info: data.pricing_info || '',
                    business_hours: data.business_hours || '',
                    delivery_info: data.delivery_info || '',
                    faqs: data.faqs || '',
                    special_offers: data.special_offers || '',
                });
                setBusinessType(data.business_type || settings.business_type || 'general');
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
                // Load payment methods
                if (data.payment_methods && data.payment_methods.length > 0) {
                    setPaymentMethods(data.payment_methods.map((m: any) =>
                        typeof m === 'string' ? { name: m, details: '' } : m
                    ));
                }
                // Restaurant fields
                setRestaurantModes({
                    dine_in:  data.restaurant_has_dine_in  ?? true,
                    delivery: data.restaurant_has_delivery ?? true,
                    takeout:  data.restaurant_has_takeout  ?? true,
                });
                setRestaurantTableRange(data.restaurant_table_range || '');
                setRestaurantAvgWait(data.restaurant_avg_wait || '');
                setRestaurantMinDelivery(data.restaurant_min_delivery || '');
                // Retail fields
                setRetailHasDelivery(data.retail_has_delivery !== false);
                setRetailHasPickup(data.retail_has_pickup !== false);
                setRetailDeliveryFee(data.retail_delivery_fee || '');
                setRetailFreeDeliveryAbove(data.retail_free_delivery_above || '');

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

    const PM_PRESETS = [
        { name: 'M-Pesa', icon: 'phone-portrait', detailLabel: 'Phone Number', placeholder: 'e.g. 0712 345 678', kb: 'phone-pad' },
        { name: 'PayPal', icon: 'logo-paypal', detailLabel: 'PayPal Email', placeholder: 'e.g. pay@youremail.com', kb: 'email-address' },
        { name: 'Bank Transfer', icon: 'business', detailLabel: 'Account / Bank Name', placeholder: 'e.g. KCB 1234567890', kb: 'default' },
        { name: 'Cash', icon: 'cash', detailLabel: '', placeholder: '', kb: 'default' },
        { name: 'Visa/Card', icon: 'card', detailLabel: 'POS / Reference', placeholder: 'e.g. POS terminal', kb: 'default' },
        { name: 'Airtel Money', icon: 'phone-portrait', detailLabel: 'Phone Number', placeholder: 'e.g. 0733 123 456', kb: 'phone-pad' },
        { name: 'Stripe', icon: 'card', detailLabel: 'Payment Link', placeholder: 'https://buy.stripe.com/...', kb: 'default' },
        { name: 'Bitcoin/Crypto', icon: 'logo-bitcoin', detailLabel: 'Wallet Address', placeholder: 'e.g. 1A1zP1eP5...', kb: 'default' },
        { name: 'Chipper Cash', icon: 'wallet', detailLabel: 'Username / Phone', placeholder: 'e.g. @yourname', kb: 'default' },
        { name: 'Wave', icon: 'wallet', detailLabel: 'Phone Number', placeholder: 'e.g. +221 77 000 0000', kb: 'phone-pad' },
    ];

    const selectedPreset = PM_PRESETS.find(p => p.name === newPmName);

    const handleSave = async () => {
        setSaving(true);
        const updatedKnowledge = {
            ...knowledge,
            products_services: itemsToString(productItems),
            delivery_info: itemsToString(deliveryItems),
            faqs: faqList.map(f => `Q: ${f.question}\nA: ${f.answer}`).join('\n'),
            special_offers: itemsToString(offerItems),
            business_type: businessType,
            // Restaurant fields
            restaurant_has_dine_in:  restaurantModes.dine_in,
            restaurant_has_delivery: restaurantModes.delivery,
            restaurant_has_takeout:  restaurantModes.takeout,
            restaurant_table_range:  restaurantTableRange,
            restaurant_avg_wait:     restaurantAvgWait,
            restaurant_min_delivery: restaurantMinDelivery,
            // Retail fields
            retail_has_delivery:        retailHasDelivery,
            retail_has_pickup:          retailHasPickup,
            retail_delivery_fee:        retailDeliveryFee,
            retail_free_delivery_above: retailFreeDeliveryAbove,
            ...creator,
            creator_platforms: selectedPlatforms.join(', '),
        };
        try {
            await Promise.all([
                settingsAPI.updateBusinessKnowledge(updatedKnowledge),
                apiClient.put('/settings', { payment_methods: paymentMethods }),
            ]);
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

    // AI Description Generation for Business About
    const handleAIGenerateAbout = async () => {
        setIsGeneratingAbout(true);
        try {
            const result = await settingsAPI.generateBusinessAbout({
                business_type: businessType,
                mode: 'generate'
            });
            
            if (result.description) {
                setKnowledge({ ...knowledge, business_description: result.description });
                // Scroll to top of description after setting it
                setTimeout(() => {
                    aboutInputRef.current?.setNativeProps({
                        selection: { start: 0, end: 0 }
                    });
                }, 100);
            }
        } catch (error: any) {
            console.error('AI generation error:', error);
            Alert.alert(
                'AI Generation Failed',
                error.response?.data?.detail || 'Unable to generate description right now. Please try writing it manually.',
                [{ text: 'OK' }]
            );
        } finally {
            setIsGeneratingAbout(false);
        }
    };

    const handleAIImproveAbout = async () => {
        if (!knowledge.business_description.trim()) {
            handleAIGenerateAbout();
            return;
        }

        setIsGeneratingAbout(true);
        try {
            const result = await settingsAPI.generateBusinessAbout({
                business_type: businessType,
                current_description: knowledge.business_description,
                mode: 'improve'
            });
            
            if (result.description) {
                setKnowledge({ ...knowledge, business_description: result.description });
                // Scroll to top of description after setting it
                setTimeout(() => {
                    aboutInputRef.current?.setNativeProps({
                        selection: { start: 0, end: 0 }
                    });
                }, 100);
            }
        } catch (error: any) {
            console.error('AI improvement error:', error);
            Alert.alert(
                'AI Improvement Failed',
                error.response?.data?.detail || 'Unable to improve description right now. Please try editing it manually.',
                [{ text: 'OK' }]
            );
        } finally {
            setIsGeneratingAbout(false);
        }
    };

    const isCreator     = businessType === 'creator';
    const isRestaurant  = businessType === 'restaurant';
    const isRetail      = ['retail', 'wholesale', 'grocery'].includes(businessType);
    const typeConfig = getTypeConfig(businessType);

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

                        {/* Business Type Selector */}
                        <View style={styles.field}>
                            <Text style={styles.label}>Business Type</Text>
                            <Text style={styles.hint}>Select the type that best describes you</Text>
                            <View style={styles.typeGrid}>
                                {BUSINESS_TYPES.map(bt => (
                                    <TouchableOpacity
                                        key={bt.key}
                                        style={[styles.typeCard, businessType === bt.key && styles.typeCardActive]}
                                        onPress={() => setBusinessType(bt.key)}
                                    >
                                        <Ionicons
                                            name={bt.icon as any}
                                            size={22}
                                            color={businessType === bt.key ? '#25D366' : '#6B7D99'}
                                        />
                                        <Text style={[styles.typeLabel, businessType === bt.key && styles.typeLabelActive]}>
                                            {bt.label}
                                        </Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        </View>

                        {/* About */}
                        <View style={styles.field}>
                            <View style={styles.labelRow}>
                                <Text style={styles.label}>{typeConfig.aboutLabel}</Text>
                                <TouchableOpacity 
                                    style={styles.aiGenerateBtn}
                                    onPress={handleAIGenerateAbout}
                                    disabled={isGeneratingAbout}
                                >
                                    <Ionicons 
                                        name={isGeneratingAbout ? "sparkles-outline" : "sparkles"} 
                                        size={16} 
                                        color={isGeneratingAbout ? "#8899AA" : "#25D366"} 
                                    />
                                    <Text style={styles.aiGenerateBtnText}>
                                        {isGeneratingAbout ? "Generating..." : "AI Generate"}
                                    </Text>
                                </TouchableOpacity>
                            </View>
                            <TextInput
                                ref={aboutInputRef}
                                style={[
                                    styles.input,
                                    {
                                        minHeight: 80,
                                        maxHeight: 200,
                                        fontSize: 15,
                                        lineHeight: 22,
                                    }
                                ]}
                                placeholder={isCreator ? 'Who are you and what do you create?' : 'What does your business do?'}
                                placeholderTextColor="#555"
                                value={knowledge.business_description}
                                onChangeText={(text) => setKnowledge({ ...knowledge, business_description: text })}
                                multiline
                                scrollEnabled={true}
                            />
                            {knowledge.business_description && (
                                <TouchableOpacity 
                                    style={styles.aiImproveBtn}
                                    onPress={handleAIImproveAbout}
                                    disabled={isGeneratingAbout}
                                >
                                    <Ionicons name="refresh-outline" size={14} color="#25D366" />
                                    <Text style={styles.aiImproveBtnText}>Improve with AI</Text>
                                </TouchableOpacity>
                            )}
                        </View>

                        {/* ── RESTAURANT FIELDS ── */}
                        {isRestaurant && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="restaurant" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Restaurant Setup</Text>
                                </View>

                                {/* Order Modes */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Order Modes</Text>
                                    <Text style={styles.hint}>Choose which order types your restaurant accepts</Text>

                                    <View style={styles.toggleRow}>
                                        <View style={styles.toggleInfo}>
                                            <Ionicons name="people-outline" size={18} color="#4A90D9" />
                                            <View style={{ marginLeft: 10 }}>
                                                <Text style={styles.toggleLabel}>Dine-in</Text>
                                                <Text style={styles.toggleDesc}>Customers order at the table</Text>
                                            </View>
                                        </View>
                                        <Switch
                                            value={restaurantModes.dine_in}
                                            onValueChange={v => setRestaurantModes(m => ({ ...m, dine_in: v }))}
                                            trackColor={{ false: '#1A2942', true: '#25D366' }}
                                            thumbColor="#fff"
                                        />
                                    </View>

                                    <View style={styles.toggleRow}>
                                        <View style={styles.toggleInfo}>
                                            <Ionicons name="bicycle-outline" size={18} color="#F59E0B" />
                                            <View style={{ marginLeft: 10 }}>
                                                <Text style={styles.toggleLabel}>Delivery</Text>
                                                <Text style={styles.toggleDesc}>Deliver to customer's address</Text>
                                            </View>
                                        </View>
                                        <Switch
                                            value={restaurantModes.delivery}
                                            onValueChange={v => setRestaurantModes(m => ({ ...m, delivery: v }))}
                                            trackColor={{ false: '#1A2942', true: '#25D366' }}
                                            thumbColor="#fff"
                                        />
                                    </View>

                                    <View style={styles.toggleRow}>
                                        <View style={styles.toggleInfo}>
                                            <Ionicons name="bag-handle-outline" size={18} color="#9B59B6" />
                                            <View style={{ marginLeft: 10 }}>
                                                <Text style={styles.toggleLabel}>Takeout / Pickup</Text>
                                                <Text style={styles.toggleDesc}>Customer collects from restaurant</Text>
                                            </View>
                                        </View>
                                        <Switch
                                            value={restaurantModes.takeout}
                                            onValueChange={v => setRestaurantModes(m => ({ ...m, takeout: v }))}
                                            trackColor={{ false: '#1A2942', true: '#25D366' }}
                                            thumbColor="#fff"
                                        />
                                    </View>
                                </View>

                                {/* Table Range — only if dine-in enabled */}
                                {restaurantModes.dine_in && (
                                    <View style={styles.field}>
                                        <Text style={styles.label}>Table Numbers</Text>
                                        <Text style={styles.hint}>e.g. "Tables 1–20" or "A1–A10, B1–B10"</Text>
                                        <TextInput
                                            style={styles.input}
                                            placeholder="What table numbers do you have?"
                                            placeholderTextColor="#555"
                                            value={restaurantTableRange}
                                            onChangeText={setRestaurantTableRange}
                                        />
                                    </View>
                                )}

                                {/* Avg Wait / Prep Time */}
                                <View style={styles.field}>
                                    <Text style={styles.label}>Avg. Preparation Time</Text>
                                    <Text style={styles.hint}>e.g. "15–20 minutes" — shown to customer after ordering</Text>
                                    <TextInput
                                        style={styles.input}
                                        placeholder="How long does food take to prepare?"
                                        placeholderTextColor="#555"
                                        value={restaurantAvgWait}
                                        onChangeText={setRestaurantAvgWait}
                                    />
                                </View>

                                {/* Min Delivery Amount — only if delivery enabled */}
                                {restaurantModes.delivery && (
                                    <View style={styles.field}>
                                        <Text style={styles.label}>Minimum Delivery Order</Text>
                                        <Text style={styles.hint}>e.g. "$10 minimum" — AI will mention this to delivery customers</Text>
                                        <TextInput
                                            style={styles.input}
                                            placeholder="Minimum order amount for delivery?"
                                            placeholderTextColor="#555"
                                            value={restaurantMinDelivery}
                                            onChangeText={setRestaurantMinDelivery}
                                        />
                                    </View>
                                )}

                                <View style={styles.sectionDivider}>
                                    <Ionicons name="storefront-outline" size={16} color="#6B7D99" />
                                    <Text style={[styles.sectionDividerText, { color: '#6B7D99' }]}>Menu & General Info</Text>
                                </View>
                            </>
                        )}

                        {/* ── RETAIL DELIVERY FIELDS ── */}
                        {isRetail && (
                            <>
                                <View style={styles.sectionDivider}>
                                    <Ionicons name="car-outline" size={16} color="#25D366" />
                                    <Text style={styles.sectionDividerText}>Delivery & Shipping</Text>
                                </View>

                                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10 }}>
                                    <View style={{ flex: 1, marginRight: 12 }}>
                                        <Text style={{ color: '#ccc', fontSize: 14 }}>Offer Delivery</Text>
                                        <Text style={{ fontSize: 11, color: '#555', marginTop: 2 }}>AI will collect delivery address and add fee</Text>
                                    </View>
                                    <Switch value={retailHasDelivery} onValueChange={setRetailHasDelivery} trackColor={{ false: '#333', true: '#1A3A2A' }} thumbColor={retailHasDelivery ? '#25D366' : '#666'} />
                                </View>

                                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10 }}>
                                    <View style={{ flex: 1, marginRight: 12 }}>
                                        <Text style={{ color: '#ccc', fontSize: 14 }}>Offer Pickup</Text>
                                        <Text style={{ fontSize: 11, color: '#555', marginTop: 2 }}>AI will offer pickup from your location</Text>
                                    </View>
                                    <Switch value={retailHasPickup} onValueChange={setRetailHasPickup} trackColor={{ false: '#333', true: '#1A3A2A' }} thumbColor={retailHasPickup ? '#25D366' : '#666'} />
                                </View>

                                {retailHasDelivery && (
                                    <View style={styles.field}>
                                        <Text style={styles.label}>Delivery Fee</Text>
                                        <Text style={styles.hint}>Fixed fee added to every delivery order</Text>
                                        <TextInput
                                            style={styles.input}
                                            placeholder="e.g. 200"
                                            placeholderTextColor="#555"
                                            keyboardType="numeric"
                                            value={retailDeliveryFee}
                                            onChangeText={setRetailDeliveryFee}
                                        />
                                    </View>
                                )}

                                {retailHasDelivery && (
                                    <View style={styles.field}>
                                        <Text style={styles.label}>Free Delivery Above</Text>
                                        <Text style={styles.hint}>Order total threshold — fee waived automatically</Text>
                                        <TextInput
                                            style={styles.input}
                                            placeholder="e.g. 2000"
                                            placeholderTextColor="#555"
                                            keyboardType="numeric"
                                            value={retailFreeDeliveryAbove}
                                            onChangeText={setRetailFreeDeliveryAbove}
                                        />
                                    </View>
                                )}
                            </>
                        )}

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

                        {/* ── STANDARD FIELDS (shown for all non-creator types) ── */}
                        {!isCreator && (
                            <View style={styles.field}>
                                <View style={styles.sectionHeader}>
                                    <Ionicons name={typeConfig.servicesIcon as any} size={18} color="#25D366" />
                                    <Text style={styles.label}>{typeConfig.servicesLabel}</Text>
                                </View>
                                <ListField
                                    items={productItems}
                                    onUpdate={setProductItems}
                                    placeholder={typeConfig.servicesPlaceholder}
                                    icon={typeConfig.servicesIcon}
                                />
                            </View>
                        )}

                        {/* Location / Address */}
                        <View style={styles.field}>
                            <Text style={styles.label}>Location / Address</Text>
                            <Text style={styles.hint}>AI shares this when customers ask "where are you located?"</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="e.g. Westlands, Nairobi — Shop 4, ABC Mall"
                                placeholderTextColor="#555"
                                value={knowledge.business_location}
                                onChangeText={(text) => setKnowledge({ ...knowledge, business_location: text })}
                            />
                        </View>

                        {/* Business Hours */}
                        <View style={styles.field}>
                            <Text style={styles.label}>{typeConfig.hoursLabel}</Text>
                            <Text style={styles.hint}>e.g. "Mon–Sat 8am–6pm, Sunday closed"</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="When are you open / available?"
                                placeholderTextColor="#555"
                                value={knowledge.business_hours}
                                onChangeText={(text) => setKnowledge({ ...knowledge, business_hours: text })}
                            />
                        </View>

                        {/* Delivery - only for types that do delivery */}
                        {typeConfig.showDelivery && (
                            <View style={styles.field}>
                                <View style={styles.sectionHeader}>
                                    <Ionicons name="bicycle-outline" size={18} color="#25D366" />
                                    <Text style={styles.label}>{typeConfig.deliveryLabel}</Text>
                                </View>
                                <Text style={styles.hint}>Add each delivery area with cost</Text>
                                <ListField
                                    items={deliveryItems}
                                    onUpdate={setDeliveryItems}
                                    placeholder={typeConfig.deliveryPlaceholder}
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
                            {paymentMethods.map((pm, i) => (
                                <View key={i} style={styles.pmRow}>
                                    <View style={styles.pmRowIcon}>
                                        <Ionicons
                                            name={pm.name.toLowerCase().includes('mpesa') || pm.name.toLowerCase().includes('m-pesa') || pm.name.toLowerCase().includes('airtel') || pm.name.toLowerCase().includes('wave') || pm.name.toLowerCase().includes('mobile') ? 'phone-portrait' : pm.name.toLowerCase().includes('paypal') ? 'logo-paypal' : pm.name.toLowerCase().includes('bank') ? 'business' : pm.name.toLowerCase().includes('card') || pm.name.toLowerCase().includes('visa') || pm.name.toLowerCase().includes('stripe') ? 'card' : pm.name.toLowerCase().includes('bitcoin') || pm.name.toLowerCase().includes('crypto') ? 'logo-bitcoin' : 'cash'}
                                            size={16} color="#25D366"
                                        />
                                    </View>
                                    <View style={{ flex: 1 }}>
                                        <Text style={styles.pmRowName}>{pm.name}</Text>
                                        {pm.details ? <Text style={styles.pmRowDetails}>{pm.details}</Text> : <Text style={[styles.pmRowDetails, { color: '#444', fontStyle: 'italic' }]}>No details added</Text>}
                                    </View>
                                    {paymentMethods.length > 0 && (
                                        <TouchableOpacity onPress={() => setPaymentMethods(paymentMethods.filter((_, idx) => idx !== i))}>
                                            <Ionicons name="close-circle" size={20} color="#FF6B6B" />
                                        </TouchableOpacity>
                                    )}
                                </View>
                            ))}

                            {/* Add form */}
                            {addingPayment ? (
                                <View style={styles.pmAddBox}>
                                    {/* Preset chips */}
                                    <Text style={styles.pmPresetLabel}>Select or type a method:</Text>
                                    <View style={styles.pmChipRow}>
                                        {PM_PRESETS.filter(p => !paymentMethods.find(m => m.name === p.name)).map(p => (
                                            <TouchableOpacity
                                                key={p.name}
                                                style={[styles.pmChip, newPmName === p.name && styles.pmChipActive]}
                                                onPress={() => { setNewPmName(p.name); setCustomPmName(''); setNewPmDetails(''); }}
                                            >
                                                <Ionicons name={p.icon as any} size={13} color={newPmName === p.name ? '#25D366' : '#6B7D99'} />
                                                <Text style={[styles.pmChipText, newPmName === p.name && { color: '#25D366' }]}>{p.name}</Text>
                                            </TouchableOpacity>
                                        ))}
                                    </View>

                                    {/* Custom name */}
                                    <TextInput
                                        style={styles.pmInput}
                                        value={newPmName || customPmName}
                                        onChangeText={t => { setCustomPmName(t); setNewPmName(''); }}
                                        placeholder="Or type: Venmo, Chipper Cash, Wave..."
                                        placeholderTextColor="#555"
                                    />

                                    {/* Details */}
                                    <TextInput
                                        style={[styles.pmInput, { marginTop: 8 }]}
                                        value={newPmDetails}
                                        onChangeText={setNewPmDetails}
                                        placeholder={
                                            selectedPreset?.placeholder ||
                                            'Account / number / email / link'
                                        }
                                        placeholderTextColor="#555"
                                        autoCapitalize="none"
                                        keyboardType={(selectedPreset?.kb as any) || 'default'}
                                    />

                                    <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
                                        <TouchableOpacity
                                            style={styles.pmCancelBtn}
                                            onPress={() => { setAddingPayment(false); setNewPmName(''); setNewPmDetails(''); setCustomPmName(''); }}
                                        >
                                            <Text style={{ color: '#888', fontSize: 14, fontWeight: '600' }}>Cancel</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={styles.pmSaveBtn}
                                            onPress={() => {
                                                const name = (newPmName || customPmName).trim();
                                                if (!name) return;
                                                if (paymentMethods.find(m => m.name.toLowerCase() === name.toLowerCase())) return;
                                                setPaymentMethods([...paymentMethods, { name, details: newPmDetails.trim() }]);
                                                setAddingPayment(false);
                                                setNewPmName(''); setNewPmDetails(''); setCustomPmName('');
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
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 10,
        fontSize: 14,
        color: '#FFFFFF',
        marginBottom: 8,
    },
    // AI Description Generator Styles
    labelRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 8,
    },
    aiGenerateBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingHorizontal: 12,
        paddingVertical: 6,
        backgroundColor: '#1A3A2A',
        borderRadius: 6,
    },
    aiGenerateBtnText: {
        fontSize: 12,
        color: '#25D366',
        fontWeight: '600',
    },
    aiImproveBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        marginTop: 8,
        paddingHorizontal: 8,
        paddingVertical: 4,
        alignSelf: 'flex-start',
    },
    aiImproveBtnText: {
        fontSize: 12,
        color: '#25D366',
        fontWeight: '500',
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
        gap: 8,
        marginTop: 4,
    },
    typeCard: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 10,
        paddingHorizontal: 6,
        borderRadius: 12,
        borderWidth: 1.5,
        borderColor: '#2A3952',
        backgroundColor: '#1A2942',
        width: '31%',
        gap: 5,
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
    // Restaurant toggle rows
    toggleRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: '#0D1F35',
        borderRadius: 10,
        paddingVertical: 12,
        paddingHorizontal: 14,
        marginBottom: 8,
        borderWidth: 1,
        borderColor: '#1A2942',
    },
    toggleInfo: {
        flexDirection: 'row',
        alignItems: 'center',
        flex: 1,
    },
    toggleLabel: {
        fontSize: 14,
        fontWeight: '600',
        color: '#FFFFFF',
    },
    toggleDesc: {
        fontSize: 12,
        color: '#6B7D99',
        marginTop: 2,
    },
});
