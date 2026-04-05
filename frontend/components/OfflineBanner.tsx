import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { offlineQueue } from '../utils/offlineQueue';

export default function OfflineBanner() {
  const { isOffline } = useNetworkStatus();
  const [pendingCount, setPendingCount] = useState(0);
  const [showBackOnline, setShowBackOnline] = useState(false);
  const translateY = useRef(new Animated.Value(-60)).current;
  const wasOfflineRef = useRef(false);

  // Subscribe to queue count
  useEffect(() => {
    offlineQueue.count().then(setPendingCount);
    const unsub = offlineQueue.onCountChange(setPendingCount);
    return unsub;
  }, []);

  // Animate banner in/out and show "Back Online" flash
  useEffect(() => {
    if (isOffline) {
      wasOfflineRef.current = true;
      setShowBackOnline(false);
      Animated.spring(translateY, {
        toValue: 0,
        useNativeDriver: true,
        tension: 80,
        friction: 10,
      }).start();
    } else {
      if (wasOfflineRef.current) {
        // Was offline → now online: show "Back Online" briefly
        setShowBackOnline(true);
        wasOfflineRef.current = false;
        Animated.spring(translateY, {
          toValue: 0,
          useNativeDriver: true,
          tension: 80,
          friction: 10,
        }).start();
        // Hide after 3 seconds
        setTimeout(() => {
          Animated.timing(translateY, {
            toValue: -60,
            duration: 400,
            useNativeDriver: true,
          }).start(() => setShowBackOnline(false));
        }, 3000);
      } else {
        // Normal case: never was offline, keep hidden
        Animated.timing(translateY, {
          toValue: -60,
          duration: 300,
          useNativeDriver: true,
        }).start();
      }
    }
  }, [isOffline]);

  if (!isOffline && !showBackOnline) return null;

  return (
    <Animated.View
      style={[
        styles.banner,
        showBackOnline ? styles.bannerOnline : styles.bannerOffline,
        { transform: [{ translateY }] },
      ]}
    >
      <Ionicons
        name={showBackOnline ? 'wifi' : 'cloud-offline-outline'}
        size={16}
        color="#FFFFFF"
      />
      <View style={styles.textContainer}>
        <Text style={styles.title}>
          {showBackOnline ? 'Back Online' : 'No Internet Connection'}
        </Text>
        {!showBackOnline && (
          <Text style={styles.subtitle}>
            {pendingCount > 0
              ? `${pendingCount} action${pendingCount > 1 ? 's' : ''} queued — will sync when reconnected`
              : 'Showing cached data'}
          </Text>
        )}
        {showBackOnline && pendingCount === 0 && (
          <Text style={styles.subtitle}>All changes synced</Text>
        )}
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 10,
    zIndex: 9999,
  },
  bannerOffline: {
    backgroundColor: '#C0392B',
  },
  bannerOnline: {
    backgroundColor: '#25D366',
  },
  textContainer: {
    flex: 1,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },
  subtitle: {
    color: 'rgba(255,255,255,0.85)',
    fontSize: 11,
    marginTop: 1,
  },
});
