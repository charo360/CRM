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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const confirmationRef = useRef<ConfirmationResult | null>(null);

  useEffect(() => {
    loadStoredAuth();
  }, []);

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
      const storedToken = await AsyncStorage.getItem('auth_token');
      if (storedToken) {
        setToken(storedToken);
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;

        // Fetch current user
        try {
          const response = await apiClient.get('/auth/me');
          setUser(response.data);
        } catch (error) {
          // Token invalid, clear it
          await AsyncStorage.removeItem('auth_token');
          setToken(null);
          delete apiClient.defaults.headers.common['Authorization'];
        }
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
      if (!confirmationRef.current) {
        return {
          success: false,
          message: 'Your verification session expired. Please request a new code.',
        };
      }

      const credential = await confirmationRef.current.confirm(code);
      const idToken = await credential.user.getIdToken();
      confirmationRef.current = null;

      const response = await apiClient.post('/auth/firebase', { id_token: idToken });

      const { token: newToken, is_new_user, user: userData } = response.data;

      setToken(newToken);
      await AsyncStorage.setItem('auth_token', newToken);
      apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;

      if (!is_new_user && userData) {
        setUser(userData);
      }

      return {
        success: true,
        isNewUser: is_new_user,
      };
    } catch (error: any) {
      console.warn('[FirebaseAuth] Code verification failed:', error);
      return {
        success: false,
        message: error.response?.data?.detail || 'Verification failed',
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
        await AsyncStorage.setItem('auth_token', newToken);
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
      }
      if (userData) {
        setUser(userData);
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
    setUser(null);
    setToken(null);
    await AsyncStorage.removeItem('auth_token');
    delete apiClient.defaults.headers.common['Authorization'];
  };

  const refreshUser = async () => {
    try {
      const response = await apiClient.get('/auth/me');
      setUser(response.data);
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
