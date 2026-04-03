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

              {/* ── Code box ── */}
              <Text style={styles.pairingTitle}>Your pairing code</Text>
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
                    {copied ? 'Copied!' : 'Tap to copy'}
                  </Text>
                </View>
              </TouchableOpacity>

              {/* ── Auto-refresh status ── */}
              <View style={styles.countdownRow}>
                <View style={[styles.countdownDot, { backgroundColor: countdown > 10 ? '#25D366' : '#FFA500' }]} />
                <Text style={[styles.countdownText, countdown <= 10 && { color: '#FFA500' }]}>
                  {countdown > 0 ? `Code valid for ${countdown}s — auto-renews` : 'Getting new code...'}
                </Text>
              </View>

              {/* ── Open WhatsApp button ── */}
              <TouchableOpacity style={styles.openWaButton} onPress={handleOpenWhatsApp}>
                <Ionicons name="logo-whatsapp" size={20} color="#FFFFFF" />
                <Text style={styles.openWaText}>Open WhatsApp</Text>
              </TouchableOpacity>

              {/* ── Numbered steps ── */}
              <View style={styles.stepsBox}>
                <Text style={styles.stepsTitle}>How to enter the code:</Text>
                {[
                  'Open WhatsApp on this phone',
                  'Tap the 3-dot menu (⋮) → Linked Devices',
                  'Tap "Link a Device"',
                  'Choose "Link with phone number" at the bottom',
                  'Enter the code shown above',
                ].map((step, i) => (
                  <View key={i} style={styles.stepRow}>
                    <View style={styles.stepBadge}>
                      <Text style={styles.stepBadgeText}>{i + 1}</Text>
                    </View>
                    <Text style={styles.stepText}>{step}</Text>
                  </View>
                ))}
              </View>

              {/* ── Waiting indicator ── */}
              <View style={styles.waitingRow}>
                <ActivityIndicator size="small" color="#25D366" />
                <Text style={styles.waitingText}>Waiting for you to connect...</Text>
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
    fontWeight: '700',
    marginBottom: 12,
    textAlign: 'center',
  },
  codeBox: {
    backgroundColor: 'rgba(37,211,102,0.12)',
    borderRadius: 14,
    paddingVertical: 22,
    paddingHorizontal: 20,
    alignItems: 'center',
    marginBottom: 10,
    borderWidth: 1,
    borderColor: 'rgba(37,211,102,0.3)',
  },
  codeText: {
    color: '#25D366',
    fontSize: 40,
    fontWeight: '700',
    letterSpacing: 10,
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
    marginBottom: 14,
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
  openWaButton: {
    backgroundColor: '#25D366',
    borderRadius: 12,
    paddingVertical: 15,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
    gap: 10,
  },
  openWaText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  stepsBox: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: 12,
    padding: 16,
    marginBottom: 18,
  },
  stepsTitle: {
    color: '#8B9DC3',
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 12,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 10,
  },
  stepBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'rgba(37,211,102,0.2)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
    marginTop: 1,
    flexShrink: 0,
  },
  stepBadgeText: {
    color: '#25D366',
    fontSize: 11,
    fontWeight: '700',
  },
  stepText: {
    color: '#CCCCCC',
    fontSize: 13,
    lineHeight: 20,
    flex: 1,
  },
  waitingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginBottom: 16,
  },
  waitingText: {
    color: '#8B9DC3',
    fontSize: 12,
    textAlign: 'center',
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
