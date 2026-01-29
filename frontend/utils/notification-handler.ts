/**
 * Notification Handler
 * Manages push notifications using Expo Notifications
 */
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import { settingsAPI } from '../context/api';

// Configure how notifications are handled when app is in foreground
Notifications.setNotificationHandler({
    handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: true,
        shouldShowBanner: true,
        shouldShowList: true,
    }),
});

export class NotificationHandler {
    private static pushToken: string | null = null;

    /**
     * Register for push notifications and get token
     */
    static async registerForPushNotifications(): Promise<string | null> {
        if (!Device.isDevice) {
            console.log('Push notifications only work on physical devices');
            return null;
        }

        try {
            // Check existing permissions
            const { status: existingStatus } = await Notifications.getPermissionsAsync();
            let finalStatus = existingStatus;

            // Request permissions if not granted
            if (existingStatus !== 'granted') {
                const { status } = await Notifications.requestPermissionsAsync();
                finalStatus = status;
            }

            if (finalStatus !== 'granted') {
                console.log('Push notification permission not granted');
                return null;
            }

            // Get push token
            const tokenData = await Notifications.getExpoPushTokenAsync({
                projectId: 'your-project-id', // Replace with your Expo project ID
            });

            this.pushToken = tokenData.data;
            console.log('Push token:', this.pushToken);

            // Register token with backend
            await settingsAPI.registerPushToken(this.pushToken);

            // Configure notification channel for Android
            if (Platform.OS === 'android') {
                await Notifications.setNotificationChannelAsync('default', {
                    name: 'default',
                    importance: Notifications.AndroidImportance.MAX,
                    vibrationPattern: [0, 250, 250, 250],
                    lightColor: '#25D366',
                });
            }

            return this.pushToken;
        } catch (error) {
            console.error('Error registering for push notifications:', error);
            return null;
        }
    }

    /**
     * Add listener for notification received while app is in foreground
     */
    static addNotificationReceivedListener(
        callback: (notification: Notifications.Notification) => void
    ) {
        return Notifications.addNotificationReceivedListener(callback);
    }

    /**
     * Add listener for notification tapped/clicked
     */
    static addNotificationResponseListener(
        callback: (response: Notifications.NotificationResponse) => void
    ) {
        return Notifications.addNotificationResponseReceivedListener(callback);
    }

    /**
     * Schedule a local notification
     */
    static async scheduleLocalNotification(
        title: string,
        body: string,
        data?: any,
        trigger?: Notifications.NotificationTriggerInput
    ) {
        try {
            await Notifications.scheduleNotificationAsync({
                content: {
                    title,
                    body,
                    data,
                    sound: true,
                },
                trigger: trigger || null, // null means immediate
            });
        } catch (error) {
            console.error('Error scheduling notification:', error);
        }
    }

    /**
     * Cancel all scheduled notifications
     */
    static async cancelAllNotifications() {
        await Notifications.cancelAllScheduledNotificationsAsync();
    }

    /**
     * Get notification badge count
     */
    static async getBadgeCount(): Promise<number> {
        return await Notifications.getBadgeCountAsync();
    }

    /**
     * Set notification badge count
     */
    static async setBadgeCount(count: number) {
        await Notifications.setBadgeCountAsync(count);
    }

    /**
     * Clear badge
     */
    static async clearBadge() {
        await Notifications.setBadgeCountAsync(0);
    }
}
