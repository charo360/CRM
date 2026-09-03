import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BUSINESS_TYPE_OPTIONS, BusinessType } from '../context/BusinessContext';

/**
 * The business type decides what a merchant's whole app looks like — Products
 * or Services, whether Bookings appears, and whether their public shop takes
 * orders or bookings. Shown at sign-up and changeable in settings.
 */
export default function BusinessTypePicker({
    value,
    onChange,
}: {
    value: BusinessType | string;
    onChange: (type: BusinessType) => void;
}) {
    return (
        <View style={styles.grid}>
            {BUSINESS_TYPE_OPTIONS.map((option) => {
                const selected = value === option.id;
                return (
                    <TouchableOpacity
                        key={option.id}
                        style={[styles.tile, selected && styles.tileSelected]}
                        onPress={() => onChange(option.id)}
                        activeOpacity={0.8}
                    >
                        <Ionicons
                            name={option.icon as any}
                            size={22}
                            color={selected ? '#25D366' : '#8899AA'}
                        />
                        <Text style={[styles.label, selected && styles.labelSelected]} numberOfLines={2}>
                            {option.label}
                        </Text>
                    </TouchableOpacity>
                );
            })}
        </View>
    );
}

const styles = StyleSheet.create({
    grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
    tile: {
        width: '30%',
        minHeight: 82,
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        paddingVertical: 12,
        paddingHorizontal: 6,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: 'transparent',
        backgroundColor: 'rgba(255,255,255,0.05)',
    },
    tileSelected: {
        borderColor: '#25D366',
        backgroundColor: 'rgba(37,211,102,0.08)',
    },
    label: { color: '#8899AA', fontSize: 11, textAlign: 'center' },
    labelSelected: { color: '#FFFFFF', fontWeight: '600' },
});
