import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
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

// Creator-specific categories for content catalog
const CREATOR_CATEGORIES = [
    'Sponsored Post',
    'Instagram Reel', 
    'Instagram Story',
    'TikTok Video',
    'YouTube Video',
    'Brand Ambassador',
    'Product Review',
    'Shoutout',
    'Photo Shoot',
    'Video Testimonial',
    'Live Stream',
    'Podcast Mention',
    'Blog Post',
    'Other'
];

// Restaurant-specific categories
const RESTAURANT_CATEGORIES = [
    'Appetizers',
    'Main Course',
    'Desserts',
    'Beverages',
    'Breakfast',
    'Lunch Special',
    'Dinner Special',
    'Kids Menu',
    'Daily Special',
    'Other'
];

// Healthcare-specific categories
const HEALTHCARE_CATEGORIES = [
    'Consultation',
    'Check-up',
    'Treatment',
    'Surgery',
    'Therapy',
    'Diagnostic',
    'Vaccination',
    'Emergency',
    'Follow-up',
    'Other'
];

// Fitness-specific categories
const FITNESS_CATEGORIES = [
    'Yoga',
    'Cardio',
    'Strength Training',
    'Pilates',
    'CrossFit',
    'Dance',
    'Martial Arts',
    'Swimming',
    'Group Class',
    'Personal Training',
    'Other'
];

// Services/Tech-specific categories
const SERVICES_CATEGORIES = [
    'Repair',
    'Installation',
    'Maintenance',
    'Consultation',
    'Support',
    'Training',
    'Inspection',
    'Cleaning',
    'Delivery',
    'Other'
];

// Salon-specific categories
const SALON_CATEGORIES = [
    'Haircut',
    'Hair Color',
    'Styling',
    'Nails',
    'Facial',
    'Massage',
    'Waxing',
    'Makeup',
    'Treatment',
    'Other'
];

// Rental-specific categories  
const RENTAL_CATEGORIES = [
    'Apartment',
    'House',
    'Car',
    'Equipment',
    'Venue',
    'Office Space',
    'Storage',
    'Vacation Rental',
    'Long-term Rental',
    'Other'
];

// Spa-specific categories
const SPA_CATEGORIES = [
    'Swedish Massage',
    'Deep Tissue Massage',
    'Hot Stone Massage',
    'Facial',
    'Body Scrub',
    'Body Wrap',
    'Aromatherapy',
    'Couples Treatment',
    'Manicure & Pedicure',
    'Other'
];

// Cleaning-specific categories
const CLEANING_CATEGORIES = [
    'Deep Clean',
    'Regular Clean',
    'Move In/Out Clean',
    'Office Cleaning',
    'Post-Construction',
    'Carpet & Upholstery',
    'Window Cleaning',
    'Other'
];

// Events & Photography categories
const EVENTS_CATEGORIES = [
    'Wedding',
    'Birthday Party',
    'Corporate Event',
    'Graduation',
    'Baby Shower',
    'Product Launch',
    'Conference',
    'Portrait Session',
    'Other'
];

// Retail categories (physical products)
const RETAIL_CATEGORIES = [
    'Electronics',
    'Clothing',
    'Food & Beverages',
    'Home & Garden',
    'Beauty & Health',
    'Sports & Outdoors',
    'Books & Media',
    'Toys & Games',
    'Automotive',
    'Other'
];

// Bakery-specific categories
const BAKERY_CATEGORIES = [
    'Cakes',
    'Bread & Loaves',
    'Pastries & Croissants',
    'Cookies & Biscuits',
    'Cupcakes & Muffins',
    'Pies & Tarts',
    'Custom Orders',
    'Beverages',
    'Seasonal Specials',
    'Other'
];

// Grocery-specific categories
const GROCERY_CATEGORIES = [
    'Fresh Produce',
    'Dairy & Eggs',
    'Meat & Seafood',
    'Beverages',
    'Grains & Cereals',
    'Cooking Essentials',
    'Snacks & Confectionery',
    'Household & Cleaning',
    'Personal Care',
    'Baby & Kids',
    'Other'
];

const GROCERY_UNITS = [
    'per piece', 'per kg', 'per g', 'per packet',
    'per bottle', 'per litre', 'per dozen', 'per bundle', 'per box', 'per bag',
];

// Wholesale-specific categories
const WHOLESALE_CATEGORIES = [
    'Food & Beverages',
    'Electronics & Appliances',
    'Clothing & Textiles',
    'Beauty & Personal Care',
    'Household Products',
    'Industrial & Hardware',
    'Stationery & Office',
    'Agricultural Products',
    'Pharmaceutical',
    'Other'
];

const WHOLESALE_UNITS = [
    'per carton', 'per case', 'per dozen', 'per pallet',
    'per kg', 'per bag', 'per box', 'per bundle', 'per piece',
];

interface Variant {
    name: string;
    price: number;
}

interface PricingTier {
    min_qty: number;
    price: number;
}

interface ModifierOption {
    name: string;
    price_delta: number;
}

interface ModifierGroup {
    name: string;
    required: boolean;
    multi_select: boolean;
    options: ModifierOption[];
}

