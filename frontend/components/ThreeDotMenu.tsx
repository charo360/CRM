import React, { useState, useRef } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    StyleSheet,
    Animated,
    TouchableWithoutFeedback,
    Switch,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface MenuItem {
    icon: string;
    label: string;
    onPress: () => void;
    color?: string;
    type?: 'button' | 'toggle';
    value?: boolean;
}

interface ThreeDotMenuProps {
    items: MenuItem[];
    color?: string;
}

export default function ThreeDotMenu({ items, color = '#333' }: ThreeDotMenuProps) {
    const [visible, setVisible] = useState(false);
    const fadeAnim = useRef(new Animated.Value(0)).current;

    // ... (keep openMenu and closeMenu same)

    const openMenu = () => {
        setVisible(true);
        Animated.timing(fadeAnim, {
            toValue: 1,
            duration: 200,
            useNativeDriver: true,
        }).start();
    };

    const closeMenu = () => {
        Animated.timing(fadeAnim, {
            toValue: 0,
            duration: 150,
            useNativeDriver: true,
        }).start(() => setVisible(false));
    };

    const handleItemPress = (item: MenuItem) => {
        if (item.type === 'toggle') {
            item.onPress();
            // Don't close menu for toggles
            return;
        }
        closeMenu();
        setTimeout(item.onPress, 200);
    };

    return (
        <>
            <TouchableOpacity onPress={openMenu} style={styles.menuButton}>
                <Ionicons name="ellipsis-vertical" size={24} color={color} />
            </TouchableOpacity>

            <Modal
                visible={visible}
                transparent
                animationType="none"
                onRequestClose={closeMenu}
            >
                <TouchableWithoutFeedback onPress={closeMenu}>
                    <View style={styles.overlay}>
                        <TouchableWithoutFeedback>
                            <Animated.View
                                style={[
                                    styles.menuContainer,
                                    {
                                        opacity: fadeAnim,
                                        transform: [
                                            {
                                                scale: fadeAnim.interpolate({
                                                    inputRange: [0, 1],
                                                    outputRange: [0.8, 1],
                                                }),
                                            },
                                        ],
                                    },
                                ]}
                            >
                                {items.map((item, index) => (
                                    <TouchableOpacity
                                        key={index}
                                        style={[
                                            styles.menuItem,
                                            index === items.length - 1 && styles.lastMenuItem,
                                        ]}
                                        onPress={() => handleItemPress(item)}
                                        activeOpacity={item.type === 'toggle' ? 1 : 0.7}
                                    >
                                        <View style={styles.menuItemContent}>
                                            <Ionicons
                                                name={item.icon as any}
                                                size={20}
                                                color={item.color || '#333'}
                                                style={styles.menuIcon}
                                            />
                                            <Text
                                                style={[
                                                    styles.menuText,
                                                    item.color && { color: item.color },
                                                ]}
                                            >
                                                {item.label}
                                            </Text>
                                        </View>
                                        {item.type === 'toggle' && (
                                            <Switch
                                                value={item.value}
                                                onValueChange={item.onPress}
                                                trackColor={{ false: '#767577', true: '#25D366' }}
                                                thumbColor={item.value ? '#FFFFFF' : '#f4f3f4'}
                                                style={{ transform: [{ scaleX: 0.8 }, { scaleY: 0.8 }] }}
                                            />
                                        )}
                                    </TouchableOpacity>
                                ))}
                            </Animated.View>
                        </TouchableWithoutFeedback>
                    </View>
                </TouchableWithoutFeedback>
            </Modal>
        </>
    );
}

const styles = StyleSheet.create({
    // ... (keep existing styles)
    menuButton: {
        padding: 8,
    },
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.3)',
        justifyContent: 'flex-start',
        alignItems: 'flex-end',
        paddingTop: 60,
        paddingRight: 16,
    },
    menuContainer: {
        backgroundColor: '#FFFFFF',
        borderRadius: 12,
        minWidth: 260, // Increased width for toggles
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 8,
        elevation: 8,
    },
    menuItem: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between', // Changed for toggles
        paddingVertical: 12,
        paddingHorizontal: 16,
        borderBottomWidth: 1,
        borderBottomColor: '#F0F0F0',
    },
    menuItemContent: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    lastMenuItem: {
        borderBottomWidth: 0,
    },
    menuIcon: {
        marginRight: 12,
    },
    menuText: {
        fontSize: 16,
        color: '#333',
    },
});
