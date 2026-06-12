import React, { useState, useRef, useEffect, useCallback } from 'react';
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
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';

const RESEND_COOLDOWN = 30; // seconds

export default function VerifyScreen() {
  const { phone, devOtp } = useLocalSearchParams<{ phone: string; devOtp: string }>();
  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(RESEND_COOLDOWN);
  const [resending, setResending] = useState(false);
  const inputRefs = useRef<TextInput[]>([]);
  const router = useRouter();
  const { verifyOTP, sendOTP } = useAuth();

  // Countdown timer for resend
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleCodeChange = (text: string, index: number) => {
    const newCode = [...code];
    newCode[index] = text;
    setCode(newCode);

    // Auto-focus next input
    if (text && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }

    // Auto-submit when all digits entered
    if (index === 5 && text) {
      const fullCode = newCode.join('');
      if (fullCode.length === 6) {
        handleVerify(fullCode);
      }
    }
  };

  const handleKeyPress = (e: any, index: number) => {
    if (e.nativeEvent.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleVerify = async (otp?: string) => {
    const fullCode = otp || code.join('');
    if (fullCode.length !== 6) {
      Alert.alert('Error', 'Please enter the 6-digit code');
      return;
    }

    setLoading(true);
    try {
      const result = await verifyOTP(phone!, fullCode);
      if (result.success) {
        if (result.isNewUser) {
          router.replace({
            pathname: '/(auth)/register',
            params: { phone: phone },
          });
        } else {
          router.replace('/(tabs)/customers');
        }
      } else {
        Alert.alert('Invalid Code', result.message || 'The code you entered is incorrect. Please try again.');
      }
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Verification failed');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || resending) return;
    setResending(true);
    try {
      const result = await sendOTP(phone!);
      if (result.success) {
        // Reset code inputs
        setCode(['', '', '', '', '', '']);
        inputRefs.current[0]?.focus();
        // Restart cooldown
        setResendCooldown(RESEND_COOLDOWN);
        Alert.alert('Code Sent', `A new verification code has been sent to ${phone}`);
      } else {
        Alert.alert('Error', result.message || 'Failed to resend code');
      }
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Something went wrong');
    } finally {
      setResending(false);
    }
  };

  const maskedPhone = phone
    ? phone.slice(0, -4).replace(/\d/g, '•') + phone.slice(-4)
    : '';

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.content}>
        <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
        </TouchableOpacity>

        <View style={styles.header}>
          <View style={styles.iconCircle}>
            <Ionicons name="chatbubble-ellipses-outline" size={32} color="#25D366" />
          </View>
          <Text style={styles.title}>Check your SMS</Text>
          <Text style={styles.subtitle}>We sent a 6-digit code to</Text>
          <Text style={styles.phone}>{maskedPhone}</Text>
        </View>

        {/* OTP input boxes */}
        <View style={styles.codeContainer}>
          {code.map((digit, index) => (
            <TextInput
              key={index}
              ref={(ref) => { if (ref) inputRefs.current[index] = ref; }}
              style={[
                styles.codeInput,
                digit && styles.codeInputFilled,
              ]}
              value={digit}
              onChangeText={(text) => handleCodeChange(text.slice(-1), index)}
              onKeyPress={(e) => handleKeyPress(e, index)}
              keyboardType="number-pad"
              maxLength={1}
              selectTextOnFocus
              autoFocus={index === 0}
            />
          ))}
        </View>

        {/* Verify button */}
        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={() => handleVerify()}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.buttonText}>Verify Code</Text>
          )}
        </TouchableOpacity>

        {/* Resend */}
        <View style={styles.resendRow}>
          <Text style={styles.resendText}>Didn't receive it? </Text>
          {resendCooldown > 0 ? (
            <Text style={styles.resendCooldown}>Resend in {resendCooldown}s</Text>
          ) : (
            <TouchableOpacity onPress={handleResend} disabled={resending}>
              {resending ? (
                <ActivityIndicator size="small" color="#25D366" />
              ) : (
                <Text style={styles.resendLink}>Resend Code</Text>
              )}
            </TouchableOpacity>
          )}
        </View>

        {/* Dev sandbox box — only shown when SMS was NOT sent (no real Vonage keys) */}
        {devOtp ? (
          <View style={styles.devBox}>
            <Ionicons name="flask-outline" size={16} color="#F59E0B" />
            <Text style={styles.devText}>Dev mode — code: <Text style={styles.devCode}>{devOtp}</Text></Text>
          </View>
        ) : null}
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
  },
  backButton: {
    marginTop: 48,
    marginBottom: 24,
    width: 40,
    height: 40,
    justifyContent: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: 40,
  },
  iconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: '#111F35',
    borderWidth: 2,
    borderColor: '#25D366',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
  },
  title: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 15,
    color: '#8A9BB5',
    marginBottom: 4,
  },
  phone: {
    fontSize: 16,
    color: '#25D366',
    fontWeight: '600',
    letterSpacing: 1,
  },
  codeContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 32,
  },
  codeInput: {
    width: 48,
    height: 60,
    backgroundColor: '#1A2942',
    borderRadius: 14,
    fontSize: 26,
    fontWeight: 'bold',
    color: '#FFFFFF',
    textAlign: 'center',
    borderWidth: 2,
    borderColor: '#243451',
  },
  codeInputFilled: {
    backgroundColor: '#1A3D2A',
    borderColor: '#25D366',
    color: '#25D366',
  },
  button: {
    backgroundColor: '#25D366',
    borderRadius: 14,
    height: 58,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
    shadowColor: '#25D366',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '700',
  },
  resendRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
  },
  resendText: {
    color: '#8A9BB5',
    fontSize: 14,
  },
  resendLink: {
    color: '#25D366',
    fontSize: 14,
    fontWeight: '700',
  },
  resendCooldown: {
    color: '#4A5A72',
    fontSize: 14,
  },
  devBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F1A0D',
    borderRadius: 10,
    padding: 12,
    marginTop: 32,
    borderWidth: 1,
    borderColor: '#F59E0B',
    gap: 8,
  },
  devText: {
    color: '#F59E0B',
    fontSize: 13,
  },
  devCode: {
    fontWeight: 'bold',
    letterSpacing: 2,
  },
});
