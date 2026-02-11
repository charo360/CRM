import React, { useEffect } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';

export default function VerifyScreen() {
  const router = useRouter();

  useEffect(() => {
    // OTP verification is no longer used — redirect to login
    router.replace('/(auth)/login');
  }, []);

  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color="#25D366" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
    justifyContent: 'center',
    alignItems: 'center',
  },
});
