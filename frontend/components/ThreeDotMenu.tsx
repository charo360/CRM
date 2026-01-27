import React, { useState, useRef } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    Modal,
    StyleSheet,
    Animated,
    TouchableWithoutFeedback,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface MenuItem {
    icon: string;
    label: string;
    onPress: () => void;
    color?: string;
}

interface ThreeDotMenuProps {
    items: MenuItem[];
}

export default function ThreeDotMenu({ items }: ThreeDotMenuProps) {
    const [visible, setVisible] = useState(false);
    const fadeAnim = useRef(new Animated.Value(0)).current;

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

    const handleItemPress = (onPress: () => void) => {
        closeMenu();
        // Small delay to let menu close animation finish
        setTimeout(onPress, 200);
    };

    return (
        <>
            <TouchableOpacity onPress={openMenu} style={styles.menuButton}>
                <Ionicons name="ellipsis-vertical" size={24} color="#333" />
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
                                        onPress={() => handleItemPress(item.onPress)}
                                    >
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
        minWidth: 220,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 8,
        elevation: 8,
    },
    menuItem: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 14,
        paddingHorizontal: 16,
        borderBottomWidth: 1,
        borderBottomColor: '#F0F0F0',
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
