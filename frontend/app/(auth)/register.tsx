import React, { useEffect, useState } from 'react';
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
import { settingsAPI, storefrontAPI } from '../../context/api';
import BusinessTypePicker from '../../components/BusinessTypePicker';
import { BusinessType } from '../../context/BusinessContext';

export default function RegisterScreen() {
  const { phone } = useLocalSearchParams<{ phone: string }>();
  const [businessName, setBusinessName] = useState('');
  const [ownerName, setOwnerName] = useState('');
  const [businessType, setBusinessType] = useState<BusinessType>('retail');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { register } = useAuth();
  const [linkCheck, setLinkCheck] = useState<{ slug: string; available: boolean; reason: string } | null>(null);

  // The business name becomes the public shop link, so say up front when
  // another shop already holds it — the name still works, but the link would
  // carry extra characters.
  useEffect(() => {
    const name = businessName.trim();
    if (name.length < 3) {
      setLinkCheck(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const result = await storefrontAPI.checkNameAvailable(name);
        if (!cancelled) setLinkCheck(result);
      } catch {
        // Never let a link hint get in the way of signing up.
        if (!cancelled) setLinkCheck(null);
      }
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [businessName]);

  const handleRegister = async () => {
    if (!businessName.trim()) {
      Alert.alert('Error', 'Please enter your business name');
      return;
    }

    setLoading(true);
    try {
      const result = await register(phone!, businessName, ownerName);
      if (result.success) {
        // The type decides the labels, the tabs and what the public shop does,
        // so set it before the app first renders rather than leaving every
        // new business looking like a shop.
        try {
          await settingsAPI.updateSettings({ business_type: businessType });
        } catch {
          // Not worth blocking sign-up; it can be changed in settings.
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
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <View style={styles.content}>
          <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
          </TouchableOpacity>

          <View style={styles.header}>
            <Text style={styles.title}>Setup Business</Text>
            <Text style={styles.subtitle}>
              Tell us about your business to get started
            </Text>
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
                />
              </View>
              {linkCheck && linkCheck.reason !== 'invalid' && (
                <Text style={linkCheck.available ? styles.linkHintOk : styles.linkHintWarn}>
                  {linkCheck.available
                    ? `Your shop link will be zilo.pro/${linkCheck.slug}`
                    : linkCheck.reason === 'reserved'
                      ? `"${linkCheck.slug}" can't be used as a shop link. Another name gives you a shorter one.`
                      : `Another shop already uses zilo.pro/${linkCheck.slug}, so yours would have extra characters. You can still use this name.`}
                </Text>
              )}
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>What kind of business? *</Text>
              <BusinessTypePicker value={businessType} onChange={setBusinessType} />
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

            <View style={styles.phoneDisplay}>
              <Text style={styles.phoneLabel}>Phone Number</Text>
              <Text style={styles.phoneValue}>{phone}</Text>
            </View>

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

          <View style={styles.features}>
            <Text style={styles.featuresTitle}>What you get:</Text>
            {[
              'Manage customer contacts',
              'Set follow-up reminders',
              'Send receipts via WhatsApp',
              'Broadcast promotions',
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
  },
  backButton: {
    marginTop: 48,
    marginBottom: 24,
    width: 40,
    height: 40,
    justifyContent: 'center',
  },
  header: {
    marginBottom: 32,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#666',
  },
  form: {
    marginBottom: 32,
  },
  inputGroup: {
    marginBottom: 20,
  },
  linkHintOk: {
    marginTop: 8,
    fontSize: 13,
    color: '#25D366',
  },
  linkHintWarn: {
    marginTop: 8,
    fontSize: 13,
    color: '#F0B429',
    lineHeight: 18,
  },
  label: {
    fontSize: 14,
    color: '#FFFFFF',
    marginBottom: 8,
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
    height: 56,
    fontSize: 16,
    color: '#FFFFFF',
  },
  phoneDisplay: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
  },
  phoneLabel: {
    fontSize: 12,
    color: '#666',
    marginBottom: 4,
  },
  phoneValue: {
    fontSize: 16,
    color: '#25D366',
    fontWeight: '600',
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
  features: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 20,
  },
  featuresTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  featureText: {
    fontSize: 14,
    color: '#FFFFFF',
    marginLeft: 12,
  },
});
