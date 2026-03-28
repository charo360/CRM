import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider } from '../context/AuthContext';
import { BusinessProvider } from '../context/BusinessContext';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StyleSheet, Platform } from 'react-native';
import Constants from 'expo-constants';

export default function RootLayout() {
  useEffect(() => {
    // Skip RevenueCat entirely in Expo Go — it cannot use native billing
    const isExpoGo = Constants.appOwnership === 'expo';
    if (isExpoGo) {
      console.log('RevenueCat init skipped (Expo Go mode)');
      return;
    }
    // Only configure in real native builds (APK / IPA)
    try {
      const Purchases = require('react-native-purchases').default;
      if (Platform.OS === 'android') {
        Purchases.configure({ apiKey: 'goog_YOUR_GOOGLE_API_KEY' });
      } else if (Platform.OS === 'ios') {
        Purchases.configure({ apiKey: 'appl_YOUR_APPLE_API_KEY' });
      }
    } catch (error) {
      console.log('RevenueCat init failed:', error);
    }
  }, []);

  return (
    <GestureHandlerRootView style={styles.container}>
      <AuthProvider>
        <BusinessProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: '#0A1628' },
          }}
        >
          <Stack.Screen name="index" />
          <Stack.Screen name="(auth)" />
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="chat" options={{ headerShown: false, animation: 'slide_from_right' }} />
          <Stack.Screen name="customer-profile" options={{ headerShown: false, animation: 'slide_from_right' }} />
        </Stack>
        </BusinessProvider>
      </AuthProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
