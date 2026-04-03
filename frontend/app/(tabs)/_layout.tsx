import React, { useState, useEffect, useRef } from 'react';
import { Tabs, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, View, Platform, Modal } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import ThreeDotMenu from '../../components/ThreeDotMenu';
import ProductCatalogModal from '../../components/ProductCatalogModal';
import BusinessKnowledgeModal from '../../components/BusinessKnowledgeModal';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';

import { useAuth } from '../../context/AuthContext';
import { useBusiness } from '../../context/BusinessContext';
import { settingsAPI, apiClient } from '../../context/api';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [showProductCatalog, setShowProductCatalog] = useState(false);
  const [showBusinessKnowledge, setShowBusinessKnowledge] = useState(false);

  // Settings State
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [notificationEnabled, setNotificationEnabled] = useState(false);
  const [dailyPulseEnabled, setDailyPulseEnabled] = useState(false);

  const { user } = useAuth();
  const { config, isRetailBusiness } = useBusiness();
  const notificationListener = useRef<any>();
  const responseListener = useRef<any>();

  // Fetch initial settings only after auth is ready
  React.useEffect(() => {
    if (user) {
      loadSettings();
      registerForPushNotifications();
    }
    return () => {
      if (notificationListener.current) notificationListener.current.remove();
      if (responseListener.current) responseListener.current.remove();
    };
  }, [user]);

  const registerForPushNotifications = async () => {
    try {
      if (!Device.isDevice) return;

      if (Platform.OS === 'android') {
        await Notifications.setNotificationChannelAsync('default', {
          name: 'default',
          importance: Notifications.AndroidImportance.MAX,
          vibrationPattern: [0, 250, 250, 250],
          lightColor: '#25D366',
        });
      }

      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;
      if (existingStatus !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync();
        finalStatus = status;
      }
      if (finalStatus !== 'granted') return;

      // Remote push requires a dev build (not Expo Go) and a projectId
      // Skip silently if not available — local notifications still work
      let token: string | null = null;
      try {
        const Constants = (await import('expo-constants')).default;
        const projectId =
          Constants.expoConfig?.extra?.eas?.projectId ??
          Constants.easConfig?.projectId;
        if (projectId) {
          const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
          token = tokenData.data;
        }
      } catch {
        // Running in Expo Go or no projectId — skip remote push silently
      }

      if (token) {
        await apiClient.post('/auth/push-token', { token });
      }

      notificationListener.current = Notifications.addNotificationReceivedListener(() => {});
      responseListener.current = Notifications.addNotificationResponseReceivedListener((response) => {
        const data = response.notification.request.content.data as any;
        if (data?.type === 'new_contact' || data?.type === 'new_message') {
          router.push('/(tabs)/customers');
        }
      });
    } catch (e) {
      console.log('Push notification setup failed:', e);
    }
  };

  const loadSettings = async () => {
    try {
      const settings = await settingsAPI.getSettings();
      setAutoReplyEnabled(settings.auto_reply_enabled ?? false);
      setNotificationEnabled(settings.notification_enabled ?? false);
      setDailyPulseEnabled(settings.daily_pulse_enabled ?? false);
    } catch (error) {
      console.log('Error loading settings:', error);
    }
  };

  const handleToggleAutoReply = async () => {
    const newValue = !autoReplyEnabled;
    setAutoReplyEnabled(newValue);
    try {
      await settingsAPI.updateSettings({ auto_reply_enabled: newValue });
    } catch (error) {
      console.error('Failed to update auto-reply', error);
      setAutoReplyEnabled(!newValue); // Revert on failure
    }
  };

  const handleToggleNotification = async () => {
    const newValue = !notificationEnabled;
    setNotificationEnabled(newValue);
    try {
      await settingsAPI.updateSettings({ notification_enabled: newValue });
    } catch (error) {
      console.error('Failed to update notifications', error);
      setNotificationEnabled(!newValue); // Revert on failure
    }
  };

  const handleToggleDailyPulse = async () => {
    const newValue = !dailyPulseEnabled;
    setDailyPulseEnabled(newValue);
    try {
      await settingsAPI.updateSettings({ daily_pulse_enabled: newValue });
    } catch (error) {
      console.error('Failed to update daily pulse', error);
      setDailyPulseEnabled(!newValue);
    }
  };

  return (
    <>
      <Tabs
        screenOptions={{
          headerShown: true,
          headerStyle: {
            backgroundColor: '#0A1628',
            borderBottomWidth: 1,
            borderBottomColor: '#1A2942',
            height: Platform.OS === 'ios' ? 100 : 80,
          },
          headerTitleStyle: {
            color: '#FFFFFF',
            fontSize: 20,
            fontWeight: 'bold',
          },
          headerRight: () => (
            <View style={{ marginRight: 10 }}>
              <ThreeDotMenu
                color="#FFFFFF"
                items={[
                  {
                    icon: 'analytics-outline',
                    label: 'Analytics',
                    onPress: () => router.push('../analytics' as any),
                    color: '#25D366'
                  },
                  ...(user?.role === 'owner' || user?.role === 'manager' || !user?.role ? [{
                    icon: 'people-outline' as const,
                    label: 'Team Analytics',
                    onPress: () => router.push('../team-analytics' as any),
                    color: '#4A90E2'
                  }] : []),
                  ...(!isRetailBusiness ? [{
                    icon: 'megaphone-outline' as const,
                    label: 'Broadcast',
                    onPress: () => router.push('/(tabs)/broadcast' as any),
                    color: '#F59E0B'
                  }] : []),
                  {
                    icon: 'cube-outline',
                    label: `${config.catalogLabel} Catalog`,
                    onPress: () => setShowProductCatalog(true)
                  },
                  {
                    icon: 'book-outline',
                    label: 'Business Knowledge',
                    onPress: () => setShowBusinessKnowledge(true)
                  },
                  {
                    icon: 'chatbubbles-outline',
                    label: 'Auto Reply',
                    type: 'toggle',
                    value: autoReplyEnabled,
                    onPress: handleToggleAutoReply,
                  },
                  {
                    icon: 'notifications-outline',
                    label: 'Notifications',
                    type: 'toggle',
                    value: notificationEnabled,
                    onPress: handleToggleNotification,
                  },
                  {
                    icon: 'pulse',
                    label: 'Daily Pulse',
                    type: 'toggle',
                    value: dailyPulseEnabled,
                    onPress: handleToggleDailyPulse,
                    color: '#25D366',
                  }
                ]}
              />
            </View>
          ),
          tabBarStyle: {
            ...styles.tabBar,
            height: (Platform.OS === 'ios' ? 88 : 64) + (Platform.OS === 'android' ? insets.bottom : 0),
            paddingBottom: (Platform.OS === 'ios' ? 28 : 8) + (Platform.OS === 'android' ? insets.bottom : 0),
          },
          tabBarActiveTintColor: '#25D366',
          tabBarInactiveTintColor: '#666',
          tabBarLabelStyle: styles.tabBarLabel,
        }}
      >
        <Tabs.Screen
          name="customers"
          options={{
            title: 'Customers',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="people" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="followups"
          options={{
            title: 'Follow-ups',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="notifications" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="bookings"
          options={{
            title: 'Bookings',
            href: config.bookingsTabVisible ? undefined : null,
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="calendar" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="sales"
          options={{
            title: config.salesTabLabel || 'Sales',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="cash" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="broadcast"
          options={{
            title: 'Broadcast',
            href: isRetailBusiness ? undefined : null,
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="megaphone" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="account"
          options={{
            title: 'Account',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="person" size={size} color={color} />
            ),
          }}
        />
      </Tabs>

      <ProductCatalogModal
        visible={showProductCatalog}
        onClose={() => setShowProductCatalog(false)}
      />
      <BusinessKnowledgeModal
        visible={showBusinessKnowledge}
        onClose={() => setShowBusinessKnowledge(false)}
      />
    </>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: '#0A1628',
    borderTopColor: '#1A2942',
    borderTopWidth: 1,
    paddingTop: 8,
  },
  tabBarLabel: {
    fontSize: 11,
    fontWeight: '500',
  },
});
