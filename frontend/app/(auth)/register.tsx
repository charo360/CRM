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
import { useBusiness } from '../../context/BusinessContext';
import { COUNTRIES } from '../../components/CountryPicker';

const BUSINESS_TYPES = [
  { id: 'retail',     icon: '🛍️',  label: 'Retail',           desc: 'Physical or online shop' },
  { id: 'salon',      icon: '✂️',   label: 'Salon & Beauty',   desc: 'Hair, nails & beauty services' },
  { id: 'services',   icon: '🔧',   label: 'Services / Tech',  desc: 'IT, freelance, trades & repairs' },
  { id: 'fitness',    icon: '🏋️',  label: 'Fitness',          desc: 'Gym, classes & training' },
  { id: 'restaurant', icon: '🍽️',  label: 'Restaurant',       desc: 'Food & dining' },
  { id: 'healthcare', icon: '🏥',   label: 'Healthcare',       desc: 'Clinic, dental & medical' },
  { id: 'creator',    icon: '🎨',   label: 'Creator',          desc: 'Digital products & content' },
  { id: 'rental',     icon: '🏡',   label: 'Rental / Airbnb',  desc: 'Properties, cars & equipment' },
  { id: 'general',    icon: '💬',   label: 'General / Other',  desc: 'Fintech, NGO, info & assistant' },
];

export default function RegisterScreen() {
  const { countryCode } = useLocalSearchParams<{ countryCode: string }>();
  const country = COUNTRIES.find(c => c.code === (countryCode || 'US'));
  const [step, setStep] = useState<'info' | 'type'>('info');
  const [businessName, setBusinessName] = useState('');
  const [ownerName, setOwnerName] = useState('');
  const [businessType, setBusinessType] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { register, user } = useAuth();
  const { refresh: refreshBusinessContext } = useBusiness();

  const handleNextStep = () => {
    if (!businessName.trim()) {
      Alert.alert('Error', 'Please enter your business name');
      return;
    }
    setStep('type');
  };

  const handleRegister = async (selectedType: string) => {
    setBusinessType(selectedType);
    setLoading(true);
    try {
      const result = await register(businessName, ownerName, selectedType);
      if (result.success) {
        const settingsPayload: any = { business_type: selectedType };
        if (country) {
          settingsPayload.country_code = country.code;
          settingsPayload.currency = country.currency || 'USD';
        }
        try {
          await settingsAPI.updateSettings(settingsPayload);
          await refreshBusinessContext();
        } catch (e) {}
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

  if (step === 'type') {
    return (
      <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <View style={styles.content}>
            <TouchableOpacity style={styles.backBtn} onPress={() => setStep('info')}>
              <Ionicons name="arrow-back" size={22} color="#94A3B8" />
            </TouchableOpacity>

            <View style={styles.header}>
              <Text style={styles.stepLabel}>Step 2 of 2</Text>
              <Text style={styles.title}>What kind of business?</Text>
              <Text style={styles.subtitle}>
                This personalises your dashboard, products, and booking features.
              </Text>
            </View>

            <View style={styles.typeGrid}>
              {BUSINESS_TYPES.map(bt => (
                <TouchableOpacity
                  key={bt.id}
                  style={[styles.typeCard, businessType === bt.id && styles.typeCardActive]}
                  onPress={() => !loading && handleRegister(bt.id)}
                  disabled={loading}
                  activeOpacity={0.8}
                >
                  {loading && businessType === bt.id ? (
                    <ActivityIndicator color="#25D366" style={{ marginBottom: 8 }} />
                  ) : (
                    <Text style={styles.typeIcon}>{bt.icon}</Text>
                  )}
                  <Text style={[styles.typeLabel, businessType === bt.id && styles.typeLabelActive]}>
                    {bt.label}
                  </Text>
                  <Text style={styles.typeDesc}>{bt.desc}</Text>
                  {businessType === bt.id && !loading && (
                    <View style={styles.typeCheck}>
                      <Ionicons name="checkmark-circle" size={20} color="#25D366" />
                    </View>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <View style={styles.content}>
          <View style={styles.header}>
            <View style={styles.connectedBadge}>
              <Ionicons name="checkmark-circle" size={20} color="#25D366" />
              <Text style={styles.connectedText}>WhatsApp Connected</Text>
            </View>
            <Text style={styles.stepLabel}>Step 1 of 2</Text>
            <Text style={styles.title}>Setup Business</Text>
            <Text style={styles.subtitle}>Tell us about your business to get started</Text>
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

            {user?.phone_number ? (
              <View style={styles.phoneDisplay}>
                <Text style={styles.phoneLabel}>WhatsApp Number</Text>
                <Text style={styles.phoneValue}>{user.phone_number}</Text>
              </View>
            ) : null}

            <TouchableOpacity style={styles.button} onPress={handleNextStep}>
              <Text style={styles.buttonText}>Next →</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.features}>
            <Text style={styles.featuresTitle}>What you get:</Text>
            {[
              'AI-powered customer management',
              'Bookings & appointments',
              'Sales & revenue tracking',
              'WhatsApp automations',
            ].map((feature, index) => (
              <View key={index} style={styles.featureItem}>
                <Ionicons name="checkmark-circle" size={20} color="#25D366" />
                <Text style={styles.featureText}>{feature}</Text>
              </View>
            ))}
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
  typeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 },
  typeCard: {
    width: '47%', backgroundColor: '#1A2942', borderRadius: 16,
    padding: 18, borderWidth: 2, borderColor: '#1A2942',
    alignItems: 'flex-start', position: 'relative',
  },
  typeCardActive: { borderColor: '#25D366', backgroundColor: 'rgba(37,211,102,0.08)' },
  typeIcon: { fontSize: 32, marginBottom: 10 },
  typeLabel: { fontSize: 15, fontWeight: '700', color: '#FFFFFF', marginBottom: 4 },
  typeLabelActive: { color: '#25D366' },
  typeDesc: { fontSize: 12, color: '#64748B', lineHeight: 17 },
  typeCheck: { position: 'absolute', top: 10, right: 10 },
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
  features: {
    marginTop: 28,
    paddingBottom: 16,
    backgroundColor: '#0A1628',
  },
  featuresTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#8B9DC3',
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 10,
  },
  featureText: {
    fontSize: 14,
    color: '#CBD5E1',
  },
});
