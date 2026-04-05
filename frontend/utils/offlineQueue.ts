import AsyncStorage from '@react-native-async-storage/async-storage';
import { onNetworkChange } from '../hooks/useNetworkStatus';

const QUEUE_KEY = 'offline_mutation_queue';

export interface QueuedMutation {
  id: string;
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  url: string;
  data?: any;
  headers?: Record<string, string>;
  timestamp: number;
  retries: number;
  description: string; // human-readable e.g. "Create customer John"
}

type SyncHandler = (mutation: QueuedMutation) => Promise<void>;
let _syncHandler: SyncHandler | null = null;
let _isSyncing = false;
let _pendingCallbacks: ((count: number) => void)[] = [];

export const offlineQueue = {
  // Register the function that will re-execute each queued mutation
  registerSyncHandler(handler: SyncHandler) {
    _syncHandler = handler;
  },

  async enqueue(mutation: Omit<QueuedMutation, 'id' | 'timestamp' | 'retries'>): Promise<void> {
    try {
      const queue = await offlineQueue.getAll();
      const entry: QueuedMutation = {
        ...mutation,
        id: `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        timestamp: Date.now(),
        retries: 0,
      };
      queue.push(entry);
      await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
      _notifyCount(queue.length);
      console.log(`[OfflineQueue] Queued: ${mutation.description}`);
    } catch (err) {
      console.warn('[OfflineQueue] Failed to enqueue:', err);
    }
  },

  async getAll(): Promise<QueuedMutation[]> {
    try {
      const raw = await AsyncStorage.getItem(QUEUE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  },

  async remove(id: string): Promise<void> {
    try {
      const queue = await offlineQueue.getAll();
      const updated = queue.filter((m) => m.id !== id);
      await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(updated));
      _notifyCount(updated.length);
    } catch (err) {
      console.warn('[OfflineQueue] Failed to remove item:', err);
    }
  },

  async clear(): Promise<void> {
    try {
      await AsyncStorage.removeItem(QUEUE_KEY);
      _notifyCount(0);
    } catch (err) {
      console.warn('[OfflineQueue] Failed to clear queue:', err);
    }
  },

  async count(): Promise<number> {
    const queue = await offlineQueue.getAll();
    return queue.length;
  },

  // Process all queued mutations now
  async syncNow(): Promise<{ succeeded: number; failed: number }> {
    if (_isSyncing || !_syncHandler) return { succeeded: 0, failed: 0 };
    _isSyncing = true;

    let succeeded = 0;
    let failed = 0;

    try {
      const queue = await offlineQueue.getAll();
      if (queue.length === 0) return { succeeded: 0, failed: 0 };

      console.log(`[OfflineQueue] Syncing ${queue.length} queued mutations...`);

      for (const mutation of queue) {
        try {
          await _syncHandler(mutation);
          await offlineQueue.remove(mutation.id);
          succeeded++;
          console.log(`[OfflineQueue] ✅ Synced: ${mutation.description}`);
        } catch (err) {
          mutation.retries = (mutation.retries || 0) + 1;
          if (mutation.retries >= 3) {
            // Give up after 3 retries
            await offlineQueue.remove(mutation.id);
            failed++;
            console.warn(`[OfflineQueue] ❌ Gave up after 3 retries: ${mutation.description}`);
          } else {
            // Update retry count in storage
            const all = await offlineQueue.getAll();
            const idx = all.findIndex((m) => m.id === mutation.id);
            if (idx >= 0) {
              all[idx].retries = mutation.retries;
              await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(all));
            }
            failed++;
            console.warn(`[OfflineQueue] ⚠️ Retry ${mutation.retries}/3: ${mutation.description}`);
          }
        }
      }
    } finally {
      _isSyncing = false;
    }

    return { succeeded, failed };
  },

  // Subscribe to queue count changes (used by OfflineBanner)
  onCountChange(cb: (count: number) => void): () => void {
    _pendingCallbacks.push(cb);
    return () => {
      _pendingCallbacks = _pendingCallbacks.filter((l) => l !== cb);
    };
  },
};

function _notifyCount(count: number) {
  _pendingCallbacks.forEach((cb) => cb(count));
}

// Auto-sync when coming back online
onNetworkChange((isOffline) => {
  if (!isOffline) {
    // Small delay to let the connection stabilize
    setTimeout(() => {
      offlineQueue.syncNow().then(({ succeeded, failed }) => {
        if (succeeded > 0 || failed > 0) {
          console.log(`[OfflineQueue] Auto-sync complete: ${succeeded} OK, ${failed} failed`);
        }
      });
    }, 2000);
  }
});
