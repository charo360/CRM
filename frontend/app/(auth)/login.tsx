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
  Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';

export default function LoginScreen() {
  const [phoneNumber, setPhoneNumber] = useState('+');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { sendOTP } = useAuth();

  const handleSendOTP = async () => {
    const cleaned = phoneNumber.replace(/\s/g, '');
    if (cleaned.length < 10 || !cleaned.startsWith('+')) {
      Alert.alert('Invalid Number', 'Please enter your number with country code, e.g. +254712345678');
      return;
    }

    setLoading(true);
    try {
      const result = await sendOTP(cleaned);
      if (result.success) {
        router.push({
          pathname: '/(auth)/verify',
          params: { phone: cleaned, devOtp: result.devOtp || '' },
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
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.logoCircle}>
            <Text style={styles.logoText}>Z</Text>
          </View>
          <Text style={styles.title}>Zilo CRM</Text>
          <Text style={styles.subtitle}>Grow your business with AI</Text>
        </View>

        {/* Form */}
        <View style={styles.form}>
          <Text style={styles.label}>Phone Number</Text>
          <View style={styles.inputContainer}>
            <Ionicons name="call-outline" size={20} color="#8A9BB5" style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              value={phoneNumber}
              onChangeText={(text) => {
                // Always keep the + prefix
                if (!text.startsWith('+')) {
                  setPhoneNumber('+' + text.replace(/\+/g, ''));
                } else {
                  setPhoneNumber(text);
                }
              }}
              placeholder="+1 555 000 0000"
              placeholderTextColor="#4A5A72"
              keyboardType="phone-pad"
              autoComplete="tel"
            />
          </View>
          <Text style={styles.hint}>
            Include your country code · e.g. +254 for Kenya, +1 for US
          </Text>

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleSendOTP}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <View style={styles.buttonInner}>
                <Ionicons name="send" size={18} color="#FFFFFF" style={{ marginRight: 8 }} />
                <Text style={styles.buttonText}>Send Verification Code</Text>
              </View>
            )}
          </TouchableOpacity>
        </View>

        {/* Features */}
        <View style={styles.featuresCard}>
          {[
            { icon: 'people-outline', text: 'Manage customer contacts' },
            { icon: 'notifications-outline', text: 'Smart follow-up reminders' },
            { icon: 'bar-chart-outline', text: 'AI-powered business insights' },
            { icon: 'megaphone-outline', text: 'Broadcast promotions & offers' },
          ].map((item, i) => (
            <View key={i} style={styles.featureRow}>
              <View style={styles.featureIcon}>
                <Ionicons name={item.icon as any} size={16} color="#25D366" />
              </View>
              <Text style={styles.featureText}>{item.text}</Text>
            </View>
          ))}
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
    marginBottom: 40,
  },
  logoCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: '#25D366',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
    shadowColor: '#25D366',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 16,
    elevation: 8,
  },
  logoText: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 15,
    color: '#8A9BB5',
  },
  form: {
    marginBottom: 24,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 10,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 14,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: '#243451',
    marginBottom: 8,
  },
  inputIcon: {
    marginRight: 12,
  },
  input: {
    flex: 1,
    height: 58,
    fontSize: 20,
    color: '#FFFFFF',
    letterSpacing: 1,
  },
  hint: {
    fontSize: 12,
    color: '#4A5A72',
    marginBottom: 24,
    paddingHorizontal: 4,
  },
  button: {
    backgroundColor: '#25D366',
    borderRadius: 14,
    height: 58,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#25D366',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonInner: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '700',
  },
  featuresCard: {
    backgroundColor: '#111F35',
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: '#1E3452',
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 14,
  },
  featureIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: '#0D2038',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  featureText: {
    fontSize: 14,
    color: '#8A9BB5',
    flex: 1,
  },
});
