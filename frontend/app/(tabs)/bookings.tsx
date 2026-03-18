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
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiClient, bookingsAPI, productsAPI } from '../../context/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface BookingAddon {
  name: string;
  price: number;
}

interface Booking {
  id: string;
  booking_number: string;
  customer_id: string;
  customer_name: string;
  customer_phone?: string;
  service_id: string;
  service_name: string;
  service_category?: string;
  staff_name?: string;
  date: string;
  time: string;
  end_time?: string;
  duration?: number;
  checkin_date?: string;
  checkout_date?: string;
  nights?: number;
  addons?: BookingAddon[];
  total_price?: number;
  status: 'pending' | 'confirmed' | 'completed' | 'cancelled' | 'no_show';
  payment_status: 'unpaid' | 'partial' | 'paid';
  price: number;
  notes?: string;
  source?: string;
  last_reminder_at?: string;
  created_at: string;
}

interface Service {
  id: string;
  name: string;
  price: number;
  duration?: number;
  offering_type?: string;
}

interface Customer {
  id: string;
  name: string;
  phone_number: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS_FILTERS = ['All', 'pending', 'confirmed', 'completed', 'cancelled'];

const STATUS_COLORS: Record<string, string> = {
  pending:   '#F59E0B',
  confirmed: '#10B981',
  completed: '#6366F1',
  cancelled: '#EF4444',
  no_show:   '#9CA3AF',
};

const PAYMENT_COLORS: Record<string, string> = {
  unpaid:  '#EF4444',
  partial: '#F59E0B',
  paid:    '#10B981',
};

const STATUS_LABELS: Record<string, string> = {
  pending:   'Pending',
  confirmed: 'Confirmed',
  completed: 'Completed',
  cancelled: 'Cancelled',
  no_show:   'No Show',
};

const PAYMENT_LABELS: Record<string, string> = {
  unpaid:  'Unpaid',
  partial: 'Partial',
  paid:    'Paid',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${dd}`;
}

function formatDisplayDate(dateStr: string): string {
  if (!dateStr) return '';
  const [y, m, d] = dateStr.split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${d} ${months[parseInt(m) - 1]} ${y}`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={[styles.statCard, { borderLeftColor: color }]}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function BookingCard({ booking, onPress }: { booking: Booking; onPress: () => void }) {
  const statusColor = STATUS_COLORS[booking.status] || '#9CA3AF';
  const payColor = PAYMENT_COLORS[booking.payment_status] || '#9CA3AF';
  const isToday = booking.date === formatDate(new Date());
  const isWhatsApp = booking.source === 'whatsapp';

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.cardLeft}>
        <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
      </View>
      <View style={styles.cardBody}>
        <View style={styles.cardTopRow}>
          <Text style={styles.customerName} numberOfLines={1}>{booking.customer_name}</Text>
          {isToday && <View style={styles.todayBadge}><Text style={styles.todayBadgeText}>Today</Text></View>}
          {isWhatsApp && <View style={styles.waBadge}><Text style={styles.waBadgeText}>WhatsApp</Text></View>}
        </View>
        <Text style={styles.serviceName} numberOfLines={1}>{booking.service_name}</Text>
        <View style={styles.cardMetaRow}>
          <Ionicons name="calendar-outline" size={12} color="#94A3B8" />
          {booking.service_category === 'rental' && booking.checkin_date ? (
            <Text style={styles.metaText}>
              {formatDisplayDate(booking.checkin_date)}{booking.checkout_date ? ` → ${formatDisplayDate(booking.checkout_date)}` : ''}
              {booking.nights ? ` · ${booking.nights}n` : ''}
            </Text>
          ) : (
            <>
              <Text style={styles.metaText}>{formatDisplayDate(booking.date)}</Text>
              <Ionicons name="time-outline" size={12} color="#94A3B8" style={{ marginLeft: 8 }} />
              <Text style={styles.metaText}>{booking.time}{booking.end_time ? ` – ${booking.end_time}` : ''}</Text>
            </>
          )}
        </View>
        {booking.addons && booking.addons.length > 0 && (
          <Text style={styles.addonsText} numberOfLines={1}>
            +{booking.addons.map(a => a.name).join(', ')}
          </Text>
        )}
      </View>
      <View style={styles.cardRight}>
        <View style={[styles.statusChip, { backgroundColor: statusColor + '22' }]}>
          <Text style={[styles.statusChipText, { color: statusColor }]}>{STATUS_LABELS[booking.status] || booking.status}</Text>
        </View>
        <View style={[styles.payChip, { backgroundColor: payColor + '22' }]}>
          <Text style={[styles.payChipText, { color: payColor }]}>{PAYMENT_LABELS[booking.payment_status] || booking.payment_status}</Text>
        </View>
      </View>
    </TouchableOpacity>
  );
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function BookingsScreen() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statusFilter, setStatusFilter] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');

  // New booking modal
  const [showNewModal, setShowNewModal] = useState(false);
  const [customerSelectVisible, setCustomerSelectVisible] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [isWalkInCustomer, setIsWalkInCustomer] = useState(false);
  const [customerSearchQuery, setCustomerSearchQuery] = useState('');
  const [newBooking, setNewBooking] = useState({
    customer_id: '',
    customer_name: '',
    service_id: '',
    service_name: '',
    date: formatDate(new Date()),
    time: '09:00',
    notes: '',
  });
  const [saving, setSaving] = useState(false);

  // Detail modal
  const [selectedBooking, setSelectedBooking] = useState<Booking | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [sendingReminder, setSendingReminder] = useState(false);

  // ── Data ────────────────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    try {
      const [bookingsData, productsData, customersRes] = await Promise.all([
        bookingsAPI.getBookings(),
        productsAPI.getProducts(),
        apiClient.get('/customers'),
      ]);
      setBookings(bookingsData || []);
      const all = productsData || [];
      const svcList = all.filter((p: Service) =>
        ['service', 'class', 'appointment', 'consultation'].includes(p.offering_type || '')
      );
      setServices(svcList.length > 0 ? svcList : all);
      setCustomers(customersRes.data || []);
    } catch (err) {
      console.error('Bookings load error:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Filters ─────────────────────────────────────────────────────────────────

  const filtered = bookings
    .filter(b => {
      const matchStatus = statusFilter === 'All' || b.status === statusFilter;
      const q = searchQuery.toLowerCase();
      const matchSearch = !q ||
        b.customer_name?.toLowerCase().includes(q) ||
        b.service_name?.toLowerCase().includes(q) ||
        b.booking_number?.toLowerCase().includes(q);
      return matchStatus && matchSearch;
    })
    .sort((a, b) => {
      const ta = new Date(`${a.date}T${a.time}`).getTime();
      const tb = new Date(`${b.date}T${b.time}`).getTime();
      return ta - tb;
    });

  const filteredCustomers = customers.filter(c => {
    if (!customerSearchQuery.trim()) return true;
    const q = customerSearchQuery.toLowerCase();
    return c.name?.toLowerCase().includes(q) || c.phone_number?.toLowerCase().includes(q);
  });

  // ── Create ──────────────────────────────────────────────────────────────────

  const handleCreate = async () => {
    if (!isWalkInCustomer && !selectedCustomer) {
      Alert.alert('Missing Fields', 'Please select a customer.');
      return;
    }
    if (!newBooking.service_id) {
      Alert.alert('Missing Fields', 'Please select a service.');
      return;
    }
    if (!newBooking.date || !newBooking.time) {
      Alert.alert('Missing Fields', 'Please set a date and time.');
      return;
    }
    setSaving(true);
    try {
      const svc = services.find(s => s.id === newBooking.service_id);
      const payload: any = {
        service_id: newBooking.service_id,
        date: newBooking.date,
        time: newBooking.time,
        notes: newBooking.notes,
        price: svc?.price || 0,
      };
      if (isWalkInCustomer) {
        payload.customer_name = 'Walk-in Customer';
      } else {
        payload.customer_id = selectedCustomer!.id;
      }
      await bookingsAPI.createBooking(payload);
      setShowNewModal(false);
      setNewBooking({ customer_id: '', customer_name: '', service_id: '', service_name: '', date: formatDate(new Date()), time: '09:00', notes: '' });
      setSelectedCustomer(null);
      setIsWalkInCustomer(false);
      setCustomerSearchQuery('');
      await loadData();
    } catch (err: any) {
      Alert.alert('Error', err?.response?.data?.detail || 'Failed to create booking.');
    } finally {
      setSaving(false);
    }
  };

  // ── Update status ────────────────────────────────────────────────────────────

  const handleStatusUpdate = async (bookingId: string, status: string) => {
    setUpdatingStatus(true);
    try {
      await bookingsAPI.updateBooking(bookingId, { status });
      setBookings(prev => prev.map(b => b.id === bookingId ? { ...b, status: status as Booking['status'] } : b));
      setSelectedBooking(prev => prev?.id === bookingId ? { ...prev, status: status as Booking['status'] } : prev);
    } catch (err: any) {
      Alert.alert('Error', err?.response?.data?.detail || 'Failed to update booking.');
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handlePaymentUpdate = async (bookingId: string, payment_status: string) => {
    try {
      await bookingsAPI.updateBooking(bookingId, { payment_status });
      setBookings(prev => prev.map(b => b.id === bookingId ? { ...b, payment_status: payment_status as Booking['payment_status'] } : b));
      setSelectedBooking(prev => prev?.id === bookingId ? { ...prev, payment_status: payment_status as Booking['payment_status'] } : prev);
    } catch (err: any) {
      Alert.alert('Error', err?.response?.data?.detail || 'Failed to update payment.');
    }
  };

  const handleSendReminder = async (bookingId: string) => {
    setSendingReminder(true);
    try {
      await bookingsAPI.sendReminder(bookingId);
      const now = new Date().toISOString();
      setSelectedBooking(prev => prev ? { ...prev, last_reminder_at: now } : prev);
      Alert.alert('Reminder Sent', 'WhatsApp reminder has been sent to the customer.');
    } catch (err: any) {
      Alert.alert('Error', err?.response?.data?.detail || 'Failed to send reminder.');
    } finally {
      setSendingReminder(false);
    }
  };

  const handleDelete = (bookingId: string) => {
    Alert.alert('Delete Booking', 'Are you sure? This cannot be undone.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive',
        onPress: async () => {
          try {
            await bookingsAPI.deleteBooking(bookingId);
            setBookings(prev => prev.filter(b => b.id !== bookingId));
            setShowDetailModal(false);
          } catch (err: any) {
            Alert.alert('Error', err?.response?.data?.detail || 'Failed to delete.');
          }
        }
      }
    ]);
  };

  // ── Stats ────────────────────────────────────────────────────────────────────

  const todayStr = formatDate(new Date());
  const todayCount = bookings.filter(b => b.date === todayStr && b.status !== 'cancelled').length;

  const _now = new Date();
  // Week: Monday → Sunday of current week (includes future days)
  const _dow = _now.getDay(); // 0=Sun
  const _mondayOffset = (_dow === 0 ? -6 : 1 - _dow);
  const _weekStart = new Date(_now);
  _weekStart.setDate(_now.getDate() + _mondayOffset);
  _weekStart.setHours(0, 0, 0, 0);
  const _weekEnd = new Date(_weekStart);
  _weekEnd.setDate(_weekStart.getDate() + 6);
  const _weekStartStr = formatDate(_weekStart);
  const _weekEndStr = formatDate(_weekEnd);
  const thisWeekCount = bookings.filter(b => b.date >= _weekStartStr && b.date <= _weekEndStr && b.status !== 'cancelled').length;

  // Month: entire current calendar month (includes future dates)
  const _curYear = _now.getFullYear();
  const _curMonth = _now.getMonth() + 1;
  const thisMonthCount = bookings.filter(b => {
    const parts = b.date.split('-');
    return Number(parts[0]) === _curYear && Number(parts[1]) === _curMonth && b.status !== 'cancelled';
  }).length;

  const allTimeCount = bookings.filter(b => b.status !== 'cancelled').length;

  // ── Loading ──────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#25D366" />
        <Text style={styles.loadingText}>Loading bookings...</Text>
      </View>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      {/* Stats */}
      <View style={styles.statsRow}>
        <StatCard label="Today" value={todayCount} color="#25D366" />
        <StatCard label="This Week" value={thisWeekCount} color="#06B6D4" />
        <StatCard label="This Month" value={thisMonthCount} color="#F59E0B" />
        <StatCard label="All Time" value={allTimeCount} color="#6366F1" />
      </View>

      {/* Search + Add */}
      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={16} color="#666" />
          <TextInput
            style={styles.searchInput}
            placeholder="Search bookings..."
            placeholderTextColor="#666"
            value={searchQuery}
            onChangeText={setSearchQuery}
          />
          {searchQuery !== '' && (
            <TouchableOpacity onPress={() => setSearchQuery('')}>
              <Ionicons name="close-circle" size={16} color="#666" />
            </TouchableOpacity>
          )}
        </View>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowNewModal(true)}>
          <Ionicons name="add" size={22} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Status filter chips */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterContent}>
        {([['All','All'],['pending','Pending'],['confirmed','Confirmed'],['completed','Completed'],['cancelled','Cancelled']] as [string,string][]).map(([val, label]) => (
          <TouchableOpacity
            key={val}
            style={[styles.filterChip, statusFilter === val && styles.filterChipActive]}
            onPress={() => setStatusFilter(val)}
          >
            <Text style={[styles.filterChipText, statusFilter === val && styles.filterChipTextActive]}>
              {label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Bookings list */}
      <FlatList
        data={filtered}
        keyExtractor={item => item.id}
        renderItem={({ item }) => (
          <BookingCard
            booking={item}
            onPress={() => { setSelectedBooking(item); setShowDetailModal(true); }}
          />
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadData} tintColor="#25D366" />}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="calendar-outline" size={48} color="#334155" />
            <Text style={styles.emptyTitle}>No bookings found</Text>
            <Text style={styles.emptySubtitle}>
              {statusFilter !== 'All' ? `No ${STATUS_LABELS[statusFilter]?.toLowerCase()} bookings` : 'Tap + to create your first booking'}
            </Text>
          </View>
        }
        contentContainerStyle={filtered.length === 0 ? { flex: 1 } : { paddingBottom: 20 }}
      />

      {/* ── New Booking Modal ─────────────────────────────────────────────── */}
      <Modal visible={showNewModal} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => { setShowNewModal(false); setCustomerSearchQuery(''); }}>
              <Ionicons name="close" size={24} color="#94A3B8" />
            </TouchableOpacity>
            <Text style={styles.modalTitle}>New Booking</Text>
            <TouchableOpacity onPress={handleCreate} disabled={saving}>
              {saving
                ? <ActivityIndicator size="small" color="#25D366" />
                : <Text style={styles.saveBtn}>Save</Text>
              }
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalBody} keyboardShouldPersistTaps="handled">
            {/* Customer selection */}
            <Text style={styles.fieldLabel}>Customer *</Text>
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
                    <Text style={styles.miniAvatarText}>{selectedCustomer.name.charAt(0)}</Text>
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

            {/* Service selection */}
            <Text style={styles.fieldLabel}>Service *</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
              {services.map(s => (
                <TouchableOpacity
                  key={s.id}
                  style={[styles.serviceChip, newBooking.service_id === s.id && styles.serviceChipActive]}
                  onPress={() => setNewBooking(prev => ({ ...prev, service_id: s.id, service_name: s.name }))}
                >
                  <Text style={[styles.serviceChipText, newBooking.service_id === s.id && styles.serviceChipTextActive]}>
                    {s.name}
                  </Text>
                  {s.duration && (
                    <Text style={[styles.serviceChipSub, newBooking.service_id === s.id && { color: '#25D366' }]}>
                      {s.duration}min
                    </Text>
                  )}
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Date */}
            <Text style={styles.fieldLabel}>Date *</Text>
            <TextInput
              style={styles.input}
              placeholder="YYYY-MM-DD"
              placeholderTextColor="#475569"
              value={newBooking.date}
              onChangeText={text => setNewBooking(prev => ({ ...prev, date: text }))}
            />

            {/* Time */}
            <Text style={styles.fieldLabel}>Time *</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
              {['08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','17:00','18:00'].map(t => (
                <TouchableOpacity
                  key={t}
                  style={[styles.timeChip, newBooking.time === t && styles.timeChipActive]}
                  onPress={() => setNewBooking(prev => ({ ...prev, time: t }))}
                >
                  <Text style={[styles.timeChipText, newBooking.time === t && styles.timeChipTextActive]}>{t}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Notes */}
            <Text style={styles.fieldLabel}>Notes</Text>
            <TextInput
              style={[styles.input, { height: 80, textAlignVertical: 'top' }]}
              placeholder="Optional notes..."
              placeholderTextColor="#475569"
              value={newBooking.notes}
              onChangeText={text => setNewBooking(prev => ({ ...prev, notes: text }))}
              multiline
            />
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* ── Customer Select Modal ─────────────────────────────────────── */}
      <Modal
        visible={customerSelectVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => { setCustomerSelectVisible(false); setCustomerSearchQuery(''); }}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => { setCustomerSelectVisible(false); setCustomerSearchQuery(''); }}>
              <Text style={{ color: '#94A3B8', fontSize: 16 }}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Select Customer</Text>
            <View style={{ width: 60 }} />
          </View>

          {/* Search */}
          <View style={styles.csSearchContainer}>
            <Ionicons name="search" size={20} color="#666" style={{ marginRight: 8 }} />
            <TextInput
              style={styles.csSearchInput}
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

          {/* Walk-in option */}
          <TouchableOpacity
            style={styles.walkInButton}
            onPress={() => {
              setIsWalkInCustomer(true);
              setSelectedCustomer(null);
              setCustomerSelectVisible(false);
              setCustomerSearchQuery('');
            }}
          >
            <Ionicons name="walk-outline" size={24} color="#25D366" />
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={styles.walkInButtonText}>Walk-in Customer</Text>
              <Text style={styles.walkInButtonSubtext}>Quick booking without customer details</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#666" />
          </TouchableOpacity>

          <FlatList
            data={filteredCustomers}
            keyExtractor={item => item.id}
            contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 20 }}
            renderItem={({ item: c }) => (
              <TouchableOpacity
                style={styles.customerOption}
                onPress={() => {
                  setSelectedCustomer(c);
                  setIsWalkInCustomer(false);
                  setCustomerSelectVisible(false);
                  setCustomerSearchQuery('');
                }}
              >
                <View style={styles.miniAvatar}>
                  <Text style={styles.miniAvatarText}>{c.name.charAt(0)}</Text>
                </View>
                <View style={styles.customerOptionInfo}>
                  <Text style={styles.customerOptionName}>{c.name}</Text>
                  <Text style={styles.customerOptionPhone}>{c.phone_number}</Text>
                </View>
                {selectedCustomer?.id === c.id && (
                  <Ionicons name="checkmark-circle" size={24} color="#25D366" />
                )}
              </TouchableOpacity>
            )}
            ListEmptyComponent={
              <View style={{ alignItems: 'center', marginTop: 40 }}>
                <Text style={{ color: '#64748B', fontSize: 15 }}>No customers found</Text>
              </View>
            }
          />
        </SafeAreaView>
      </Modal>

      {/* ── Detail Modal ──────────────────────────────────────────────────── */}
      <Modal visible={showDetailModal} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => { setShowDetailModal(false); setSelectedBooking(null); }}>
              <Ionicons name="close" size={24} color="#94A3B8" />
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Booking Details</Text>
            <TouchableOpacity onPress={() => selectedBooking && handleDelete(selectedBooking.id)}>
              <Ionicons name="trash-outline" size={20} color="#EF4444" />
            </TouchableOpacity>
          </View>

          {selectedBooking && (
            <ScrollView style={styles.modalBody}>
              {/* Booking ref */}
              <View style={styles.detailSection}>
                <Text style={styles.bookingRef}>{selectedBooking.booking_number}</Text>
                <Text style={styles.detailCreated}>
                  Booked {formatDisplayDate(selectedBooking.created_at?.split('T')[0] || '')}
                </Text>
              </View>

              {/* Customer & Service */}
              <View style={styles.detailCard}>
                <DetailRow icon="person-outline" label="Customer" value={selectedBooking.customer_name} />
                {selectedBooking.customer_phone && (
                  <DetailRow icon="call-outline" label="Phone" value={selectedBooking.customer_phone} />
                )}
                <DetailRow icon="cut-outline" label="Service" value={selectedBooking.service_name} />
                {selectedBooking.staff_name && (
                  <DetailRow icon="people-outline" label="Staff" value={selectedBooking.staff_name} />
                )}
              </View>

              {/* Time / Rental Dates */}
              <View style={styles.detailCard}>
                {selectedBooking.service_category === 'rental' ? (
                  <>
                    <DetailRow icon="log-in-outline" label="Check-in" value={formatDisplayDate(selectedBooking.checkin_date || selectedBooking.date)} />
                    {selectedBooking.checkout_date && (
                      <DetailRow icon="log-out-outline" label="Check-out" value={formatDisplayDate(selectedBooking.checkout_date)} />
                    )}
                    {selectedBooking.nights ? (
                      <DetailRow icon="moon-outline" label="Nights" value={`${selectedBooking.nights} night(s)`} />
                    ) : null}
                  </>
                ) : (
                  <>
                    <DetailRow icon="calendar-outline" label="Date" value={formatDisplayDate(selectedBooking.date)} />
                    <DetailRow
                      icon="time-outline"
                      label="Time"
                      value={`${selectedBooking.time}${selectedBooking.end_time ? ` – ${selectedBooking.end_time}` : ''}${selectedBooking.duration ? ` (${selectedBooking.duration} min)` : ''}`}
                    />
                  </>
                )}
              </View>

              {/* Add-ons */}
              {selectedBooking.addons && selectedBooking.addons.length > 0 && (
                <View style={styles.detailCard}>
                  <DetailRow
                    icon="add-circle-outline"
                    label="Add-ons"
                    value={selectedBooking.addons.map(a => `${a.name}${a.price > 0 ? ` (+${a.price.toLocaleString()})` : ''}`).join(', ')}
                  />
                </View>
              )}

              {/* Price */}
              <View style={styles.detailCard}>
                <DetailRow icon="cash-outline" label="Price" value={`${(selectedBooking.total_price || selectedBooking.price) > 0 ? (selectedBooking.total_price || selectedBooking.price).toLocaleString() : 'Not set'}`} />
              </View>

              {selectedBooking.notes && (
                <View style={styles.detailCard}>
                  <DetailRow icon="document-text-outline" label="Notes" value={selectedBooking.notes} />
                </View>
              )}

              {/* Send Reminder */}
              {selectedBooking.customer_phone && (
                <TouchableOpacity
                  style={styles.reminderBtn}
                  onPress={() => handleSendReminder(selectedBooking.id)}
                  disabled={sendingReminder}
                >
                  {sendingReminder
                    ? <ActivityIndicator size="small" color="#25D366" />
                    : <Ionicons name="notifications-outline" size={16} color="#25D366" />
                  }
                  <Text style={styles.reminderBtnText}>
                    {sendingReminder ? 'Sending…' : 'Send WhatsApp Reminder'}
                  </Text>
                  {selectedBooking.last_reminder_at && (
                    <Text style={styles.reminderSentAt}>
                      Last: {formatDisplayDate(selectedBooking.last_reminder_at.split('T')[0])}
                    </Text>
                  )}
                </TouchableOpacity>
              )}

              {/* Status update */}
              <Text style={styles.sectionTitle}>Booking Status</Text>
              <View style={styles.statusGrid}>
                {(['pending','confirmed','completed','cancelled','no_show'] as const).map(s => (
                  <TouchableOpacity
                    key={s}
                    style={[
                      styles.statusOption,
                      selectedBooking.status === s && { borderColor: STATUS_COLORS[s], backgroundColor: STATUS_COLORS[s] + '22' }
                    ]}
                    onPress={() => handleStatusUpdate(selectedBooking.id, s)}
                    disabled={updatingStatus}
                  >
                    <Text style={[styles.statusOptionText, selectedBooking.status === s && { color: STATUS_COLORS[s] }]}>
                      {STATUS_LABELS[s]}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Payment status */}
              <Text style={styles.sectionTitle}>Payment Status</Text>
              <View style={styles.paymentRow}>
                {(['unpaid','partial','paid'] as const).map(p => (
                  <TouchableOpacity
                    key={p}
                    style={[
                      styles.payOption,
                      selectedBooking.payment_status === p && { borderColor: PAYMENT_COLORS[p], backgroundColor: PAYMENT_COLORS[p] + '22' }
                    ]}
                    onPress={() => handlePaymentUpdate(selectedBooking.id, p)}
                  >
                    <Text style={[styles.payOptionText, selectedBooking.payment_status === p && { color: PAYMENT_COLORS[p] }]}>
                      {PAYMENT_LABELS[p]}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

// ── Small helpers ─────────────────────────────────────────────────────────────

function DetailRow({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <View style={styles.detailRow}>
      <Ionicons name={icon as any} size={16} color="#64748B" style={{ width: 20 }} />
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue} numberOfLines={2}>{value}</Text>
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A1628' },
  centered: { flex: 1, backgroundColor: '#0A1628', alignItems: 'center', justifyContent: 'center' },
  loadingText: { color: '#64748B', marginTop: 12, fontSize: 14 },

  // Stats
  statsRow: { flexDirection: 'row', padding: 12, gap: 8 },
  statCard: {
    flex: 1, backgroundColor: '#0F1E35', borderRadius: 10, padding: 10,
    borderLeftWidth: 3, alignItems: 'center',
  },
  statValue: { fontSize: 22, fontWeight: 'bold' },
  statLabel: { color: '#64748B', fontSize: 11, marginTop: 2 },

  // Search row
  searchRow: { flexDirection: 'row', paddingHorizontal: 12, paddingBottom: 8, gap: 8 },
  searchBox: {
    flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#0F1E35', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8,
    borderWidth: 1, borderColor: '#1A2942',
  },
  searchInput: { flex: 1, color: '#FFFFFF', fontSize: 14 },
  addBtn: { backgroundColor: '#25D366', borderRadius: 10, padding: 10, alignItems: 'center', justifyContent: 'center' },

  // Filters
  filterContent: {
    flexDirection: 'row', paddingHorizontal: 12, paddingBottom: 10, paddingTop: 2,
  },
  filterChip: {
    paddingHorizontal: 16, paddingVertical: 9, borderRadius: 20, marginRight: 8,
    backgroundColor: '#1E3050', borderWidth: 1.5, borderColor: '#3D5A80',
  },
  filterChipActive: { backgroundColor: '#25D366', borderColor: '#1DB954' },
  filterChipText: { color: '#FFFFFF', fontSize: 14, fontWeight: '600' },
  filterChipTextActive: { color: '#FFFFFF', fontWeight: '700' },

  // Booking card
  card: {
    flexDirection: 'row', backgroundColor: '#0F1E35', marginHorizontal: 12, marginBottom: 8,
    borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#1A2942', alignItems: 'center',
  },
  cardLeft: { marginRight: 12 },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
  cardBody: { flex: 1 },
  cardTopRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 2 },
  customerName: { color: '#FFFFFF', fontSize: 15, fontWeight: '600', flex: 1 },
  todayBadge: { backgroundColor: '#25D36622', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  todayBadgeText: { color: '#25D366', fontSize: 10, fontWeight: '600' },
  serviceName: { color: '#94A3B8', fontSize: 13, marginBottom: 4 },
  cardMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { color: '#64748B', fontSize: 12 },
  addonsText: { color: '#4A90D9', fontSize: 11, marginTop: 2 },
  cardRight: { alignItems: 'flex-end', gap: 4 },
  statusChip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  statusChipText: { fontSize: 11, fontWeight: '600' },
  payChip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  payChipText: { fontSize: 11, fontWeight: '500' },

  // Empty
  emptyContainer: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 },
  emptyTitle: { color: '#FFFFFF', fontSize: 17, fontWeight: '600', marginTop: 16 },
  emptySubtitle: { color: '#64748B', fontSize: 14, marginTop: 6, textAlign: 'center' },

  // Modal
  modalContainer: { flex: 1, backgroundColor: '#0A1628' },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: '#1A2942',
  },
  modalTitle: { color: '#FFFFFF', fontSize: 17, fontWeight: '700' },
  saveBtn: { color: '#25D366', fontSize: 16, fontWeight: '600' },
  modalBody: { flex: 1, padding: 16 },

  // Form
  fieldLabel: { color: '#94A3B8', fontSize: 13, fontWeight: '500', marginBottom: 6, marginTop: 4 },
  input: {
    backgroundColor: '#0F1E35', color: '#FFFFFF', borderRadius: 10,
    borderWidth: 1, borderColor: '#1A2942', paddingHorizontal: 14, paddingVertical: 10,
    fontSize: 15, marginBottom: 16,
  },
  customerSelect: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#1A2942', borderRadius: 12, padding: 16, marginBottom: 16 },
  customerSelectPlaceholder: { fontSize: 16, color: '#666' },
  selectedCustomer: { flexDirection: 'row', alignItems: 'center' },
  miniAvatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: '#25D366', justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  miniAvatarText: { fontSize: 14, fontWeight: 'bold', color: '#FFFFFF' },
  selectedName: { fontSize: 16, fontWeight: '600', color: '#FFFFFF' },
  selectedPhone: { fontSize: 12, color: '#666' },
  csSearchContainer: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', marginHorizontal: 16, borderRadius: 10, paddingHorizontal: 12, marginBottom: 8, borderWidth: 1, borderColor: '#2A3952' },
  csSearchInput: { flex: 1, paddingVertical: 8, fontSize: 14, color: '#FFFFFF' },
  walkInButton: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', borderRadius: 12, padding: 16, marginHorizontal: 20, marginBottom: 12, borderWidth: 1, borderColor: '#25D366' },
  walkInButtonText: { fontSize: 16, fontWeight: '600', color: '#FFFFFF' },
  walkInButtonSubtext: { fontSize: 12, color: '#888', marginTop: 2 },
  customerOption: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', borderRadius: 12, padding: 16, marginBottom: 8 },
  customerOptionInfo: { flex: 1 },
  customerOptionName: { fontSize: 16, fontWeight: '600', color: '#FFFFFF' },
  customerOptionPhone: { fontSize: 12, color: '#666' },
  dropdownList: { backgroundColor: '#0F1E35', borderRadius: 10, borderWidth: 1, borderColor: '#1A2942', marginTop: -12, marginBottom: 16 },
  dropdownEmpty: { color: '#64748B', padding: 12, textAlign: 'center' },
  dropdownItem: { padding: 12, borderBottomWidth: 1, borderBottomColor: '#1A2942' },
  dropdownItemText: { color: '#FFFFFF', fontSize: 14 },
  dropdownItemSub: { color: '#64748B', fontSize: 12, marginTop: 2 },

  // Service chips
  serviceChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
    backgroundColor: '#0F1E35', borderWidth: 1, borderColor: '#1A2942', marginRight: 8, alignItems: 'center',
  },
  serviceChipActive: { borderColor: '#25D366', backgroundColor: '#25D36622' },
  serviceChipText: { color: '#94A3B8', fontSize: 13, fontWeight: '500' },
  serviceChipTextActive: { color: '#25D366' },
  serviceChipSub: { color: '#64748B', fontSize: 11, marginTop: 2 },

  // Time chips
  timeChip: {
    paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8,
    backgroundColor: '#0F1E35', borderWidth: 1, borderColor: '#1A2942', marginRight: 6,
  },
  timeChipActive: { borderColor: '#25D366', backgroundColor: '#25D36622' },
  timeChipText: { color: '#94A3B8', fontSize: 13 },
  timeChipTextActive: { color: '#25D366' },

  // Detail modal
  detailSection: { alignItems: 'center', paddingVertical: 16 },
  bookingRef: { color: '#25D366', fontSize: 18, fontWeight: '700' },
  detailCreated: { color: '#64748B', fontSize: 13, marginTop: 4 },
  detailCard: {
    backgroundColor: '#0F1E35', borderRadius: 12, borderWidth: 1, borderColor: '#1A2942',
    marginBottom: 12, overflow: 'hidden',
  },
  detailRow: { flexDirection: 'row', alignItems: 'flex-start', padding: 12, borderBottomWidth: 1, borderBottomColor: '#1A2942' },
  detailLabel: { color: '#64748B', fontSize: 13, width: 70 },
  detailValue: { color: '#FFFFFF', fontSize: 13, flex: 1 },
  sectionTitle: { color: '#94A3B8', fontSize: 13, fontWeight: '600', marginBottom: 8, marginTop: 4 },

  // Status grid
  statusGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  statusOption: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
    borderWidth: 1, borderColor: '#1A2942', backgroundColor: '#0F1E35',
  },
  statusOptionText: { color: '#64748B', fontSize: 13, fontWeight: '500' },

  // Reminder button
  reminderBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16,
    backgroundColor: '#25D36615', borderRadius: 10, padding: 14,
    borderWidth: 1, borderColor: '#25D36640',
  },
  reminderBtnText: { color: '#25D366', fontSize: 14, fontWeight: '600', flex: 1 },
  reminderSentAt: { color: '#64748B', fontSize: 11 },

  // Source badge
  waBadge: { backgroundColor: '#25D36622', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  waBadgeText: { color: '#25D366', fontSize: 10, fontWeight: '600' },

  // Payment row
  paymentRow: { flexDirection: 'row', gap: 8, marginBottom: 32 },
  payOption: {
    flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center',
    borderWidth: 1, borderColor: '#1A2942', backgroundColor: '#0F1E35',
  },
  payOptionText: { color: '#64748B', fontSize: 13, fontWeight: '500' },
});
