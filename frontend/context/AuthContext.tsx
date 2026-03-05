import React, { createContext, useContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiClient, whatsappAPI } from './api';

interface User {
  id: string;
  phone_number: string;
  business_name: string;
  owner_name?: string;
  subscription_active: boolean;
  subscription_plan?: string;
  role?: string;
  business_id?: string;
  team_members_count?: number;
}

interface WhatsAppStartResult {
  success: boolean;
  message?: string;
  sessionToken?: string;
  pairingCode?: string;
  pairingData?: any;
  isNewUser?: boolean;
  alreadyConnected?: boolean;
  token?: string;
}

interface WhatsAppCheckResult {
  success: boolean;
  connected: boolean;
  message?: string;
  isNewUser?: boolean;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  startWhatsAppAuth: (phone: string, countryCode?: string) => Promise<WhatsAppStartResult>;
  checkWhatsAppAuth: (sessionToken: string) => Promise<WhatsAppCheckResult>;
  refreshPairingCode: (sessionToken: string) => Promise<{ success: boolean; pairingCode?: string; pairingData?: any; message?: string }>;
  register: (businessName: string, ownerName?: string) => Promise<{ success: boolean; message?: string }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadStoredAuth();
  }, []);

  // Keep Render free-tier services alive (ping every 4 minutes)
  useEffect(() => {
    if (!token) return;
    const keepAlive = setInterval(async () => {
      try {
        await apiClient.get('/health', { timeout: 10000 });
      } catch (_) {}
    }, 4 * 60 * 1000);
    return () => clearInterval(keepAlive);
  }, [token]);

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
          // Trigger background profile picture refresh (fire-and-forget)
          whatsappAPI.refreshProfilePictures();
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

  const startWhatsAppAuth = async (phone: string, countryCode?: string): Promise<WhatsAppStartResult> => {
    try {
      const response = await apiClient.post('/auth/whatsapp-start', {
        phone_number: phone,
        country_code: countryCode,
      }, { timeout: 300000 });

      // If user already has WhatsApp connected, backend returns token directly
      if (response.data.status === 'success' && response.data.token) {
        const newToken = response.data.token;
        setToken(newToken);
        await AsyncStorage.setItem('auth_token', newToken);
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
        if (response.data.user) {
          setUser(response.data.user);
        }
        return {
          success: true,
          alreadyConnected: true,
          token: newToken,
          isNewUser: response.data.is_new_user,
        };
      }

      // Normal pairing flow
      return {
        success: true,
        sessionToken: response.data.session_token,
        pairingCode: response.data.pairing_code,
        pairingData: response.data.pairing_data,
        isNewUser: response.data.is_new_user,
      };
    } catch (error: any) {
      return {
        success: false,
        message: error.response?.data?.detail || 'Failed to start WhatsApp pairing',
      };
    }
  };

  const checkWhatsAppAuth = async (sessionToken: string): Promise<WhatsAppCheckResult> => {
    try {
      const response = await apiClient.post('/auth/whatsapp-check', {
        session_token: sessionToken,
      });

      if (response.data.connected && response.data.token) {
        const newToken = response.data.token;
        setToken(newToken);
        await AsyncStorage.setItem('auth_token', newToken);
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;

        if (response.data.user) {
          setUser(response.data.user);
        }

        return {
          success: true,
          connected: true,
          isNewUser: response.data.is_new_user,
        };
      }

      return { success: true, connected: false };
    } catch (error: any) {
      return {
        success: false,
        connected: false,
        message: error.response?.data?.detail || 'Connection check failed',
      };
    }
  };

  const refreshPairingCode = async (sessionToken: string) => {
    try {
      const response = await apiClient.post('/auth/whatsapp-refresh', {
        session_token: sessionToken,
      });
      return {
        success: true,
        pairingCode: response.data.pairing_code,
        pairingData: response.data.pairing_data,
      };
    } catch (error: any) {
      return {
        success: false,
        message: error.response?.data?.detail || 'Failed to refresh code',
        pairingData: null,
      };
    }
  };

  const register = async (businessName: string, ownerName?: string) => {
    try {
      const response = await apiClient.post('/auth/register', {
        phone_number: user?.phone_number || '',
        business_name: businessName,
        owner_name: ownerName,
      });

      if (response.data.user) {
        setUser(response.data.user);
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
        startWhatsAppAuth,
        checkWhatsAppAuth,
        refreshPairingCode,
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
