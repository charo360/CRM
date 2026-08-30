import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getAuth, signInWithPhoneNumber, type ConfirmationResult } from '@react-native-firebase/auth';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { apiClient } from './api';

interface User {
  id: string;
  phone_number: string;
  business_name: string;
  owner_name?: string;
  subscription_active: boolean;
  subscription_plan?: string;
  dashboard_access?: boolean;
  role?: string;
  team_members_count?: number;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  sendOTP: (phone: string) => Promise<{ success: boolean; message?: string }>;
  verifyOTP: (code: string) => Promise<{ success: boolean; message?: string; isNewUser?: boolean }>;
  register: (phone: string, businessName: string, ownerName?: string) => Promise<{ success: boolean; message?: string }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);
const AUTH_TOKEN_KEY = 'auth_token';
const AUTH_USER_KEY = 'auth_user';

const isInvalidSessionError = (error: any) => {
  const status = error?.response?.status;
  const accountDeleted = error?.response?.headers?.['x-account-deleted'] === 'true';
  return status === 401 || accountDeleted;
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const confirmationRef = useRef<ConfirmationResult | null>(null);
  // A confirmed SMS code is single-use, so the Firebase token it produced is
  // held here until the Zilo exchange succeeds. Without it, a failed exchange
  // would strand the sign-in: the code is already spent, but the session is not
  // yet established, and every retry would need a fresh SMS.
  const verifiedTokenRef = useRef<string | null>(null);

  useEffect(() => {
    loadStoredAuth();
  }, []);

  const storeUser = async (nextUser: User) => {
    setUser(nextUser);
    await AsyncStorage.setItem(AUTH_USER_KEY, JSON.stringify(nextUser));
  };

  const clearStoredAuth = async () => {
    setUser(null);
    setToken(null);
    await AsyncStorage.multiRemove([AUTH_TOKEN_KEY, AUTH_USER_KEY]);
    delete apiClient.defaults.headers.common['Authorization'];
  };

  useEffect(() => {
    const initRevenueCat = async () => {
      const isExpoGo = Constants.appOwnership === 'expo';
      if (isExpoGo) {
        console.log('[RevenueCat] Skipping configuration in Expo Go');
        return;
      }
      if (Platform.OS !== 'android') return;

      try {
        const Purchases = require('react-native-purchases').default;
        
        if (__DEV__) {
          await Purchases.setLogLevel(Purchases.LOG_LEVEL.DEBUG);
        }

        const apiKey = "goog_QgGKlpHwtYdpJXDHLTdCuGHqkmC";
        await Purchases.configure({ apiKey });

        if (user && user.id) {
          const loginResult = await Purchases.logIn(user.id);
          console.log('[RevenueCat] User identified:', user.id, loginResult);
        } else {
          await Purchases.logOut();
          console.log('[RevenueCat] User logged out');
        }
      } catch (err) {
        console.warn('[RevenueCat] Failed to initialize:', err);
      }
    };

    initRevenueCat();
  }, [user]);

  const loadStoredAuth = async () => {
    try {
      const [[, storedToken], [, storedUser]] = await AsyncStorage.multiGet([
        AUTH_TOKEN_KEY,
        AUTH_USER_KEY,
      ]);

      if (storedToken) {
        setToken(storedToken);
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;

        // A cached profile means a brief network failure cannot make the user
        // appear signed out at app launch.
        if (storedUser) {
          try {
            setUser(JSON.parse(storedUser) as User);
          } catch {
            await AsyncStorage.removeItem(AUTH_USER_KEY);
          }
        }

        try {
          const response = await apiClient.get('/auth/me');
          await storeUser(response.data);
        } catch (error: any) {
          // Only a confirmed invalid session should require another SMS sign-in.
          // Render deployments, timeouts, and short connectivity issues are
          // temporary and must preserve the saved session.
          if (isInvalidSessionError(error)) {
            await clearStoredAuth();
          } else {
            console.warn('[Auth] Keeping saved session after a temporary /auth/me failure');
          }
        }
      } else if (storedUser) {
        // A profile without its matching token cannot be authenticated.
        await AsyncStorage.removeItem(AUTH_USER_KEY);
      }
    } catch (error) {
      console.error('Error loading auth:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const sendOTP = async (phone: string) => {
    try {
      confirmationRef.current = await signInWithPhoneNumber(getAuth(), phone);
      verifiedTokenRef.current = null;
      return { success: true };
    } catch (error: any) {
      const errorMessage = error?.message || 'Failed to send verification code';
      console.warn('[FirebaseAuth] SMS sign-in failed:', error);
      return {
        success: false,
        message: errorMessage,
      };
    }
  };

  const verifyOTP = async (code: string) => {
    try {
      if (!confirmationRef.current && !verifiedTokenRef.current) {
        return {
          success: false,
          message: 'Your verification session expired. Please request a new code.',
        };
      }

      // Only spend the code when it has not been confirmed yet. A retry after a
      // failed exchange reuses the token from the first confirmation, so a slow
      // backend no longer costs the user another SMS.
      if (!verifiedTokenRef.current) {
        const credential = await confirmationRef.current!.confirm(code);
        verifiedTokenRef.current = await credential.user.getIdToken();
      }

      const response = await apiClient.post('/auth/firebase', {
        id_token: verifiedTokenRef.current,
      });

      const { token: newToken, is_new_user, user: userData } = response.data;

      setToken(newToken);
      await AsyncStorage.setItem(AUTH_TOKEN_KEY, newToken);
      apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;

      if (!is_new_user && userData) {
        await storeUser(userData);
      }

      // Cleared only once the session is actually established.
      confirmationRef.current = null;
      verifiedTokenRef.current = null;

      return {
        success: true,
        isNewUser: is_new_user,
      };
    } catch (error: any) {
      console.warn('[FirebaseAuth] Code verification failed:', error);
      const detail = error.response?.data?.detail;
      if (detail) {
        return { success: false, message: detail };
      }
      // The code itself was accepted if it produced a token, so a failure past
      // that point is the exchange, not the code — say so, and let them retry.
      return {
        success: false,
        message: verifiedTokenRef.current
          ? 'Could not reach Zilo to finish signing in. Tap Verify again.'
          : 'Verification failed',
      };
    }
  };

  const register = async (phone: string, businessName: string, ownerName?: string) => {
    try {
      const response = await apiClient.post('/auth/register', {
        phone_number: phone,
        business_name: businessName,
        owner_name: ownerName,
      });

      const { token: newToken, user: userData } = response.data;

      // Registration completes the profile for the authenticated user.  The
      // backend intentionally keeps the session that was issued after phone
      // verification, so it does not always return a replacement token here.
      if (newToken) {
        setToken(newToken);
        await AsyncStorage.setItem(AUTH_TOKEN_KEY, newToken);
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
      }
      if (userData) {
        await storeUser(userData);
      }

      return { success: true };
    } catch (error: any) {
      return {
        success: false,
        message: error.response?.data?.detail || 'Registration failed',
      };
    }
  };

  const logout = async () => {
    await clearStoredAuth();
  };

  const refreshUser = async () => {
    try {
      const response = await apiClient.get('/auth/me');
      await storeUser(response.data);
    } catch (error) {
      console.error('Error refreshing user:', error);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        sendOTP,
        verifyOTP,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