interface Product {
    id: string;
    name: string;
    price: number;
    discount_price?: number;
    image_url: string;
    images: string[];
    category: string;
    sub_category?: string;
    description?: string;
    in_stock: boolean;
    stock_quantity?: number;
    variants?: Variant[];
    modifier_groups?: ModifierGroup[];
    unit?: string;
    moq?: number;
    pricing_tiers?: PricingTier[];
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
    const [editDescription, setEditDescription] = useState('');
    const [editCategory, setEditCategory] = useState('');
    const [editSubCategory, setEditSubCategory] = useState('');
    const [editStockQuantity, setEditStockQuantity] = useState('');
    const [editInStock, setEditInStock] = useState(true);
    const [editImages, setEditImages] = useState<string[]>([]);
    const [isGeneratingDescription, setIsGeneratingDescription] = useState(false);
    const [saving, setSaving] = useState(false);
    const [activeImageIndex, setActiveImageIndex] = useState(0);
    const [addingPhotos, setAddingPhotos] = useState(false);
    const [aiFailedBanner, setAiFailedBanner] = useState(false);
    const [pendingAssets, setPendingAssets] = useState<ImagePicker.ImagePickerAsset[]>([]);
    const [planLimits, setPlanLimits] = useState<{ products: number | null; images: number | null }>({ products: 20, images: 100 });
    const [subscriptionPlan, setSubscriptionPlan] = useState('free');

    // Variants state
    const [editVariants, setEditVariants] = useState<Variant[]>([]);
    const [newVariantName, setNewVariantName] = useState('');
    const [newVariantPrice, setNewVariantPrice] = useState('');

    // Modifier groups state
    const [editModifierGroups, setEditModifierGroups] = useState<ModifierGroup[]>([]);
    const [newGroupName, setNewGroupName] = useState('');
    const [newGroupRequired, setNewGroupRequired] = useState(false);
    const [newGroupMulti, setNewGroupMulti] = useState(false);
    const [newGroupOptions, setNewGroupOptions] = useState<ModifierOption[]>([]);
    const [newOptionName, setNewOptionName] = useState('');
    const [newOptionPrice, setNewOptionPrice] = useState('');
    const [showAddGroup, setShowAddGroup] = useState(false);

    // Ref for description TextInput to control scroll position
    const descriptionInputRef = useRef<TextInput>(null);

    const [editUnit, setEditUnit] = useState('');
    const [editMoq, setEditMoq] = useState('');
    const [editPricingTiers, setEditPricingTiers] = useState<PricingTier[]>([]);
    const [newTierMinQty, setNewTierMinQty] = useState('');
    const [newTierPrice, setNewTierPrice] = useState('');

    const { config, businessType } = useBusiness();
    const catalogLabel = config.catalogLabel;
    const itemLabel = config.catalogItemLabel;
    const showStock = config.showStock;
    const isCreator    = config.customerLabel === 'Fan';
    const isRestaurant = catalogLabel === 'Menu' && businessType === 'restaurant';
    const isBakery     = businessType === 'bakery';
    const isGrocery    = businessType === 'grocery';
    const isWholesale  = businessType === 'wholesale';
    const isRental     = catalogLabel === 'Listings';
    const isHealthcare = config.customerLabel === 'Patient';
    const isFitness    = config.customerLabel === 'Member' && config.bookingLabel === 'Class';
    const isServices   = config.customerLabel === 'Client' && config.staffLabel === 'Technician';
    const isSalon      = config.customerLabel === 'Client' && config.staffLabel === 'Stylist';
    const isSpa        = config.catalogLabel === 'Treatments';
    const isCleaning   = config.catalogLabel === 'Packages' && config.staffLabel === '';
    const isEvents     = config.staffLabel === 'Photographer';

    const maxProducts = planLimits.products;
    const maxImages = planLimits.images;

