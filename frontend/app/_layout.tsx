import React, { useEffect } from 'react';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider, useAuth } from '../context/AuthContext';
import { BusinessProvider } from '../context/BusinessContext';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StyleSheet } from 'react-native';

/**
 * Leave the signed-in screens whenever the session goes.
 *
 * Routing otherwise happens once, at start-up, so losing a session mid-use —
 * an account deleted, a token expired, a sign-out elsewhere — left the app
 * showing a signed-in interface until it was force-closed. Every screen that
 * cleared a session had to remember to navigate, and one of them did not.
 *
 * The auth screens are left alone, since that is where this would send people
 * anyway. The launch screen needs no special case: it routes to the same place
 * when signed out, and when signed in this guard does nothing, so it is free to
 * resume an unfinished setup without being overridden.
 */
function SessionGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    const inAuthScreens = segments[0] === '(auth)';
    if (!isAuthenticated && !inAuthScreens) {
      router.replace('/(auth)/login');
    }
  }, [isAuthenticated, isLoading, segments, router]);

  return <>{children}</>;
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.container}>
      <AuthProvider>
        <SessionGuard>
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
        </SessionGuard>
      </AuthProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
