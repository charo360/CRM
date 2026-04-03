import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider } from '../context/AuthContext';
import { BusinessProvider } from '../context/BusinessContext';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StyleSheet, Platform } from 'react-native';
import { settingsAPI } from '../context/api';

async function registerPushToken() {
  try {
    const Notifications = await import('expo-notifications');
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== 'granted') return;

    const tokenData = await Notifications.getExpoPushTokenAsync();
    const token = tokenData.data;
    if (token) {
      await settingsAPI.registerPushToken(token);
    }

    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('followups', {
        name: 'Follow-up Reminders',
        importance: Notifications.AndroidImportance.HIGH,
        sound: 'default',
      });
    }
  } catch (e) {
    console.log('Push token registration skipped:', e);
  }
}

export default function RootLayout() {
  useEffect(() => {
    registerPushToken();
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
