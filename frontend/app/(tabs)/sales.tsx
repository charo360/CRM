import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
  Share,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import DateTimePicker from '@react-native-community/datetimepicker';
import { apiClient, settingsAPI } from '../../context/api';
import { useRouter } from 'expo-router';

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
  is_credit?: boolean;
  due_date?: string;
  paid_date?: string;
  created_at: string;
}

interface Order {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  product: string;
  quantity: number;
  price: number;
  total_amount: number;
  payment_status: 'Pending' | 'Partial' | 'Paid';
  delivery_status: 'Processing' | 'Shipped' | 'Delivered';
  notes?: string;
  due_date?: string;
  created_at: string;
}

interface Expense {
  id: string;
  category: string;
  amount: number;
  description?: string;
  created_at: string;
}

const DATE_FILTERS = ['Today', 'This Week', 'This Month', 'All Time'];
const EXPENSE_CATEGORIES = ['Inventory', 'Rent', 'Transport', 'Utilities', 'Salaries', 'Other'];

export default function SalesScreen() {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<'sales' | 'expenses' | 'orders'>('sales');
  const [sales, setSales] = useState<Sale[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<string[]>(['Cash', 'Mobile Money']);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [customerSelectVisible, setCustomerSelectVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFilter, setDateFilter] = useState('All Time');
  const [selectedSale, setSelectedSale] = useState<Sale | null>(null);
  const [saleDetailsVisible, setSaleDetailsVisible] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [orderDetailsVisible, setOrderDetailsVisible] = useState(false);

  // Form state
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [item, setItem] = useState('');
  const [amount, setAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('M-Pesa');
  const [sendReceipt, setSendReceipt] = useState(true);
  const [receiptMessage, setReceiptMessage] = useState('');
  const [editingReceipt, setEditingReceipt] = useState(false);
  const [paymentSettingsVisible, setPaymentSettingsVisible] = useState(false);
  const [newPaymentMethod, setNewPaymentMethod] = useState('');
  const [addingPaymentMethod, setAddingPaymentMethod] = useState(false);

  // Customer selection state
  const [customerSearchQuery, setCustomerSearchQuery] = useState('');
  const [isWalkInCustomer, setIsWalkInCustomer] = useState(false);

  // Credit sale state
  const [isCreditSale, setIsCreditSale] = useState(false);
  const [dueDate, setDueDate] = useState('');
  const [showDueDatePicker, setShowDueDatePicker] = useState(false);
  const [tempDueDate, setTempDueDate] = useState<Date>(new Date());

  // Expense form state
  const [expenseCategory, setExpenseCategory] = useState('Inventory');
  const [expenseAmount, setExpenseAmount] = useState('');
  const [expenseDescription, setExpenseDescription] = useState('');

  // Order form state
  const [orderProduct, setOrderProduct] = useState('');
  const [orderQuantity, setOrderQuantity] = useState('1');
  const [orderPrice, setOrderPrice] = useState('');
  const [orderNotes, setOrderNotes] = useState('');
  const [orderDueDate, setOrderDueDate] = useState('');
  const [showOrderDueDatePicker, setShowOrderDueDatePicker] = useState(false);
  const [tempOrderDueDate, setTempOrderDueDate] = useState<Date>(new Date());

  // Currency
  const [currency, setCurrency] = useState('USD');

  useEffect(() => {
    const loadCurrency = async () => {
      try {
        const settings = await settingsAPI.getSettings();
        if (settings.currency) setCurrency(settings.currency);
      } catch (e) {}
    };
    loadCurrency();
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const [salesRes, expensesRes, ordersRes, customersRes, userRes] = await Promise.all([
        apiClient.get('/sales'),
        apiClient.get('/expenses'),
        apiClient.get('/orders'),
        apiClient.get('/customers'),
        apiClient.get('/auth/me'),
      ]);
      setSales(salesRes.data);
      setExpenses(expensesRes.data);
      setOrders(ordersRes.data);
      setCustomers(customersRes.data);
      if (userRes.data.payment_methods && userRes.data.payment_methods.length > 0) {
        setPaymentMethods(userRes.data.payment_methods);
        setPaymentMethod(userRes.data.payment_methods[0]);
      }
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
    if (!isWalkInCustomer && !selectedCustomer) {
      Alert.alert('Error', 'Please select a customer or choose Walk-in Customer');
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
        customer_id: isWalkInCustomer ? 'walk-in' : selectedCustomer!.id,
        item: item.trim(),
        amount: parseFloat(amount),
        payment_method: isCreditSale ? undefined : paymentMethod,
        send_receipt: sendReceipt && !isWalkInCustomer,
        receipt_message: receiptMessage.trim() || undefined,
        is_credit: isCreditSale,
        due_date: isCreditSale && dueDate ? dueDate : undefined,
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
    setReceiptMessage('');
    setEditingReceipt(false);
    setIsCreditSale(false);
    setDueDate('');
  };

  const resetExpenseForm = () => {
    setExpenseCategory('Inventory');
    setExpenseAmount('');
    setExpenseDescription('');
  };

  const handleCreateExpense = async () => {
    if (!expenseAmount || parseFloat(expenseAmount) <= 0) {
      Alert.alert('Error', 'Please enter a valid amount');
      return;
    }

    setSaving(true);
    try {
      const response = await apiClient.post('/expenses', {
        category: expenseCategory,
        amount: parseFloat(expenseAmount),
        description: expenseDescription.trim() || undefined,
      });

      setExpenses([response.data, ...expenses]);
      setModalVisible(false);
      resetExpenseForm();

      Alert.alert('Success', 'Expense recorded!');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to record expense');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteExpense = async (expenseId: string) => {
    Alert.alert(
      'Delete Expense',
      'Are you sure you want to delete this expense?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.delete(`/expenses/${expenseId}`);
              setExpenses(expenses.filter((e) => e.id !== expenseId));
              Alert.alert('Success', 'Expense deleted');
            } catch (error) {
              Alert.alert('Error', 'Failed to delete expense');
            }
          },
        },
      ]
    );
  };

  const handleCreateOrder = async () => {
    // Validate
    if (!isWalkInCustomer && !selectedCustomer) {
      Alert.alert('Error', 'Please select a customer or choose Walk-in Customer');
      return;
    }
    if (!orderProduct.trim()) {
      Alert.alert('Error', 'Please enter the product name');
      return;
    }
    if (!orderQuantity || parseInt(orderQuantity) <= 0) {
      Alert.alert('Error', 'Please enter a valid quantity');
      return;
    }
    if (!orderPrice || parseFloat(orderPrice) <= 0) {
      Alert.alert('Error', 'Please enter a valid price');
      return;
    }

    setSaving(true);
    try {
      const totalAmount = parseInt(orderQuantity) * parseFloat(orderPrice);
      const response = await apiClient.post('/orders', {
        customer_id: isWalkInCustomer ? 'walk-in' : selectedCustomer!.id,
        product: orderProduct.trim(),
        quantity: parseInt(orderQuantity),
        price: parseFloat(orderPrice),
        total_amount: totalAmount,
        payment_status: 'Pending',
        delivery_status: 'Processing',
        notes: orderNotes.trim() || undefined,
        due_date: orderDueDate || undefined,
      });

      setOrders([response.data, ...orders]);
      setModalVisible(false);
      Alert.alert('Success', 'Order created successfully!');

      // Reset form
      setSelectedCustomer(null);
      setIsWalkInCustomer(false);
      setOrderProduct('');
      setOrderQuantity('1');
      setOrderPrice('');
      setOrderNotes('');
      setOrderDueDate('');
    } catch (error: any) {
      console.error('Error creating order:', error);
      Alert.alert('Error', error.response?.data?.detail || 'Failed to create order');
    } finally {
      setSaving(false);
    }
  };

  // Initialize receipt message when editing starts
  const handleEditReceipt = () => {
    if (!receiptMessage) {
      const defaultMessage = `✅ Payment received\nItem: ${item || '[Item]'}\nAmount: ${currency} ${amount ? parseFloat(amount).toLocaleString() : '0'}\nThank you for shopping with us 🙏`;
      setReceiptMessage(defaultMessage);
    }
    setEditingReceipt(true);
  };

  // Filter sales based on search and date
  const filteredSales = useMemo(() => {
    let filtered = sales;

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (s) =>
          s.customer_name.toLowerCase().includes(query) ||
          s.item.toLowerCase().includes(query)
      );
    }

    // Apply date filter
    if (dateFilter !== 'All Time') {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

      filtered = filtered.filter((s) => {
        const saleDate = new Date(s.created_at);

        if (dateFilter === 'Today') {
          return saleDate >= today;
        } else if (dateFilter === 'This Week') {
          const weekAgo = new Date(today);
          weekAgo.setDate(weekAgo.getDate() - 7);
          return saleDate >= weekAgo;
        } else if (dateFilter === 'This Month') {
          const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
          return saleDate >= monthStart;
        }
        return true;
      });
    }

    return filtered;
  }, [sales, searchQuery, dateFilter]);

  // Filter expenses based on date
  const filteredExpenses = useMemo(() => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    return expenses.filter((e) => {
      const expenseDate = new Date(e.created_at);

      if (dateFilter === 'Today') {
        return expenseDate >= today;
      } else if (dateFilter === 'This Week') {
        const weekAgo = new Date(today);
        weekAgo.setDate(weekAgo.getDate() - 7);
        return expenseDate >= weekAgo;
      } else if (dateFilter === 'This Month') {
        const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
        return expenseDate >= monthStart;
      }
      return true;
    });
  }, [expenses, dateFilter]);

  // Calculate analytics
  const analytics = useMemo(() => {
    const totalRevenue = filteredSales.reduce((sum, s) => sum + s.amount, 0);
    const totalExpenses = filteredExpenses.reduce((sum, e) => sum + e.amount, 0);
    const netProfit = totalRevenue - totalExpenses;
    const salesCount = filteredSales.length;
    const avgSale = salesCount > 0 ? totalRevenue / salesCount : 0;

    // Order analytics
    const totalOrders = orders.length;
    const pendingPayment = orders
      .filter(o => o.payment_status === 'Pending' || o.payment_status === 'Partial')
      .reduce((sum, o) => sum + o.total_amount, 0);
    const ordersToDeliver = orders.filter(
      o => o.delivery_status === 'Processing' || o.delivery_status === 'Shipped'
    ).length;

    // Find top customer
    const customerSales: { [key: string]: { name: string; total: number } } = {};
    filteredSales.forEach((s) => {
      if (!customerSales[s.customer_id]) {
        customerSales[s.customer_id] = { name: s.customer_name, total: 0 };
      }
      customerSales[s.customer_id].total += s.amount;
    });

    const topCustomer = Object.values(customerSales).sort((a, b) => b.total - a.total)[0];

    return {
      totalRevenue,
      totalExpenses,
      netProfit,
      salesCount,
      avgSale,
      topCustomer,
      totalOrders,
      pendingPayment,
      ordersToDeliver
    };
  }, [filteredSales, filteredExpenses, orders]);

  const handleExportSales = async () => {
    if (filteredSales.length === 0) {
      Alert.alert('No Data', 'No sales to export');
      return;
    }

    const csvHeader = 'Date,Customer,Phone,Item,Amount,Payment Method,Receipt Sent\n';
    const csvRows = filteredSales.map((s) => {
      const date = new Date(s.created_at).toLocaleDateString('en-KE');
      return `${date},${s.customer_name},${s.customer_phone},${s.item},${s.amount},${s.payment_method},${s.receipt_sent ? 'Yes' : 'No'}`;
    }).join('\n');

    const csvContent = csvHeader + csvRows;

    try {
      await Share.share({
        message: csvContent,
        title: `Sales Report - ${dateFilter}`,
      });
    } catch (error) {
      console.error('Error sharing:', error);
    }
  };

  const handleResendReceipt = (sale: Sale) => {
    const message = `✅ Payment received\nItem: ${sale.item}\nAmount: ${currency} ${sale.amount.toLocaleString()}\nThank you for shopping with us 🙏`;
    router.push({
      pathname: '/chat',
      params: {
        customerId: sale.customer_id,
        customerName: sale.customer_name || 'Customer',
        customerPhone: sale.customer_phone,
        prefill: message,
      },
    });
  };

  const handleMarkAsPaid = async (sale: Sale) => {
    // Show payment method selection
    Alert.alert(
      'Mark as Paid',
      'How was this credit sale paid?',
      [
        ...paymentMethods.map((method) => ({
          text: method,
          onPress: async () => {
            try {
              await apiClient.put(`/sales/${sale.id}/mark-paid?payment_method=${encodeURIComponent(method)}`);

              // Update local state
              const updatedSales = sales.map((s) =>
                s.id === sale.id
                  ? { ...s, paid_date: new Date().toISOString(), payment_method: method }
                  : s
              );
              setSales(updatedSales);

              // Update selected sale if it's open
              if (selectedSale?.id === sale.id) {
                setSelectedSale({ ...sale, paid_date: new Date().toISOString(), payment_method: method });
              }

              Alert.alert('Success', `Sale marked as paid via ${method}!`);
            } catch (error) {
              Alert.alert('Error', 'Failed to mark sale as paid');
            }
          },
        })),
        { text: 'Cancel', style: 'cancel' },
      ]
    );
  };

  const renderSale = ({ item: sale }: { item: Sale }) => (
    <TouchableOpacity
      style={styles.saleCard}
      onPress={() => {
        setSelectedSale(sale);
        setSaleDetailsVisible(true);
      }}
      activeOpacity={0.7}
    >
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
          <Text style={styles.amount}>{currency} {sale.amount.toLocaleString()}</Text>
          <View style={[
            styles.paymentBadge,
            sale.payment_method === 'M-Pesa' && styles.mpesaBadge,
            sale.is_credit && styles.creditBadge
          ]}>
            <Text style={styles.paymentText}>{sale.payment_method || 'Credit'}</Text>
          </View>
        </View>
      </View>
      <View style={styles.saleDetails}>
        <Ionicons name="pricetag-outline" size={14} color="#666" />
        <Text style={styles.itemText}>{sale.item}</Text>
        {!!sale.receipt_sent && (
          <View style={styles.receiptBadge}>
            <Ionicons name="checkmark-circle" size={14} color="#25D366" />
            <Text style={styles.receiptText}>Receipt sent</Text>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );

  const renderExpense = ({ item: expense }: { item: Expense }) => (
    <View style={styles.expenseCard}>
      <View style={styles.expenseHeader}>
        <View style={styles.expenseInfo}>
          <View style={styles.categoryBadge}>
            <Text style={styles.categoryText}>{expense.category}</Text>
          </View>
          <Text style={styles.expenseDate}>
            {new Date(expense.created_at).toLocaleDateString('en-KE', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Text>
        </View>
        <View style={styles.expenseAmountContainer}>
          <Text style={styles.expenseAmount}>{currency} {expense.amount.toLocaleString()}</Text>
          <TouchableOpacity onPress={() => handleDeleteExpense(expense.id)}>
            <Ionicons name="trash-outline" size={20} color="#FF6B6B" />
          </TouchableOpacity>
        </View>
      </View>
      {!!expense.description && (
        <Text style={styles.expenseDescription}>{expense.description}</Text>
      )}
    </View>
  );

  const renderOrder = ({ item: order }: { item: Order }) => {
    const getPaymentStatusColor = (status: string) => {
      switch (status) {
        case 'Paid': return '#25D366';
        case 'Partial': return '#FFD700';
        case 'Pending': return '#FF6B6B';
        default: return '#666';
      }
    };

    const getDeliveryStatusColor = (status: string) => {
      switch (status) {
        case 'Delivered': return '#25D366';
        case 'Shipped': return '#9B59B6';
        case 'Processing': return '#3498DB';
        default: return '#666';
      }
    };

    return (
      <TouchableOpacity
        style={styles.saleCard}
        onPress={() => {
          setSelectedOrder(order);
          setOrderDetailsVisible(true);
        }}
      >
        <View style={styles.saleHeader}>
          <View style={styles.saleCustomer}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{order.customer_name.charAt(0)}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.customerName} numberOfLines={1}>{order.customer_name}</Text>
              <Text style={styles.saleDate}>
                {new Date(order.created_at).toLocaleDateString('en-KE', {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </Text>
            </View>
          </View>
          <Text style={[styles.amount, { flexShrink: 0 }]}>{currency} {order.total_amount.toLocaleString()}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
          <View style={[styles.statusBadge, { backgroundColor: getPaymentStatusColor(order.payment_status) }]}>
            <Text style={styles.statusBadgeText}>{order.payment_status}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: getDeliveryStatusColor(order.delivery_status) }]}>
            <Text style={styles.statusBadgeText}>{order.delivery_status}</Text>
          </View>
        </View>
        <View style={styles.saleDetails}>
          <Text style={styles.itemText}>{order.product} (x{order.quantity})</Text>
          <Text style={styles.paymentText}>@ {currency} {order.price.toLocaleString()} each</Text>
        </View>
        {order.payment_status === 'Paid' && (
          <View style={{ backgroundColor: '#1A3A2A', borderRadius: 8, padding: 8, marginTop: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            <Ionicons name="checkmark-circle" size={14} color="#25D366" />
            <Text style={{ color: '#25D366', fontSize: 12, fontWeight: '600' }}>Ready to convert to sale</Text>
          </View>
        )}
      </TouchableOpacity>
    );
  };

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
          <Text style={styles.headerSubtitle}>
            {viewMode === 'sales'
              ? `${analytics.salesCount} sales`
              : viewMode === 'expenses'
                ? `${filteredExpenses.length} expenses`
                : `${orders.length} orders`} {dateFilter === 'All Time' ? 'total' : dateFilter.toLowerCase()}
          </Text>
        </View>
        <View style={styles.headerActions}>
          <TouchableOpacity onPress={() => setPaymentSettingsVisible(true)} style={styles.exportButton}>
            <Ionicons name="settings-outline" size={20} color="#888" />
          </TouchableOpacity>
          <TouchableOpacity onPress={handleExportSales} style={styles.exportButton}>
            <Ionicons name="download-outline" size={20} color="#4A90D9" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Sales/Expenses/Orders Toggle */}
      <View style={styles.viewToggle}>
        <TouchableOpacity
          style={[styles.toggleButton, viewMode === 'sales' && styles.toggleButtonActive]}
          onPress={() => setViewMode('sales')}
        >
          <Text style={[styles.toggleText, viewMode === 'sales' && styles.toggleTextActive]}>Sales</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.toggleButton, viewMode === 'expenses' && styles.toggleButtonActive]}
          onPress={() => setViewMode('expenses')}
        >
          <Text style={[styles.toggleText, viewMode === 'expenses' && styles.toggleTextActive]}>Expenses</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.toggleButton, viewMode === 'orders' && styles.toggleButtonActive]}
          onPress={() => setViewMode('orders')}
        >
          <Text style={[styles.toggleText, viewMode === 'orders' && styles.toggleTextActive]}>Orders</Text>
        </TouchableOpacity>
      </View>

      {/* Search Bar */}
      {viewMode === 'sales' && (
        <View style={styles.searchContainer}>
          <Ionicons name="search" size={20} color="#666" style={styles.searchIcon} />
          <TextInput
            style={styles.searchInput}
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="Search by customer or item..."
            placeholderTextColor="#666"
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => setSearchQuery('')}>
              <Ionicons name="close-circle" size={20} color="#666" />
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* Date Filter */}
      <View style={styles.filterContainer}>
        {DATE_FILTERS.map((filter) => (
          <TouchableOpacity
            key={filter}
            style={[
              styles.filterChip,
              dateFilter === filter && styles.filterChipActive,
            ]}
            onPress={() => setDateFilter(filter)}
          >
            <Text
              style={[
                styles.filterChipText,
                dateFilter === filter && styles.filterChipTextActive,
              ]}
            >
              {filter}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Analytics Cards */}
      <View style={styles.analyticsContainer}>
        {viewMode === 'sales' ? (
          <>
            <View style={styles.analyticsCard}>
              <Text style={styles.analyticsLabel}>Revenue</Text>
              <Text style={styles.analyticsValue}>{currency} {analytics.totalRevenue.toLocaleString()}</Text>
            </View>
            <View style={styles.analyticsCard}>
              <Text style={styles.analyticsLabel}>Avg Sale</Text>
              <Text style={styles.analyticsValue}>{currency} {Math.round(analytics.avgSale).toLocaleString()}</Text>
            </View>
            {!!analytics.topCustomer && (
              <View style={[styles.analyticsCard, { marginRight: 0 }]}>
                <Text style={styles.analyticsLabel}>Top Customer</Text>
                <Text style={styles.analyticsValue}>{analytics.topCustomer.name}</Text>
                <Text style={styles.analyticsSubtext} numberOfLines={1}>{currency} {analytics.topCustomer.total.toLocaleString()}</Text>
              </View>
            )}
          </>
        ) : viewMode === 'expenses' ? (
          <>
            <View style={styles.analyticsCard}>
              <Text style={styles.analyticsLabel}>Revenue</Text>
              <Text style={styles.analyticsValue}>{currency} {analytics.totalRevenue.toLocaleString()}</Text>
            </View>
            <View style={styles.analyticsCard}>
              <Text style={styles.analyticsLabel}>Expenses</Text>
              <Text style={styles.analyticsValue}>{currency} {analytics.totalExpenses.toLocaleString()}</Text>
            </View>
            <View style={[styles.analyticsCard, { marginRight: 0 }]}>
              <Text style={styles.analyticsLabel}>Net Profit</Text>
              <Text style={[styles.analyticsValue, analytics.netProfit < 0 && { color: '#FF6B6B' }]}>
                {currency} {analytics.netProfit.toLocaleString()}
              </Text>
            </View>
          </>
        ) : (
          <>
            <View style={styles.analyticsCard}>
              <Text style={styles.analyticsLabel}>Total Orders</Text>
              <Text style={styles.analyticsValue}>{analytics.totalOrders}</Text>
            </View>
            <View style={styles.analyticsCard}>
              <Text style={styles.analyticsLabel}>Pending Payment</Text>
              <Text style={styles.analyticsValue}>{currency} {analytics.pendingPayment.toLocaleString()}</Text>
            </View>
            <View style={[styles.analyticsCard, { marginRight: 0 }]}>
              <Text style={styles.analyticsLabel}>To Deliver</Text>
              <Text style={styles.analyticsValue}>{analytics.ordersToDeliver}</Text>
            </View>
          </>
        )}
      </View>

      <FlatList
        data={(viewMode === 'sales' ? filteredSales : viewMode === 'expenses' ? filteredExpenses : orders) as any[]}
        renderItem={(viewMode === 'sales' ? renderSale : viewMode === 'expenses' ? renderExpense : renderOrder) as any}
        keyExtractor={(item: any) => item.id}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#25D366" />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons
              name={viewMode === 'sales' ? 'receipt-outline' : viewMode === 'expenses' ? 'wallet-outline' : 'cart-outline'}
              size={64}
              color="#666"
            />
            <Text style={styles.emptyText}>
              {viewMode === 'sales'
                ? (searchQuery || dateFilter !== 'All Time' ? 'No sales found' : 'No sales yet')
                : viewMode === 'expenses'
                  ? (dateFilter !== 'All Time' ? 'No expenses found' : 'No expenses yet')
                  : 'No orders yet'
              }
            </Text>
            <Text style={styles.emptySubtext}>
              {viewMode === 'sales'
                ? (searchQuery || dateFilter !== 'All Time' ? 'Try adjusting your filters' : 'Record your first sale')
                : viewMode === 'expenses'
                  ? (dateFilter !== 'All Time' ? 'Try adjusting your filters' : 'Record your first expense')
                  : 'Create your first order'
              }
            </Text>
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
              <Ionicons name="close" size={28} color="#888" />
            </TouchableOpacity>
            <Text style={styles.modalTitle}>
              {viewMode === 'sales' ? 'New Sale' : viewMode === 'expenses' ? 'New Expense' : 'New Order'}
            </Text>
            <TouchableOpacity
              onPress={viewMode === 'sales' ? handleCreateSale : viewMode === 'expenses' ? handleCreateExpense : handleCreateOrder}
              disabled={saving}
            >
              <Text style={[styles.modalSave, saving && styles.modalSaveDisabled]}>
                {saving ? 'Saving...' : 'Save'}
              </Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalContent}>
            {viewMode === 'sales' ? (
              <>
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Customer *</Text>
                  <TouchableOpacity
                    style={styles.customerSelect}
                    onPress={() => setCustomerSelectVisible(true)}
                  >
                    {isWalkInCustomer ? (
                      <View style={styles.selectedCustomer}>
                        <View style={styles.miniAvatar}>
                          <Ionicons name="walk-outline" size={16} color="#FFFFFF" />
                        </View>
                        <View>
                          <Text style={styles.selectedName}>Walk-in Customer</Text>
                          <Text style={styles.selectedPhone}>No contact info</Text>
                        </View>
                      </View>
                    ) : selectedCustomer ? (
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
                  <Text style={styles.formLabel}>Amount ({currency}) *</Text>
                  <TextInput
                    style={styles.formInput}
                    value={amount}
                    onChangeText={setAmount}
                    placeholder="0"
                    placeholderTextColor="#666"
                    keyboardType="numeric"
                  />
                </View>

                {/* Credit Sale Checkbox */}
                <TouchableOpacity
                  style={styles.receiptToggle}
                  onPress={() => {
                    setIsCreditSale(!isCreditSale);
                    if (!isCreditSale) {
                      // When enabling credit sale, clear payment method
                      setPaymentMethod('');
                    } else {
                      // When disabling credit sale, set default payment method
                      setPaymentMethod(paymentMethods[0] || 'Cash');
                      setDueDate('');
                    }
                  }}
                >
                  <View style={[styles.checkbox, isCreditSale && styles.checkboxChecked]}>
                    {isCreditSale && <Ionicons name="checkmark" size={16} color="#FFFFFF" />}
                  </View>
                  <Text style={styles.receiptToggleText}>Credit Sale (Pay Later)</Text>
                </TouchableOpacity>

                {/* Due Date for Credit Sales */}
                {isCreditSale && (
                  <View style={styles.formGroup}>
                    <Text style={styles.formLabel}>Due Date (Optional)</Text>
                    <TouchableOpacity
                      style={styles.formInput}
                      onPress={() => {
                        setTempDueDate(dueDate ? new Date(dueDate) : new Date());
                        setShowDueDatePicker(true);
                      }}
                    >
                      <Text style={{ color: dueDate ? '#FFF' : '#666' }}>
                        {dueDate ? new Date(dueDate).toLocaleDateString() : 'No due date set'}
                      </Text>
                      <Ionicons name="calendar-outline" size={20} color="#666" style={{ position: 'absolute', right: 12, top: 12 }} />
                    </TouchableOpacity>

                    {showDueDatePicker && (
                      <DateTimePicker
                        value={tempDueDate}
                        mode="date"
                        display="default"
                        onChange={(event, selectedDate) => {
                          setShowDueDatePicker(false);
                          if (event.type === 'set' && selectedDate) {
                            setDueDate(selectedDate.toISOString());
                          }
                        }}
                        minimumDate={new Date()}
                      />
                    )}

                    {!!dueDate && (
                      <TouchableOpacity
                        onPress={() => setDueDate('')}
                        style={{ marginTop: 8, alignSelf: 'flex-start' }}
                      >
                        <Text style={{ color: '#FF4444', fontSize: 12 }}>Clear Due Date</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                )}

                {/* Payment Method - Hidden for Credit Sales */}
                {!isCreditSale && (
                  <View style={styles.formGroup}>
                    <Text style={styles.formLabel}>Payment Method</Text>
                    <View style={styles.paymentMethods}>
                      {paymentMethods.map((method) => (
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
                )}

                <TouchableOpacity
                  style={styles.receiptToggle}
                  onPress={() => setSendReceipt(!sendReceipt)}
                >
                  <View style={[styles.checkbox, sendReceipt && styles.checkboxChecked]}>
                    {sendReceipt && <Ionicons name="checkmark" size={16} color="#FFFFFF" />}
                  </View>
                  <Text style={styles.receiptToggleText}>Send receipt via WhatsApp</Text>
                </TouchableOpacity>

                {sendReceipt && !editingReceipt && (
                  <View style={styles.receiptPreview}>
                    <View style={styles.receiptPreviewHeader}>
                      <Text style={styles.receiptPreviewTitle}>Receipt Preview:</Text>
                      <TouchableOpacity onPress={handleEditReceipt}>
                        <Ionicons name="pencil" size={20} color="#25D366" />
                      </TouchableOpacity>
                    </View>
                    <Text style={styles.receiptPreviewText}>
                      {receiptMessage || `✅ Payment received\nItem: ${item || '[Item]'}\nAmount: ${currency} ${amount ? parseFloat(amount).toLocaleString() : '0'}\nThank you for shopping with us 🙏`}
                    </Text>
                  </View>
                )}

                {sendReceipt && editingReceipt && (
                  <View style={styles.formGroup}>
                    <View style={styles.receiptEditHeader}>
                      <Text style={styles.formLabel}>Edit Receipt Message</Text>
                      <TouchableOpacity onPress={() => setEditingReceipt(false)}>
                        <Text style={styles.doneButton}>Done</Text>
                      </TouchableOpacity>
                    </View>
                    <TextInput
                      style={[styles.formInput, styles.receiptMessageInput]}
                      value={receiptMessage}
                      onChangeText={setReceiptMessage}
                      placeholder="Customize your receipt message..."
                      placeholderTextColor="#666"
                      multiline
                      numberOfLines={5}
                      textAlignVertical="top"
                    />
                    <Text style={styles.receiptHint}>
                      Tip: Add your business name for a professional touch
                    </Text>
                  </View>
                )}
              </>
            ) : viewMode === 'expenses' ? (

              <>
                {/* Expense Category Selection */}
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Category *</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryScroll}>
                    {EXPENSE_CATEGORIES.map((cat) => (
                      <TouchableOpacity
                        key={cat}
                        style={[
                          styles.categoryOption,
                          expenseCategory === cat && styles.categoryOptionSelected,
                        ]}
                        onPress={() => setExpenseCategory(cat)}
                      >
                        <Text
                          style={[
                            styles.categoryOptionText,
                            expenseCategory === cat && styles.categoryOptionTextSelected,
                          ]}
                        >
                          {cat}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                </View>


                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Amount ({currency}) *</Text>
                  <TextInput
                    style={styles.formInput}
                    value={expenseAmount}
                    onChangeText={setExpenseAmount}
                    placeholder="0"
                    placeholderTextColor="#666"
                    keyboardType="numeric"
                  />
                </View>

                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Description (Optional)</Text>
                  <TextInput
                    style={[styles.formInput, styles.receiptMessageInput]}
                    value={expenseDescription}
                    onChangeText={setExpenseDescription}
                    placeholder="e.g., Bought inventory from supplier"
                    placeholderTextColor="#666"
                    multiline
                    numberOfLines={3}
                    textAlignVertical="top"
                  />
                </View>
              </>
            ) : (
              <>
                {/* Order Form */}
                {/* Customer Selection */}
                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Customer *</Text>
                  <TouchableOpacity
                    style={styles.customerSelect}
                    onPress={() => setCustomerSelectVisible(true)}
                  >
                    {isWalkInCustomer ? (
                      <View style={styles.selectedCustomer}>
                        <View style={styles.miniAvatar}>
                          <Ionicons name="walk-outline" size={16} color="#FFFFFF" />
                        </View>
                        <View>
                          <Text style={styles.selectedName}>Walk-in Customer</Text>
                          <Text style={styles.selectedPhone}>No contact info</Text>
                        </View>
                      </View>
                    ) : selectedCustomer ? (
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
                  </TouchableOpacity>
                </View>

                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Product *</Text>
                  <TextInput
                    style={styles.formInput}
                    value={orderProduct}
                    onChangeText={setOrderProduct}
                    placeholder="e.g., Laptop, Phone, etc."
                    placeholderTextColor="#666"
                  />
                </View>

                <View style={styles.formRow}>
                  <View style={[styles.formGroup, { flex: 1, marginRight: 8 }]}>
                    <Text style={styles.formLabel}>Quantity *</Text>
                    <TextInput
                      style={styles.formInput}
                      value={orderQuantity}
                      onChangeText={setOrderQuantity}
                      placeholder="1"
                      placeholderTextColor="#666"
                      keyboardType="numeric"
                    />
                  </View>
                  <View style={[styles.formGroup, { flex: 1, marginLeft: 8 }]}>
                    <Text style={styles.formLabel}>Price ({currency}) *</Text>
                    <TextInput
                      style={styles.formInput}
                      value={orderPrice}
                      onChangeText={setOrderPrice}
                      placeholder="0"
                      placeholderTextColor="#666"
                      keyboardType="numeric"
                    />
                  </View>
                </View>

                {!!orderQuantity && !!orderPrice && parseInt(orderQuantity) > 0 && parseFloat(orderPrice) > 0 ? (
                  <View style={styles.totalDisplay}>
                    <Text style={styles.totalLabel}>Total Amount:</Text>
                    <Text style={styles.totalValue}>
                      {currency} {(parseInt(orderQuantity) * parseFloat(orderPrice)).toLocaleString()}
                    </Text>
                  </View>
                ) : null}

                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Notes (Optional)</Text>
                  <TextInput
                    style={[styles.formInput, styles.receiptMessageInput]}
                    value={orderNotes}
                    onChangeText={setOrderNotes}
                    placeholder="e.g., Customer requested blue color"
                    placeholderTextColor="#666"
                    multiline
                    numberOfLines={3}
                    textAlignVertical="top"
                  />
                </View>

                <View style={styles.formGroup}>
                  <Text style={styles.formLabel}>Due Date (Optional)</Text>
                  <TouchableOpacity
                    style={styles.formInput}
                    onPress={() => {
                      setTempOrderDueDate(orderDueDate ? new Date(orderDueDate) : new Date());
                      setShowOrderDueDatePicker(true);
                    }}
                  >
                    <Text style={!!orderDueDate ? styles.dateText : styles.datePlaceholder}>
                      {orderDueDate ? new Date(orderDueDate).toLocaleDateString() : 'Select due date'}
                    </Text>
                  </TouchableOpacity>

                  {showOrderDueDatePicker && (
                    <DateTimePicker
                      value={tempOrderDueDate}
                      mode="date"
                      display="default"
                      onChange={(event, selectedDate) => {
                        setShowOrderDueDatePicker(false);
                        if (event.type === 'set' && selectedDate) {
                          setOrderDueDate(selectedDate.toISOString());
                        }
                      }}
                      minimumDate={new Date()}
                    />
                  )}

                  {!!orderDueDate && (
                    <TouchableOpacity
                      onPress={() => setOrderDueDate('')}
                      style={{ marginTop: 8, alignSelf: 'flex-start' }}
                    >
                      <Text style={{ color: '#FF4444', fontSize: 12 }}>Clear Due Date</Text>
                    </TouchableOpacity>
                  )}
                </View>
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Customer Select Modal */}
      <Modal
        visible={customerSelectVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => {
          setCustomerSelectVisible(false);
          setCustomerSearchQuery('');
        }}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => {
              setCustomerSelectVisible(false);
              setCustomerSearchQuery('');
            }}>
              <Text style={styles.modalCancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Select Customer</Text>
            <View style={{ width: 60 }} />
          </View>

          {/* Search Input */}
          <View style={styles.searchContainer}>
            <Ionicons name="search" size={20} color="#666" style={styles.searchIcon} />
            <TextInput
              style={styles.searchInput}
              placeholder="Search by name or phone..."
              placeholderTextColor="#666"
              value={customerSearchQuery}
              onChangeText={setCustomerSearchQuery}
              autoCapitalize="none"
            />
            {customerSearchQuery.length > 0 && (
              <TouchableOpacity onPress={() => setCustomerSearchQuery('')}>
                <Ionicons name="close-circle" size={20} color="#666" />
              </TouchableOpacity>
            )}
          </View>

          {/* Walk-in Customer Button */}
          <TouchableOpacity
            style={styles.walkInButton}
            onPress={() => {
              setIsWalkInCustomer(true);
              setSelectedCustomer(null);
              setSendReceipt(false);
              setCustomerSelectVisible(false);
              setCustomerSearchQuery('');
            }}
          >
            <Ionicons name="walk-outline" size={24} color="#25D366" />
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={styles.walkInButtonText}>Walk-in Customer</Text>
              <Text style={styles.walkInButtonSubtext}>Quick sale without customer details</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#666" />
          </TouchableOpacity>

          <FlatList
            data={customers.filter((c) => {
              if (!customerSearchQuery.trim()) return true;
              const query = customerSearchQuery.toLowerCase();
              return (
                c.name.toLowerCase().includes(query) ||
                c.phone_number.toLowerCase().includes(query)
              );
            })}
            renderItem={({ item: customer }) => (
              <TouchableOpacity
                style={styles.customerOption}
                onPress={() => {
                  setSelectedCustomer(customer);
                  setIsWalkInCustomer(false);
                  setSendReceipt(true);
                  setCustomerSelectVisible(false);
                  setCustomerSearchQuery('');
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

      {/* Sale Details Modal */}
      <Modal
        visible={saleDetailsVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setSaleDetailsVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setSaleDetailsVisible(false)}>
              <Text style={styles.modalCancel}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Sale Details</Text>
            <View style={{ width: 60 }} />
          </View>

          {selectedSale && (
            <ScrollView style={styles.modalContent}>
              <View style={styles.detailsCard}>
                <View style={styles.detailsHeader}>
                  <View style={styles.avatar}>
                    <Text style={styles.avatarText}>{selectedSale.customer_name.charAt(0)}</Text>
                  </View>
                  <View style={styles.detailsHeaderInfo}>
                    <Text style={styles.detailsCustomerName}>{selectedSale.customer_name}</Text>
                    <Text style={styles.detailsPhone}>{selectedSale.customer_phone}</Text>
                  </View>
                </View>

                <View style={styles.detailsDivider} />

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Item</Text>
                  <Text style={styles.detailsValue}>{selectedSale.item}</Text>
                </View>

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Amount</Text>
                  <Text style={[styles.detailsValue, styles.detailsAmount]}>
                    {currency} {selectedSale.amount.toLocaleString()}
                  </Text>
                </View>

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Payment Method</Text>
                  <View style={[styles.paymentBadge, selectedSale.payment_method === 'M-Pesa' && styles.mpesaBadge]}>
                    <Text style={styles.paymentText}>{selectedSale.payment_method || 'Credit'}</Text>
                  </View>
                </View>

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Date & Time</Text>
                  <Text style={styles.detailsValue}>
                    {new Date(selectedSale.created_at).toLocaleString('en-KE', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </Text>
                </View>

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Receipt Status</Text>
                  <View style={styles.receiptStatus}>
                    <Ionicons
                      name={selectedSale.receipt_sent ? 'checkmark-circle' : 'close-circle'}
                      size={16}
                      color={selectedSale.receipt_sent ? '#25D366' : '#666'}
                    />
                    <Text
                      style={[
                        styles.receiptStatusText,
                        !!selectedSale.receipt_sent && styles.receiptStatusTextSent,
                      ]}
                    >
                      {selectedSale.receipt_sent ? 'Sent' : 'Not sent'}
                    </Text>
                  </View>
                </View>

                {/* Credit Sale Information */}
                {!!selectedSale.is_credit && (
                  <>
                    <View style={styles.detailsRow}>
                      <Text style={styles.detailsLabel}>Sale Type</Text>
                      <View style={styles.creditBadge}>
                        <Text style={styles.paymentText}>Credit Sale</Text>
                      </View>
                    </View>

                    {!!selectedSale.due_date && (
                      <View style={styles.detailsRow}>
                        <Text style={styles.detailsLabel}>Due Date</Text>
                        <Text style={styles.detailsValue}>
                          {new Date(selectedSale.due_date).toLocaleDateString('en-KE', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                          })}
                        </Text>
                      </View>
                    )}

                    <View style={styles.detailsRow}>
                      <Text style={styles.detailsLabel}>Payment Status</Text>
                      <View style={styles.receiptStatus}>
                        <Ionicons
                          name={selectedSale.paid_date ? 'checkmark-circle' : 'time-outline'}
                          size={16}
                          color={selectedSale.paid_date ? '#25D366' : '#FF8C00'}
                        />
                        <Text
                          style={[
                            styles.receiptStatusText,
                            !!selectedSale.paid_date && styles.receiptStatusTextSent,
                          ]}
                        >
                          {selectedSale.paid_date ? 'Paid' : 'Unpaid'}
                        </Text>
                      </View>
                    </View>

                    {!!selectedSale.paid_date && (
                      <View style={styles.detailsRow}>
                        <Text style={styles.detailsLabel}>Paid On</Text>
                        <Text style={styles.detailsValue}>
                          {new Date(selectedSale.paid_date).toLocaleDateString('en-KE', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                          })}
                        </Text>
                      </View>
                    )}
                  </>
                )}
              </View>

              {!selectedSale.receipt_sent && (
                <TouchableOpacity
                  style={styles.resendButton}
                  onPress={() => handleResendReceipt(selectedSale)}
                >
                  <Ionicons name="paper-plane-outline" size={20} color="#FFFFFF" />
                  <Text style={styles.resendButtonText}>Send Receipt</Text>
                </TouchableOpacity>
              )}

              {/* Mark as Paid Button for Unpaid Credit Sales */}
              {!!selectedSale.is_credit && !selectedSale.paid_date && (
                <TouchableOpacity
                  style={[styles.resendButton, { backgroundColor: '#25D366', marginTop: 12 }]}
                  onPress={() => handleMarkAsPaid(selectedSale)}
                >
                  <Ionicons name="cash-outline" size={20} color="#FFFFFF" />
                  <Text style={styles.resendButtonText}>Mark as Paid</Text>
                </TouchableOpacity>
              )}
            </ScrollView>
          )}
        </SafeAreaView>
      </Modal>

      {/* Order Details Modal */}
      <Modal
        visible={orderDetailsVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setOrderDetailsVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setOrderDetailsVisible(false)}>
              <Ionicons name="close" size={28} color="#888" />
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Order Details</Text>
            <TouchableOpacity onPress={async () => {
              if (!selectedOrder) return;
              Alert.alert(
                'Delete Order',
                'Are you sure you want to delete this order?',
                [
                  { text: 'Cancel', style: 'cancel' },
                  {
                    text: 'Delete',
                    style: 'destructive',
                    onPress: async () => {
                      try {
                        await apiClient.delete(`/orders/${selectedOrder.id}`);
                        setOrders(orders.filter(o => o.id !== selectedOrder.id));
                        setOrderDetailsVisible(false);
                        Alert.alert('Success', 'Order deleted');
                      } catch (error) {
                        Alert.alert('Error', 'Failed to delete order');
                      }
                    },
                  },
                ]
              );
            }}>
              <Ionicons name="trash-outline" size={24} color="#FF6B6B" />
            </TouchableOpacity>
          </View>

          {selectedOrder && (
            <ScrollView style={styles.modalContent}>
              <View style={styles.detailsCard}>
                <View style={styles.detailsHeader}>
                  <View style={styles.avatar}>
                    <Text style={styles.avatarText}>{selectedOrder.customer_name.charAt(0)}</Text>
                  </View>
                  <View style={styles.detailsHeaderInfo}>
                    <Text style={styles.detailsCustomerName}>{selectedOrder.customer_name}</Text>
                    <Text style={styles.detailsPhone}>{selectedOrder.customer_phone}</Text>
                  </View>
                </View>

                <View style={styles.detailsDivider} />

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Product</Text>
                  <Text style={styles.detailsValue}>{selectedOrder.product}</Text>
                </View>

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Quantity</Text>
                  <Text style={styles.detailsValue}>{selectedOrder.quantity}</Text>
                </View>

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Price per unit</Text>
                  <Text style={styles.detailsValue}>{currency} {selectedOrder.price.toLocaleString()}</Text>
                </View>

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Total Amount</Text>
                  <Text style={[styles.detailsValue, { fontSize: 18, fontWeight: 'bold', color: '#25D366' }]}>
                    {currency} {selectedOrder.total_amount.toLocaleString()}
                  </Text>
                </View>

                <View style={styles.detailsDivider} />

                {/* Payment Status Update */}
                <View style={{ marginBottom: 16 }}>
                  <Text style={[styles.detailsLabel, { marginBottom: 8 }]}>Payment Status</Text>
                  <View style={styles.statusUpdateContainer}>
                    {['Pending', 'Partial', 'Paid'].map((status) => (
                      <TouchableOpacity
                        key={status}
                        style={[
                          styles.statusOption,
                          selectedOrder.payment_status === status && styles.statusOptionActive,
                        ]}
                        onPress={async () => {
                          try {
                            const response = await apiClient.put(`/orders/${selectedOrder.id}?payment_status=${status}`);
                            setOrders(orders.map(o => o.id === selectedOrder.id ? response.data : o));
                            setSelectedOrder(response.data);
                            Alert.alert('Success', 'Payment status updated');
                          } catch (error) {
                            Alert.alert('Error', 'Failed to update status');
                          }
                        }}
                      >
                        <Text style={[
                          styles.statusOptionText,
                          selectedOrder.payment_status === status && styles.statusOptionTextActive,
                        ]}>
                          {status}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>

                {/* Delivery Status Update */}
                <View style={{ marginBottom: 16 }}>
                  <Text style={[styles.detailsLabel, { marginBottom: 8 }]}>Delivery Status</Text>
                  <View style={styles.statusUpdateContainer}>
                    {['Processing', 'Shipped', 'Delivered'].map((status) => (
                      <TouchableOpacity
                        key={status}
                        style={[
                          styles.statusOption,
                          selectedOrder.delivery_status === status && styles.statusOptionActive,
                        ]}
                        onPress={async () => {
                          try {
                            const response = await apiClient.put(`/orders/${selectedOrder.id}?delivery_status=${status}`);
                            setOrders(orders.map(o => o.id === selectedOrder.id ? response.data : o));
                            setSelectedOrder(response.data);
                            Alert.alert('Success', 'Delivery status updated');
                          } catch (error) {
                            Alert.alert('Error', 'Failed to update status');
                          }
                        }}
                      >
                        <Text style={[
                          styles.statusOptionText,
                          selectedOrder.delivery_status === status && styles.statusOptionTextActive,
                        ]}>
                          {status}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>

                {/* Convert to Sale Button (only for paid orders) */}
                {selectedOrder.payment_status === 'Paid' && (
                  <>
                    <View style={styles.detailsDivider} />
                    <TouchableOpacity
                      style={[styles.convertButton, { marginHorizontal: 0, marginBottom: 16 }]}
                      onPress={() => {
                        Alert.alert(
                          'Convert to Sale',
                          'This will convert the order to a sale and remove it from orders. Choose payment method:',
                          [
                            ...paymentMethods.map((method) => ({
                              text: method,
                              onPress: async () => {
                                try {
                                  await apiClient.post(`/orders/${selectedOrder.id}/convert-to-sale?payment_method=${encodeURIComponent(method)}`);
                                  setOrders(orders.filter(o => o.id !== selectedOrder.id));
                                  setOrderDetailsVisible(false);
                                  Alert.alert('Success', 'Order converted to sale!');
                                  fetchData();
                                } catch (error: any) {
                                  Alert.alert('Error', error.response?.data?.detail || 'Failed to convert order');
                                }
                              },
                            })),
                            { text: 'Cancel', style: 'cancel' },
                          ]
                        );
                      }}
                    >
                      <Ionicons name="checkmark-circle-outline" size={20} color="#FFFFFF" />
                      <Text style={styles.convertButtonText}>Convert to Sale</Text>
                    </TouchableOpacity>
                  </>
                )}

                {!!selectedOrder.notes && (
                  <>
                    <View style={styles.detailsDivider} />
                    <View style={styles.detailsRow}>
                      <Text style={styles.detailsLabel}>Notes</Text>
                      <Text style={styles.detailsValue}>{selectedOrder.notes}</Text>
                    </View>
                  </>
                )}

                {!!selectedOrder.due_date && (
                  <View style={styles.detailsRow}>
                    <Text style={styles.detailsLabel}>Due Date</Text>
                    <Text style={styles.detailsValue}>
                      {new Date(selectedOrder.due_date).toLocaleDateString('en-KE')}
                    </Text>
                  </View>
                )}

                <View style={styles.detailsRow}>
                  <Text style={styles.detailsLabel}>Created</Text>
                  <Text style={styles.detailsValue}>
                    {new Date(selectedOrder.created_at).toLocaleString('en-KE', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </Text>
                </View>
              </View>
            </ScrollView>
          )}
        </SafeAreaView>
      </Modal>

      {/* Payment Method Settings Modal */}
      <Modal
        visible={paymentSettingsVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setPaymentSettingsVisible(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setPaymentSettingsVisible(false)}>
              <Text style={styles.modalCancel}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Payment Methods</Text>
            <View style={{ width: 60 }} />
          </View>

          <ScrollView style={styles.modalContent}>
            <Text style={styles.settingsHint}>
              Manage the payment methods available when recording sales
            </Text>

            {paymentMethods.map((method, index) => (
              <View key={index} style={styles.paymentMethodItem}>
                <Text style={styles.paymentMethodName}>{method}</Text>
                {paymentMethods.length > 1 && (
                  <TouchableOpacity
                    onPress={async () => {
                      const updated = paymentMethods.filter((_, i) => i !== index);
                      setPaymentMethods(updated);
                      try {
                        await apiClient.put('/settings', { payment_methods: updated });
                        Alert.alert('Success', 'Payment method removed');
                      } catch (error) {
                        console.error('Error updating payment methods:', error);
                        Alert.alert('Error', 'Failed to update payment methods');
                      }
                    }}
                  >
                    <Ionicons name="close-circle" size={24} color="#FF6B6B" />
                  </TouchableOpacity>
                )}
              </View>
            ))}

            {!addingPaymentMethod && paymentMethods.length < 3 && (
              <TouchableOpacity
                style={styles.addPaymentButton}
                onPress={() => setAddingPaymentMethod(true)}
              >
                <Ionicons name="add-circle-outline" size={24} color="#25D366" />
                <Text style={styles.addPaymentText}>Add Payment Method</Text>
              </TouchableOpacity>
            )}

            {paymentMethods.length >= 3 && !addingPaymentMethod && (
              <View style={styles.maxMethodsNotice}>
                <Ionicons name="information-circle" size={20} color="#FFD700" />
                <Text style={styles.maxMethodsText}>
                  Maximum of 3 payment methods. Remove one to add another.
                </Text>
              </View>
            )}

            {addingPaymentMethod && (
              <View style={styles.addPaymentForm}>
                <TextInput
                  style={styles.formInput}
                  value={newPaymentMethod}
                  onChangeText={setNewPaymentMethod}
                  placeholder="e.g., Credit Card, PayPal"
                  placeholderTextColor="#666"
                  autoFocus
                />
                <View style={styles.addPaymentActions}>
                  <TouchableOpacity
                    style={styles.cancelAddButton}
                    onPress={() => {
                      setAddingPaymentMethod(false);
                      setNewPaymentMethod('');
                    }}
                  >
                    <Text style={styles.cancelAddText}>Cancel</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.saveAddButton}
                    onPress={async () => {
                      if (!newPaymentMethod.trim()) {
                        Alert.alert('Error', 'Please enter a payment method name');
                        return;
                      }
                      const updated = [...paymentMethods, newPaymentMethod.trim()];
                      setPaymentMethods(updated);
                      try {
                        await apiClient.put('/settings', { payment_methods: updated });
                        Alert.alert('Success', 'Payment method added');
                        setAddingPaymentMethod(false);
                        setNewPaymentMethod('');
                      } catch (error) {
                        console.error('Error updating payment methods:', error);
                        Alert.alert('Error', 'Failed to add payment method');
                      }
                    }}
                  >
                    <Text style={styles.saveAddText}>Add</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </ScrollView>
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
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#2A3952',
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
    flex: 1,
    marginRight: 8,
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
  creditBadge: {
    backgroundColor: '#FF8C00',
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
  exportButton: {
    padding: 8,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    marginHorizontal: 20,
    borderRadius: 14,
    paddingHorizontal: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#2A3952',
  },
  searchIcon: {
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    paddingVertical: 12,
    fontSize: 16,
    color: '#FFFFFF',
  },
  filterContainer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 12,
    gap: 8,
  },
  filterChip: {
    flex: 1,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#1A2942',
    borderWidth: 1,
    borderColor: '#2A3952',
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterChipActive: {
    backgroundColor: '#25D366',
    borderColor: '#25D366',
  },
  filterChipText: {
    fontSize: 12,
    color: '#888',
    fontWeight: '600',
  },
  filterChipTextActive: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
  analyticsContainer: {
    paddingHorizontal: 20,
    flexDirection: 'row',
    marginBottom: 16,
  },
  analyticsCard: {
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 12,
    paddingVertical: 10,
    flex: 1,
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#2A3952',
  },
  analyticsCardWide: {
    flex: 1,
  },
  analyticsLabel: {
    fontSize: 10,
    color: '#888',
    marginBottom: 4,
    fontWeight: '500',
  },
  analyticsValue: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#FFFFFF',
    letterSpacing: 0.3,
    flexWrap: 'wrap',
  },
  analyticsSubtext: {
    fontSize: 10,
    color: '#25D366',
    marginTop: 2,
    fontWeight: '500',
  },
  detailsCard: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#2A3952',
  },
  detailsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
  },
  detailsHeaderInfo: {
    flex: 1,
  },
  detailsCustomerName: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  detailsPhone: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },
  detailsDivider: {
    height: 1,
    backgroundColor: '#2A3952',
    marginBottom: 16,
  },
  detailsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  detailsLabel: {
    fontSize: 14,
    color: '#888',
  },
  detailsValue: {
    fontSize: 16,
    color: '#FFFFFF',
    fontWeight: '500',
  },
  detailsAmount: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#25D366',
  },
  receiptStatus: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  receiptStatusText: {
    fontSize: 14,
    color: '#666',
    marginLeft: 6,
  },
  receiptStatusTextSent: {
    color: '#25D366',
  },
  resendButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    borderRadius: 14,
    padding: 18,
    gap: 10,
    shadowColor: '#25D366',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  resendButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
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
  receiptPreviewHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  receiptPreviewTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#666',
  },
  receiptPreviewText: {
    fontSize: 14,
    color: '#FFFFFF',
    lineHeight: 22,
  },
  receiptEditHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  doneButton: {
    fontSize: 16,
    fontWeight: '600',
    color: '#25D366',
  },
  receiptMessageInput: {
    minHeight: 100,
    paddingTop: 14,
  },
  receiptHint: {
    fontSize: 12,
    color: '#888',
    marginTop: 8,
    fontStyle: 'italic',
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
  walkInButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 20,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#25D366',
  },
  walkInButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  walkInButtonSubtext: {
    fontSize: 12,
    color: '#888',
    marginTop: 2,
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
  headerActions: {
    flexDirection: 'row',
    gap: 12,
  },
  settingsHint: {
    fontSize: 14,
    color: '#888',
    marginBottom: 20,
    paddingHorizontal: 20,
    lineHeight: 20,
  },
  paymentMethodItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 20,
    marginBottom: 12,
  },
  paymentMethodName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  addPaymentButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 20,
    marginTop: 8,
    gap: 8,
  },
  addPaymentText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#25D366',
  },
  maxMethodsNotice: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2A2416',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 20,
    marginTop: 8,
    gap: 12,
    borderWidth: 1,
    borderColor: '#FFD700',
  },
  maxMethodsText: {
    flex: 1,
    fontSize: 14,
    color: '#FFD700',
    lineHeight: 20,
  },
  addPaymentForm: {
    marginHorizontal: 20,
    marginTop: 8,
  },
  addPaymentActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 12,
  },
  cancelAddButton: {
    flex: 1,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  cancelAddText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#888',
  },
  saveAddButton: {
    flex: 1,
    backgroundColor: '#25D366',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  saveAddText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  viewToggle: {
    flexDirection: 'row',
    marginHorizontal: 20,
    marginBottom: 16,
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 4,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 8,
  },
  toggleButtonActive: {
    backgroundColor: '#25D366',
  },
  toggleText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#888',
  },
  toggleTextActive: {
    color: '#FFFFFF',
  },
  expenseCard: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 16,
    marginHorizontal: 20,
    marginBottom: 12,
  },
  expenseHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  expenseInfo: {
    flex: 1,
  },
  categoryBadge: {
    backgroundColor: '#4A90D9',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
    alignSelf: 'flex-start',
    marginBottom: 8,
  },
  categoryText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  expenseDate: {
    fontSize: 12,
    color: '#666',
  },
  expenseAmountContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  expenseAmount: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  expenseDescription: {
    fontSize: 14,
    color: '#888',
    marginTop: 12,
    lineHeight: 20,
  },
  categoryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  categoryOption: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: '#1A2942',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2A3952',
  },
  categoryOptionSelected: {
    backgroundColor: '#25D366',
    borderColor: '#25D366',
  },
  categoryOptionText: {
    fontSize: 14,
    color: '#888',
    fontWeight: '500',
  },
  categoryOptionTextSelected: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    alignSelf: 'flex-start',
  },
  statusBadgeText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  formRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  totalDisplay: {
    backgroundColor: '#1A2942',
    padding: 16,
    borderRadius: 12,
    marginBottom: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  totalLabel: {
    fontSize: 16,
    color: '#888',
  },
  totalValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#25D366',
  },
  dateText: {
    color: '#FFFFFF',
  },
  datePlaceholder: {
    color: '#666',
  },
  categoryScroll: {
    marginTop: 8,
  },
  statusUpdateContainer: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  statusOption: {
    flex: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#1A2942',
    borderWidth: 1,
    borderColor: '#2A3952',
    alignItems: 'center',
  },
  statusOptionActive: {
    backgroundColor: '#25D366',
    borderColor: '#25D366',
  },
  statusOptionText: {
    fontSize: 14,
    color: '#888',
  },
  statusOptionTextActive: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  convertButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    padding: 16,
    borderRadius: 12,
    marginHorizontal: 20,
    marginBottom: 20,
    gap: 8,
  },
  convertButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
});
