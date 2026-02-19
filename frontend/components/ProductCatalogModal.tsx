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

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const CARD_GAP = 10;
const CARD_WIDTH = (SCREEN_WIDTH - 48 - CARD_GAP) / 2;

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
    created_at: string;
}

interface ProductCatalogModalProps {
    visible: boolean;
    onClose: () => void;
}

export default function ProductCatalogModal({
    visible,
    onClose,
}: ProductCatalogModalProps) {
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
    const [saving, setSaving] = useState(false);
    const [activeImageIndex, setActiveImageIndex] = useState(0);
    const [addingPhotos, setAddingPhotos] = useState(false);

    const MAX_PRODUCTS = 20;

    useEffect(() => {
        const loadCurrency = async () => {
            try {
                const settings = await settingsAPI.getSettings();
                if (settings.currency) setCurrency(settings.currency);
            } catch (e) {}
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

    const handleUploadProducts = async () => {
        if (products.length >= MAX_PRODUCTS) {
            Alert.alert('Limit Reached', `You can have a maximum of ${MAX_PRODUCTS} products. Delete some to add new ones.`);
            return;
        }
        try {
            const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
            if (status !== 'granted') {
                Alert.alert('Permission needed', 'Please allow access to your photos');
                return;
            }

            const result = await ImagePicker.launchImageLibraryAsync({
                mediaTypes: ['images'] as any,
                allowsMultipleSelection: true,
                quality: 0.8,
            });

            if (!result.canceled && result.assets.length > 0) {
                setUploading(true);
                try {
                    const response = await productsAPI.uploadProducts(result.assets);
                    Alert.alert(
                        'Products Added!',
                        `${response.products_created} product${response.products_created !== 1 ? 's' : ''} uploaded. AI suggested names & prices — tap any product to review and edit.`,
                        [{ text: 'OK', onPress: fetchProducts }]
                    );
                } catch (error) {
                    console.error('Upload error:', error);
                    Alert.alert('Error', 'Failed to upload products');
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
            'Delete Product',
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
                            Alert.alert('Error', 'Failed to delete product');
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
        setSelectedProduct(product);
        setEditMode(true);
        setDetailVisible(true);
        console.log('Edit mode set to true, detailVisible set to true');
    };

    const startAddProduct = () => {
        if (products.length >= MAX_PRODUCTS) {
            Alert.alert('Limit Reached', `You can have a maximum of ${MAX_PRODUCTS} products. Delete some to add new ones.`);
            return;
        }
        setEditName('');
        setEditPrice('');
        setEditDiscountPrice('');
        setEditCategory('Other');
        setEditDescription('');
        setEditInStock(true);
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
            if (addMode) {
                const productData: any = {
                    name: editName.trim(),
                    price: parseFloat(editPrice),
                    category: editCategory.trim() || 'Other',
                    description: editDescription.trim() || undefined,
                    in_stock: editInStock,
                };
                if (discountPrice !== null) {
                    productData.discount_price = discountPrice;
                }
                await productsAPI.createProduct(productData);
            } else if (selectedProduct) {
                const updateData: any = {
                    name: editName.trim(),
                    price: parseFloat(editPrice),
                    category: editCategory.trim() || 'Other',
                    description: editDescription.trim() || undefined,
                    in_stock: editInStock,
                };
                if (discountPrice !== null) {
                    updateData.discount_price = discountPrice;
                }
                await productsAPI.updateProduct(selectedProduct.id, updateData);
            }
            setEditMode(false);
            setAddMode(false);
            setDetailVisible(false);
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

    const handleAddPhotosToProduct = async (product: Product) => {
        try {
            const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
            if (status !== 'granted') {
                Alert.alert('Permission needed', 'Please allow access to your photos');
                return;
            }
            const currentCount = (product.images || []).length;
            if (currentCount >= 5) {
                Alert.alert('Limit reached', 'Maximum 5 photos per product');
                return;
            }
            const result = await ImagePicker.launchImageLibraryAsync({
                mediaTypes: ['images'] as any,
                allowsMultipleSelection: true,
                quality: 0.8,
                selectionLimit: 5 - currentCount,
            });
            if (!result.canceled && result.assets.length > 0) {
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
        } catch (error) {
            Alert.alert('Error', 'Failed to open image picker');
        }
    };

    const handleDeletePhoto = async (product: Product, imageIndex: number) => {
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
        <Modal visible={detailVisible} animationType="slide" onRequestClose={() => { setDetailVisible(false); setEditMode(false); setAddMode(false); }}>
            <SafeAreaView style={styles.container}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => { setDetailVisible(false); setEditMode(false); setAddMode(false); }}>
                        <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>{addMode ? 'Add Product' : editMode ? 'Edit Product' : 'Product Details'}</Text>
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
                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Product Name *</Text>
                                <TextInput
                                    style={styles.formInput}
                                    value={editName}
                                    onChangeText={setEditName}
                                    placeholder="e.g. Chocolate Cake"
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
                                    placeholder="e.g. Cakes, Electronics, Clothing"
                                    placeholderTextColor="#555"
                                />
                            </View>

                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Description</Text>
                                <TextInput
                                    style={[styles.formInput, { height: 80, textAlignVertical: 'top' }]}
                                    value={editDescription}
                                    onChangeText={setEditDescription}
                                    placeholder="Describe your product..."
                                    placeholderTextColor="#555"
                                    multiline
                                    numberOfLines={3}
                                />
                            </View>

                            <View style={styles.stockToggleRow}>
                                <View>
                                    <Text style={styles.formLabel}>In Stock</Text>
                                    <Text style={styles.stockHint}>{editInStock ? 'Available for customers' : 'Hidden from AI replies'}</Text>
                                </View>
                                <Switch
                                    value={editInStock}
                                    onValueChange={setEditInStock}
                                    trackColor={{ false: '#333', true: '#1A3A2A' }}
                                    thumbColor={editInStock ? '#25D366' : '#666'}
                                />
                            </View>

                            {!addMode && selectedProduct && (
                                <TouchableOpacity
                                    style={styles.uploadImageBtn}
                                    onPress={() => handleAddPhotosToProduct(selectedProduct)}
                                    disabled={addingPhotos}
                                >
                                    {addingPhotos ? (
                                        <ActivityIndicator size="small" color="#25D366" />
                                    ) : (
                                        <>
                                            <Ionicons name="camera-outline" size={20} color="#25D366" />
                                            <Text style={styles.uploadImageText}>
                                                {(selectedProduct.images || []).length > 0
                                                    ? `Add Photos (${(selectedProduct.images || []).length}/5)`
                                                    : 'Add Photos'}
                                            </Text>
                                        </>
                                    )}
                                </TouchableOpacity>
                            )}

                            <TouchableOpacity
                                style={[styles.saveBtn, saving && { opacity: 0.6 }]}
                                onPress={handleSaveEdit}
                                disabled={saving}
                            >
                                {saving ? (
                                    <ActivityIndicator color="#FFF" size="small" />
                                ) : (
                                    <Text style={styles.saveBtnText}>{addMode ? 'Add Product' : 'Save Changes'}</Text>
                                )}
                            </TouchableOpacity>

                            {!addMode && selectedProduct && (
                                <TouchableOpacity style={styles.deleteBtn} onPress={() => handleDeleteProduct(selectedProduct)}>
                                    <Ionicons name="trash-outline" size={18} color="#FF6B6B" />
                                    <Text style={styles.deleteBtnText}>Delete Product</Text>
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
                                            {selectedProduct.in_stock === false ? 'Out of Stock' : 'In Stock'}
                                        </Text>
                                    </View>
                                </View>

                                <Text style={styles.detailPrice}>{currency} {selectedProduct.price.toLocaleString()}</Text>

                                <View style={styles.detailCategoryRow}>
                                    <Ionicons name="pricetag-outline" size={14} color="#8899AA" />
                                    <Text style={styles.detailCategory}>{selectedProduct.category || 'Other'}</Text>
                                </View>

                                {selectedProduct.description ? (
                                    <View style={styles.descriptionBox}>
                                        <Text style={styles.descriptionLabel}>Description</Text>
                                        <Text style={styles.descriptionText}>{selectedProduct.description}</Text>
                                    </View>
                                ) : null}

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
                                        <Text style={styles.actionBtnText}>Edit Product</Text>
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
                    <Text style={styles.headerTitle}>Product Catalog</Text>
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
                        <Text style={[styles.statNumber, products.length >= MAX_PRODUCTS && { color: '#FF6B6B' }]}>{products.length}/{MAX_PRODUCTS}</Text>
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
                        <Text style={styles.emptySubtext}>Add products to share with customers and let AI recommend them automatically</Text>
                        <TouchableOpacity style={styles.emptyUploadBtn} onPress={handleUploadProducts}>
                            <Ionicons name="cloud-upload-outline" size={20} color="#FFF" />
                            <Text style={styles.emptyUploadText}>Upload Product Photos</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.emptyAddBtn} onPress={startAddProduct}>
                            <Ionicons name="add-circle-outline" size={20} color="#25D366" />
                            <Text style={styles.emptyAddText}>Add Manually</Text>
                        </TouchableOpacity>
                    </View>
                )}

                {/* FAB - Upload */}
                {products.length > 0 && (
                    <TouchableOpacity
                        style={[styles.fab, uploading && { opacity: 0.6 }]}
                        onPress={handleUploadProducts}
                        disabled={uploading}
                    >
                        {uploading ? (
                            <ActivityIndicator color="#FFF" size="small" />
                        ) : (
                            <Ionicons name="camera" size={26} color="#FFF" />
                        )}
                    </TouchableOpacity>
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
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#25D366',
        paddingHorizontal: 24,
        paddingVertical: 14,
        borderRadius: 12,
        gap: 8,
        marginTop: 24,
    },
    emptyUploadText: {
        color: '#FFF',
        fontSize: 15,
        fontWeight: '600',
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
        position: 'absolute',
        bottom: 30,
        right: 20,
        width: 56,
        height: 56,
        borderRadius: 28,
        backgroundColor: '#25D366',
        justifyContent: 'center',
        alignItems: 'center',
        elevation: 8,
        shadowColor: '#25D366',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
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
});
