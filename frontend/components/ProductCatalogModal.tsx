import React, { useState, useEffect } from 'react';
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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { productsAPI } from '../context/api';

interface Product {
    id: string;
    name: string;
    price: number;
    image_url: string;
    category: string;
    in_stock: boolean;
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

    useEffect(() => {
        if (visible) {
            fetchProducts();
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

    const handleUploadProducts = async () => {
        try {
            const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
            if (status !== 'granted') {
                Alert.alert('Permission needed', 'Please allow access to your photos');
                return;
            }

            const result = await ImagePicker.launchImageLibraryAsync({
                mediaTypes: ImagePicker.MediaTypeOptions.Images,
                allowsMultipleSelection: true,
                quality: 0.8,
            });

            if (!result.canceled && result.assets.length > 0) {
                setUploading(true);

                try {
                    const response = await productsAPI.uploadProducts(result.assets);

                    Alert.alert(
                        'Success!',
                        `Uploaded ${response.products_created} products. AI has suggested names and prices.`,
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

    const handleDeleteProduct = (productId: string) => {
        Alert.alert(
            'Delete Product',
            'Are you sure you want to delete this product?',
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Delete',
                    style: 'destructive',
                    onPress: async () => {
                        try {
                            await productsAPI.deleteProduct(productId);
                            fetchProducts();
                        } catch (error) {
                            Alert.alert('Error', 'Failed to delete product');
                        }
                    },
                },
            ]
        );
    };

    return (
        <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
            <SafeAreaView style={styles.container}>
                {/* Header */}
                <View style={styles.header}>
                    <TouchableOpacity onPress={onClose} style={styles.backButton}>
                        <Ionicons name="arrow-back" size={24} color="#333" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Product Catalog</Text>
                    <View style={styles.placeholder} />
                </View>

                {/* Content */}
                <ScrollView style={styles.content}>
                    {/* Upload Button */}
                    <TouchableOpacity
                        style={styles.uploadButton}
                        onPress={handleUploadProducts}
                        disabled={uploading}
                    >
                        <Ionicons name="cloud-upload-outline" size={24} color="#FFFFFF" />
                        <Text style={styles.uploadButtonText}>
                            {uploading ? 'Uploading...' : 'Upload Products'}
                        </Text>
                    </TouchableOpacity>

                    {loading ? (
                        <ActivityIndicator size="large" color="#25D366" style={styles.loader} />
                    ) : products.length > 0 ? (
                        <>
                            <Text style={styles.productCount}>
                                {products.length} product{products.length !== 1 ? 's' : ''}
                            </Text>
                            <View style={styles.productGrid}>
                                {products.map((product) => (
                                    <View key={product.id} style={styles.productCard}>
                                        <Image
                                            source={{
                                                uri: `${process.env.EXPO_PUBLIC_BACKEND_URL}${product.image_url}`,
                                            }}
                                            style={styles.productImage}
                                            resizeMode="cover"
                                        />
                                        <View style={styles.productInfo}>
                                            <Text style={styles.productName} numberOfLines={1}>
                                                {product.name}
                                            </Text>
                                            <Text style={styles.productPrice}>
                                                KES {product.price.toLocaleString()}
                                            </Text>
                                        </View>
                                        <TouchableOpacity
                                            style={styles.deleteButton}
                                            onPress={() => handleDeleteProduct(product.id)}
                                        >
                                            <Ionicons name="trash-outline" size={16} color="#FF4444" />
                                        </TouchableOpacity>
                                    </View>
                                ))}
                            </View>
                        </>
                    ) : (
                        <View style={styles.emptyState}>
                            <Ionicons name="cube-outline" size={64} color="#CCC" />
                            <Text style={styles.emptyText}>No products yet</Text>
                            <Text style={styles.emptySubtext}>
                                Upload some products to get started!
                            </Text>
                        </View>
                    )}
                </ScrollView>
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
    placeholder: {
        width: 32,
    },
    content: {
        flex: 1,
        padding: 16,
    },
    uploadButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#25D366',
        paddingVertical: 14,
        paddingHorizontal: 20,
        borderRadius: 12,
        gap: 8,
        marginBottom: 20,
    },
    uploadButtonText: {
        color: '#FFFFFF',
        fontSize: 16,
        fontWeight: '600',
    },
    loader: {
        marginTop: 40,
    },
    productCount: {
        fontSize: 14,
        color: '#666',
        marginBottom: 12,
    },
    productGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 12,
    },
    productCard: {
        width: '31%',
        backgroundColor: '#FFFFFF',
        borderRadius: 12,
        overflow: 'hidden',
        borderWidth: 1,
        borderColor: '#E0E0E0',
    },
    productImage: {
        width: '100%',
        height: 100,
        backgroundColor: '#F5F5F5',
    },
    productInfo: {
        padding: 8,
    },
    productName: {
        fontSize: 12,
        fontWeight: '600',
        color: '#333',
        marginBottom: 4,
    },
    productPrice: {
        fontSize: 11,
        color: '#25D366',
        fontWeight: '600',
    },
    deleteButton: {
        position: 'absolute',
        top: 4,
        right: 4,
        backgroundColor: '#FFFFFF',
        borderRadius: 12,
        padding: 4,
    },
    emptyState: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 60,
    },
    emptyText: {
        fontSize: 18,
        fontWeight: '600',
        color: '#999',
        marginTop: 16,
    },
    emptySubtext: {
        fontSize: 14,
        color: '#BBB',
        marginTop: 8,
    },
});
