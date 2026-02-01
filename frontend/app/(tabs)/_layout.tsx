import React, { useState } from 'react';
import { Tabs, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, View, Platform, Modal } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import ThreeDotMenu from '../../components/ThreeDotMenu';
import ProductCatalogModal from '../../components/ProductCatalogModal';
import BusinessKnowledgeModal from '../../components/BusinessKnowledgeModal';

import { useAuth } from '../../context/AuthContext';
import { settingsAPI } from '../../context/api';

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
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
      setNotificationEnabled(!newValue); // Revert on failure
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
                    label: 'Follow-up Analytics',
                    onPress: () => router.push('../analytics' as any),
                    color: '#25D366'
                  },
                  {
                    icon: 'cube-outline',
                    label: 'Product Catalog',
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
            title: 'Sales',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="cash" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="broadcast"
          options={{
            title: 'Broadcast',
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