    // Get appropriate categories based on business type
    const getAppropriateCategories = () => {
        if (isCreator)     return CREATOR_CATEGORIES;
        if (isRestaurant)  return RESTAURANT_CATEGORIES;
        if (isBakery)      return BAKERY_CATEGORIES;
        if (isGrocery)     return GROCERY_CATEGORIES;
        if (isWholesale)   return WHOLESALE_CATEGORIES;
        if (isHealthcare)  return HEALTHCARE_CATEGORIES;
        if (isFitness)     return FITNESS_CATEGORIES;
        if (isServices)    return SERVICES_CATEGORIES;
        if (isSalon)       return SALON_CATEGORIES;
        if (isRental)      return RENTAL_CATEGORIES;
        if (isSpa)         return SPA_CATEGORIES;
        if (isCleaning)    return CLEANING_CATEGORIES;
        if (isEvents)      return EVENTS_CATEGORIES;
        return RETAIL_CATEGORIES;
    };

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
            Alert.alert('Plan Limit Reached', `Your ${subscriptionPlan} plan allows ${maxProducts} ${itemLabel.toLowerCase()}s. Upgrade to add more.`);
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
                                    `${response.products.length} ${catalogLabel} Items Uploaded`,
                                    'Reviewing the first one — go back to the catalog to check the rest.',
                                    [{ text: 'OK' }]
                                );
                            }, 500);
                        }
                    }
                } catch (error) {
                    console.error('Upload error:', error);
                    Alert.alert('Upload Failed', `Could not upload ${itemLabel.toLowerCase()}s. Please try again.`);
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

    // AI Description Generation Functions
    const getBusinessType = () => {
        if (isCreator) return 'creator';
        if (isRestaurant) return 'restaurant';
        if (isRental) return 'rental';
        if (isHealthcare) return 'healthcare';
        if (isFitness) return 'fitness';
        if (isServices) return 'services';
        if (isSalon) return 'salon';
        return 'retail';
    };

    const handleAIGenerateDescription = async () => {
        if (!editName.trim()) {
            Alert.alert('Missing Information', 'Please enter a product name first, then AI can generate a description.');
            return;
        }

        setIsGeneratingDescription(true);
        try {
            const result = await productsAPI.generateAIDescription({
                product_name: editName,
                category: editCategory || undefined,
                business_type: getBusinessType(),
                mode: 'generate'
            });
            
            if (result.description) {
                setEditDescription(result.description);
                // Scroll to top of description after setting it
                setTimeout(() => {
                    descriptionInputRef.current?.setNativeProps({
                        selection: { start: 0, end: 0 }
                    });
                }, 100);
            } else {
                throw new Error('No description generated');
            }
        } catch (error: any) {
            console.error('AI generation error:', error);
            Alert.alert(
                'AI Generation Failed',
                error.response?.data?.detail || 'Unable to generate description right now. Please try writing it manually.',
                [{ text: 'OK' }]
            );
        } finally {
            setIsGeneratingDescription(false);
        }
    };

    const handleAIImproveDescription = async () => {
        if (!editDescription.trim()) {
            handleAIGenerateDescription();
            return;
        }

        setIsGeneratingDescription(true);
        try {
            const result = await productsAPI.generateAIDescription({
                product_name: editName,
                category: editCategory || undefined,
                business_type: getBusinessType(),
                current_description: editDescription,
                mode: 'improve'
            });
            
            if (result.description) {
                setEditDescription(result.description);
                // Scroll to top of description after setting it
                setTimeout(() => {
                    descriptionInputRef.current?.setNativeProps({
                        selection: { start: 0, end: 0 }
                    });
                }, 100);
            } else {
                throw new Error('No improvement generated');
            }
        } catch (error: any) {
            console.error('AI improvement error:', error);
            Alert.alert(
                'AI Improvement Failed',
                error.response?.data?.detail || 'Unable to improve description right now. Please try editing it manually.',
                [{ text: 'OK' }]
            );
        } finally {
            setIsGeneratingDescription(false);
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
        setEditSubCategory(product.sub_category || '');
        setEditUnit((product as any).unit || '');
        setEditMoq((product as any).moq ? String((product as any).moq) : '');
        setEditPricingTiers((product as any).pricing_tiers || []);
        setEditDescription(product.description || '');
        setEditInStock(product.in_stock);
        setEditStockQuantity(product.stock_quantity?.toString() || '');
        setEditVariants(product.variants || []);
        setNewVariantName('');
        setNewVariantPrice('');
        setEditModifierGroups(product.modifier_groups || []);
        setNewGroupName('');
        setNewGroupRequired(false);
        setNewGroupMulti(false);
        setNewGroupOptions([]);
        setShowAddGroup(false);
        setSelectedProduct(product);
        setEditMode(true);
        setDetailVisible(true);
        console.log('Edit mode set to true, detailVisible set to true');
    };

    const startAddProduct = () => {
        if (maxProducts !== null && products.length >= maxProducts) {
            Alert.alert('Plan Limit Reached', `Your ${subscriptionPlan} plan allows ${maxProducts} ${itemLabel.toLowerCase()}s. Upgrade to add more.`);
            return;
        }
        setEditName('');
        setEditPrice('');
        setEditDiscountPrice('');
        setEditCategory('Other');
        setEditSubCategory('');
        setEditUnit('');
        setEditMoq('');
        setEditPricingTiers([]);
        setNewTierMinQty('');
        setNewTierPrice('');
        setEditDescription('');
        setEditInStock(true);
        setEditStockQuantity('');
        setEditVariants([]);
        setNewVariantName('');
        setNewVariantPrice('');
        setEditModifierGroups([]);
        setNewGroupName('');
        setNewGroupRequired(false);
        setNewGroupMulti(false);
        setNewGroupOptions([]);
        setShowAddGroup(false);
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

            const variantsToSave = editVariants.filter(v => v.name.trim());
            const modifierGroupsToSave = editModifierGroups.filter(g => g.name.trim() && g.options.length > 0);

            if (addMode) {
                const productData: any = {
                    name: editName.trim(),
                    price: parseFloat(editPrice),
                    category: editCategory.trim() || 'Other',
                    description: editDescription.trim() || undefined,
                    in_stock: editInStock,
                    stock_quantity: stockQuantity,
                    variants: variantsToSave.length > 0 ? variantsToSave : undefined,
                    modifier_groups: modifierGroupsToSave.length > 0 ? modifierGroupsToSave : undefined,
                    sub_category: editSubCategory.trim() || undefined,
                    unit: editUnit.trim() || undefined,
                    moq: editMoq ? parseInt(editMoq) : undefined,
                    pricing_tiers: editPricingTiers.length > 0 ? editPricingTiers : undefined,
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
                    variants: variantsToSave,
                    modifier_groups: modifierGroupsToSave,
                    sub_category: editSubCategory.trim() || undefined,
                    unit: editUnit.trim() || undefined,
                    moq: editMoq ? parseInt(editMoq) : undefined,
                    pricing_tiers: editPricingTiers,
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
                            <Text style={styles.productPrice}>{currency} {product.price.toLocaleString()}{(product as any).unit ? ` / ${(product as any).unit.replace('per ', '')}` : ''}</Text>
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

    // ============ RESTAURANT LIST ROW ============
    const EMOJI_NUMS = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟'];

    const renderMenuRow = (product: Product, index: number) => {
        const imageUri = getImageUri(product);
        const isOutOfStock = product.in_stock === false;
        const num = EMOJI_NUMS[index] ?? `${index + 1}.`;

        return (
            <TouchableOpacity
                key={product.id}
                style={styles.menuRow}
                onPress={() => openProductDetail(product)}
                activeOpacity={0.75}
            >
                {/* Number badge */}
                <Text style={styles.menuNum}>{num}</Text>

                {/* Thumbnail */}
                {imageUri ? (
                    <Image source={{ uri: imageUri }} style={styles.menuThumb} resizeMode="cover" />
                ) : (
                    <View style={[styles.menuThumb, styles.noImagePlaceholder]}>
                        <Ionicons name="image-outline" size={22} color="#3A4A5C" />
                    </View>
                )}

                {/* Info */}
                <View style={styles.menuInfo}>
                    <Text style={styles.menuName} numberOfLines={1}>{product.name}</Text>
                    {product.description ? (
                        <Text style={styles.menuDesc} numberOfLines={2}>{product.description}</Text>
                    ) : null}
                    <View style={styles.menuBottom}>
                        <View style={[styles.availBadge, isOutOfStock ? styles.availBadgeOff : styles.availBadgeOn]}>
                            <Text style={[styles.availText, isOutOfStock ? styles.availTextOff : styles.availTextOn]}>
                                {isOutOfStock ? 'Unavailable' : 'Available'}
                            </Text>
                        </View>
                        {product.sub_category ? (
                            <Text style={styles.menuSubCat}>{product.sub_category}</Text>
                        ) : null}
                    </View>
                </View>

                {/* Price */}
                <View style={styles.menuPriceCol}>
                    {product.discount_price ? (
                        <>
                            <Text style={styles.menuDiscountPrice}>{currency} {product.discount_price.toLocaleString()}</Text>
                            <Text style={styles.menuOriginalPrice}>{currency} {product.price.toLocaleString()}</Text>
                        </>
                    ) : (
                        <Text style={styles.menuPrice}>{currency} {product.price.toLocaleString()}</Text>
                    )}
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
                                    placeholder={
                                        isCreator ? "e.g. Instagram Reel Package" :
                                        isRestaurant ? "e.g. Caesar Salad" :
                                        isRental ? "e.g. 2BR Apartment Downtown" :
                                        isHealthcare ? "e.g. General Consultation" :
                                        isFitness ? "e.g. Yoga Class" :
                                        isServices ? "e.g. Computer Repair" :
                                        isSalon ? "e.g. Haircut & Style" :
                                        "e.g. Chocolate Cake"
                                    }
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
                                    placeholder={
                                        isCreator ? "e.g. Instagram Reel, Sponsored Post" :
                                        isRestaurant ? "e.g. Main Course, Appetizers" :
                                        isRental ? "e.g. Apartment, Car, Equipment" :
                                        isHealthcare ? "e.g. Consultation, Check-up" :
                                        isFitness ? "e.g. Yoga, Cardio, Strength" :
                                        isServices ? "e.g. Repair, Installation, Maintenance" :
                                        isSalon ? "e.g. Hair, Nails, Facial" :
                                        "e.g. Cakes, Electronics, Clothing"
                                    }
                                    placeholderTextColor="#555"
                                />
                                {/* Category suggestions for all business types */}
                                <View style={styles.categorySuggestions}>
                                    <Text style={styles.suggestionsLabel}>Popular categories:</Text>
                                    <View style={styles.suggestionChips}>
                                        {getAppropriateCategories().slice(0, 6).map(cat => (
                                            <TouchableOpacity
                                                key={cat}
                                                style={styles.suggestionChip}
                                                onPress={() => setEditCategory(cat)}
                                            >
                                                <Text style={styles.suggestionChipText}>{cat}</Text>
                                            </TouchableOpacity>
                                        ))}
                                    </View>
                                </View>
                            </View>

                            {(isRestaurant || isBakery) && (
                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Sub-category <Text style={{ color: '#555', fontWeight: '400' }}>(Optional)</Text></Text>
                                <TextInput
                                    style={styles.formInput}
                                    value={editSubCategory}
                                    onChangeText={setEditSubCategory}
                                    placeholder={isBakery ? "e.g. Birthday Cakes, Wedding Cakes, Sourdough" : "e.g. Pizza, Burgers, Rice Dishes, Cocktails"}
                                    placeholderTextColor="#555"
                                />
                                <Text style={styles.stockHint}>Groups items under a category — e.g. {isBakery ? 'Cakes → Birthday Cakes' : 'Main Course → Pizza'}</Text>
                            </View>
                            )}

                            {(isGrocery || isWholesale) && (
                            <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Unit <Text style={{ color: '#555', fontWeight: '400' }}>(how it's sold)</Text></Text>
                                <TextInput
                                    style={styles.formInput}
                                    value={editUnit}
                                    onChangeText={setEditUnit}
                                    placeholder={isWholesale ? "e.g. per carton, per dozen, per pallet" : "e.g. per kg, per piece, per packet"}
                                    placeholderTextColor="#555"
                                />
                                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                                    {(isWholesale ? WHOLESALE_UNITS : GROCERY_UNITS).slice(0, 6).map(u => (
                                        <TouchableOpacity
                                            key={u}
                                            onPress={() => setEditUnit(u)}
                                            style={[styles.suggestionChip, editUnit === u && { backgroundColor: '#0d3321', borderColor: '#25D366' }]}
                                        >
                                            <Text style={[styles.suggestionChipText, editUnit === u && { color: '#25D366' }]}>{u}</Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                                <Text style={styles.stockHint}>Helps customers know exactly what they're ordering</Text>
                            </View>
                            )}

                            {isWholesale && (
                            <>
                              <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Minimum Order Qty <Text style={{ color: '#555', fontWeight: '400' }}>(Optional)</Text></Text>
                                <TextInput
                                    style={styles.formInput}
                                    value={editMoq}
                                    onChangeText={setEditMoq}
                                    placeholder="e.g. 5 (minimum 5 cartons)"
                                    placeholderTextColor="#555"
                                    keyboardType="numeric"
                                />
                                <Text style={styles.stockHint}>Customer cannot order less than this quantity</Text>
                              </View>

                              <View style={styles.formGroup}>
                                <Text style={styles.formLabel}>Bulk Pricing Tiers <Text style={{ color: '#555', fontWeight: '400' }}>(Optional)</Text></Text>
                                <Text style={styles.stockHint}>Set lower prices for higher quantities — e.g. 1–10 cartons: KES 500, 11+: KES 450</Text>
                                {editPricingTiers.map((tier, idx) => (
                                    <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', marginTop: 6, gap: 8 }}>
                                        <Text style={{ color: '#ccc', fontSize: 13, flex: 1 }}>
                                            {tier.min_qty}+ {editUnit ? editUnit.replace('per ', '') : 'units'} → {currency} {tier.price.toLocaleString()}
                                        </Text>
                                        <TouchableOpacity onPress={() => setEditPricingTiers(editPricingTiers.filter((_, i) => i !== idx))}>
                                            <Ionicons name="close-circle" size={20} color="#FF4444" />
                                        </TouchableOpacity>
                                    </View>
                                ))}
                                <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                                    <TextInput
                                        style={[styles.formInput, { flex: 1 }]}
                                        value={newTierMinQty}
                                        onChangeText={setNewTierMinQty}
                                        placeholder="Min qty"
                                        placeholderTextColor="#555"
                                        keyboardType="numeric"
                                    />
                                    <TextInput
                                        style={[styles.formInput, { flex: 1 }]}
                                        value={newTierPrice}
                                        onChangeText={setNewTierPrice}
                                        placeholder={`Price (${currency})`}
                                        placeholderTextColor="#555"
                                        keyboardType="numeric"
                                    />
                                    <TouchableOpacity
                                        style={{ backgroundColor: '#25D366', borderRadius: 8, paddingHorizontal: 12, justifyContent: 'center' }}
                                        onPress={() => {
                                            const minQty = parseInt(newTierMinQty);
                                            const price = parseFloat(newTierPrice);
                                            if (!minQty || !price) return;
                                            setEditPricingTiers(prev => [...prev, { min_qty: minQty, price }].sort((a, b) => a.min_qty - b.min_qty));
                                            setNewTierMinQty('');
                                            setNewTierPrice('');
                                        }}
                                    >
                                        <Text style={{ color: '#000', fontWeight: '700' }}>+ Add</Text>
                                    </TouchableOpacity>
                                </View>
                              </View>
                            </>
                            )}

                            <View style={styles.formGroup}>
                                <View style={styles.formLabelRow}>
                                    <Text style={styles.formLabel}>Description</Text>
                                    <TouchableOpacity 
                                        style={styles.aiGenerateBtn}
                                        onPress={handleAIGenerateDescription}
                                        disabled={isGeneratingDescription}
                                    >
                                        <Ionicons 
                                            name={isGeneratingDescription ? "sparkles-outline" : "sparkles"} 
                                            size={16} 
                                            color={isGeneratingDescription ? "#8899AA" : "#25D366"} 
                                        />
                                        <Text style={styles.aiGenerateBtnText}>
                                            {isGeneratingDescription ? "Generating..." : "AI Generate"}
                                        </Text>
                                    </TouchableOpacity>
                                </View>
                                <TextInput
                                    ref={descriptionInputRef}
                                    style={[
                                        styles.formInput, 
                                        { 
                                            minHeight: 80,
                                            maxHeight: 200,
                                            textAlignVertical: 'top',
                                            fontSize: 15,
                                            lineHeight: 22,
                                        }
                                    ]}
                                    value={editDescription}
                                    onChangeText={setEditDescription}
                                    placeholder={
                                        isCreator ? "Describe what brands get with this content package..." :
                                        isRestaurant ? "Describe ingredients, preparation, allergens..." :
                                        isRental ? "Describe amenities, location, terms..." :
                                        isHealthcare ? "Describe procedure, duration, what to expect..." :
                                        isFitness ? "Describe class format, intensity, equipment needed..." :
                                        isServices ? "Describe service scope, timeline, requirements..." :
                                        isSalon ? "Describe treatment, duration, aftercare..." :
                                        "Describe your product..."
                                    }
                                    placeholderTextColor="#555"
                                    multiline
                                    scrollEnabled={true}
                                />
                                {editDescription && (
                                    <TouchableOpacity 
                                        style={styles.aiImproveBtn}
                                        onPress={handleAIImproveDescription}
                                        disabled={isGeneratingDescription}
                                    >
                                        <Ionicons name="refresh-outline" size={14} color="#25D366" />
                                        <Text style={styles.aiImproveBtnText}>Improve with AI</Text>
                                    </TouchableOpacity>
                                )}
                            </View>

                            {/* ── Variants Section ── */}
                            <View style={styles.formGroup}>
                                <View style={styles.formLabelRow}>
                                    <Text style={styles.formLabel}>Sizes / Versions (Optional)</Text>
                                    <Text style={styles.stockHint}>Enter the full price a customer pays for each option — the price shown to customer when they choose that size or version</Text>
                                </View>

                                {editVariants.map((v, idx) => (
                                    <View key={idx} style={styles.variantRow}>
                                        <Text style={styles.variantName}>{v.name}</Text>
                                        <Text style={styles.variantPrice}>{currency} {v.price.toLocaleString()}</Text>
                                        <TouchableOpacity onPress={() => setEditVariants(editVariants.filter((_, i) => i !== idx))}>
                                            <Ionicons name="close-circle" size={20} color="#e05252" />
                                        </TouchableOpacity>
                                    </View>
                                ))}

                                <View style={styles.variantAddRow}>
                                    <TextInput
                                        style={[styles.formInput, { flex: 2, marginRight: 6 }]}
                                        value={newVariantName}
                                        onChangeText={setNewVariantName}
                                        placeholder="e.g. Small, Regular, Family, 500ml"
                                        placeholderTextColor="#555"
                                    />
                                    <TextInput
                                        style={[styles.formInput, { flex: 1, marginRight: 6 }]}
                                        value={newVariantPrice}
                                        onChangeText={setNewVariantPrice}
                                        placeholder="Full price (e.g. 750)"
                                        placeholderTextColor="#555"
                                        keyboardType="numeric"
                                    />
                                    <TouchableOpacity
                                        style={styles.variantAddBtn}
                                        onPress={() => {
                                            if (!newVariantName.trim()) return;
                                            const price = parseFloat(newVariantPrice) || parseFloat(editPrice) || 0;
                                            setEditVariants([...editVariants, { name: newVariantName.trim(), price }]);
                                            setNewVariantName('');
                                            setNewVariantPrice('');
                                        }}
                                    >
                                        <Ionicons name="add" size={20} color="#fff" />
                                    </TouchableOpacity>
                                </View>
                            </View>

                            {/* ── Modifier Groups Section ── */}
                            <View style={styles.formGroup}>
                                <View style={styles.formLabelRow}>
                                    <Text style={styles.formLabel}>Modifier Groups (Optional)</Text>
                                    <Text style={styles.stockHint}>e.g. Spice Level · Extras</Text>
                                </View>

                                {editModifierGroups.map((group, gi) => (
                                    <View key={gi} style={styles.modifierGroupCard}>
                                        <View style={styles.modifierGroupHeader}>
                                            <Text style={styles.modifierGroupName}>{group.name}</Text>
                                            <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                                                <Text style={styles.modifierGroupBadge}>
                                                    {group.required ? 'Required' : 'Optional'}
                                                    {group.multi_select ? ' · Multi' : ''}
                                                </Text>
                                                <TouchableOpacity onPress={() => setEditModifierGroups(editModifierGroups.filter((_, i) => i !== gi))}>
                                                    <Ionicons name="close-circle" size={18} color="#e05252" />
                                                </TouchableOpacity>
                                            </View>
                                        </View>
                                        {group.options.map((opt, oi) => (
                                            <View key={oi} style={styles.modifierOptionRow}>
                                                <Text style={styles.modifierOptionName}>{opt.name}</Text>
                                                {opt.price_delta > 0 && (
                                                    <Text style={styles.modifierOptionPrice}>+{currency} {opt.price_delta.toLocaleString()}</Text>
                                                )}
                                                <TouchableOpacity onPress={() => {
                                                    const updated = [...editModifierGroups];
                                                    updated[gi] = { ...updated[gi], options: updated[gi].options.filter((_, i) => i !== oi) };
                                                    setEditModifierGroups(updated);
                                                }}>
                                                    <Ionicons name="remove-circle-outline" size={16} color="#888" />
                                                </TouchableOpacity>
                                            </View>
                                        ))}
                                    </View>
                                ))}

                                {!showAddGroup ? (
                                    <TouchableOpacity style={styles.addGroupBtn} onPress={() => setShowAddGroup(true)}>
                                        <Ionicons name="add-circle-outline" size={16} color="#25D366" />
                                        <Text style={styles.addGroupBtnText}>Add modifier group</Text>
                                    </TouchableOpacity>
                                ) : (
                                    <View style={styles.modifierGroupCard}>
                                        <TextInput
                                            style={[styles.formInput, { marginBottom: 8 }]}
                                            value={newGroupName}
                                            onChangeText={setNewGroupName}
                                            placeholder="Group name (e.g. Spice Level)"
                                            placeholderTextColor="#555"
                                        />
                                        <View style={{ flexDirection: 'row', gap: 16, marginBottom: 10 }}>
                                            <TouchableOpacity
                                                style={[styles.modifierToggleBtn, newGroupRequired && styles.modifierToggleBtnActive]}
                                                onPress={() => setNewGroupRequired(!newGroupRequired)}
                                            >
                                                <Text style={[styles.modifierToggleText, newGroupRequired && styles.modifierToggleTextActive]}>Required</Text>
                                            </TouchableOpacity>
                                            <TouchableOpacity
                                                style={[styles.modifierToggleBtn, newGroupMulti && styles.modifierToggleBtnActive]}
                                                onPress={() => setNewGroupMulti(!newGroupMulti)}
                                            >
                                                <Text style={[styles.modifierToggleText, newGroupMulti && styles.modifierToggleTextActive]}>Multi-select</Text>
                                            </TouchableOpacity>
                                        </View>

                                        {newGroupOptions.map((opt, oi) => (
                                            <View key={oi} style={styles.modifierOptionRow}>
                                                <Text style={styles.modifierOptionName}>{opt.name}</Text>
                                                {opt.price_delta > 0 && <Text style={styles.modifierOptionPrice}>+{currency} {opt.price_delta.toLocaleString()}</Text>}
                                                <TouchableOpacity onPress={() => setNewGroupOptions(newGroupOptions.filter((_, i) => i !== oi))}>
                                                    <Ionicons name="remove-circle-outline" size={16} color="#888" />
                                                </TouchableOpacity>
                                            </View>
                                        ))}

                                        <View style={styles.variantAddRow}>
                                            <TextInput
                                                style={[styles.formInput, { flex: 2, marginRight: 6 }]}
                                                value={newOptionName}
                                                onChangeText={setNewOptionName}
                                                placeholder="Option (e.g. Mild)"
                                                placeholderTextColor="#555"
                                            />
                                            <TextInput
                                                style={[styles.formInput, { flex: 1, marginRight: 6 }]}
                                                value={newOptionPrice}
                                                onChangeText={setNewOptionPrice}
                                                placeholder="+Price"
                                                placeholderTextColor="#555"
                                                keyboardType="numeric"
                                            />
                                            <TouchableOpacity
                                                style={styles.variantAddBtn}
                                                onPress={() => {
                                                    if (!newOptionName.trim()) return;
                                                    setNewGroupOptions([...newGroupOptions, { name: newOptionName.trim(), price_delta: parseFloat(newOptionPrice) || 0 }]);
                                                    setNewOptionName('');
                                                    setNewOptionPrice('');
                                                }}
                                            >
                                                <Ionicons name="add" size={20} color="#fff" />
                                            </TouchableOpacity>
                                        </View>

                                        <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                                            <TouchableOpacity
                                                style={[styles.variantAddBtn, { flex: 1, height: 36 }]}
                                                onPress={() => {
                                                    if (!newGroupName.trim() || newGroupOptions.length === 0) return;
                                                    setEditModifierGroups([...editModifierGroups, {
                                                        name: newGroupName.trim(),
                                                        required: newGroupRequired,
                                                        multi_select: newGroupMulti,
                                                        options: newGroupOptions,
                                                    }]);
                                                    setNewGroupName('');
                                                    setNewGroupRequired(false);
                                                    setNewGroupMulti(false);
                                                    setNewGroupOptions([]);
                                                    setShowAddGroup(false);
                                                }}
                                            >
                                                <Text style={{ color: '#fff', fontWeight: '600', fontSize: 13 }}>Save Group</Text>
                                            </TouchableOpacity>
                                            <TouchableOpacity
                                                style={[styles.variantAddBtn, { flex: 1, height: 36, backgroundColor: '#333' }]}
                                                onPress={() => { setShowAddGroup(false); setNewGroupName(''); setNewGroupOptions([]); }}
                                            >
                                                <Text style={{ color: '#aaa', fontWeight: '600', fontSize: 13 }}>Cancel</Text>
                                            </TouchableOpacity>
                                        </View>
                                    </View>
                                )}
                            </View>

                            {showStock && (
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

{showStock && (
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
                        )}

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
                                    <Text style={styles.deleteBtnText}>Delete {itemLabel}</Text>
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
                                    {showStock && (
                                        <View style={[styles.stockBadge, selectedProduct.in_stock === false ? styles.stockBadgeRed : styles.stockBadgeGreen]}>
                                            <Text style={styles.stockBadgeText}>
                                                {selectedProduct.in_stock === false ? 'Out of Stock' : 'In Stock'}
                                            </Text>
                                        </View>
                                    )}
                                </View>

                                <Text style={styles.detailPrice}>{currency} {selectedProduct.price.toLocaleString()}</Text>

                                <View style={styles.detailCategoryRow}>
                                    <Ionicons name="pricetag-outline" size={14} color="#8899AA" />
                                    <Text style={styles.detailCategory}>{selectedProduct.category || 'Other'}</Text>

                                    {showStock && selectedProduct.stock_quantity !== undefined && selectedProduct.stock_quantity !== null && (
                                        <View style={styles.detailStockInfo}>
                                            <Ionicons name="cube-outline" size={14} color="#8899AA" style={{ marginLeft: 12 }} />
                                            <Text style={styles.detailCategory}>Stock: {selectedProduct.stock_quantity}</Text>
                                        </View>
                                    )}
                                </View>

                                {selectedProduct.description ? (
                                    <View style={styles.descriptionBox}>
                                        <Text style={styles.descriptionLabel}>Description</Text>
                                        <Text style={styles.descriptionText}>{selectedProduct.description}</Text>
                                    </View>
                                ) : null}

                                {/* Action Buttons */}
                                <View style={styles.actionButtons}>
                                    {showStock && (
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
                                    )}

                                    <TouchableOpacity
                                        style={styles.actionBtn}
                                        onPress={() => startEdit(selectedProduct)}
                                    >
                                        <Ionicons name="create-outline" size={22} color="#4A90D9" />
                                        <Text style={styles.actionBtnText}>Edit {itemLabel}</Text>
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
                    <Text style={styles.headerTitle}>{catalogLabel} Catalog</Text>
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
                            placeholder={
                                isCreator ? "Search content packages..." :
                                isRestaurant ? "Search menu items..." :
                                isRental ? "Search listings..." :
                                isHealthcare ? "Search services..." :
                                isFitness ? "Search classes..." :
                                isServices ? "Search services..." :
                                isSalon ? "Search services..." :
                                "Search products..."
                            }
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
                        <Text style={styles.statLabel}>{isCreator ? 'Packages' : catalogLabel.slice(0, -1) + 's'}</Text>
                    </View>
                    {showStock && (
                        <>
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
                        </>
                    )}
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
                        {isRestaurant ? (
                            <View style={styles.menuList}>
                                {filteredProducts.map((p, i) => renderMenuRow(p, i))}
                            </View>
                        ) : (
                            <View style={styles.productGrid}>
                                {filteredProducts.map(renderProductCard)}
                            </View>
                        )}
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
                        <Text style={styles.emptyText}>Your {catalogLabel.toLowerCase()} is empty</Text>
                        <Text style={styles.emptySubtext}>
                            {isCreator 
                                ? 'Add content packages to share with brands and let AI recommend them automatically' 
                                : isRestaurant
                                ? 'Add menu items to share with customers and let AI recommend them automatically'
                                : isRental
                                ? 'Add listings to share with guests and let AI recommend them automatically'
                                : isHealthcare || isFitness || isServices || isSalon
                                ? 'Add services to share with clients and let AI recommend them automatically'
                                : 'Add products to share with customers and let AI recommend them automatically'
                            }
                        </Text>
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

    // ── Restaurant menu list ──
    menuList: {
        gap: 1,
    },
    menuRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#1A2535',
        borderRadius: 12,
        marginBottom: 8,
        padding: 10,
        gap: 10,
    },
    menuNum: {
        fontSize: 16,
        width: 28,
        textAlign: 'center',
    },
    menuThumb: {
        width: 70,
        height: 70,
        borderRadius: 8,
        backgroundColor: '#243447',
    },
    menuInfo: {
        flex: 1,
        gap: 3,
    },
    menuName: {
        fontSize: 14,
        fontWeight: '700',
        color: '#FFFFFF',
    },
    menuDesc: {
        fontSize: 12,
        color: '#8899AA',
        lineHeight: 16,
    },
    menuBottom: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        marginTop: 2,
    },
    availBadge: {
        borderRadius: 4,
        paddingHorizontal: 6,
        paddingVertical: 2,
    },
    availBadgeOn: { backgroundColor: '#0d3321' },
    availBadgeOff: { backgroundColor: '#3a1a1a' },
    availText: { fontSize: 11, fontWeight: '600' },
    availTextOn: { color: '#25D366' },
    availTextOff: { color: '#e05252' },
    menuSubCat: {
        fontSize: 11,
        color: '#556677',
    },
    menuPriceCol: {
        alignItems: 'flex-end',
        minWidth: 60,
    },
    menuPrice: {
        fontSize: 14,
        fontWeight: '700',
        color: '#25D366',
    },
    menuDiscountPrice: {
        fontSize: 14,
        fontWeight: '700',
        color: '#25D366',
    },
    menuOriginalPrice: {
        fontSize: 11,
        color: '#556677',
        textDecorationLine: 'line-through',
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
    // Category Suggestions for Creators
    categorySuggestions: {
        marginTop: 8,
    },
    suggestionsLabel: {
        fontSize: 12,
        color: '#8899AA',
        marginBottom: 8,
        fontWeight: '500',
    },
    suggestionChips: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
    },
    suggestionChip: {
        backgroundColor: '#1A2942',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: '#334455',
    },
    suggestionChipText: {
        fontSize: 12,
        color: '#CCD6E0',
        fontWeight: '500',
    },
    // AI Description Generator Styles
    formLabelRow: {
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
    variantRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#1A2535',
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 8,
        marginBottom: 6,
        gap: 8,
    },
    variantName: {
        flex: 1,
        color: '#fff',
        fontSize: 14,
        fontWeight: '500',
    },
    variantPrice: {
        color: '#25D366',
        fontSize: 13,
        fontWeight: '600',
        marginRight: 4,
    },
    variantAddRow: {
        flexDirection: 'row',
        alignItems: 'center',
        marginTop: 4,
    },
    variantAddBtn: {
        width: 40,
        height: 40,
        borderRadius: 8,
        backgroundColor: '#25D366',
        alignItems: 'center',
        justifyContent: 'center',
    },
    modifierGroupCard: {
        backgroundColor: '#111D2B',
        borderRadius: 10,
        borderWidth: 1,
        borderColor: '#1E3050',
        padding: 12,
        marginBottom: 10,
    },
    modifierGroupHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 8,
    },
    modifierGroupName: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '700',
        flex: 1,
    },
    modifierGroupBadge: {
        color: '#25D366',
        fontSize: 11,
        fontWeight: '600',
        backgroundColor: '#1A3A2A',
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 10,
    },
    modifierOptionRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 5,
        borderTopWidth: 1,
        borderTopColor: '#1E3050',
        gap: 8,
    },
    modifierOptionName: {
        flex: 1,
        color: '#ccc',
        fontSize: 13,
    },
    modifierOptionPrice: {
        color: '#25D366',
        fontSize: 12,
        fontWeight: '600',
    },
    addGroupBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 10,
        paddingHorizontal: 4,
    },
    addGroupBtnText: {
        color: '#25D366',
        fontSize: 13,
        fontWeight: '600',
    },
    modifierToggleBtn: {
        paddingHorizontal: 14,
        paddingVertical: 6,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: '#333',
        backgroundColor: '#111',
    },
    modifierToggleBtnActive: {
        borderColor: '#25D366',
        backgroundColor: '#1A3A2A',
    },
    modifierToggleText: {
        color: '#888',
        fontSize: 12,
        fontWeight: '600',
    },
    modifierToggleTextActive: {
        color: '#25D366',
    },
});
