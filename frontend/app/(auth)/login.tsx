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
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import CountryPicker, { Country, COUNTRIES } from '../../components/CountryPicker';

export default function LoginScreen() {
  const [selectedCountry, setSelectedCountry] = useState<Country>(
    COUNTRIES.find(c => c.code === 'KE')!
  );
  const [phoneNumber, setPhoneNumber] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { sendOTP } = useAuth();

  const fullPhone = `${selectedCountry.dial}${phoneNumber.replace(/^0+/, '')}`;

  const handleSendOTP = async () => {
    if (phoneNumber.length < 6) {
      Alert.alert('Error', 'Please enter a valid phone number');
      return;
    }

    setLoading(true);
    try {
      const result = await sendOTP(fullPhone);
      if (result.success) {
        router.push({
          pathname: '/(auth)/verify',
          params: { phone: fullPhone, devOtp: result.devOtp || '', countryCode: selectedCountry.code },
        });
      } else {
        Alert.alert('Error', result.message || 'Failed to send OTP');
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
      <View style={styles.content}>
        <View style={styles.header}>
          <Text style={styles.emoji}>💼</Text>
          <Text style={styles.title}>WhatsApp CRM</Text>
          <Text style={styles.subtitle}>For Businesses Worldwide</Text>
        </View>

        <View style={styles.form}>
          <Text style={styles.label}>Enter your phone number</Text>
          <View style={styles.phoneRow}>
            <CountryPicker
              selectedCountry={selectedCountry}
              onSelect={setSelectedCountry}
            />
            <View style={styles.phoneInputContainer}>
              <TextInput
                style={styles.phoneInput}
                value={phoneNumber}
                onChangeText={setPhoneNumber}
                placeholder="Phone number"
                placeholderTextColor="#666"
                keyboardType="phone-pad"
                autoComplete="tel"
              />
            </View>
          </View>
          <Text style={styles.hint}>
            We'll send you a verification code via SMS
          </Text>

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleSendOTP}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>Send OTP</Text>
            )}
          </TouchableOpacity>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            Manage customers, follow up, send offers{"\n"}and receipts — all from WhatsApp
          </Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  content: {
    flex: 1,
    padding: 24,
    justifyContent: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: 48,
  },
  emoji: {
    fontSize: 48,
    marginBottom: 16,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#25D366',
  },
  form: {
    marginBottom: 32,
  },
  label: {
    fontSize: 16,
    color: '#FFFFFF',
    marginBottom: 12,
  },
  phoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  phoneInputContainer: {
    flex: 1,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    paddingHorizontal: 16,
  },
  phoneInput: {
    height: 56,
    fontSize: 18,
    color: '#FFFFFF',
  },
  hint: {
    fontSize: 13,
    color: '#666',
    marginBottom: 24,
  },
  button: {
    backgroundColor: '#25D366',
    borderRadius: 12,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '600',
  },
  footer: {
    alignItems: 'center',
  },
  footerText: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    lineHeight: 22,
  },
});
