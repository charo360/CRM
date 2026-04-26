import React, { useState, useRef, useEffect } from 'react';
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

export default function VerifyScreen() {
  const { phone, devOtp } = useLocalSearchParams<{ phone: string; devOtp: string }>();
  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [showOtp, setShowOtp] = useState(true);
  const inputRefs = useRef<TextInput[]>([]);
  const router = useRouter();
  const { verifyOTP } = useAuth();

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
        Alert.alert('Error', result.message || 'Invalid OTP');
      }
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Verification failed');
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
        <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
        </TouchableOpacity>

        <View style={styles.header}>
          <Text style={styles.title}>Verify Phone</Text>
          <Text style={styles.subtitle}>Enter the 6-digit code sent to</Text>
          <Text style={styles.phone}>{phone}</Text>
        </View>

        {/* SANDBOX MODE - Show OTP on screen */}
        {devOtp && showOtp && (
          <View style={styles.otpBox}>
            <View style={styles.otpBoxHeader}>
              <Text style={styles.otpBoxTitle}>🧪 SANDBOX MODE</Text>
              <TouchableOpacity onPress={() => setShowOtp(false)}>
                <Ionicons name="close" size={20} color="#666" />
              </TouchableOpacity>
            </View>
            <Text style={styles.otpBoxCode}>{devOtp}</Text>
            <Text style={styles.otpBoxHint}>Use this code to verify (SMS not sent)</Text>
            <TouchableOpacity
              style={styles.autoFillButton}
              onPress={() => {
                const digits = devOtp.split('');
                setCode(digits);
                // Auto verify after filling
                setTimeout(() => handleVerify(devOtp), 500);
              }}
            >
              <Text style={styles.autoFillText}>Tap to Auto-Fill & Verify</Text>
            </TouchableOpacity>
          </View>
        )}

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
            />
          ))}
        </View>

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={() => handleVerify()}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.buttonText}>Verify</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity style={styles.resendButton}>
          <Text style={styles.resendText}>Didn't receive code? </Text>
          <Text style={styles.resendLink}>Resend</Text>
        </TouchableOpacity>
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
    marginBottom: 48,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 16,
    color: '#666',
  },
  phone: {
    fontSize: 16,
    color: '#25D366',
    fontWeight: '600',
  },
  codeContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 32,
  },
  codeInput: {
    width: 48,
    height: 56,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFFFFF',
    textAlign: 'center',
  },
  codeInputFilled: {
    backgroundColor: '#25D366',
  },
  button: {
    backgroundColor: '#25D366',
    borderRadius: 12,
    height: 56,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '600',
  },
  resendButton: {
    flexDirection: 'row',
    justifyContent: 'center',
  },
  resendText: {
    color: '#666',
    fontSize: 14,
  },
  resendLink: {
    color: '#25D366',
    fontSize: 14,
    fontWeight: '600',
  },
  otpBox: {
    backgroundColor: '#1E3A5F',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
    borderWidth: 2,
    borderColor: '#25D366',
  },
  otpBoxHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  otpBoxTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#25D366',
  },
  otpBoxCode: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#FFFFFF',
    textAlign: 'center',
    letterSpacing: 8,
    marginVertical: 8,
  },
  otpBoxHint: {
    fontSize: 12,
    color: '#888',
    textAlign: 'center',
  },
  autoFillButton: {
    backgroundColor: '#25D366',
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
    alignItems: 'center',
  },
  autoFillText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
});
