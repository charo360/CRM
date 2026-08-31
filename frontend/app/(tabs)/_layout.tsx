import React, { useState } from 'react';
import { Tabs, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, View, Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import ThreeDotMenu from '../../components/ThreeDotMenu';
import ProductCatalogModal from '../../components/ProductCatalogModal';
import BusinessKnowledgeModal from '../../components/BusinessKnowledgeModal';
import { useAuth } from '../../context/AuthContext';
import { useBusiness } from '../../context/BusinessContext';

import { settingsAPI } from '../../context/api';

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { config, isRetailBusiness, isLoading } = useBusiness();
  const [showProductCatalog, setShowProductCatalog] = useState(false);
  const [showBusinessKnowledge, setShowBusinessKnowledge] = useState(false);

  // Settings State
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [notificationEnabled, setNotificationEnabled] = useState(false);

  // Fetch initial settings
  React.useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const settings = await settingsAPI.getSettings();
      setAutoReplyEnabled(settings.auto_reply_enabled ?? false);
      setNotificationEnabled(settings.notification_enabled ?? false);
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
    }
  };

  // Wait for business settings to load before mounting the tabs.
  // Mounting earlier hides Bookings/Broadcast because the default config
  // has them off until the real settings arrive.
  if (isLoading) {
    return <View style={styles.loadingContainer} />;
  }

  // Bookings and Broadcast swap a single tab slot: booking businesses get the
  // Bookings tab (Broadcast moves to the three-dot menu), everyone else gets
  // the Broadcast tab (Bookings in the menu when the business supports them).
  const showBookingsTab = config.bookingsTabVisible && !isRetailBusiness;
  const showBroadcastTab = !showBookingsTab;

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
                  // Whichever of Bookings/Broadcast isn't in the tab bar lives here
                  ...(showBookingsTab ? [{
                    icon: 'megaphone-outline' as const,
                    label: 'Broadcast',
                    onPress: () => router.push('/(tabs)/broadcast' as any),
                    color: '#25D366'
                  }] : []),
                  ...(showBroadcastTab && config.bookingsTabVisible ? [{
                    icon: 'calendar-outline' as const,
                    label: config.bookingLabel ? `${config.bookingLabel}s` : 'Bookings',
                    onPress: () => router.push('/(tabs)/bookings' as any),
                    color: '#25D366'
                  }] : []),
                  {
                    icon: 'analytics-outline',
                    label: 'Follow-up Analytics',
                    onPress: () => router.push('../analytics' as any),
                    color: '#25D366'
                  },
                  ...(user?.role === 'owner' || user?.role === 'manager' || !user?.role ? [{
                    icon: 'people-outline' as const,
                    label: 'Team Analytics',
                    onPress: () => router.push('../team-analytics' as any),
                    color: '#4A90E2'
                  }] : []),
                  {
                    icon: 'cube-outline',
                    label: `${config.catalogLabel || 'Product'} Catalog`,
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
          name="sales"
          options={{
            title: config.salesTabLabel || 'Sales',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="cash" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="bookings"
          options={{
            title: config.bookingLabel || 'Bookings',
            href: showBookingsTab ? undefined : null,
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="calendar" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="broadcast"
          options={{
            title: 'Broadcast',
            href: showBroadcastTab ? undefined : null,
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
  loadingContainer: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
});
