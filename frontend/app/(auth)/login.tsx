import React, { useState, useEffect, useRef, useCallback } from 'react';
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
  Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { useAuth } from '../../context/AuthContext';
import CountryPicker, { Country, COUNTRIES } from '../../components/CountryPicker';

export default function LoginScreen() {
  const [selectedCountry, setSelectedCountry] = useState<Country>(
    COUNTRIES.find(c => c.code === 'KE')!
  );
  const [phoneNumber, setPhoneNumber] = useState('');
  const [loading, setLoading] = useState(false);

  // Pairing state
  const [pairingCode, setPairingCode] = useState('');
  const [sessionToken, setSessionToken] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [copied, setCopied] = useState(false);
  const [isPairing, setIsPairing] = useState(false);

  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const router = useRouter();
  const { startWhatsAppAuth, checkWhatsAppAuth, refreshPairingCode } = useAuth();

  const fullPhone = `${selectedCountry.dial}${phoneNumber.replace(/^0+/, '')}`;

  const clearTimers = useCallback(() => {
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    if (refreshRef.current) { clearTimeout(refreshRef.current); refreshRef.current = null; }
  }, []);

  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  const startPairingTimers = useCallback((code: string, token: string) => {
    clearTimers();
    setPairingCode(code);
    setCountdown(60);
    setCopied(false);

    // Copy to clipboard immediately
    Clipboard.setStringAsync(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });

    // Countdown timer
    countdownRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          if (countdownRef.current) clearInterval(countdownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    // Auto-refresh code at 50s (before 60s expiry)
    refreshRef.current = setTimeout(async () => {
      try {
        const res = await refreshPairingCode(token);
        if (res.success && res.pairingCode) {
          startPairingTimers(res.pairingCode, token);
        }
      } catch (e) {
        console.log('Auto-refresh pairing code failed');
      }
    }, 50000);

    // Poll for connection every 5s
    pollingRef.current = setInterval(async () => {
      try {
        const result = await checkWhatsAppAuth(token);
        if (result.connected) {
          clearTimers();
          setIsPairing(false);
          setPairingCode('');
          if (result.isNewUser) {
            router.replace({
              pathname: '/(auth)/register',
              params: { countryCode: selectedCountry.code },
            });
          } else {
            router.replace('/(tabs)/customers');
          }
        }
      } catch (e) { /* ignore */ }
    }, 5000);
  }, [clearTimers, refreshPairingCode, checkWhatsAppAuth, router, selectedCountry.code]);

  const handleConnect = async () => {
    if (phoneNumber.length < 6) {
      Alert.alert('Error', 'Please enter a valid phone number');
      return;
    }

    setLoading(true);
    try {
      const result = await startWhatsAppAuth(fullPhone, selectedCountry.code);

      if (result.success && result.alreadyConnected) {
        // User already has WhatsApp connected — skip pairing, go straight in
        if (result.isNewUser) {
          router.replace({
            pathname: '/(auth)/register',
            params: { countryCode: selectedCountry.code },
          });
        } else {
          router.replace('/(tabs)/customers');
        }
        return;
      }

      if (result.success && result.pairingCode && result.sessionToken) {
        setSessionToken(result.sessionToken);
        setIsPairing(true);
        startPairingTimers(result.pairingCode, result.sessionToken);
      } else {
        Alert.alert('Error', result.message || 'Failed to connect WhatsApp');
      }
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyCode = async () => {
    if (!pairingCode) return;
    await Clipboard.setStringAsync(pairingCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenWhatsApp = () => {
    if (pairingCode) {
      const link = `https://wa.me/login?code=${pairingCode}`;
      Linking.openURL(link)
        .catch(() => Linking.openURL('whatsapp://'))
        .catch(() => {
          Alert.alert('Error', 'Could not open WhatsApp. Please open it manually and go to Linked Devices.');
        });
    } else {
      Linking.openURL('whatsapp://')
        .catch(() => {
          Alert.alert('Error', 'Could not open WhatsApp. Please open it manually.');
        });
    }
  };

  const handleCancel = () => {
    clearTimers();
    setIsPairing(false);
    setPairingCode('');
    setSessionToken('');
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <View style={styles.content}>
          <View style={styles.header}>
            <Text style={styles.emoji}>💼</Text>
            <Text style={styles.title}>WhatsApp CRM</Text>
            <Text style={styles.subtitle}>For Businesses Worldwide</Text>
          </View>

          {!isPairing ? (
            <View style={styles.form}>
              <Text style={styles.label}>Enter your WhatsApp number</Text>
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
                We'll connect your WhatsApp to verify your identity
              </Text>

              <TouchableOpacity
                style={[styles.button, loading && styles.buttonDisabled]}
                onPress={handleConnect}
                disabled={loading}
              >
                {loading ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <View style={styles.buttonInner}>
                    <Ionicons name="logo-whatsapp" size={22} color="#FFFFFF" />
                    <Text style={styles.buttonText}>Connect WhatsApp</Text>
                  </View>
                )}
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.pairingSection}>
              <Text style={styles.pairingTitle}>Enter this code in WhatsApp</Text>
              <Text style={styles.pairingInstructions}>
                Open WhatsApp {'>'} Linked Devices {'>'} Link a Device {'>'} Link with phone number
              </Text>

              <TouchableOpacity
                onPress={handleCopyCode}
                activeOpacity={0.7}
                style={styles.codeBox}
              >
                <Text style={styles.codeText}>{pairingCode}</Text>
                <View style={styles.copyRow}>
                  <Ionicons
                    name={copied ? 'checkmark-circle' : 'copy-outline'}
                    size={16}
                    color={copied ? '#25D366' : '#8B9DC3'}
                  />
                  <Text style={[styles.copyText, copied && { color: '#25D366' }]}>
                    {copied ? 'Copied to clipboard!' : 'Tap to copy code'}
                  </Text>
                </View>
              </TouchableOpacity>

              <View style={styles.notificationBox}>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
                  <Ionicons name="notifications" size={18} color="#25D366" />
                  <Text style={{ color: '#25D366', fontSize: 13, fontWeight: '600', marginLeft: 8 }}>Check your phone for push notification</Text>
                </View>
                <Text style={{ color: '#8B9DC3', fontSize: 12, lineHeight: 18 }}>
                  WhatsApp will send a notification to link this device. Tap it to open the pairing screen, then enter the code above.
                </Text>
              </View>

              <View style={styles.countdownRow}>
                <View style={[styles.countdownDot, { backgroundColor: countdown > 10 ? '#25D366' : '#FF4444' }]} />
                <Text style={[styles.countdownText, countdown <= 10 && { color: '#FF4444' }]}>
                  {countdown > 0 ? `Code refreshes in ${countdown}s` : 'Refreshing code...'}
                </Text>
              </View>

              <View style={styles.waitingRow}>
                <ActivityIndicator size="small" color="#25D366" />
                <Text style={styles.waitingText}>Waiting for connection...</Text>
              </View>

              <TouchableOpacity style={styles.cancelButton} onPress={handleCancel}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          )}

          <View style={styles.footer}>
            <Text style={styles.footerText}>
              Manage customers, follow up, send offers{"\n"}and receipts — all from WhatsApp
            </Text>
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
  buttonInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '600',
  },
  // Pairing section
  pairingSection: {
    marginBottom: 32,
  },
  pairingTitle: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 8,
  },
  pairingInstructions: {
    color: '#8B9DC3',
    fontSize: 13,
    marginBottom: 16,
    lineHeight: 20,
  },
  codeBox: {
    backgroundColor: 'rgba(37,211,102,0.1)',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
    marginBottom: 12,
  },
  codeText: {
    color: '#25D366',
    fontSize: 36,
    fontWeight: '700',
    letterSpacing: 8,
  },
  copyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 10,
  },
  copyText: {
    color: '#8B9DC3',
    fontSize: 12,
    marginLeft: 6,
  },
  countdownRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  countdownDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  countdownText: {
    color: '#8B9DC3',
    fontSize: 12,
  },
  notificationBox: {
    backgroundColor: 'rgba(37,211,102,0.05)',
    borderRadius: 10,
    padding: 12,
    marginBottom: 12,
  },
  openWaButton: {
    backgroundColor: '#25D366',
    borderRadius: 10,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  openWaText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
    marginLeft: 8,
  },
  waitingRow: {
    alignItems: 'center',
    marginBottom: 16,
  },
  waitingText: {
    color: '#8B9DC3',
    fontSize: 11,
    textAlign: 'center',
    marginTop: 8,
  },
  cancelButton: {
    alignItems: 'center',
    paddingVertical: 10,
  },
  cancelText: {
    color: '#8B9DC3',
    fontSize: 14,
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
