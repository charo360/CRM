import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import {
  paystackAPI,
  type PaystackConnection,
  type PaystackPayoutOption,
  type PaystackPayoutType,
} from '../context/api';

interface PaymentSetupModalProps {
  visible: boolean;
  businessName?: string;
  onClose: () => void;
  onConnectionChanged?: () => void;
}

const errorMessage = (error: any, fallback: string) =>
  error?.response?.data?.detail || error?.message || fallback;

export default function PaymentSetupModal({
  visible,
  businessName = '',
  onClose,
  onConnectionChanged,
}: PaymentSetupModalProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [connection, setConnection] = useState<PaystackConnection | null>(null);
  const [platformAvailable, setPlatformAvailable] = useState(false);
  const [payoutType, setPayoutType] = useState<PaystackPayoutType>('mobile_money');
  const [payoutOptions, setPayoutOptions] = useState<PaystackPayoutOption[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [showPayoutPicker, setShowPayoutPicker] = useState(false);
  const [providerSearch, setProviderSearch] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<PaystackPayoutOption | null>(null);
  const [payoutAccount, setPayoutAccount] = useState('');
  const [merchantName, setMerchantName] = useState(businessName);
  const [loadError, setLoadError] = useState('');

  const loadOptions = useCallback(async (type: PaystackPayoutType) => {
    setLoadingOptions(true);
    setShowPayoutPicker(false);
    setSelectedProvider(null);
    setProviderSearch('');
    try {
      const result = await paystackAPI.getPayoutOptions(type);
      setPayoutOptions(result.options || []);
      if (!result.supported && result.hint) setLoadError(result.hint);
    } catch (error: any) {
      setPayoutOptions([]);
      setLoadError(errorMessage(error, 'Could not load payout providers. Please try again.'));
    } finally {
      setLoadingOptions(false);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const [setup, currentConnection] = await Promise.all([
        paystackAPI.getSetup(),
        paystackAPI.getConnection(),
      ]);
      setPlatformAvailable(Boolean(setup.platform_available));
      setConnection(currentConnection);
      setMerchantName((current) => current || currentConnection.subaccount_name || businessName);
      if (setup.platform_available && !currentConnection.connected) {
        await loadOptions(payoutType);
      }
    } catch (error: any) {
      setLoadError(errorMessage(error, 'Could not load payment setup. Please try again.'));
    } finally {
      setLoading(false);
    }
  }, [businessName, loadOptions, payoutType]);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  const filteredOptions = useMemo(() => {
    const search = providerSearch.trim().toLowerCase();
    return search
      ? payoutOptions.filter((option) => option.name.toLowerCase().includes(search))
      : payoutOptions;
  }, [payoutOptions, providerSearch]);

  const handlePayoutTypeChange = async (nextType: PaystackPayoutType) => {
    if (nextType === payoutType) return;
    setPayoutType(nextType);
    setLoadError('');
    await loadOptions(nextType);
  };

  const handleConnect = async () => {
    if (!merchantName.trim()) {
      Alert.alert('Business name required', 'Enter the name your customers know your business by.');
      return;
    }
    if (!selectedProvider) {
      Alert.alert('Choose where to receive money', 'Select your bank or mobile-money provider first.');
      return;
    }
    if (payoutAccount.trim().length < 5) {
      Alert.alert(
        payoutType === 'mobile_money' ? 'M-Pesa number required' : 'Account number required',
        payoutType === 'mobile_money'
          ? 'Enter the mobile-money number that should receive settlements.'
          : 'Enter the bank account number that should receive settlements.',
      );
      return;
    }

    setSaving(true);
    try {
      await paystackAPI.connectKenya({
        business_name: merchantName.trim(),
        payout_type: payoutType,
        settlement_bank: selectedProvider.code,
        account_number: payoutAccount.trim().replace(/\s/g, ''),
      });
      const updated = await paystackAPI.getConnection();
      setConnection(updated);
      onConnectionChanged?.();
      Alert.alert(
        'Payments ready',
        'Customers can now pay securely from your shared catalog. Paid orders will appear in Sales.',
      );
    } catch (error: any) {
      Alert.alert('Could not set up payments', errorMessage(error, 'Please check your payout details and try again.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDisconnect = () => {
    Alert.alert(
      'Disconnect online payments?',
      'Customers will no longer be able to pay online from your catalog until you set up a payout account again.',
      [
        { text: 'Keep connected', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: async () => {
            setSaving(true);
            try {
              await paystackAPI.disconnect();
              setConnection(null);
              setPayoutAccount('');
              setSelectedProvider(null);
              await loadOptions(payoutType);
              onConnectionChanged?.();
            } catch (error: any) {
              Alert.alert('Could not disconnect', errorMessage(error, 'Please try again.'));
            } finally {
              setSaving(false);
            }
          },
        },
      ],
    );
  };

  const connectedDestination = connection?.payout_type === 'mobile_money' ? 'M-Pesa' : 'bank account';
  const selectedLabel = selectedProvider?.name || `Choose ${payoutType === 'mobile_money' ? 'mobile-money provider' : 'bank'}`;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} accessibilityLabel="Close payment setup">
            <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Receive payments</Text>
          <View style={styles.headerSpacer} />
        </View>

        {loading ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator size="large" color="#25D366" />
            <Text style={styles.mutedText}>Loading payment setup…</Text>
          </View>
        ) : (
          <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
            {!platformAvailable ? (
              <View style={styles.noticeCard}>
                <Ionicons name="time-outline" size={28} color="#FBBF24" />
                <View style={styles.noticeCopy}>
                  <Text style={styles.noticeTitle}>Payments are being activated</Text>
                  <Text style={styles.noticeText}>
                    Zilo Paystack for Kenya is not live on this server yet. Please try again shortly.
                  </Text>
                </View>
              </View>
            ) : connection?.connected ? (
              <>
                <View style={styles.connectedCard}>
                  <View style={styles.connectedIcon}>
                    <Ionicons name="checkmark" size={24} color="#FFFFFF" />
                  </View>
                  <View style={styles.connectedCopy}>
                    <Text style={styles.connectedTitle}>Online payments are on</Text>
                    <Text style={styles.connectedText}>
                      Customers can pay from your shared catalog.
                    </Text>
                  </View>
                </View>

                <View style={styles.detailCard}>
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>Business</Text>
                    <Text style={styles.detailValue}>{connection.subaccount_name || connection.business_name || 'Your business'}</Text>
                  </View>
                  <View style={styles.divider} />
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>Payout destination</Text>
                    <Text style={styles.detailValue}>{connectedDestination}</Text>
                  </View>
                  <View style={styles.divider} />
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>Currency</Text>
                    <Text style={styles.detailValue}>{connection.default_currency || 'KES'}</Text>
                  </View>
                </View>

                <View style={styles.infoCard}>
                  <Ionicons name="receipt-outline" size={21} color="#8B9DC3" />
                  <Text style={styles.infoText}>
                    When a customer pays, the order is marked paid automatically in Sales. Funds settle to your chosen {connectedDestination} through Paystack.
                  </Text>
                </View>

                <TouchableOpacity style={styles.disconnectButton} onPress={handleDisconnect} disabled={saving}>
                  {saving ? <ActivityIndicator color="#F87171" /> : <Text style={styles.disconnectText}>Disconnect payment setup</Text>}
                </TouchableOpacity>
              </>
            ) : (
              <>
                <View style={styles.heroCard}>
                  <View style={styles.heroIcon}>
                    <Ionicons name="wallet-outline" size={27} color="#25D366" />
                  </View>
                  <View style={styles.heroCopy}>
                    <Text style={styles.heroTitle}>Get paid from your catalog</Text>
                    <Text style={styles.heroText}>
                      Set up where you receive customer payments. You do not need a Paystack account or website.
                    </Text>
                  </View>
                </View>

                {loadError ? <Text style={styles.errorText}>{loadError}</Text> : null}

                <Text style={styles.label}>Business name</Text>
                <TextInput
                  value={merchantName}
                  onChangeText={setMerchantName}
                  style={styles.input}
                  placeholder="Your business name"
                  placeholderTextColor="#66758D"
                  autoCapitalize="words"
                  editable={!saving}
                />

                <Text style={styles.label}>Where should you receive money?</Text>
                <View style={styles.typeRow}>
                  <TouchableOpacity
                    style={[styles.typeButton, payoutType === 'mobile_money' && styles.typeButtonSelected]}
                    onPress={() => handlePayoutTypeChange('mobile_money')}
                    disabled={saving}
                  >
                    <Ionicons name="phone-portrait-outline" size={19} color={payoutType === 'mobile_money' ? '#FFFFFF' : '#8B9DC3'} />
                    <Text style={[styles.typeText, payoutType === 'mobile_money' && styles.typeTextSelected]}>M-Pesa</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.typeButton, payoutType === 'bank' && styles.typeButtonSelected]}
                    onPress={() => handlePayoutTypeChange('bank')}
                    disabled={saving}
                  >
                    <Ionicons name="business-outline" size={19} color={payoutType === 'bank' ? '#FFFFFF' : '#8B9DC3'} />
                    <Text style={[styles.typeText, payoutType === 'bank' && styles.typeTextSelected]}>Bank</Text>
                  </TouchableOpacity>
                </View>

                <Text style={styles.label}>{payoutType === 'mobile_money' ? 'Mobile-money provider' : 'Bank'}</Text>
                <TouchableOpacity
                  style={styles.selector}
                  onPress={() => setShowPayoutPicker((current) => !current)}
                  disabled={saving || loadingOptions || payoutOptions.length === 0}
                >
                  <Text style={[styles.selectorText, !selectedProvider && styles.placeholderText]} numberOfLines={1}>{selectedLabel}</Text>
                  {loadingOptions ? <ActivityIndicator size="small" color="#25D366" /> : <Ionicons name="chevron-down" size={20} color="#8B9DC3" />}
                </TouchableOpacity>

                {showPayoutPicker ? (
                  <View style={styles.optionPanel}>
                    <TextInput
                      value={providerSearch}
                      onChangeText={setProviderSearch}
                      style={styles.searchInput}
                      placeholder="Search"
                      placeholderTextColor="#66758D"
                    />
                    <ScrollView style={styles.optionList} nestedScrollEnabled keyboardShouldPersistTaps="handled">
                      {filteredOptions.slice(0, 50).map((option) => (
                        <TouchableOpacity
                          key={option.code}
                          style={styles.optionRow}
                          onPress={() => {
                            setSelectedProvider(option);
                            setShowPayoutPicker(false);
                            setProviderSearch('');
                          }}
                        >
                          <Text style={styles.optionText}>{option.name}</Text>
                          {selectedProvider?.code === option.code ? <Ionicons name="checkmark" size={18} color="#25D366" /> : null}
                        </TouchableOpacity>
                      ))}
                      {!filteredOptions.length ? <Text style={styles.noOptions}>No providers found</Text> : null}
                    </ScrollView>
                  </View>
                ) : null}

                <Text style={styles.label}>{payoutType === 'mobile_money' ? 'M-Pesa number' : 'Account number'}</Text>
                <TextInput
                  value={payoutAccount}
                  onChangeText={setPayoutAccount}
                  style={styles.input}
                  placeholder={payoutType === 'mobile_money' ? 'e.g. 254712345678' : 'Enter account number'}
                  placeholderTextColor="#66758D"
                  keyboardType="phone-pad"
                  editable={!saving}
                />
                <Text style={styles.helperText}>
                  {payoutType === 'mobile_money'
                    ? 'Use the number where you want customer payments settled.'
                    : 'Use the bank account where you want customer payments settled.'}
                </Text>

                <View style={styles.infoCard}>
                  <Ionicons name="shield-checkmark-outline" size={21} color="#25D366" />
                  <Text style={styles.infoText}>
                    Your payout details are used only to set up your Zilo payment destination. Customers pay securely through Paystack.
                  </Text>
                </View>

                <TouchableOpacity style={[styles.primaryButton, saving && styles.primaryButtonDisabled]} onPress={handleConnect} disabled={saving || !platformAvailable}>
                  {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryButtonText}>Set up payments</Text>}
                </TouchableOpacity>
              </>
            )}
          </ScrollView>
        )}
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A1628' },
  header: { height: 58, paddingHorizontal: 20, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#1A2942' },
  headerTitle: { flex: 1, textAlign: 'center', color: '#FFFFFF', fontSize: 18, fontWeight: '700' },
  headerSpacer: { width: 24 },
  content: { padding: 20, paddingBottom: 42 },
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  mutedText: { color: '#8B9DC3', marginTop: 12 },
  heroCard: { flexDirection: 'row', borderRadius: 16, padding: 16, backgroundColor: '#112B24', borderWidth: 1, borderColor: '#1D5A43', marginBottom: 22 },
  heroIcon: { width: 46, height: 46, borderRadius: 23, backgroundColor: '#0A3B2B', alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  heroCopy: { flex: 1 },
  heroTitle: { color: '#FFFFFF', fontSize: 16, fontWeight: '700', marginBottom: 4 },
  heroText: { color: '#B8C5D8', fontSize: 13, lineHeight: 19 },
  label: { color: '#D8E2F0', fontSize: 13, fontWeight: '600', marginBottom: 8, marginTop: 16 },
  input: { backgroundColor: '#101F35', borderWidth: 1, borderColor: '#233754', color: '#FFFFFF', borderRadius: 11, paddingHorizontal: 14, paddingVertical: 13, fontSize: 15 },
  typeRow: { flexDirection: 'row', gap: 10 },
  typeButton: { flex: 1, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 7, borderRadius: 11, paddingVertical: 13, backgroundColor: '#101F35', borderWidth: 1, borderColor: '#233754' },
  typeButtonSelected: { backgroundColor: '#168A4B', borderColor: '#25D366' },
  typeText: { color: '#B8C5D8', fontWeight: '700' },
  typeTextSelected: { color: '#FFFFFF' },
  selector: { minHeight: 50, paddingHorizontal: 14, borderRadius: 11, backgroundColor: '#101F35', borderWidth: 1, borderColor: '#233754', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  selectorText: { color: '#FFFFFF', flex: 1, paddingRight: 10, fontSize: 15 },
  placeholderText: { color: '#66758D' },
  optionPanel: { backgroundColor: '#101F35', borderWidth: 1, borderColor: '#2C4568', borderRadius: 11, marginTop: 7, overflow: 'hidden' },
  searchInput: { color: '#FFFFFF', margin: 10, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 8, backgroundColor: '#0A1628' },
  optionList: { maxHeight: 220 },
  optionRow: { minHeight: 46, paddingHorizontal: 14, borderTopWidth: 1, borderTopColor: '#1A2942', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  optionText: { color: '#E7EEF9', fontSize: 14, flex: 1, paddingRight: 8 },
  noOptions: { color: '#8B9DC3', textAlign: 'center', padding: 18 },
  helperText: { color: '#8B9DC3', fontSize: 12, marginTop: 7, lineHeight: 17 },
  infoCard: { backgroundColor: '#10233D', borderRadius: 12, padding: 13, marginTop: 20, flexDirection: 'row', gap: 10 },
  infoText: { color: '#B8C5D8', fontSize: 12, lineHeight: 18, flex: 1 },
  primaryButton: { marginTop: 22, borderRadius: 12, paddingVertical: 15, backgroundColor: '#25D366', alignItems: 'center' },
  primaryButtonDisabled: { opacity: 0.65 },
  primaryButtonText: { color: '#062414', fontWeight: '800', fontSize: 16 },
  noticeCard: { flexDirection: 'row', backgroundColor: '#332A12', borderWidth: 1, borderColor: '#725D1C', borderRadius: 14, padding: 16 },
  noticeCopy: { flex: 1, marginLeft: 12 },
  noticeTitle: { color: '#FDE68A', fontSize: 16, fontWeight: '700', marginBottom: 4 },
  noticeText: { color: '#EFDFA5', fontSize: 13, lineHeight: 19 },
  connectedCard: { flexDirection: 'row', backgroundColor: '#112B24', borderRadius: 15, padding: 16, marginBottom: 16 },
  connectedIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#25D366', alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  connectedCopy: { flex: 1 },
  connectedTitle: { color: '#FFFFFF', fontSize: 17, fontWeight: '800', marginBottom: 4 },
  connectedText: { color: '#B8C5D8', fontSize: 13 },
  detailCard: { backgroundColor: '#101F35', borderRadius: 14, borderWidth: 1, borderColor: '#1A2942', paddingHorizontal: 14 },
  detailRow: { paddingVertical: 15 },
  detailLabel: { color: '#8B9DC3', fontSize: 12, marginBottom: 4 },
  detailValue: { color: '#FFFFFF', fontWeight: '700', fontSize: 15 },
  divider: { height: 1, backgroundColor: '#1A2942' },
  disconnectButton: { alignItems: 'center', paddingVertical: 14, marginTop: 20 },
  disconnectText: { color: '#F87171', fontWeight: '700' },
  errorText: { color: '#FCA5A5', fontSize: 13, lineHeight: 18, marginBottom: 2 },
});
