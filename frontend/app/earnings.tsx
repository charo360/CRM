/**
 * Earnings — what customers paid, and how much of it has actually reached you.
 *
 * Two different numbers people routinely confuse. "Received" is what buyers
 * paid, recorded from the Paystack webhook. "Paid out" is what Paystack has
 * actually settled to the M-Pesa or bank account on file, and it lags by a
 * settlement cycle. The gap is money earned and not yet spendable, which is
 * the question an owner actually has.
 *
 * When Paystack will not tell us what it has settled we say so, rather than
 * showing a zero. "Nothing settled yet" and "we could not ask" look the same
 * to a worried owner, and only one is a reason to contact support.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Stack, useRouter } from 'expo-router';
import { apiClient } from '../context/api';

type CurrencyRow = {
  currency: string;
  payments: number;
  received: number;
  settled?: number;
  held?: number;
};

type Summary = {
  connected: boolean;
  settlement_data: boolean;
  currencies: CurrencyRow[];
};

type Txn = {
  reference: string;
  amount: number;
  currency: string;
  status: string;
  channel: string;
  customer: string;
  order_id: string;
  created_at?: string;
};

const money = (amount: number, currency: string) =>
  `${currency} ${Number(amount || 0).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}`;

const when = (iso?: string) => {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
};

export default function EarningsScreen() {
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Txn[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([
        apiClient.get('/paystack/earnings'),
        apiClient.get('/paystack/earnings/transactions?limit=50'),
      ]);
      setSummary(s.data);
      setTransactions(t.data?.transactions || []);
      setError('');
    } catch {
      setError('Could not load earnings. Pull down to try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const shown = showAll ? transactions : transactions.slice(0, 8);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.back}>
          <Ionicons name="arrow-back" size={24} color="#E9EDEF" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Earnings</Text>
      </View>

      {loading ? (
        <View style={styles.centre}>
          <ActivityIndicator color="#25D366" />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.body}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => {
                setRefreshing(true);
                load();
              }}
              tintColor="#25D366"
            />
          }
        >
          {error ? <Text style={styles.error}>{error}</Text> : null}

          {!summary?.connected ? (
            <View style={styles.empty}>
              <Ionicons name="wallet-outline" size={40} color="#3A4A5C" />
              <Text style={styles.emptyTitle}>Online payments are off</Text>
              <Text style={styles.emptyText}>
                Set up M-Pesa or a bank payout in Account to start taking payments from your
                catalog.
              </Text>
            </View>
          ) : summary.currencies.length === 0 ? (
            <View style={styles.empty}>
              <Ionicons name="time-outline" size={40} color="#3A4A5C" />
              <Text style={styles.emptyTitle}>No payments yet</Text>
              <Text style={styles.emptyText}>
                Payments from your catalog will show here as soon as the first one comes in.
              </Text>
            </View>
          ) : (
            summary.currencies.map((row) => (
              <View key={row.currency} style={styles.card}>
                <Text style={styles.cardLabel}>Received</Text>
                <Text style={styles.big}>{money(row.received, row.currency)}</Text>
                <Text style={styles.sub}>
                  {row.payments} payment{row.payments === 1 ? '' : 's'}
                </Text>

                {summary.settlement_data ? (
                  <View style={styles.split}>
                    <View style={styles.splitHalf}>
                      <Text style={styles.splitLabel}>Paid out to you</Text>
                      <Text style={[styles.splitValue, { color: '#25D366' }]}>
                        {money(row.settled || 0, row.currency)}
                      </Text>
                    </View>
                    <View style={styles.splitDivider} />
                    <View style={styles.splitHalf}>
                      <Text style={styles.splitLabel}>Still with Paystack</Text>
                      <Text style={[styles.splitValue, { color: '#FFD700' }]}>
                        {money(row.held || 0, row.currency)}
                      </Text>
                    </View>
                  </View>
                ) : (
                  <View style={styles.notice}>
                    <Ionicons name="information-circle-outline" size={16} color="#8B9DC3" />
                    <Text style={styles.noticeText}>
                      Paystack hasn&apos;t reported settlements yet, so we can&apos;t show what has
                      been paid out. This is not the same as nothing being paid.
                    </Text>
                  </View>
                )}
              </View>
            ))
          )}

          {transactions.length > 0 && (
            <>
              <Text style={styles.sectionTitle}>Transactions</Text>
              {shown.map((t) => (
                <View key={t.reference} style={styles.txn}>
                  <View style={styles.txnLeft}>
                    <Text style={styles.txnAmount}>{money(t.amount, t.currency)}</Text>
                    <Text style={styles.txnMeta} numberOfLines={1}>
                      {[when(t.created_at), t.channel?.replace('_', ' '), t.customer]
                        .filter(Boolean)
                        .join(' · ')}
                    </Text>
                  </View>
                  <Text
                    style={[
                      styles.txnStatus,
                      t.status === 'success' && { color: '#25D366' },
                      t.status === 'refunded' && { color: '#FFD700' },
                      t.status === 'failed' && { color: '#FF6B6B' },
                    ]}
                  >
                    {t.status}
                  </Text>
                </View>
              ))}
              {transactions.length > 8 && (
                <TouchableOpacity onPress={() => setShowAll((v) => !v)} style={styles.more}>
                  <Text style={styles.moreText}>
                    {showAll ? 'Show less' : `Show all ${transactions.length}`}
                  </Text>
                </TouchableOpacity>
              )}
            </>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A1628' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 12,
    gap: 6,
  },
  back: { padding: 4 },
  headerTitle: { color: '#E9EDEF', fontSize: 18, fontWeight: '700' },
  centre: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  body: { padding: 16, paddingBottom: 40 },
  error: { color: '#FF6B6B', fontSize: 13, marginBottom: 12 },

  card: {
    backgroundColor: '#14213A',
    borderRadius: 16,
    padding: 18,
    marginBottom: 16,
  },
  cardLabel: { color: '#8B9DC3', fontSize: 12, fontWeight: '600', letterSpacing: 0.4 },
  big: { color: '#FFFFFF', fontSize: 30, fontWeight: '700', marginTop: 4 },
  sub: { color: '#8B9DC3', fontSize: 12, marginTop: 2 },

  split: { flexDirection: 'row', marginTop: 18, alignItems: 'stretch' },
  splitHalf: { flex: 1 },
  splitDivider: { width: 1, backgroundColor: '#24344F', marginHorizontal: 14 },
  splitLabel: { color: '#8B9DC3', fontSize: 11 },
  splitValue: { fontSize: 17, fontWeight: '700', marginTop: 3 },

  notice: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 16,
    backgroundColor: '#0F1A2E',
    borderRadius: 10,
    padding: 11,
  },
  noticeText: { color: '#8B9DC3', fontSize: 11, lineHeight: 16, flex: 1 },

  sectionTitle: {
    color: '#E9EDEF',
    fontSize: 15,
    fontWeight: '700',
    marginTop: 6,
    marginBottom: 10,
  },
  txn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#14213A',
    borderRadius: 12,
    padding: 13,
    marginBottom: 8,
  },
  txnLeft: { flex: 1 },
  txnAmount: { color: '#E9EDEF', fontSize: 15, fontWeight: '600' },
  txnMeta: { color: '#8B9DC3', fontSize: 11, marginTop: 2 },
  txnStatus: { color: '#8B9DC3', fontSize: 11, fontWeight: '700', textTransform: 'capitalize' },
  more: { paddingVertical: 12, alignItems: 'center' },
  moreText: { color: '#25D366', fontSize: 13, fontWeight: '600' },

  empty: { alignItems: 'center', paddingVertical: 46, gap: 8 },
  emptyTitle: { color: '#E9EDEF', fontSize: 16, fontWeight: '700' },
  emptyText: {
    color: '#8B9DC3',
    fontSize: 13,
    textAlign: 'center',
    lineHeight: 19,
    paddingHorizontal: 30,
  },
});
