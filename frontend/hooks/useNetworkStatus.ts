import { useState, useEffect } from 'react';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';

export interface NetworkStatus {
  isConnected: boolean;
  isInternetReachable: boolean | null;
  connectionType: string | null;
}

let _listeners: ((status: NetworkStatus) => void)[] = [];
let _currentStatus: NetworkStatus = {
  isConnected: true,
  isInternetReachable: true,
  connectionType: null,
};

let _subscription: (() => void) | null = null;

function ensureSubscription() {
  if (_subscription) return;
  _subscription = NetInfo.addEventListener((state: NetInfoState) => {
    _currentStatus = {
      isConnected: state.isConnected ?? false,
      isInternetReachable: state.isInternetReachable,
      connectionType: state.type,
    };
    _listeners.forEach((cb) => cb({ ..._currentStatus }));
  });
}

export function useNetworkStatus(): NetworkStatus & { isOffline: boolean } {
  const [status, setStatus] = useState<NetworkStatus>(_currentStatus);

  useEffect(() => {
    ensureSubscription();

    NetInfo.fetch().then((state: NetInfoState) => {
      const s: NetworkStatus = {
        isConnected: state.isConnected ?? false,
        isInternetReachable: state.isInternetReachable,
        connectionType: state.type,
      };
      _currentStatus = s;
      setStatus(s);
    });

    const handler = (s: NetworkStatus) => setStatus({ ...s });
    _listeners.push(handler);
    return () => {
      _listeners = _listeners.filter((l) => l !== handler);
    };
  }, []);

  return {
    ...status,
    isOffline: !status.isConnected || status.isInternetReachable === false,
  };
}

// Non-hook helper for use inside utilities (api.ts, queue, etc.)
export function getIsOffline(): boolean {
  return !_currentStatus.isConnected || _currentStatus.isInternetReachable === false;
}

// Subscribe to network changes outside React (used by offlineQueue)
export function onNetworkChange(cb: (isOffline: boolean) => void): () => void {
  ensureSubscription();
  const handler = (s: NetworkStatus) =>
    cb(!s.isConnected || s.isInternetReachable === false);
  _listeners.push(handler);
  return () => {
    _listeners = _listeners.filter((l) => l !== handler);
  };
}
