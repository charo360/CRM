import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { settingsAPI } from '../../context/api';
import { COUNTRIES } from '../../components/CountryPicker';

const BUSINESS_TYPES = [
  { id: 'fashion', label: 'Fashion', icon: 'shirt-outline' as const },
  { id: 'food', label: 'Food & Drinks', icon: 'restaurant-outline' as const },
  { id: 'beauty', label: 'Beauty & Salon', icon: 'cut-outline' as const },
  { id: 'electronics', label: 'Electronics', icon: 'phone-portrait-outline' as const },
  { id: 'grocery', label: 'Grocery', icon: 'basket-outline' as const },
  { id: 'services', label: 'Services', icon: 'construct-outline' as const },
  { id: 'health', label: 'Health', icon: 'medkit-outline' as const },
  { id: 'other', label: 'Other', icon: 'grid-outline' as const },
];

export default function RegisterScreen() {
  const { countryCode } = useLocalSearchParams<{ countryCode: string }>();
  const country = COUNTRIES.find(c => c.code === (countryCode || 'US'));
  const [businessName, setBusinessName] = useState('');
  const [ownerName, setOwnerName] = useState('');
  const [businessType, setBusinessType] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { register, user } = useAuth();

  const handleRegister = async () => {
    if (!businessName.trim()) {
      Alert.alert('Error', 'Please enter your business name');
      return;
    }
    if (!businessType) {
      Alert.alert('Error', 'Please select your business type');
      return;
    }

    setLoading(true);
    try {
      const result = await register(businessName, ownerName, businessType);
      if (result.success) {
        if (country) {
          try {
            await settingsAPI.updateSettings({
              country_code: country.code,
              currency: country.currency || 'USD',
            });
          } catch (e) {}
        }
        router.replace('/(tabs)/customers');
      } else {
        Alert.alert('Error', result.message || 'Registration failed');
      }
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <View style={styles.content}>
          <View style={styles.header}>
            <View style={styles.connectedBadge}>
              <Ionicons name="checkmark-circle" size={20} color="#25D366" />
              <Text style={styles.connectedText}>WhatsApp Connected</Text>
            </View>
            <Text style={styles.title}>Setup Your Business</Text>
            <Text style={styles.subtitle}>Tell us about your business to personalise your experience</Text>
          </View>

          <View style={styles.form}>
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Business Name *</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="storefront-outline" size={20} color="#666" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={businessName}
                  onChangeText={setBusinessName}
                  placeholder="e.g., Jane's Boutique"
                  placeholderTextColor="#666"
                  autoFocus
                />
              </View>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Your Name (Optional)</Text>
              <View style={styles.inputContainer}>
                <Ionicons name="person-outline" size={20} color="#666" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  value={ownerName}
                  onChangeText={setOwnerName}
                  placeholder="e.g., Jane Doe"
                  placeholderTextColor="#666"
                />
              </View>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Business Type *</Text>
              <View style={styles.typeGrid}>
                {BUSINESS_TYPES.map((type) => {
                  const selected = businessType === type.id;
                  return (
                    <TouchableOpacity
                      key={type.id}
                      style={[styles.typeCard, selected && styles.typeCardSelected]}
                      onPress={() => setBusinessType(type.id)}
                      activeOpacity={0.7}
                    >
                      <Ionicons
                        name={type.icon}
                        size={24}
                        color={selected ? '#25D366' : '#888'}
                      />
                      <Text style={[styles.typeLabel, selected && styles.typeLabelSelected]}>
                        {type.label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            {user?.phone_number ? (
              <View style={styles.phoneDisplay}>
                <Text style={styles.phoneLabel}>WhatsApp Number</Text>
                <Text style={styles.phoneValue}>{user.phone_number}</Text>
              </View>
            ) : null}

            <TouchableOpacity
              style={[styles.button, loading && styles.buttonDisabled]}
              onPress={handleRegister}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.buttonText}>Get Started</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  scrollContent: {
    flexGrow: 1,
  },
  content: {
    flex: 1,
    padding: 24,
    paddingTop: 64,
    paddingBottom: 40,
  },
  connectedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(37,211,102,0.1)',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 8,
    alignSelf: 'flex-start',
    marginBottom: 16,
  },
  connectedText: {
    color: '#25D366',
    fontSize: 13,
    fontWeight: '600',
    marginLeft: 6,
  },
  header: {
    marginBottom: 28,
  },
  title: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 14,
    color: '#888',
    lineHeight: 20,
  },
  form: {
    marginBottom: 24,
  },
  inputGroup: {
    marginBottom: 20,
  },
  label: {
    fontSize: 13,
    color: '#AAAAAA',
    marginBottom: 8,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    paddingHorizontal: 16,
  },
  inputIcon: {
    marginRight: 12,
  },
  input: {
    flex: 1,
    height: 52,
    fontSize: 16,
    color: '#FFFFFF',
  },
  typeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  typeCard: {
    width: '22%',
    aspectRatio: 1,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: 'transparent',
    paddingVertical: 8,
  },
  typeCardSelected: {
    borderColor: '#25D366',
    backgroundColor: 'rgba(37,211,102,0.08)',
  },
  typeLabel: {
    fontSize: 10,
    color: '#888',
    marginTop: 6,
    textAlign: 'center',
    fontWeight: '500',
  },
  typeLabelSelected: {
    color: '#25D366',
  },
  phoneDisplay: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 14,
    marginBottom: 20,
  },
  phoneLabel: {
    fontSize: 11,
    color: '#666',
    marginBottom: 4,
  },
  phoneValue: {
    fontSize: 15,
    color: '#25D366',
    fontWeight: '600',
  },
  button: {
    backgroundColor: '#25D366',
    borderRadius: 14,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '700',
  },
});
