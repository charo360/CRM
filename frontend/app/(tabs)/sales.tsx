import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
  Modal,
  Alert,
  ActivityIndicator,
  RefreshControl,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiClient } from '../../context/api';

interface Customer {
  id: string;
  name: string;
  phone_number: string;
}

interface Sale {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  item: string;
  amount: number;
  payment_method: string;
  receipt_sent: boolean;
  created_at: string;
}

const PAYMENT_METHODS = ['Cash', 'M-Pesa'];

export default function SalesScreen() {
  const [sales, setSales] = useState<Sale[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [customerSelectVisible, setCustomerSelectVisible] = useState(false);
  const [saving, setSaving] = useState(false);

  // Form state
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [item, setItem] = useState('');
  const [amount, setAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('M-Pesa');
  const [sendReceipt, setSendReceipt] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [salesRes, customersRes] = await Promise.all([
        apiClient.get('/sales'),
        apiClient.get('/customers'),
      ]);
      setSales(salesRes.data);
      setCustomers(customersRes.data);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const handleCreateSale = async () => {
    if (!selectedCustomer) {
      Alert.alert('Error', 'Please select a customer');
      return;
    }
    if (!item.trim()) {
      Alert.alert('Error', 'Please enter the item');
      return;
    }
    if (!amount || parseFloat(amount) <= 0) {
      Alert.alert('Error', 'Please enter a valid amount');
      return;
    }

    setSaving(true);
    try {
      const response = await apiClient.post('/sales', {
        customer_id: selectedCustomer.id,
        item: item.trim(),
        amount: parseFloat(amount),
        payment_method: paymentMethod,
        send_receipt: sendReceipt,
      });

      setSales([response.data, ...sales]);
      setModalVisible(false);
      resetForm();

      Alert.alert(
        'Success',
        `Sale recorded!${sendReceipt ? ' Receipt sent to customer.' : ''}`,
        [{ text: 'OK' }]
      );
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to record sale');
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    setSelectedCustomer(null);
    setItem('');
    setAmount('');
    setPaymentMethod('M-Pesa');
    setSendReceipt(true);
  };

  const totalRevenue = sales.reduce((sum, s) => sum + s.amount, 0);

  const renderSale = ({ item: sale }: { item: Sale }) => (
    <View style={styles.saleCard}>
      <View style={styles.saleHeader}>
        <View style={styles.saleCustomer}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{sale.customer_name.charAt(0)}</Text>
          </View>
          <View>
            <Text style={styles.customerName}>{sale.customer_name}</Text>
            <Text style={styles.saleDate}>
              {new Date(sale.created_at).toLocaleDateString('en-KE', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </Text>
          </View>
        </View>
        <View style={styles.amountContainer}>
          <Text style={styles.amount}>KES {sale.amount.toLocaleString()}</Text>
          <View style={[styles.paymentBadge, sale.payment_method === 'M-Pesa' && styles.mpesaBadge]}>
            <Text style={styles.paymentText}>{sale.payment_method}</Text>
          </View>
        </View>
      </View>
      <View style={styles.saleDetails}>
        <Ionicons name="pricetag-outline" size={14} color="#666" />
        <Text style={styles.itemText}>{sale.item}</Text>
        {sale.receipt_sent && (
          <View style={styles.receiptBadge}>
            <Ionicons name="checkmark-circle" size={14} color="#25D366" />
            <Text style={styles.receiptText}>Receipt sent</Text>
          </View>
        )}
      </View>
    </View>
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#25D366" />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Sales</Text>
          <Text style={styles.headerSubtitle}>{sales.length} receipts this month</Text>
        </View>
      </View>

      <View style={styles.statsCard}>
        <Text style={styles.statsLabel}>Total Revenue</Text>
        <Text style={styles.statsValue}>KES {totalRevenue.toLocaleString()}</Text>
      </View>

      <FlatList
        data={sales}
        renderItem={renderSale}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="receipt-outline" size={64} color="#666" />
            <Text style={styles.emptyText}>No sales yet</Text>
            <Text style={styles.emptySubtext}>Record your first sale</Text>
          </View>
        }
      />

      {/* WhatsApp-style Floating Action Button */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => setModalVisible(true)}
        activeOpacity={0.8}
      >
        <Ionicons name="add" size={28} color="#FFFFFF" />
      </TouchableOpacity>

      {/* New Sale Modal */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => {
          setModalVisible(false);
          resetForm();
        }}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => {
              setModalVisible(false);
              resetForm();
            }}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>New Sale</Text>
            <TouchableOpacity onPress={handleCreateSale} disabled={saving}>
              <Text style={[styles.modalSave, saving && styles.modalSaveDisabled]}>
                {saving ? 'Saving...' : 'Save'}
              </Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalContent}>
            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Customer *</Text>
              <TouchableOpacity
                style={styles.customerSelect}
                onPress={() => setCustomerSelectVisible(true)}
              >
                {selectedCustomer ? (
                  <View style={styles.selectedCustomer}>
                    <View style={styles.miniAvatar}>
                      <Text style={styles.miniAvatarText}>
                        {selectedCustomer.name.charAt(0)}
                      </Text>
                    </View>
                    <View>
                      <Text style={styles.selectedName}>{selectedCustomer.name}</Text>
                      <Text style={styles.selectedPhone}>{selectedCustomer.phone_number}</Text>
                    </View>
                  </View>
                ) : (
                  <Text style={styles.customerSelectPlaceholder}>Select a customer</Text>
                )}
                <Ionicons name="chevron-forward" size={20} color="#666" />
              </TouchableOpacity>
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Item *</Text>
              <TextInput
                style={styles.formInput}
                value={item}
                onChangeText={setItem}
                placeholder="e.g., Blue Jeans, iPhone Case"
                placeholderTextColor="#666"
              />
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Amount (KES) *</Text>
              <TextInput
                style={styles.formInput}
                value={amount}
                onChangeText={setAmount}
                placeholder="0"
                placeholderTextColor="#666"
                keyboardType="numeric"
              />
            </View>

            <View style={styles.formGroup}>
              <Text style={styles.formLabel}>Payment Method</Text>
              <View style={styles.paymentMethods}>
                {PAYMENT_METHODS.map((method) => (
                  <TouchableOpacity
                    key={method}
                    style={[
                      styles.paymentOption,
                      paymentMethod === method && styles.paymentOptionSelected,
                    ]}
                    onPress={() => setPaymentMethod(method)}
                  >
                    <Ionicons
                      name={method === 'M-Pesa' ? 'phone-portrait' : 'cash'}
                      size={20}
                      color={paymentMethod === method ? '#FFFFFF' : '#666'}
                    />
                    <Text
                      style={[
                        styles.paymentOptionText,
                        paymentMethod === method && styles.paymentOptionTextSelected,
                      ]}
                    >
                      {method}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <TouchableOpacity
              style={styles.receiptToggle}
              onPress={() => setSendReceipt(!sendReceipt)}
            >
              <View style={[styles.checkbox, sendReceipt && styles.checkboxChecked]}>
                {sendReceipt && <Ionicons name="checkmark" size={16} color="#FFFFFF" />}
              </View>
              <Text style={styles.receiptToggleText}>Send receipt via WhatsApp</Text>
            </TouchableOpacity>

            {sendReceipt && (
              <View style={styles.receiptPreview}>
                <Text style={styles.receiptPreviewTitle}>Receipt Preview:</Text>
                <Text style={styles.receiptPreviewText}>
                  ✅ Payment received{"\n"}
                  Item: {item || '[Item]'}{"\n"}
                  Amount: KES {amount ? parseFloat(amount).toLocaleString() : '0'}{"\n"}
                  Thank you for shopping with us 🙏
                </Text>
              </View>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Customer Select Modal */}
      <Modal
        visible={customerSelectVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setCustomerSelectVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setCustomerSelectVisible(false)}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Select Customer</Text>
            <View style={{ width: 60 }} />
          </View>

          <FlatList
            data={customers}
            renderItem={({ item: customer }) => (
              <TouchableOpacity
                style={styles.customerOption}
                onPress={() => {
                  setSelectedCustomer(customer);
                  setCustomerSelectVisible(false);
                }}
              >
                <View style={styles.miniAvatar}>
                  <Text style={styles.miniAvatarText}>{customer.name.charAt(0)}</Text>
                </View>
                <View style={styles.customerOptionInfo}>
                  <Text style={styles.customerOptionName}>{customer.name}</Text>
                  <Text style={styles.customerOptionPhone}>{customer.phone_number}</Text>
                </View>
                {selectedCustomer?.id === customer.id && (
                  <Ionicons name="checkmark-circle" size={24} color="#25D366" />
                )}
              </TouchableOpacity>
            )}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.listContent}
            ListEmptyComponent={
              <View style={styles.emptyContainer}>
                <Text style={styles.emptyText}>No customers found</Text>
                <Text style={styles.emptySubtext}>Add customers first</Text>
              </View>
            }
          />
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },
  statsCard: {
    backgroundColor: '#1A2942',
    marginHorizontal: 20,
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
  },
  statsLabel: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  statsValue: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#25D366',
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  saleCard: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  saleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  saleCustomer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  avatarText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  customerName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  saleDate: {
    fontSize: 12,
    color: '#666',
    marginTop: 2,
  },
  amountContainer: {
    alignItems: 'flex-end',
  },
  amount: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 4,
  },
  paymentBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: '#4A90D9',
    borderRadius: 10,
  },
  mpesaBadge: {
    backgroundColor: '#25D366',
  },
  paymentText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  saleDetails: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#2A3952',
  },
  itemText: {
    fontSize: 14,
    color: '#888',
    marginLeft: 8,
    flex: 1,
  },
  receiptBadge: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  receiptText: {
    fontSize: 12,
    color: '#25D366',
    marginLeft: 4,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingTop: 60,
  },
  emptyText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginTop: 16,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#666',
    marginTop: 8,
  },
  // Modal styles
  modalContainer: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  modalCancel: {
    fontSize: 16,
    color: '#FF4444',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  modalSave: {
    fontSize: 16,
    fontWeight: '600',
    color: '#25D366',
  },
  modalSaveDisabled: {
    opacity: 0.5,
  },
  modalContent: {
    padding: 20,
  },
  formGroup: {
    marginBottom: 20,
  },
  formLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  formInput: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: '#FFFFFF',
  },
  customerSelect: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
  },
  customerSelectPlaceholder: {
    fontSize: 16,
    color: '#666',
  },
  selectedCustomer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  miniAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  miniAvatarText: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  selectedName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  selectedPhone: {
    fontSize: 12,
    color: '#666',
  },
  paymentMethods: {
    flexDirection: 'row',
  },
  paymentOption: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginRight: 12,
  },
  paymentOptionSelected: {
    backgroundColor: '#25D366',
  },
  paymentOptionText: {
    fontSize: 16,
    color: '#666',
    marginLeft: 8,
  },
  paymentOptionTextSelected: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  receiptToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#666',
    marginRight: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  checkboxChecked: {
    backgroundColor: '#25D366',
    borderColor: '#25D366',
  },
  receiptToggleText: {
    fontSize: 16,
    color: '#FFFFFF',
  },
  receiptPreview: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
  },
  receiptPreviewTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#666',
    marginBottom: 8,
  },
  receiptPreviewText: {
    fontSize: 14,
    color: '#FFFFFF',
    lineHeight: 22,
  },
  customerOption: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  customerOptionInfo: {
    flex: 1,
  },
  customerOptionName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  customerOptionPhone: {
    fontSize: 12,
    color: '#666',
  },
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
});
