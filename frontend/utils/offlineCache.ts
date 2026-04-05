import AsyncStorage from '@react-native-async-storage/async-storage';

const CACHE_PREFIX = 'offline_cache:';
const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

// Cache keys for each major data type
export const CACHE_KEYS = {
  CUSTOMERS: 'customers',
  CUSTOMERS_RECENT: 'customers_recent',
  PRODUCTS: 'products',
  DASHBOARD: 'dashboard',
  BOOKINGS: 'bookings',
  ORDERS: 'orders',
  SALES: 'sales',
  EXPENSES: 'expenses',
  SETTINGS: 'settings',
  BUSINESS_KNOWLEDGE: 'business_knowledge',
  CONTACTS: 'contacts',
} as const;

export type CacheKey = typeof CACHE_KEYS[keyof typeof CACHE_KEYS];

export const offlineCache = {
  async set<T>(key: string, data: T, ttlMs = DEFAULT_TTL_MS): Promise<void> {
    try {
      const entry: CacheEntry<T> = {
        data,
        timestamp: Date.now(),
        ttl: ttlMs,
      };
      await AsyncStorage.setItem(CACHE_PREFIX + key, JSON.stringify(entry));
    } catch (err) {
      console.warn('[OfflineCache] Failed to write cache:', key, err);
    }
  },

  async get<T>(key: string): Promise<T | null> {
    try {
      const raw = await AsyncStorage.getItem(CACHE_PREFIX + key);
      if (!raw) return null;

      const entry: CacheEntry<T> = JSON.parse(raw);
      const age = Date.now() - entry.timestamp;

      if (age > entry.ttl) {
        await AsyncStorage.removeItem(CACHE_PREFIX + key);
        return null;
      }

      return entry.data;
    } catch (err) {
      console.warn('[OfflineCache] Failed to read cache:', key, err);
      return null;
    }
  },

  // Get stale data even if TTL expired (used when offline — stale > nothing)
  async getStale<T>(key: string): Promise<T | null> {
    try {
      const raw = await AsyncStorage.getItem(CACHE_PREFIX + key);
      if (!raw) return null;
      const entry: CacheEntry<T> = JSON.parse(raw);
      return entry.data;
    } catch (err) {
      console.warn('[OfflineCache] Failed to read stale cache:', key, err);
      return null;
    }
  },

  async remove(key: string): Promise<void> {
    try {
      await AsyncStorage.removeItem(CACHE_PREFIX + key);
    } catch (err) {
      console.warn('[OfflineCache] Failed to remove cache:', key, err);
    }
  },

  async clear(): Promise<void> {
    try {
      const keys = await AsyncStorage.getAllKeys();
      const cacheKeys = keys.filter((k) => k.startsWith(CACHE_PREFIX));
      if (cacheKeys.length > 0) {
        await AsyncStorage.multiRemove(cacheKeys);
      }
    } catch (err) {
      console.warn('[OfflineCache] Failed to clear cache:', err);
    }
  },

  // Get cache age in minutes (useful for showing "last updated X min ago")
  async getAgeMinutes(key: string): Promise<number | null> {
    try {
      const raw = await AsyncStorage.getItem(CACHE_PREFIX + key);
      if (!raw) return null;
      const entry: CacheEntry<unknown> = JSON.parse(raw);
      return Math.floor((Date.now() - entry.timestamp) / 60000);
    } catch {
      return null;
    }
  },
};
