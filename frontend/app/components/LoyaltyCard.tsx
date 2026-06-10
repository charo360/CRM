import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { loyaltyAPI } from '../../context/api';

type Props = {
  customerId: string;
};

const TIERS = [
  { name: 'Bronze', min: 0, next: 1000, color: '#CD7F32' },
  { name: 'Silver', min: 1000, next: 5000, color: '#C0C0C0' },
  { name: 'Gold', min: 5000, next: 15000, color: '#FFD700' },
  { name: 'Premium', min: 15000, next: null, color: '#9B59B6' },
];

const getTier = (points: number) => {
  for (let i = TIERS.length - 1; i >= 0; i--) {
    if (points >= TIERS[i].min) return TIERS[i];
  }
  return TIERS[0];
};

export default function LoyaltyCard({ customerId }: Props) {
  const [loading, setLoading] = useState(true);
  const [points, setPoints] = useState<number>(0);
  const [history, setHistory] = useState<any[]>([]);
  const [adding, setAdding] = useState(false);
  const [addAmount, setAddAmount] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!customerId) return;
    load();
  }, [customerId]);

  const load = async () => {
    setLoading(true);
    try {
      const p = await loyaltyAPI.getPoints(customerId);
      const h = await loyaltyAPI.getHistory(customerId);
      setPoints(p?.points ?? 0);
      setHistory(Array.isArray(h) ? h : []);
    } catch (err) {
      console.error('Loyalty load error', err);
    } finally {
      setLoading(false);
    }
  };

  const onAddPoints = async () => {
    const amt = Number(addAmount);
    if (!amt || amt <= 0) return;
    setSaving(true);
    try {
      await loyaltyAPI.addPoints(customerId, amt, 'manual');
      setAddAmount('');
      setAdding(false);
      await load();
    } catch (err) {
      console.error('Add points error', err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <ActivityIndicator size="small" color="#00A884" />;

  const tier = getTier(points);
  const next = tier.next;
  const progress = next ? Math.min(1, (points - tier.min) / (next - tier.min)) : 1;

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <View style={[styles.badge, { backgroundColor: tier.color }]}> 
          <Text style={styles.badgeText}>{tier.name}</Text>
        </View>
        <View style={{ marginLeft: 12 }}>
          <Text style={styles.pointsText}>{points.toLocaleString()}</Text>
          <Text style={styles.pointsLabel}>Points</Text>
        </View>
      </View>

      <View style={styles.progressBarBackground}>
        <View style={[styles.progressBarFill, { width: `${progress * 100}%`, backgroundColor: tier.color }]} />
      </View>
      {next ? (
        <Text style={styles.progressText}>{Math.floor(progress * 100)}% to {next.toLocaleString()} pts ({tier.name} → next)</Text>
      ) : (
        <Text style={styles.progressText}>Top tier reached</Text>
      )}

      <View style={styles.actionsRow}>
        {adding ? (
          <>
            <TextInput
              value={addAmount}
              onChangeText={setAddAmount}
              keyboardType="numeric"
              placeholder="Points to add"
              placeholderTextColor="#8696A0"
              style={styles.addInput}
            />
            <TouchableOpacity style={styles.addButton} onPress={onAddPoints} disabled={saving}>
              <Text style={styles.addButtonText}>{saving ? 'Saving...' : 'Add'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.cancelButton} onPress={() => { setAdding(false); setAddAmount(''); }}>
              <Ionicons name="close" size={18} color="#8696A0" />
            </TouchableOpacity>
          </>
        ) : (
          <>
            <TouchableOpacity style={styles.actionButton} onPress={() => setAdding(true)}>
              <Ionicons name="add" size={18} color="#00A884" />
              <Text style={styles.actionButtonText}>Add points</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.actionButton} onPress={load}>
              <Ionicons name="reload" size={18} color="#00A884" />
              <Text style={styles.actionButtonText}>Refresh</Text>
            </TouchableOpacity>
          </>
        )}
      </View>

      {history.length > 0 && (
        <View style={styles.historySection}>
          <Text style={styles.historyTitle}>Recent activity</Text>
          {history.slice(0, 5).map((h, i) => (
            <View key={i} style={styles.historyRow}>
              <Text style={styles.historyText}>{h.description || h.type || 'Points'}</Text>
              <Text style={styles.historyPoints}>{(h.amount ?? h.points ?? 0) > 0 ? `+${h.amount ?? h.points}` : `${h.amount ?? h.points}`}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#1F2C34',
    padding: 16,
    borderRadius: 12,
    marginHorizontal: 20,
    marginTop: 12,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center' },
  badge: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20 },
  badgeText: { color: '#fff', fontWeight: '700' },
  pointsText: { color: '#E9EDEF', fontSize: 20, fontWeight: '700' },
  pointsLabel: { color: '#8696A0', fontSize: 12 },
  progressBarBackground: { height: 8, backgroundColor: '#0B141A', borderRadius: 8, marginTop: 12, overflow: 'hidden' },
  progressBarFill: { height: 8, borderRadius: 8 },
  progressText: { color: '#8696A0', fontSize: 12, marginTop: 8 },
  actionsRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12 },
  actionButton: { flexDirection: 'row', alignItems: 'center', marginRight: 12, gap: 6 },
  actionButtonText: { color: '#00A884', fontWeight: '600', marginLeft: 6 },
  addInput: { backgroundColor: '#0B141A', color: '#E9EDEF', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, width: 120 },
  addButton: { backgroundColor: '#00A884', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, marginLeft: 8 },
  addButtonText: { color: '#fff', fontWeight: '700' },
  cancelButton: { marginLeft: 8 },
  historySection: { marginTop: 12, borderTopWidth: 1, borderTopColor: 'rgba(134,150,160,0.05)', paddingTop: 10 },
  historyTitle: { color: '#8696A0', fontWeight: '600', marginBottom: 8 },
  historyRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 },
  historyText: { color: '#E9EDEF' },
  historyPoints: { color: '#00A884', fontWeight: '700' },
});
