import React, { useState } from 'react';
import { Tabs, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, View, Platform, Modal, Text, TouchableOpacity } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import ThreeDotMenu from '../../components/ThreeDotMenu';
import ProductCatalogModal from '../../components/ProductCatalogModal';
import BusinessKnowledgeModal from '../../components/BusinessKnowledgeModal';
import { useAuth } from '../../context/AuthContext';
import SubscriptionModal from '../../components/SubscriptionModal';

import { settingsAPI } from '../../context/api';

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout, refreshUser } = useAuth();
  const [showProductCatalog, setShowProductCatalog] = useState(false);
  const [showBusinessKnowledge, setShowBusinessKnowledge] = useState(false);
  const [showSubModal, setShowSubModal] = useState(false);

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

  // If user is loaded and does not have dashboard access, block app access with a premium paywall screen
  const isExpired = user && user.dashboard_access === false;

  if (isExpired) {
    return (
      <View style={styles.paywallContainer}>
        <View style={styles.paywallCard}>
          <View style={styles.paywallIconContainer}>
            <Ionicons name="lock-closed" size={54} color="#25D366" />
          </View>
          <Text style={styles.paywallTitle}>Trial Expired</Text>
          <Text style={styles.paywallDescription}>
            Your free trial has ended. To continue managing your customers, tracking your sales, and sending AI automated replies, please choose a plan.
          </Text>
          
          <TouchableOpacity style={styles.paywallButton} onPress={() => setShowSubModal(true)}>
            <Text style={styles.paywallButtonText}>Unlock Zilo CRM</Text>
          </TouchableOpacity>
          
          <TouchableOpacity style={styles.paywallLogout} onPress={() => logout()}>
            <Text style={styles.paywallLogoutText}>Log Out</Text>
          </TouchableOpacity>
        </View>

        <SubscriptionModal
          visible={showSubModal}
          onClose={() => setShowSubModal(false)}
          onSuccess={() => {
            setShowSubModal(false);
            refreshUser();
          }}
          currentPlan={user?.subscription_plan}
        />
      </View>
    );
  }

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
              <Ionicons name="receipt" size={size} color={color} />
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
  paywallContainer: {
    flex: 1,
    backgroundColor: '#0A1628',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  paywallCard: {
    backgroundColor: '#111F35',
    borderRadius: 24,
    padding: 32,
    alignItems: 'center',
    width: '100%',
    borderWidth: 1.5,
    borderColor: '#1E3452',
  },
  paywallIconContainer: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: 'rgba(37, 211, 102, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  paywallTitle: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 12,
    textAlign: 'center',
  },
  paywallDescription: {
    fontSize: 15,
    color: '#8A9BB5',
    lineHeight: 22,
    textAlign: 'center',
    marginBottom: 32,
    paddingHorizontal: 10,
  },
  paywallButton: {
    backgroundColor: '#25D366',
    borderRadius: 14,
    paddingVertical: 16,
    paddingHorizontal: 32,
    width: '100%',
    alignItems: 'center',
    shadowColor: '#25D366',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
    marginBottom: 16,
  },
  paywallButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'bold',
  },
  paywallLogout: {
    paddingVertical: 10,
  },
  paywallLogoutText: {
    color: '#FF4444',
    fontSize: 15,
    fontWeight: '600',
  },
});
