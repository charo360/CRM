import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, FlatList, TextInput, Linking, Share, Alert } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Ionicons } from '@expo/vector-icons';
import { feedbackAPI } from '../../context/api';

type Props = {
  customerId: string;
  visible: boolean;
  onClose: () => void;
};

export default function CustomerFeedbackModal({ customerId, visible, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [surveys, setSurveys] = useState<any[]>([]);
  const [responses, setResponses] = useState<any[]>([]);
  const [sending, setSending] = useState(false);
  const [lastLink, setLastLink] = useState<string | null>(null);
  const [loggingSurveyId, setLoggingSurveyId] = useState<string | null>(null);
  const [logRating, setLogRating] = useState('');
  const [logComment, setLogComment] = useState('');
  const [logging, setLogging] = useState(false);

  useEffect(() => {
    if (!visible) return;
    load();
  }, [visible]);

  const load = async () => {
    setLoading(true);
    try {
      const s = await feedbackAPI.listSurveys();
      const r = await feedbackAPI.getCustomerResponses(customerId);
      setSurveys(Array.isArray(s) ? s : []);
      setResponses(Array.isArray(r) ? r : []);
    } catch (err) {
      console.error('Feedback load error', err);
    } finally {
      setLoading(false);
    }
  };

  const onSend = async (surveyId: string) => {
    setSending(true);
    try {
      const res = await feedbackAPI.sendSurveyLink(surveyId, customerId);
      const url = res?.url || res?.share_url || res?.link || (res?.response_id ? `${process.env.EXPO_PUBLIC_APP_URL || 'http://localhost:3000'}/feedback/response/${res.response_id}` : null);
      if (url) {
        setLastLink(url);
        Alert.alert('Sent', 'Survey link sent');
      } else {
        const derived = `${process.env.EXPO_PUBLIC_APP_URL || 'http://localhost:3000'}/feedback/survey/${surveyId}`;
        setLastLink(derived);
        Alert.alert('Sent (local)', 'Survey link derived locally');
      }
    } catch (err) {
      console.error('Send survey error', err);
      const derived = `${process.env.EXPO_PUBLIC_APP_URL || 'http://localhost:3000'}/feedback/survey/${surveyId}`;
      setLastLink(derived);
      const msg = (err as any)?.response?.data?.detail || (err as any)?.message || 'Failed to call send endpoint; derived link shown';
      Alert.alert('Send failed', String(msg));
    } finally {
      setSending(false);
    }
  };

  const derivedSurveyLink = (item: any) => {
    return item?.url || item?.share_url || item?.link || `${process.env.EXPO_PUBLIC_APP_URL || 'http://localhost:3000'}/feedback/survey/${item.id || item._id}`;
  };

  const onCopy = async (url: string | null) => {
    if (!url) return;
    try {
      await Clipboard.setStringAsync(url);
      Alert.alert('Copied', 'Link copied to clipboard');
    } catch (err) {
      console.error('Copy error', err);
    }
  };

  const onShare = async (url: string | null) => {
    if (!url) return;
    try {
      await Share.share({ message: url, url });
    } catch (err) {
      console.error('Share error', err);
    }
  };

  const onLogResponse = async (surveyId: string) => {
    const rating = Number(logRating);
    if (!surveyId || (!rating && logComment.trim() === '')) {
      Alert && Alert.alert && Alert.alert('Invalid', 'Enter rating or comment');
      return;
    }
    setLogging(true);
    try {
      const payload: any = {
        survey_id: surveyId,
        customer_id: customerId,
        comment: logComment || undefined,
        answers: [],
      };
      if (!Number.isNaN(rating) && rating) payload.nps_score = rating;
      if (logComment && logComment.trim() !== '') payload.comment = logComment;
      if (!Number.isNaN(rating) && rating) payload.answers.push({ question_id: 'rating', answer: rating });
      if (logComment && logComment.trim() !== '') payload.answers.push({ question_id: 'comment', answer: logComment });

      const res = await feedbackAPI.submitResponse(payload);
      const url = res?.url || res?.share_url || (res?.id ? `${process.env.EXPO_PUBLIC_APP_URL || 'http://localhost:3000'}/feedback/response/${res.id}` : null);
      setLastLink(url || null);
      if (url) Alert.alert('Saved', 'Response saved — link available');
      // refresh responses
      const r = await feedbackAPI.getCustomerResponses(customerId);
      setResponses(Array.isArray(r) ? r : []);
      // reset logger
      setLoggingSurveyId(null);
      setLogRating('');
      setLogComment('');
    } catch (err) {
      console.error('Log response error', err);
      const msg = (err as any)?.response?.data?.detail || (err as any)?.message || 'Failed to save response';
      Alert.alert('Save failed', String(msg));
    } finally {
      setLogging(false);
    }
  };

  if (!visible) return null;

  return (
    <View style={styles.overlay}>
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Customer Feedback</Text>
          <TouchableOpacity onPress={onClose}>
            <Ionicons name="close" size={22} color="#8696A0" />
          </TouchableOpacity>
        </View>

        {loading ? (
          <ActivityIndicator size="large" color="#00A884" />
        ) : (
          <FlatList
            data={surveys}
            keyExtractor={(i) => i.id?.toString() || i._id || Math.random().toString()}
            renderItem={({ item }) => (
              <>
                <View style={styles.surveyRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.surveyTitle}>{item.title || item.name || 'Survey'}</Text>
                    <Text style={styles.surveySubtitle}>{item.description || ''}</Text>
                    <Text style={styles.surveyLink}>{derivedSurveyLink(item)}</Text>
                    <View style={{ flexDirection: 'row', marginTop: 6 }}>
                      <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#102027' }]} onPress={() => onCopy(derivedSurveyLink(item))}>
                        <Text style={styles.sendButtonText}>Copy link</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                  <TouchableOpacity style={styles.sendButton} onPress={() => onSend(item.id || item._id)} disabled={sending}>
                    <Text style={styles.sendButtonText}>{sending ? 'Sending...' : 'Send link'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#102027', marginLeft: 8 }]} onPress={() => {
                    const url = derivedSurveyLink(item);
                    setLastLink(url);
                  }}>
                    <Text style={styles.sendButtonText}>View link</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#102027', marginLeft: 8 }]} onPress={() => onShare(derivedSurveyLink(item))}>
                    <Text style={styles.sendButtonText}>Share</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#0B141A', borderWidth: 1, borderColor: '#00A884', marginLeft: 8 }]} onPress={() => setLoggingSurveyId(item.id || item._id)}>
                    <Text style={[styles.sendButtonText, { color: '#00A884' }]}>Log response</Text>
                  </TouchableOpacity>
                </View>
                {loggingSurveyId === (item.id || item._id) && (
                  <View style={styles.logForm}>
                    <TextInput
                      value={logRating}
                      onChangeText={setLogRating}
                      placeholder="Rating (0-10)"
                      placeholderTextColor="#8696A0"
                      keyboardType="numeric"
                      style={styles.logInput}
                    />
                    <TextInput
                      value={logComment}
                      onChangeText={setLogComment}
                      placeholder="Comment"
                      placeholderTextColor="#8696A0"
                      style={[styles.logInput, { marginTop: 8 }]}
                    />
                    <View style={{ flexDirection: 'row', marginTop: 8 }}>
                      <TouchableOpacity style={styles.sendButton} onPress={() => onLogResponse(item.id || item._id)} disabled={logging}>
                        <Text style={styles.sendButtonText}>{logging ? 'Saving...' : 'Save'}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#8696A0', marginLeft: 8 }]} onPress={() => { setLoggingSurveyId(null); setLogRating(''); setLogComment(''); }}>
                        <Text style={styles.sendButtonText}>Cancel</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
              </>
            )}
            ListEmptyComponent={<Text style={{ color: '#8696A0', padding: 12 }}>No surveys available</Text>}
            ListFooterComponent={() => (
              <>
                {lastLink && (
                  <View style={styles.linkBox}>
                    <Text style={styles.linkLabel}>Shareable link</Text>
                    <TouchableOpacity onPress={() => Linking.openURL(lastLink)}>
                      <Text style={styles.linkText}>{lastLink}</Text>
                    </TouchableOpacity>
                  </View>
                )}

                <View style={styles.responsesSection}>
                  <Text style={styles.sectionTitle}>Previous responses</Text>
                  {responses.length === 0 ? (
                    <Text style={{ color: '#8696A0' }}>No responses yet</Text>
                  ) : (
                    responses.map((r: any, idx: number) => (
                      <View key={idx} style={styles.responseRow}>
                        <Text style={styles.responseText}>{r.summary || JSON.stringify(r.answers || r)}</Text>
                        {r.url ? (
                          <TouchableOpacity onPress={() => Linking.openURL(r.url)}>
                            <Text style={styles.viewLink}>View</Text>
                          </TouchableOpacity>
                        ) : null}
                      </View>
                    ))
                  )}
                </View>
              </>
            )}
          />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', alignItems: 'center' },
  container: { width: '92%', maxHeight: '86%', backgroundColor: '#0B141A', borderRadius: 12, padding: 12 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  title: { color: '#E9EDEF', fontSize: 18, fontWeight: '700' },
  surveyRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(134,150,160,0.05)' },
  surveyTitle: { color: '#E9EDEF', fontWeight: '700' },
  surveySubtitle: { color: '#8696A0', fontSize: 12 },
  sendButton: { backgroundColor: '#00A884', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, marginLeft: 10 },
  sendButtonText: { color: '#fff', fontWeight: '700' },
  logForm: { marginTop: 8, backgroundColor: '#102027', padding: 10, borderRadius: 8 },
  logInput: { backgroundColor: '#0B141A', color: '#E9EDEF', paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8 },
  linkBox: { margin: 12, backgroundColor: '#102027', padding: 10, borderRadius: 8 },
  linkLabel: { color: '#8696A0', fontSize: 12 },
  linkText: { color: '#00A884', marginTop: 6 },
  surveyLink: { color: '#00A884', marginTop: 6, fontSize: 12 },
  responsesSection: { marginTop: 12 },
  sectionTitle: { color: '#E9EDEF', fontWeight: '700', marginBottom: 8 },
  responseRow: { backgroundColor: '#1F2C34', padding: 10, borderRadius: 8, marginBottom: 8, flexDirection: 'row', justifyContent: 'space-between' },
  responseText: { color: '#E9EDEF', flex: 1, marginRight: 8 },
  viewLink: { color: '#00A884', fontWeight: '700' },
});
