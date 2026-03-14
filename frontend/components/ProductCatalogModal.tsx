import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
    View,
    Text,
    Modal,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    Image,
    Alert,
    ActivityIndicator,
    TextInput,
    Switch,
    Dimensions,
    FlatList,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { productsAPI, settingsAPI } from '../context/api';
import { useBusiness } from '../context/BusinessContext';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const CARD_GAP = 10;
const CARD_WIDTH = (SCREEN_WIDTH - 48 - CARD_GAP) / 2;

interface Addon {
    name: string;
    price: number;
}

interface Product {
    id: string;
    name: string;
    price: number;
    discount_price?: number;
    image_url: string;
    images: string[];
    category: string;
    description?: string;
    in_stock: boolean;
    stock_quantity?: number;
    created_at: string;
    offering_type?: string;
    duration?: number;
    service_category?: string;
    addons?: Addon[];
    listing_blocked_dates?: string[];
    deposit_percent?: number;
    price_unit?: string;
}

interface ProductCatalogModalProps {
    visible: boolean;
    onClose: () => void;
}

export default function ProductCatalogModal({
    visible,
    onClose,
}: ProductCatalogModalProps) {
    const { config, isServiceBusiness, businessType } = useBusiness();
    const itemLabel = config.catalogItemLabel;   // 'Product' | 'Service' | 'Item'
    const catalogLabel = config.catalogLabel;     // 'Products' | 'Services' | 'Menu'
    const [products, setProducts] = useState<Product[]>([]);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [currency, setCurrency] = useState('USD');
    const [selectedCategory, setSelectedCategory] = useState('All');
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
    const [detailVisible, setDetailVisible] = useState(false);
    const [editMode, setEditMode] = useState(false);
    const [addMode, setAddMode] = useState(false);

    // Edit form state
    const [editName, setEditName] = useState('');
    const [editPrice, setEditPrice] = useState('');
    const [editDiscountPrice, setEditDiscountPrice] = useState('');
    const [editCategory, setEditCategory] = useState('');
    const [editDescription, setEditDescription] = useState('');
    const [editInStock, setEditInStock] = useState(true);
    const [editStockQuantity, setEditStockQuantity] = useState('');
    const [editOfferingType, setEditOfferingType] = useState('product');
    const [editDuration, setEditDuration] = useState('');
    const [editServiceCategory, setEditServiceCategory] = useState<'appointment' | 'rental'>('appointment');
    const [editAddons, setEditAddons] = useState<Addon[]>([]);
    const [editDepositPercent, setEditDepositPercent] = useState<string>('0');
    const [editPriceUnit, setEditPriceUnit] = useState<string>('night');
    const [saving, setSaving] = useState(false);
    const [activeImageIndex, setActiveImageIndex] = useState(0);

    // Per-listing availability calendar state
    const [listingBlockedDates, setListingBlockedDates] = useState<string[]>([]);
    const [listingCalMonth, setListingCalMonth] = useState(new Date());
    const [savingListingAvail, setSavingListingAvail] = useState(false);

    const getListingCalDays = (month: Date): (string | null)[] => {
        const year = month.getFullYear();
        const mo = month.getMonth();
        const firstDay = new Date(year, mo, 1).getDay();
        const daysInMonth = new Date(year, mo + 1, 0).getDate();
        const days: (string | null)[] = [];
        for (let i = 0; i < firstDay; i++) days.push(null);
        for (let d = 1; d <= daysInMonth; d++) {
            const mm = String(mo + 1).padStart(2, '0');
            const dd = String(d).padStart(2, '0');
            days.push(`${year}-${mm}-${dd}`);
        }
        return days;
    };

    const saveListingAvailability = async (productId: string) => {
        setSavingListingAvail(true);
        try {
            await productsAPI.updateProduct(productId, { listing_blocked_dates: listingBlockedDates } as any);
            setProducts(prev => prev.map(p =>
                p.id === productId ? { ...p, listing_blocked_dates: listingBlockedDates } : p
            ));
            Alert.alert('Saved', 'Listing availability updated.');
        } catch (e) {
            Alert.alert('Error', 'Failed to save listing availability');
        } finally {
            setSavingListingAvail(false);
        }
    };
    const [addingPhotos, setAddingPhotos] = useState(false);
    const [aiFailedBanner, setAiFailedBanner] = useState(false);
    const [pendingAssets, setPendingAssets] = useState<ImagePicker.ImagePickerAsset[]>([]);
    const [planLimits, setPlanLimits] = useState<{ products: number | null; images: number | null }>({ products: 20, images: 100 });
    const [subscriptionPlan, setSubscriptionPlan] = useState('free');

    const maxProducts = planLimits.products;
    const maxImages = planLimits.images;

    useEffect(() => {
        const loadCurrency = async () => {
            try {
                const settings = await settingsAPI.getSettings();
                if (settings.currency) setCurrency(settings.currency);
                if (settings.plan_limits) setPlanLimits(settings.plan_limits);
                if (settings.subscription_plan) setSubscriptionPlan(settings.subscription_plan);
            } catch (e) { }
        };
        loadCurrency();
    }, []);

    useEffect(() => {
        if (visible) {
            fetchProducts();
            setSelectedCategory('All');
            setSearchQuery('');
        }
    }, [visible]);

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const data = await productsAPI.getProducts();
            setProducts(data);
        } catch (error) {
            console.error('Error fetching products:', error);
        } finally {
            setLoading(false);
        }
    };

    // Derive categories from products
    const categories = useMemo(() => {
        const cats = new Set(products.map(p => p.category || 'Other'));
        return ['All', ...Array.from(cats).sort()];
    }, [products]);

    // Filter products
    const filteredProducts = useMemo(() => {
        let filtered = products;
        if (selectedCategory !== 'All') {
            filtered = filtered.filter(p => (p.category || 'Other') === selectedCategory);
        }
        if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase();
            filtered = filtered.filter(p =>
                p.name.toLowerCase().includes(q) ||
                (p.description || '').toLowerCase().includes(q) ||
                (p.category || '').toLowerCase().includes(q)
            );
        }
        return filtered;
    }, [products, selectedCategory, searchQuery]);

    const inStockCount = useMemo(() => products.filter(p => p.in_stock !== false).length, [products]);
    const outOfStockCount = useMemo(() => products.filter(p => p.in_stock === false).length, [products]);

    const handleUploadProducts = async (source: 'library' | 'camera' = 'library') => {
        if (maxProducts !== null && products.length >= maxProducts) {
            Alert.alert('Plan Limit Reached', `Your ${subscriptionPlan} plan allows ${maxProducts} products. Upgrade to add more.`);
            return;
        }
        try {
            if (source === 'library') {
                const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
                if (status !== 'granted') {
                    Alert.alert('Permission needed', 'Please allow access to your photos');
                    return;
                }
            } else {
                const { status } = await ImagePicker.requestCameraPermissionsAsync();
                if (status !== 'granted') {
                    Alert.alert('Permission needed', 'Please allow access to your camera');
                    return;
                }
            }

            const options: ImagePicker.ImagePickerOptions = {
                mediaTypes: ImagePicker.MediaTypeOptions.Images,
                allowsMultipleSelection: source === 'library',
                quality: 0.8,
            };

            const result = source === 'library'
                ? await ImagePicker.launchImageLibraryAsync(options)
                : await ImagePicker.launchCameraAsync(options);

            if (!result.canceled && result.assets.length > 0) {
                setUploading(true);
                try {
                    const response = await productsAPI.uploadProducts(result.assets);
                    // Refresh product list first
                    await fetchProducts();

                    if (response.products && response.products.length > 0) {
                        const first = response.products[0];
                        const aiFailed = !!first.ai_failed;
                        // Open the first uploaded product straight into edit mode
                        setAiFailedBanner(aiFailed);
                        startEdit({
                            id: first.id,
                            name: first.name,
                            price: first.price ?? 0,
                            discount_price: first.discount_price,
                            category: first.category || 'Other',
                            description: first.description || '',
                            image_url: first.image_url,
                            images: first.images ?? [],
                            in_stock: first.in_stock ?? true,
                            created_at: new Date().toISOString(),
                        });
                        if (response.products.length > 1) {
                            // Non-blocking hint about the other products
                            setTimeout(() => {
                                Alert.alert(
                                    `${response.products.length} Products Uploaded`,
                                    'Reviewing the first one — go back to the catalog to check the rest.',
                                    [{ text: 'OK' }]
                                );
                            }, 500);
                        }
                    }
                } catch (error) {
                    console.error('Upload error:', error);
                    Alert.alert('Upload Failed', 'Could not upload products. Please try again.');
                } finally {
                    setUploading(false);
                }
            }
        } catch (error) {
            console.error('Image picker error:', error);
            Alert.alert('Error', 'Failed to open image picker');
        }
    };


    const handleDeleteProduct = (product: Product) => {
        Alert.alert(
            `Delete ${itemLabel}`,
            `Delete "${product.name}"? This cannot be undone.`,
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Delete',
                    style: 'destructive',
                    onPress: async () => {
                        try {
                            await productsAPI.deleteProduct(product.id);
                            setDetailVisible(false);
                            setSelectedProduct(null);
                            fetchProducts();
                        } catch (error) {
                            Alert.alert('Error', `Failed to delete ${itemLabel.toLowerCase()}`);
                        }
                    },
                },
            ]
        );
    };

    const handleToggleStock = async (product: Product) => {
        try {
            await productsAPI.updateProduct(product.id, { in_stock: !product.in_stock });
            setProducts(prev => prev.map(p => p.id === product.id ? { ...p, in_stock: !p.in_stock } : p));
            if (selectedProduct?.id === product.id) {
                setSelectedProduct({ ...selectedProduct, in_stock: !selectedProduct.in_stock });
            }
        } catch (error) {
            Alert.alert('Error', 'Failed to update stock status');
        }
    };

    const openProductDetail = (product: Product) => {
        setSelectedProduct(product);
        setEditMode(false);
        setActiveImageIndex(0);
        setListingBlockedDates(product.listing_blocked_dates || []);
        setListingCalMonth(new Date());
        setDetailVisible(true);
    };

    const startEdit = (product: Product) => {
        console.log('Starting edit for product:', product);
        setEditName(product.name);
        setEditPrice(product.price.toString());
        setEditDiscountPrice(product.discount_price?.toString() || '');
        setEditCategory(product.category || 'Other');
        setEditDescription(product.description || '');
        setEditInStock(product.in_stock);
        setEditStockQuantity(product.stock_quantity?.toString() || '');
        setEditOfferingType(product.offering_type || 'product');
        setEditDuration(product.duration?.toString() || '');
        setEditServiceCategory((product.service_category as 'appointment' | 'rental') || 'appointment');
        setEditAddons(product.addons || []);
        setEditDepositPercent((product.deposit_percent ?? 0).toString());
        setEditPriceUnit(product.price_unit || 'night');
        setSelectedProduct(product);
        setEditMode(true);
        setDetailVisible(true);
        console.log('Edit mode set to true, detailVisible set to true');
    };

    const startAddProduct = () => {
        if (maxProducts !== null && products.length >= maxProducts) {
            Alert.alert('Plan Limit Reached', `Your ${subscriptionPlan} plan allows ${maxProducts} products. Upgrade to add more.`);
            return;
        }
        setEditName('');
        setEditPrice('');
        setEditDiscountPrice('');
        setEditCategory('Other');
        setEditDescription('');
        setEditInStock(true);
        setEditStockQuantity('');
        setEditOfferingType(businessType === 'rental' ? 'rental' : isServiceBusiness ? 'service' : businessType === 'restaurant' ? 'menu_item' : businessType === 'creator' ? 'digital' : 'product');
        setEditDuration(isServiceBusiness ? '60' : '');
        setEditServiceCategory('appointment');
        setEditAddons([]);
        setEditDepositPercent('0');
        setEditPriceUnit('night');
        setAddMode(true);
        setDetailVisible(true);
        setSelectedProduct(null);
        setEditMode(true);
    };

    const handleSaveEdit = async () => {
        if (!editName.trim()) {
            Alert.alert('Error', 'Product name is required');
            return;
        }
        if (!editPrice || parseFloat(editPrice) < 0) {
            Alert.alert('Error', 'Please enter a valid price');
            return;
        }
        const discountPriceValue = editDiscountPrice.trim() ? parseFloat(editDiscountPrice) : null;
        if (discountPriceValue !== null && discountPriceValue < 0) {
            Alert.alert('Error', 'Discount price cannot be negative');
            return;
        }
        if (discountPriceValue !== null && discountPriceValue >= parseFloat(editPrice)) {
            Alert.alert('Error', 'Discount price must be less than regular price');
            return;
        }

        setSaving(true);
        try {
            const discountPrice = discountPriceValue;
            const stockQuantity = editStockQuantity.trim() ? parseInt(editStockQuantity) : null;

            let createdProductId = '';

            if (addMode) {
                const productData: any = {
                    name: editName.trim(),
                    price: parseFloat(editPrice),
                    category: editCategory.trim() || 'Other',
                    description: editDescription.trim() || undefined,
                    in_stock: editInStock,
                    stock_quantity: stockQuantity,
                    offering_type: editOfferingType,
                    duration: editDuration.trim() ? parseInt(editDuration) : undefined,
                    service_category: editServiceCategory,
                    addons: editAddons.filter(a => a.name.trim()),
                    deposit_percent: parseInt(editDepositPercent) || 0,
                    price_unit: editPriceUnit,
                };
                if (discountPrice !== null) {
                    productData.discount_price = discountPrice;
                }
                const newProduct = await productsAPI.createProduct(productData);
                createdProductId = newProduct.id;

                // Upload pending photos if any
                if (pendingAssets.length > 0) {
                    await productsAPI.addProductImages(createdProductId, pendingAssets);
                }
            } else if (selectedProduct) {
                const updateData: any = {
                    name: editName.trim(),
                    price: parseFloat(editPrice),
                    category: editCategory.trim() || 'Other',
                    description: editDescription.trim() || undefined,
                    in_stock: editInStock,
                    stock_quantity: stockQuantity,
                    offering_type: editOfferingType,
                    duration: editDuration.trim() ? parseInt(editDuration) : undefined,
                    service_category: editServiceCategory,
                    addons: editAddons.filter(a => a.name.trim()),
                    deposit_percent: parseInt(editDepositPercent) || 0,
                    price_unit: editPriceUnit,
                };
                if (discountPrice !== null) {
                    updateData.discount_price = discountPrice;
                }
                await productsAPI.updateProduct(selectedProduct.id, updateData);
            }

            setEditMode(false);
            setAddMode(false);
            setDetailVisible(false);
            setPendingAssets([]);
            fetchProducts();
        } catch (error) {
            console.error('Save error:', error);
            Alert.alert('Error', 'Failed to save product');
        } finally {
            setSaving(false);
        }
    };

    const getImageUri = (product: Product) => {
        if (product.image_url) {
            if (product.image_url.startsWith('http')) return product.image_url;
            return `${process.env.EXPO_PUBLIC_BACKEND_URL}${product.image_url}`;
        }
        return null;
    };

    const resolveImageUrl = (url: string) => {
        if (url.startsWith('http')) return url;
        return `${process.env.EXPO_PUBLIC_BACKEND_URL}${url}`;
    };

    const handleAddPhotosToProduct = async (product: Product | null, source: 'library' | 'camera' = 'library') => {
        try {
            // Request appropriate permissions
            if (source === 'library') {
                const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
                if (status !== 'granted') {
                    Alert.alert('Permission needed', 'Please allow access to your photos');
                    return;
                }
            } else {
                const { status } = await ImagePicker.requestCameraPermissionsAsync();
                if (status !== 'granted') {
                    Alert.alert('Permission needed', 'Please allow access to your camera');
                    return;
                }
            }

            const currentCount = addMode ? pendingAssets.length : (product?.images || []).length;
            if (currentCount >= 5) {
                Alert.alert('Limit reached', 'Maximum 5 photos per product');
                return;
            }

            const options: ImagePicker.ImagePickerOptions = {
                mediaTypes: ImagePicker.MediaTypeOptions.Images,
                allowsMultipleSelection: source === 'library',
                quality: 0.8,
                selectionLimit: source === 'library' ? 5 - currentCount : 1,
            };

            const result = source === 'library'
                ? await ImagePicker.launchImageLibraryAsync(options)
                : await ImagePicker.launchCameraAsync(options);

            if (!result.canceled && result.assets.length > 0) {
                if (addMode) {
                    setPendingAssets([...pendingAssets, ...result.assets]);
                } else if (product) {
                    setAddingPhotos(true);
                    try {
                        await productsAPI.addProductImages(product.id, result.assets);
                        await fetchProducts();
                        // Refresh selected product
                        const updated = await productsAPI.getProduct(product.id);
                        setSelectedProduct(updated);
                    } catch (error: any) {
                        Alert.alert('Error', error.response?.data?.detail || 'Failed to add photos');
                    } finally {
                        setAddingPhotos(false);
                    }
                }
            }
        } catch (error) {
            console.error('Image picker error:', error);
            Alert.alert('Error', 'Failed to open image picker');
        }
    };

    const handleDeletePhoto = async (product: Product | null, imageIndex: number) => {
        if (addMode) {
            setPendingAssets(prev => prev.filter((_, i) => i !== imageIndex));
            return;
        }

        if (!product) return;

        Alert.alert('Delete Photo', 'Remove this photo?', [
            { text: 'Cancel', style: 'cancel' },
            {
                text: 'Delete', style: 'destructive',
                onPress: async () => {
                    try {
                        await productsAPI.deleteProductImage(product.id, imageIndex);
                        await fetchProducts();
                        const updated = await productsAPI.getProduct(product.id);
                        setSelectedProduct(updated);
                        setActiveImageIndex(0);
                    } catch (error) {
                        Alert.alert('Error', 'Failed to delete photo');
                    }
                }
            }
        ]);
    };

    // ============ RENDER ============

    const renderProductCard = (product: Product) => {
        const imageUri = getImageUri(product);
        const isOutOfStock = product.in_stock === false;

        return (
            <TouchableOpacity
                key={product.id}
                style={[styles.productCard, isOutOfStock && styles.productCardOutOfStock]}
                onPress={() => openProductDetail(product)}
                activeOpacity={0.7}
            >
                {imageUri ? (
                    <Image source={{ uri: imageUri }} style={styles.productImage} resizeMode="cover" />
                ) : (
                    <View style={[styles.productImage, styles.noImagePlaceholder]}>
                        <Ionicons name="image-outline" size={32} color="#3A4A5C" />
                    </View>
                )}

                {isOutOfStock && (
                    <View style={styles.outOfStockBadge}>
                        <Text style={styles.outOfStockText}>Out of Stock</Text>
                    </View>
                )}

                <View style={styles.productInfo}>
                    <Text style={styles.productName} numberOfLines={2}>{product.name}</Text>
                    <View style={styles.priceContainer}>
                        {product.discount_price ? (
                            <>
                                <Text style={styles.discountPrice}>{currency} {product.discount_price.toLocaleString()}</Text>
                                <Text style={styles.originalPrice}>{currency} {product.price.toLocaleString()}</Text>
                            </>
                        ) : (
                            <Text style={styles.productPrice}>{currency} {product.price.toLocaleString()}</Text>
                        )}
                    </View>
                    <View style={styles.productMeta}>
                        <View style={[styles.categoryBadge]}>
                            <Text style={styles.categoryBadgeText} numberOfLines={1}>{product.category || 'Other'}</Text>
                        </View>
                        <View style={[styles.stockDot, isOutOfStock ? styles.stockDotRed : styles.stockDotGreen]} />
                    </View>
                </View>
            </TouchableOpacity>
        );
    };

    // ============ PRODUCT DETAIL MODAL ============

    const renderDetailModal = () => (
        <Modal visible={detailVisible} animationType="slide" onRequestClose={() => { setDetailVisible(false); setEditMode(false); setAddMode(false); setAiFailedBanner(false); }}>
            <SafeAreaView style={styles.container}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => { setDetailVisible(false); setEditMode(false); setAddMode(false); setAiFailedBanner(false); }}>
                        <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>{addMode ? `Add ${itemLabel}` : editMode ? `Edit ${itemLabel}` : `${itemLabel} Details`}</Text>
                    {!editMode && selectedProduct ? (
                        <TouchableOpacity onPress={() => startEdit(selectedProduct)}>
                            <Ionicons name="create-outline" size={24} color="#25D366" />
                        </TouchableOpacity>
                    ) : (
                        <View style={{ width: 24 }} />
                    )}
                </View>

                <ScrollView style={styles.detailContent} contentContainerStyle={{ paddingBottom: 40 }}>
                    {editMode ? (
                        // ---- EDIT / ADD FORM ----
                        <View style={styles.editForm}>
                            {/* AI failure banner */}
                            {aiFailedBanner && (
                                <View style={styles.aiBanner}>
                                    <Ionicons name="warning-outline" size={16} color="#92400e" />
                                    <Text style={styles.aiBannerText}>
                                        AI couldn't analyse this image — please fill in the name, price and category.
                                    </Text>
                                </View>
                            )}
                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>{itemLabel} Name *</Text>
                                <TextInput
                                    style={styles.formInput}
                                    value={editName}
                                    onChangeText={setEditName}
                                    placeholder={businessType === 'rental' ? 'e.g. Beachfront Villa, Toyota Corolla, Camera Kit' : isServiceBusiness ? 'e.g. Haircut, Deep Tissue Massage' : businessType === 'restaurant' ? 'e.g. Grilled Chicken, Jollof Rice' : businessType === 'creator' ? 'e.g. Brand Deal Package, E-Book' : 'e.g. Chocolate Cake, T-Shirt'}
                                    placeholderTextColor="#555"
                                />
                            </View>

                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Price ({currency}) *</Text>
                                <TextInput
                                    style={styles.formInput}
                                    value={editPrice}
                                    onChangeText={setEditPrice}
                                    placeholder="0"
                                    placeholderTextColor="#555"
                                    keyboardType="numeric"
                                />
                            </View>

                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Discount Price ({currency}) (Optional)</Text>
                                <TextInput
                                    style={styles.formInput}
                                    value={editDiscountPrice}
                                    onChangeText={setEditDiscountPrice}
                                    placeholder="Leave empty for no discount"
                                    placeholderTextColor="#555"
                                    keyboardType="numeric"
                                />
                            </View>

                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Category</Text>
                                <TextInput
                                    style={styles.formInput}
                                    value={editCategory}
                                    onChangeText={setEditCategory}
                                    placeholder={businessType === 'rental' ? 'e.g. Property, Vehicle, Equipment, Boat' : isServiceBusiness ? 'e.g. Hair, Nails, Massage, Fitness' : businessType === 'restaurant' ? 'e.g. Mains, Starters, Drinks, Desserts' : businessType === 'creator' ? 'e.g. Sponsored Post, Digital Product, Merch' : 'e.g. Clothing, Electronics, Food'}
                                    placeholderTextColor="#555"
                                />
                                {/* Quick-pick chips from existing categories */}
                                {(() => {
                                    const existingCats = [...new Set(
                                        products
                                            .filter(p => p.category && p.category !== 'Other' && p.id !== selectedProduct?.id)
                                            .map(p => p.category!)
                                    )].slice(0, 6);
                                    return existingCats.length > 0 ? (
                                        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 6 }}>
                                            {existingCats.map(cat => (
                                                <TouchableOpacity
                                                    key={cat}
                                                    style={[styles.typeChip, editCategory === cat && styles.typeChipActive, { marginRight: 6 }]}
                                                    onPress={() => setEditCategory(cat)}
                                                >
                                                    <Text style={[styles.typeChipText, editCategory === cat && styles.typeChipTextActive]}>{cat}</Text>
                                                </TouchableOpacity>
                                            ))}
                                        </ScrollView>
                                    ) : null;
                                })()}
                            </View>

                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Description</Text>
                                <TextInput
                                    style={[styles.formInput, { height: 80, textAlignVertical: 'top' }]}
                                    value={editDescription}
                                    onChangeText={setEditDescription}
                                    placeholder={businessType === 'rental' ? 'Bedrooms, amenities, location, rules...' : isServiceBusiness ? 'What does this service include? Any preparation needed?' : businessType === 'restaurant' ? 'Ingredients, allergens, portion size...' : `Describe your ${itemLabel.toLowerCase()}...`}
                                    placeholderTextColor="#555"
                                    multiline
                                    numberOfLines={3}
                                />
                            </View>

                            {!isServiceBusiness && (
                                <View style={styles.formGroup}>
                                    <Text style={styles.formLabel}>Stock Quantity (Optional)</Text>
                                    <TextInput
                                        style={styles.formInput}
                                        value={editStockQuantity}
                                        onChangeText={setEditStockQuantity}
                                        placeholder="Leave empty for unlimited stock"
                                        placeholderTextColor="#555"
                                        keyboardType="numeric"
                                    />
                                    <Text style={styles.stockHint}>Automatically reduces when orders are placed</Text>
                                </View>
                            )}

                            <View style={styles.stockToggleRow}>
                                <View>
                                    <Text style={styles.formLabel}>{isServiceBusiness ? 'Available' : 'In Stock'}</Text>
                                    <Text style={styles.stockHint}>{editInStock ? (isServiceBusiness ? 'Bookable by customers' : 'Available for customers') : 'Hidden from AI replies'}</Text>
                                </View>
                                <Switch
                                    value={editInStock}
                                    onValueChange={setEditInStock}
                                    trackColor={{ false: '#333', true: '#1A3A2A' }}
                                    thumbColor={editInStock ? '#25D366' : '#666'}
                                />
                            </View>

                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Type</Text>
                                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                                    {(businessType === 'rental'
                                        ? [
                                            { id: 'rental',       label: '🏠 Property' },
                                            { id: 'service',      label: '🚗 Vehicle' },
                                            { id: 'equipment',    label: '🔧 Equipment' },
                                            { id: 'package',      label: '🎁 Package' },
                                          ]
                                        : isServiceBusiness
                                        ? [
                                            { id: 'service',      label: '✂️ Service' },
                                            { id: 'class',        label: '🎓 Class' },
                                            { id: 'appointment',  label: '📅 Appointment' },
                                            { id: 'consultation', label: '💬 Consultation' },
                                            { id: 'package',      label: '🎁 Package' },
                                          ]
                                        : businessType === 'restaurant'
                                        ? [
                                            { id: 'menu_item',    label: '🍽️ Menu Item' },
                                            { id: 'drink',        label: '🥤 Drink' },
                                            { id: 'combo',        label: '🥡 Combo' },
                                          ]
                                        : businessType === 'creator'
                                        ? [
                                            { id: 'digital',      label: '💾 Digital' },
                                            { id: 'service',      label: '🔧 Service' },
                                            { id: 'product',      label: '📦 Product' },
                                          ]
                                        : [
                                            { id: 'product',      label: '📦 Product' },
                                            { id: 'service',      label: '🔧 Service' },
                                            { id: 'digital',      label: '💾 Digital' },
                                            { id: 'menu_item',    label: '🍽️ Menu Item' },
                                          ]
                                    ).map(ot => (
                                        <TouchableOpacity
                                            key={ot.id}
                                            style={[
                                                styles.typeChip,
                                                editOfferingType === ot.id && styles.typeChipActive,
                                            ]}
                                            onPress={() => setEditOfferingType(ot.id)}
                                        >
                                            <Text style={[
                                                styles.typeChipText,
                                                editOfferingType === ot.id && styles.typeChipTextActive,
                                            ]}>{ot.label}</Text>
                                        </TouchableOpacity>
                                    ))}
                                </ScrollView>
                            </View>

                            {businessType !== 'rental' && editServiceCategory !== 'rental' && (isServiceBusiness || ['service','class','appointment','consultation','package'].includes(editOfferingType)) && (
                                <View style={[styles.formGroup, isServiceBusiness && { borderLeftWidth: 3, borderLeftColor: '#25D366', paddingLeft: 12 }]}>
                                    <Text style={styles.formLabel}>Duration (minutes) {isServiceBusiness && '*'}</Text>
                                    <TextInput
                                        style={styles.formInput}
                                        value={editDuration}
                                        onChangeText={setEditDuration}
                                        placeholder="e.g. 30, 60, 90"
                                        placeholderTextColor="#555"
                                        keyboardType="numeric"
                                    />
                                    <Text style={styles.stockHint}>Used for booking slot calculation</Text>
                                </View>
                            )}

                            <View style={styles.formGroup}>
                                    <Text style={styles.formLabel}>Booking Type</Text>
                                    <View style={{ flexDirection: 'row', gap: 10 }}>
                                        {[{ id: 'appointment', label: '📅 Appointment' }, { id: 'rental', label: '🏠 Rental' }].map(opt => (
                                            <TouchableOpacity
                                                key={opt.id}
                                                style={[
                                                    styles.typeChip,
                                                    editServiceCategory === opt.id && styles.typeChipActive,
                                                    { flex: 1, justifyContent: 'center' }
                                                ]}
                                                onPress={() => setEditServiceCategory(opt.id as 'appointment' | 'rental')}
                                            >
                                                <Text style={[styles.typeChipText, editServiceCategory === opt.id && styles.typeChipTextActive]}>{opt.label}</Text>
                                            </TouchableOpacity>
                                        ))}
                                    </View>
                                    <Text style={styles.stockHint}>
                                        {editServiceCategory === 'rental' ? 'Customer picks check-in & check-out dates' : 'Customer picks a date & time slot'}
                                    </Text>
                                </View>

                            <View style={styles.formGroup}>
                                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                                        <Text style={styles.formLabel}>Add-ons ({editAddons.length}/4)</Text>
                                        {editAddons.length < 4 && (
                                            <TouchableOpacity
                                                onPress={() => setEditAddons(prev => [...prev, { name: '', price: 0 }])}
                                                style={{ backgroundColor: '#1A3A2A', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4 }}
                                            >
                                                <Text style={{ color: '#25D366', fontSize: 13 }}>+ Add</Text>
                                            </TouchableOpacity>
                                        )}
                                    </View>
                                    {editAddons.map((addon, idx) => (
                                        <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                            <TextInput
                                                style={[styles.formInput, { flex: 2, marginBottom: 0 }]}
                                                value={addon.name}
                                                onChangeText={v => setEditAddons(prev => prev.map((a, i) => i === idx ? { ...a, name: v } : a))}
                                                placeholder={businessType === 'rental' || editServiceCategory === 'rental' ? 'e.g. Parking, Pool, WiFi' : 'e.g. Braids, Parking'}
                                                placeholderTextColor="#555"
                                            />
                                            <TextInput
                                                style={[styles.formInput, { flex: 1, marginBottom: 0 }]}
                                                value={addon.price === 0 ? '' : addon.price.toString()}
                                                onChangeText={v => setEditAddons(prev => prev.map((a, i) => i === idx ? { ...a, price: parseFloat(v) || 0 } : a))}
                                                placeholder="Price"
                                                placeholderTextColor="#555"
                                                keyboardType="numeric"
                                            />
                                            <TouchableOpacity onPress={() => setEditAddons(prev => prev.filter((_, i) => i !== idx))}>
                                                <Ionicons name="close-circle" size={22} color="#FF6B6B" />
                                            </TouchableOpacity>
                                        </View>
                                    ))}
                                    {editAddons.length === 0 && (
                                        <Text style={styles.stockHint}>Optional extras customers can add to their booking</Text>
                                    )}
                                </View>

                            {(businessType === 'rental' || editServiceCategory === 'rental') && (
                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Pricing Unit</Text>
                                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                                    {[
                                        { id: 'night',  label: '🌙 Per Night' },
                                        { id: 'day',    label: '☀️ Per Day' },
                                        { id: 'week',   label: '📅 Per Week' },
                                        { id: 'month',  label: '🗓 Per Month' },
                                        { id: 'year',   label: '📆 Per Year' },
                                        { id: 'person', label: '👤 Per Person' },
                                    ].map(u => (
                                        <TouchableOpacity
                                            key={u.id}
                                            style={[
                                                styles.typeChip,
                                                editPriceUnit === u.id && styles.typeChipActive,
                                            ]}
                                            onPress={() => setEditPriceUnit(u.id)}
                                        >
                                            <Text style={[styles.typeChipText, editPriceUnit === u.id && styles.typeChipTextActive]}>{u.label}</Text>
                                        </TouchableOpacity>
                                    ))}
                                </ScrollView>
                                <Text style={styles.stockHint}>How the price is charged to the customer</Text>
                            </View>
                            )}

                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Deposit Required (%)</Text>
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                                    <TextInput
                                        style={[styles.formInput, { flex: 1, marginBottom: 0 }]}
                                        value={editDepositPercent === '0' ? '' : editDepositPercent}
                                        onChangeText={v => setEditDepositPercent(v.replace(/[^0-9]/g, ''))}
                                        placeholder="0 = no deposit"
                                        placeholderTextColor="#555"
                                        keyboardType="numeric"
                                    />
                                    {parseInt(editDepositPercent) > 0 && (
                                        <Text style={{ color: '#25D366', fontSize: 13, fontWeight: '600' }}>{editDepositPercent}% upfront</Text>
                                    )}
                                </View>
                                <Text style={styles.stockHint}>
                                    {parseInt(editDepositPercent) > 0
                                        ? `Customer must pay ${editDepositPercent}% deposit to secure booking`
                                        : 'Leave at 0 for no deposit (full payment on arrival)'}
                                </Text>
                            </View>

                            {(addMode || selectedProduct) && (
                                <>
                                    <View style={styles.imageActionRow}>
                                        <TouchableOpacity
                                            style={styles.imageActionBtn}
                                            onPress={() => handleAddPhotosToProduct(selectedProduct!, 'library')}
                                            disabled={addingPhotos}
                                        >
                                            {addingPhotos ? (
                                                <ActivityIndicator size="small" color="#25D366" />
                                            ) : (
                                                <>
                                                    <Ionicons name="images-outline" size={20} color="#25D366" />
                                                    <Text style={styles.imageActionText}>
                                                        {addMode ? (
                                                            pendingAssets.length > 0 ? `Photos (${pendingAssets.length}/5)` : 'Gallery'
                                                        ) : (
                                                            (selectedProduct!.images || []).length > 0
                                                                ? `Photos (${(selectedProduct!.images || []).length}/5)`
                                                                : 'Gallery'
                                                        )}
                                                    </Text>
                                                </>
                                            )}
                                        </TouchableOpacity>

                                        <TouchableOpacity
                                            style={styles.imageActionBtn}
                                            onPress={() => handleAddPhotosToProduct(selectedProduct!, 'camera')}
                                            disabled={addingPhotos}
                                        >
                                            <Ionicons name="camera-outline" size={20} color="#25D366" />
                                            <Text style={styles.imageActionText}>Take Photo</Text>
                                        </TouchableOpacity>
                                    </View>

                                    {/* Edit mode thumbnails */}
                                    {((!addMode && selectedProduct && selectedProduct.images && selectedProduct.images.length > 0) || (addMode && pendingAssets.length > 0)) && (
                                        <View style={styles.editThumbnailsContainer}>
                                            {addMode ? (
                                                pendingAssets.map((img, idx) => (
                                                    <View key={idx} style={styles.editThumbnailWrapper}>
                                                        <Image source={{ uri: img.uri }} style={styles.editThumbnail} />
                                                        <TouchableOpacity
                                                            style={styles.deleteThumbnailBtn}
                                                            onPress={() => handleDeletePhoto(null, idx)}
                                                        >
                                                            <Ionicons name="close-circle" size={18} color="#FF6B6B" />
                                                        </TouchableOpacity>
                                                    </View>
                                                ))
                                            ) : (
                                                selectedProduct!.images!.map((img, idx) => (
                                                    <View key={idx} style={styles.editThumbnailWrapper}>
                                                        <Image source={{ uri: resolveImageUrl(img) }} style={styles.editThumbnail} />
                                                        <TouchableOpacity
                                                            style={styles.deleteThumbnailBtn}
                                                            onPress={() => handleDeletePhoto(selectedProduct!, idx)}
                                                        >
                                                            <Ionicons name="close-circle" size={18} color="#FF6B6B" />
                                                        </TouchableOpacity>
                                                    </View>
                                                ))
                                            )}
                                        </View>
                                    )}
                                </>
                            )}

                            <TouchableOpacity
                                style={[styles.saveBtn, saving && { opacity: 0.6 }]}
                                onPress={handleSaveEdit}
                                disabled={saving}
                            >
                                {saving ? (
                                    <ActivityIndicator color="#FFF" size="small" />
                                ) : (
                                    <Text style={styles.saveBtnText}>{addMode ? `Add ${itemLabel}` : 'Save Changes'}</Text>
                                )}
                            </TouchableOpacity>

                            {!addMode && selectedProduct && (
                                <TouchableOpacity style={styles.deleteBtn} onPress={() => handleDeleteProduct(selectedProduct)}>
                                    <Ionicons name="trash-outline" size={18} color="#FF6B6B" />
                                    <Text style={styles.deleteBtnText}>{`Delete ${itemLabel}`}</Text>
                                </TouchableOpacity>
                            )}
                        </View>
                    ) : selectedProduct ? (
                        // ---- DETAIL VIEW ----
                        <View>
                            {/* Image Gallery */}
                            {selectedProduct.images && selectedProduct.images.length > 0 ? (
                                <View>
                                    <ScrollView
                                        horizontal
                                        pagingEnabled
                                        showsHorizontalScrollIndicator={false}
                                        onMomentumScrollEnd={(e) => {
                                            const idx = Math.round(e.nativeEvent.contentOffset.x / SCREEN_WIDTH);
                                            setActiveImageIndex(idx);
                                        }}
                                    >
                                        {selectedProduct.images.map((img, idx) => (
                                            <Image
                                                key={idx}
                                                source={{ uri: resolveImageUrl(img) }}
                                                style={[styles.detailImage, { width: SCREEN_WIDTH }]}
                                                resizeMode="cover"
                                            />
                                        ))}
                                    </ScrollView>
                                    {/* Image dots */}
                                    {selectedProduct.images.length > 1 && (
                                        <View style={styles.imageDots}>
                                            {selectedProduct.images.map((_, idx) => (
                                                <View key={idx} style={[styles.imageDot, activeImageIndex === idx && styles.imageDotActive]} />
                                            ))}
                                        </View>
                                    )}
                                    {/* Image count & actions */}
                                    <View style={styles.imageCountBar}>
                                        <Text style={styles.imageCountText}>{selectedProduct.images.length}/5 photos</Text>
                                        <View style={{ flexDirection: 'row', gap: 12 }}>
                                            {selectedProduct.images.length < 5 && (
                                                <TouchableOpacity onPress={() => handleAddPhotosToProduct(selectedProduct)} disabled={addingPhotos}>
                                                    {addingPhotos ? <ActivityIndicator size="small" color="#25D366" /> : <Ionicons name="add-circle-outline" size={22} color="#25D366" />}
                                                </TouchableOpacity>
                                            )}
                                            {selectedProduct.images.length > 0 && (
                                                <TouchableOpacity onPress={() => handleDeletePhoto(selectedProduct, activeImageIndex)}>
                                                    <Ionicons name="trash-outline" size={20} color="#FF6B6B" />
                                                </TouchableOpacity>
                                            )}
                                        </View>
                                    </View>
                                </View>
                            ) : (
                                <TouchableOpacity
                                    style={[styles.detailImage, styles.noImagePlaceholder]}
                                    onPress={() => handleAddPhotosToProduct(selectedProduct)}
                                >
                                    <Ionicons name="camera-outline" size={48} color="#3A4A5C" />
                                    <Text style={{ color: '#556', marginTop: 8 }}>Tap to add photos</Text>
                                    {addingPhotos && <ActivityIndicator size="small" color="#25D366" style={{ marginTop: 8 }} />}
                                </TouchableOpacity>
                            )}

                            <View style={styles.detailBody}>
                                <View style={styles.detailNameRow}>
                                    <Text style={styles.detailName}>{selectedProduct.name}</Text>
                                    <View style={[styles.stockBadge, selectedProduct.in_stock === false ? styles.stockBadgeRed : styles.stockBadgeGreen]}>
                                        <Text style={styles.stockBadgeText}>
                                            {selectedProduct.in_stock === false ? (isServiceBusiness ? 'Unavailable' : 'Out of Stock') : (isServiceBusiness ? 'Available' : 'In Stock')}
                                        </Text>
                                    </View>
                                </View>

                                <Text style={styles.detailPrice}>{currency} {selectedProduct.price.toLocaleString()}</Text>

                                <View style={styles.detailCategoryRow}>
                                    <Ionicons name="pricetag-outline" size={14} color="#8899AA" />
                                    <Text style={styles.detailCategory}>{selectedProduct.category || 'Other'}</Text>

                                    {!isServiceBusiness && selectedProduct.stock_quantity !== undefined && selectedProduct.stock_quantity !== null && (
                                        <View style={styles.detailStockInfo}>
                                            <Ionicons name="cube-outline" size={14} color="#8899AA" style={{ marginLeft: 12 }} />
                                            <Text style={styles.detailCategory}>Stock: {selectedProduct.stock_quantity}</Text>
                                        </View>
                                    )}
                                    {selectedProduct.duration ? (
                                        <View style={styles.detailStockInfo}>
                                            <Ionicons name="time-outline" size={14} color="#8899AA" style={{ marginLeft: 12 }} />
                                            <Text style={styles.detailCategory}>{selectedProduct.duration} min</Text>
                                        </View>
                                    ) : null}
                                </View>

                                {selectedProduct.description ? (
                                    <View style={styles.descriptionBox}>
                                        <Text style={styles.descriptionLabel}>Description</Text>
                                        <Text style={styles.descriptionText}>{selectedProduct.description}</Text>
                                    </View>
                                ) : null}

                                {/* Per-listing Date Availability Calendar (rental only) */}
                                {(businessType === 'rental' || selectedProduct.service_category === 'rental') && (
                                    <View style={{ marginTop: 16, padding: 14, backgroundColor: '#0F1E35', borderRadius: 12, borderWidth: 1, borderColor: '#1A2942' }}>
                                        <Text style={{ color: '#FFFFFF', fontWeight: '700', fontSize: 14, marginBottom: 4 }}>Listing Availability</Text>
                                        <Text style={{ color: '#64748B', fontSize: 12, marginBottom: 12 }}>
                                            Tap dates to mark them as <Text style={{ color: '#EF4444' }}>unavailable</Text> for this listing only.
                                        </Text>
                                        {/* Month nav */}
                                        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                                            <TouchableOpacity onPress={() => setListingCalMonth(prev => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))} style={{ padding: 4 }}>
                                                <Ionicons name="chevron-back" size={18} color="#25D366" />
                                            </TouchableOpacity>
                                            <Text style={{ color: '#FFFFFF', fontWeight: '700', fontSize: 13 }}>
                                                {listingCalMonth.toLocaleString('default', { month: 'long', year: 'numeric' })}
                                            </Text>
                                            <TouchableOpacity onPress={() => setListingCalMonth(prev => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))} style={{ padding: 4 }}>
                                                <Ionicons name="chevron-forward" size={18} color="#25D366" />
                                            </TouchableOpacity>
                                        </View>
                                        {/* Day headers */}
                                        <View style={{ flexDirection: 'row', marginBottom: 3 }}>
                                            {['Su','Mo','Tu','We','Th','Fr','Sa'].map(d => (
                                                <Text key={d} style={{ flex: 1, textAlign: 'center', color: '#64748B', fontSize: 10, fontWeight: '700' }}>{d}</Text>
                                            ))}
                                        </View>
                                        {/* Calendar grid */}
                                        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
                                            {getListingCalDays(listingCalMonth).map((dateStr, i) => {
                                                if (!dateStr) return <View key={`e-${i}`} style={{ width: '14.28%', aspectRatio: 1 }} />;
                                                const todayStr = new Date().toISOString().slice(0, 10);
                                                const isPast = dateStr < todayStr;
                                                const isBlocked = listingBlockedDates.includes(dateStr);
                                                const dayNum = parseInt(dateStr.split('-')[2]);
                                                return (
                                                    <TouchableOpacity
                                                        key={dateStr}
                                                        style={{
                                                            width: '14.28%', aspectRatio: 1, alignItems: 'center', justifyContent: 'center',
                                                            borderRadius: 5,
                                                            backgroundColor: isBlocked ? '#EF444422' : 'transparent',
                                                            opacity: isPast ? 0.3 : 1,
                                                        }}
                                                        onPress={() => !isPast && setListingBlockedDates(prev =>
                                                            prev.includes(dateStr) ? prev.filter(d => d !== dateStr) : [...prev, dateStr]
                                                        )}
                                                        disabled={isPast}
                                                    >
                                                        <Text style={{ fontSize: 12, fontWeight: '600', color: isBlocked ? '#EF4444' : dateStr === todayStr ? '#25D366' : '#FFFFFF' }}>
                                                            {dayNum}
                                                        </Text>
                                                        {isBlocked && <View style={{ width: 3, height: 3, borderRadius: 2, backgroundColor: '#EF4444', marginTop: 1 }} />}
                                                    </TouchableOpacity>
                                                );
                                            })}
                                        </View>
                                        {/* Legend + count */}
                                        <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 8, gap: 12 }}>
                                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                                                <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: '#EF444422', borderWidth: 1, borderColor: '#EF4444' }} />
                                                <Text style={{ color: '#64748B', fontSize: 11 }}>Blocked</Text>
                                            </View>
                                            {listingBlockedDates.length > 0 && (
                                                <>
                                                    <Text style={{ color: '#64748B', fontSize: 11 }}>{listingBlockedDates.length} date{listingBlockedDates.length !== 1 ? 's' : ''} blocked</Text>
                                                    <TouchableOpacity onPress={() => setListingBlockedDates([])} style={{ marginLeft: 'auto' }}>
                                                        <Text style={{ color: '#64748B', fontSize: 11, textDecorationLine: 'underline' }}>Clear all</Text>
                                                    </TouchableOpacity>
                                                </>
                                            )}
                                        </View>
                                        <TouchableOpacity
                                            style={{ marginTop: 12, backgroundColor: '#25D366', borderRadius: 8, paddingVertical: 10, alignItems: 'center', opacity: savingListingAvail ? 0.6 : 1 }}
                                            onPress={() => saveListingAvailability(selectedProduct.id)}
                                            disabled={savingListingAvail}
                                        >
                                            {savingListingAvail
                                                ? <ActivityIndicator size="small" color="#FFF" />
                                                : <Text style={{ color: '#FFF', fontWeight: '600', fontSize: 13 }}>Save Availability</Text>
                                            }
                                        </TouchableOpacity>
                                    </View>
                                )}

                                {/* Action Buttons */}
                                <View style={styles.actionButtons}>
                                    <TouchableOpacity
                                        style={styles.actionBtn}
                                        onPress={() => handleToggleStock(selectedProduct)}
                                    >
                                        <Ionicons
                                            name={selectedProduct.in_stock === false ? 'checkmark-circle-outline' : 'close-circle-outline'}
                                            size={22}
                                            color={selectedProduct.in_stock === false ? '#25D366' : '#FF6B6B'}
                                        />
                                        <Text style={styles.actionBtnText}>
                                            {selectedProduct.in_stock === false ? 'Mark In Stock' : 'Mark Out of Stock'}
                                        </Text>
                                    </TouchableOpacity>

                                    <TouchableOpacity
                                        style={styles.actionBtn}
                                        onPress={() => startEdit(selectedProduct)}
                                    >
                                        <Ionicons name="create-outline" size={22} color="#4A90D9" />
                                        <Text style={styles.actionBtnText}>{`Edit ${itemLabel}`}</Text>
                                    </TouchableOpacity>

                                    <TouchableOpacity
                                        style={[styles.actionBtn, styles.actionBtnDanger]}
                                        onPress={() => handleDeleteProduct(selectedProduct)}
                                    >
                                        <Ionicons name="trash-outline" size={22} color="#FF6B6B" />
                                        <Text style={[styles.actionBtnText, { color: '#FF6B6B' }]}>Delete</Text>
                                    </TouchableOpacity>
                                </View>
                            </View>
                        </View>
                    ) : null}
                </ScrollView>
            </SafeAreaView>
        </Modal>
    );

    // ============ MAIN CATALOG VIEW ============

    return (
        <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
            <SafeAreaView style={styles.container}>
                {/* Header */}
                <View style={styles.header}>
                    <TouchableOpacity onPress={onClose}>
                        <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>{`${catalogLabel} Catalog`}</Text>
                    <TouchableOpacity onPress={startAddProduct}>
                        <Ionicons name="add-circle-outline" size={26} color="#25D366" />
                    </TouchableOpacity>
                </View>

                {/* Search Bar */}
                <View style={styles.searchContainer}>
                    <View style={styles.searchBar}>
                        <Ionicons name="search-outline" size={18} color="#8899AA" />
                        <TextInput
                            style={styles.searchInput}
                            placeholder="Search products..."
                            placeholderTextColor="#556"
                            value={searchQuery}
                            onChangeText={setSearchQuery}
                        />
                        {searchQuery ? (
                            <TouchableOpacity onPress={() => setSearchQuery('')}>
                                <Ionicons name="close-circle" size={18} color="#556" />
                            </TouchableOpacity>
                        ) : null}
                    </View>
                </View>

                {/* Stats Bar */}
                <View style={styles.statsBar}>
                    <View style={styles.statItem}>
                        <Text style={[styles.statNumber, maxProducts !== null && products.length >= maxProducts && { color: '#FF6B6B' }]}>
                            {products.length}{maxProducts !== null ? `/${maxProducts}` : ''}
                        </Text>
                        <Text style={styles.statLabel}>Products</Text>
                    </View>
                    <View style={styles.statDivider} />
                    <View style={styles.statItem}>
                        <Text style={[styles.statNumber, { color: '#25D366' }]}>{inStockCount}</Text>
                        <Text style={styles.statLabel}>In Stock</Text>
                    </View>
                    <View style={styles.statDivider} />
                    <View style={styles.statItem}>
                        <Text style={[styles.statNumber, { color: '#FF6B6B' }]}>{outOfStockCount}</Text>
                        <Text style={styles.statLabel}>Out</Text>
                    </View>
                    <View style={styles.statDivider} />
                    <View style={styles.statItem}>
                        <Text style={styles.statNumber}>{categories.length - 1}</Text>
                        <Text style={styles.statLabel}>Categories</Text>
                    </View>
                </View>

                {/* Category Tabs */}
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryScroll} contentContainerStyle={styles.categoryScrollContent}>
                    {categories.map(cat => (
                        <TouchableOpacity
                            key={cat}
                            style={[styles.categoryTab, selectedCategory === cat && styles.categoryTabActive]}
                            onPress={() => setSelectedCategory(cat)}
                        >
                            <Text style={[styles.categoryTabText, selectedCategory === cat && styles.categoryTabTextActive]}>
                                {cat}
                            </Text>
                            {cat !== 'All' && (
                                <Text style={[styles.categoryCount, selectedCategory === cat && styles.categoryCountActive]}>
                                    {products.filter(p => (p.category || 'Other') === cat).length}
                                </Text>
                            )}
                        </TouchableOpacity>
                    ))}
                </ScrollView>

                {/* Content */}
                {loading ? (
                    <View style={styles.loadingContainer}>
                        <ActivityIndicator size="large" color="#25D366" />
                        <Text style={styles.loadingText}>Loading products...</Text>
                    </View>
                ) : filteredProducts.length > 0 ? (
                    <ScrollView style={styles.content} contentContainerStyle={styles.gridContainer}>
                        <View style={styles.productGrid}>
                            {filteredProducts.map(renderProductCard)}
                        </View>
                    </ScrollView>
                ) : products.length > 0 ? (
                    <View style={styles.emptyState}>
                        <Ionicons name="search-outline" size={48} color="#3A4A5C" />
                        <Text style={styles.emptyText}>No products found</Text>
                        <Text style={styles.emptySubtext}>Try a different search or category</Text>
                    </View>
                ) : (
                    <View style={styles.emptyState}>
                        <View style={styles.emptyIcon}>
                            <Ionicons name="storefront-outline" size={64} color="#25D366" />
                        </View>
                        <Text style={styles.emptyText}>Your catalog is empty</Text>
                        <Text style={styles.emptySubtext}>{`Add ${catalogLabel.toLowerCase()} to share with customers and let AI recommend them automatically`}</Text>
                        <View style={styles.emptyActionRow}>
                            <TouchableOpacity style={styles.emptyUploadBtn} onPress={() => handleUploadProducts('library')}>
                                <Ionicons name="images-outline" size={20} color="#FFF" />
                                <Text style={styles.emptyUploadText}>Gallery</Text>
                            </TouchableOpacity>
                            <TouchableOpacity style={styles.emptyCameraBtn} onPress={() => handleUploadProducts('camera')}>
                                <Ionicons name="camera-outline" size={20} color="#25D366" />
                                <Text style={styles.emptyCameraText}>Camera</Text>
                            </TouchableOpacity>
                        </View>
                        <TouchableOpacity style={styles.emptyAddBtn} onPress={startAddProduct}>
                            <Ionicons name="add-circle-outline" size={20} color="#25D366" />
                            <Text style={styles.emptyAddText}>Add Manually</Text>
                        </TouchableOpacity>
                    </View>
                )}

                {/* FABs */}
                {products.length > 0 && (
                    <View style={styles.fabsContainer}>
                        <TouchableOpacity
                            style={[styles.fab, styles.fabGallery, uploading && { opacity: 0.6 }]}
                            onPress={() => handleUploadProducts('library')}
                            disabled={uploading}
                        >
                            <Ionicons name="images-outline" size={24} color="#FFF" />
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={[styles.fab, styles.fabCamera, uploading && { opacity: 0.6 }]}
                            onPress={() => handleUploadProducts('camera')}
                            disabled={uploading}
                        >
                            {uploading ? (
                                <ActivityIndicator color="#FFF" size="small" />
                            ) : (
                                <Ionicons name="camera" size={26} color="#FFF" />
                            )}
                        </TouchableOpacity>
                    </View>
                )}

                {renderDetailModal()}
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

    // Search
    searchContainer: {
        paddingHorizontal: 20,
        paddingTop: 12,
        paddingBottom: 4,
    },
    searchBar: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#1A2942',
        borderRadius: 12,
        paddingHorizontal: 14,
        paddingVertical: 10,
        gap: 8,
    },
    searchInput: {
        flex: 1,
        color: '#FFFFFF',
        fontSize: 15,
    },

    // Stats
    statsBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-around',
        paddingVertical: 12,
        paddingHorizontal: 20,
        marginHorizontal: 20,
        marginTop: 8,
        backgroundColor: '#1A2942',
        borderRadius: 12,
    },
    statItem: {
        alignItems: 'center',
    },
    statNumber: {
        fontSize: 18,
        fontWeight: '700',
        color: '#FFFFFF',
    },
    statLabel: {
        fontSize: 11,
        color: '#8899AA',
        marginTop: 2,
    },
    statDivider: {
        width: 1,
        height: 28,
        backgroundColor: '#2A3A52',
    },

    // Categories
    categoryScroll: {
        maxHeight: 44,
        marginTop: 12,
    },
    categoryScrollContent: {
        paddingHorizontal: 20,
        gap: 8,
    },
    categoryTab: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderRadius: 20,
        backgroundColor: '#1A2942',
        gap: 6,
    },
    categoryTabActive: {
        backgroundColor: '#25D366',
    },
    categoryTabText: {
        fontSize: 13,
        fontWeight: '600',
        color: '#8899AA',
    },
    categoryTabTextActive: {
        color: '#FFFFFF',
    },
    categoryCount: {
        fontSize: 11,
        fontWeight: '700',
        color: '#556',
        backgroundColor: '#0D1B2A',
        paddingHorizontal: 6,
        paddingVertical: 1,
        borderRadius: 8,
        overflow: 'hidden',
    },
    categoryCountActive: {
        color: '#FFF',
        backgroundColor: 'rgba(0,0,0,0.2)',
    },

    // Content & Grid
    content: {
        flex: 1,
    },
    gridContainer: {
        paddingHorizontal: 20,
        paddingTop: 16,
        paddingBottom: 100,
    },
    productGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: CARD_GAP,
    },

    // Product Card
    productCard: {
        width: CARD_WIDTH,
        backgroundColor: '#1A2942',
        borderRadius: 16,
        overflow: 'hidden',
        marginBottom: 2,
    },
    productCardOutOfStock: {
        opacity: 0.6,
    },
    productImage: {
        width: '100%',
        height: CARD_WIDTH * 0.85,
        backgroundColor: '#0D1B2A',
    },
    noImagePlaceholder: {
        justifyContent: 'center',
        alignItems: 'center',
    },
    outOfStockBadge: {
        position: 'absolute',
        top: 8,
        left: 8,
        backgroundColor: 'rgba(255,107,107,0.9)',
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 6,
    },
    outOfStockText: {
        color: '#FFF',
        fontSize: 10,
        fontWeight: '700',
    },
    productInfo: {
        padding: 12,
    },
    productName: {
        fontSize: 14,
        fontWeight: '600',
        color: '#FFFFFF',
        marginBottom: 4,
        lineHeight: 18,
    },
    productPrice: {
        fontSize: 16,
        fontWeight: '700',
        color: '#25D366',
        marginBottom: 8,
    },
    priceContainer: {
        marginBottom: 8,
    },
    discountPrice: {
        fontSize: 16,
        fontWeight: '700',
        color: '#25D366',
    },
    originalPrice: {
        fontSize: 13,
        color: '#8899AA',
        textDecorationLine: 'line-through',
        marginLeft: 8,
    },
    productMeta: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    categoryBadge: {
        backgroundColor: '#0D1B2A',
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 6,
        maxWidth: '80%',
    },
    categoryBadgeText: {
        fontSize: 10,
        fontWeight: '600',
        color: '#8899AA',
    },
    stockDot: {
        width: 8,
        height: 8,
        borderRadius: 4,
    },
    stockDotGreen: {
        backgroundColor: '#25D366',
    },
    stockDotRed: {
        backgroundColor: '#FF6B6B',
    },

    // Loading
    loadingContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        gap: 12,
    },
    loadingText: {
        color: '#8899AA',
        fontSize: 14,
    },

    // Empty State
    emptyState: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 40,
    },
    emptyIcon: {
        width: 100,
        height: 100,
        borderRadius: 50,
        backgroundColor: '#1A2942',
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 16,
    },
    emptyText: {
        fontSize: 20,
        fontWeight: '700',
        color: '#FFFFFF',
        marginTop: 8,
    },
    emptySubtext: {
        fontSize: 14,
        color: '#8899AA',
        marginTop: 8,
        textAlign: 'center',
        lineHeight: 20,
    },
    emptyUploadBtn: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#25D366',
        paddingHorizontal: 20,
        paddingVertical: 14,
        borderRadius: 12,
        gap: 8,
    },
    emptyUploadText: {
        color: '#FFF',
        fontSize: 16,
        fontWeight: '700',
    },
    emptyCameraBtn: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#112233',
        paddingHorizontal: 20,
        paddingVertical: 14,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: '#25D366',
        gap: 8,
    },
    emptyCameraText: {
        color: '#25D366',
        fontSize: 16,
        fontWeight: '700',
    },
    emptyActionRow: {
        flexDirection: 'row',
        gap: 12,
        marginBottom: 12,
        width: '100%',
        paddingHorizontal: 10,
    },
    emptyAddBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 24,
        paddingVertical: 12,
        gap: 8,
        marginTop: 12,
    },
    emptyAddText: {
        color: '#25D366',
        fontSize: 15,
        fontWeight: '600',
    },

    // FAB
    fab: {
        width: 50,
        height: 50,
        borderRadius: 25,
        backgroundColor: '#25D366',
        justifyContent: 'center',
        alignItems: 'center',
        elevation: 5,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.25,
        shadowRadius: 3.84,
    },
    fabsContainer: {
        position: 'absolute',
        bottom: 30,
        right: 20,
        flexDirection: 'row',
        gap: 12,
    },
    fabGallery: {
        backgroundColor: '#334455',
    },
    fabCamera: {
        backgroundColor: '#25D366',
    },
    // Detail View
    detailContent: {
        flex: 1,
    },
    detailImage: {
        width: '100%',
        height: 280,
        backgroundColor: '#0D1B2A',
    },
    detailBody: {
        padding: 20,
    },
    detailNameRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: 12,
    },
    detailName: {
        fontSize: 22,
        fontWeight: '700',
        color: '#FFFFFF',
        flex: 1,
    },
    stockBadge: {
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 8,
    },
    stockBadgeGreen: {
        backgroundColor: '#1A3A2A',
    },
    stockBadgeRed: {
        backgroundColor: '#3A1A1A',
    },
    stockBadgeText: {
        fontSize: 12,
        fontWeight: '600',
        color: '#FFFFFF',
    },
    detailPrice: {
        fontSize: 28,
        fontWeight: '800',
        color: '#25D366',
        marginTop: 8,
    },
    detailCategoryRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        marginTop: 12,
    },
    detailCategory: {
        fontSize: 14,
        color: '#8899AA',
        marginLeft: 6,
    },
    detailStockInfo: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    descriptionBox: {
        marginTop: 20,
        padding: 16,
        backgroundColor: '#1A2942',
        borderRadius: 12,
    },
    descriptionLabel: {
        fontSize: 12,
        fontWeight: '600',
        color: '#8899AA',
        marginBottom: 6,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    descriptionText: {
        fontSize: 15,
        color: '#CCD6E0',
        lineHeight: 22,
    },

    // Action Buttons
    actionButtons: {
        marginTop: 24,
        gap: 10,
    },
    actionBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#1A2942',
        padding: 16,
        borderRadius: 12,
        gap: 12,
    },
    actionBtnDanger: {
        backgroundColor: '#2A1A1A',
    },
    actionBtnText: {
        fontSize: 15,
        fontWeight: '600',
        color: '#CCD6E0',
    },

    // Edit Form
    editForm: {
        padding: 20,
    },
    formGroup: {
        marginBottom: 18,
    },
    formLabel: {
        fontSize: 13,
        fontWeight: '600',
        color: '#8899AA',
        marginBottom: 6,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    formInput: {
        backgroundColor: '#1A2942',
        borderRadius: 12,
        padding: 14,
        color: '#FFFFFF',
        fontSize: 15,
        borderWidth: 1,
        borderColor: '#2A3A52',
    },
    stockToggleRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: '#1A2942',
        padding: 16,
        borderRadius: 12,
        marginBottom: 18,
    },
    stockHint: {
        fontSize: 12,
        color: '#556',
        marginTop: 2,
    },
    typeChip: {
        paddingHorizontal: 12,
        paddingVertical: 7,
        borderRadius: 8,
        backgroundColor: '#0F1E35',
        borderWidth: 1,
        borderColor: '#1A2942',
        marginRight: 6,
    },
    typeChipActive: {
        borderColor: '#25D366',
        backgroundColor: 'rgba(37,211,102,0.12)',
    },
    typeChipText: {
        color: '#94A3B8',
        fontSize: 13,
    },
    typeChipTextActive: {
        color: '#25D366',
        fontWeight: '600',
    },
    uploadImageBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#1A2942',
        padding: 14,
        borderRadius: 12,
        gap: 8,
        marginBottom: 18,
        borderWidth: 1,
        borderColor: '#25D366',
        borderStyle: 'dashed',
    },
    uploadImageText: {
        color: '#25D366',
        fontSize: 14,
        fontWeight: '600',
        marginLeft: 8,
    },
    imageActionRow: {
        flexDirection: 'row',
        gap: 12,
        marginBottom: 12,
    },
    imageActionBtn: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#0D1B2A',
        borderWidth: 1,
        borderColor: '#1A3A2A',
        borderRadius: 12,
        paddingVertical: 12,
    },
    imageActionText: {
        color: '#25D366',
        fontSize: 14,
        fontWeight: '600',
        marginLeft: 8,
    },
    saveBtn: {
        backgroundColor: '#25D366',
        padding: 16,
        borderRadius: 12,
        alignItems: 'center',
        marginBottom: 12,
    },
    saveBtnText: {
        color: '#FFF',
        fontSize: 16,
        fontWeight: '700',
    },
    deleteBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 14,
        borderRadius: 12,
        gap: 8,
        backgroundColor: '#2A1A1A',
    },
    deleteBtnText: {
        color: '#FF6B6B',
        fontSize: 14,
        fontWeight: '600',
    },
    // Image Gallery
    imageDots: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 10,
        backgroundColor: '#0A1628',
    },
    imageDot: {
        width: 8,
        height: 8,
        borderRadius: 4,
        backgroundColor: '#2A3A52',
    },
    imageDotActive: {
        backgroundColor: '#25D366',
        width: 10,
        height: 10,
        borderRadius: 5,
    },
    imageCountBar: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 20,
        paddingVertical: 8,
        backgroundColor: '#0D1B2A',
    },
    imageCountText: {
        color: '#8899AA',
        fontSize: 12,
        fontWeight: '600',
    },
    aiBanner: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        backgroundColor: '#FEF3C7',
        borderRadius: 10,
        padding: 12,
        marginBottom: 16,
    },
    aiBannerText: {
        flex: 1,
        color: '#92400e',
        fontSize: 13,
        fontWeight: '500',
        lineHeight: 18,
    },
    editThumbnailsContainer: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 12,
        marginTop: 4,
        marginBottom: 20,
    },
    editThumbnailWrapper: {
        position: 'relative',
    },
    editThumbnail: {
        width: 60,
        height: 60,
        borderRadius: 8,
        backgroundColor: '#0A1628',
    },
    deleteThumbnailBtn: {
        position: 'absolute',
        top: -6,
        right: -6,
        backgroundColor: '#0D1B2A',
        borderRadius: 10,
    },
});
