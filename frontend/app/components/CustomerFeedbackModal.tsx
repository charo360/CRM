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
  const [surveyDetails, setSurveyDetails] = useState<any | null>(null);
  const [logAnswers, setLogAnswers] = useState<Record<string, any>>({});
  const [extraFields, setExtraFields] = useState<Array<{ id: string; label: string; value: string }>>([]);

  useEffect(() => {
    if (!visible) return;
    load();
  }, [visible]);

  useEffect(() => {
    // when logging a specific survey, fetch its full details
    let mounted = true;
    if (!loggingSurveyId) {
      setSurveyDetails(null);
      setLogAnswers({});
      setExtraFields([]);
      return;
    }
    (async () => {
      try {
        const s = await feedbackAPI.getSurvey(loggingSurveyId);
        if (!mounted) return;
        setSurveyDetails(s || null);
        const a: Record<string, any> = {};
        (s?.questions || []).forEach((q: any) => {
          const qid = q.id || q._id || q.question_id || q.key || String(Math.random());
          a[qid] = '';
        });
        setLogAnswers(a);
      } catch (e) {
        console.error('Failed to fetch survey details', e);
      }
    })();
    return () => { mounted = false; };
  }, [loggingSurveyId]);

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
    // dynamic submission supporting survey questions and extra fields
    if (!surveyId) return;
    setLogging(true);
    try {
      const payload: any = {
        survey_id: surveyId,
        customer_id: customerId,
        customer_name: undefined,
        customer_phone: undefined,
        answers: [],
      };
      // include answers from structured questions
      if (surveyDetails?.questions && Array.isArray(surveyDetails.questions)) {
        for (const q of surveyDetails.questions) {
          const qid = q.id || q._id || q.question_id || q.key || String(Math.random());
          const a = logAnswers[qid];
          if (a !== undefined && a !== '') payload.answers.push({ question_id: qid, answer: a });
          // if question is NPS and numeric, set nps_score for convenience
          if ((q.type === 'nps' || q.type === 'rating') && typeof a === 'number') payload.nps_score = a;
        }
      }
      // include extras
      for (const f of extraFields) {
        if (f.value && f.value.trim() !== '') payload.answers.push({ question_id: f.id, answer: { label: f.label, value: f.value } });
      }
      // fallback comment/rating for backward compatibility
      if (logComment && logComment.trim() !== '') payload.comment = logComment;
      if (logRating) {
        const nr = Number(logRating);
        if (!Number.isNaN(nr)) payload.nps_score = nr;
      }

      const res = await feedbackAPI.submitResponse(payload);
      const url = res?.url || res?.share_url || (res?.id ? `${process.env.EXPO_PUBLIC_APP_URL || 'http://localhost:3000'}/feedback/response/${res.id}` : null);
      setLastLink(url || null);
      if (url) Alert.alert('Saved', 'Response saved — link available');
      const r = await feedbackAPI.getCustomerResponses(customerId);
      setResponses(Array.isArray(r) ? r : []);
      // reset logger state
      setLoggingSurveyId(null);
      setLogRating('');
      setLogComment('');
      setSurveyDetails(null);
      setLogAnswers({});
      setExtraFields([]);
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
                    {surveyDetails ? (
                      <>
                        {(surveyDetails.questions || []).map((q: any) => {
                          const qid = q.id || q._id || q.question_id || q.key || String(Math.random());
                          const val = logAnswers[qid] ?? '';
                          return (
                            <View key={qid} style={{ marginBottom: 8 }}>
                              <Text style={{ color: '#E9EDEF', marginBottom: 6 }}>{q.text || q.title || 'Question'}</Text>
                              {q.type === 'text' && (
                                <TextInput value={val} onChangeText={(t) => setLogAnswers(prev => ({ ...prev, [qid]: t }))} placeholder="Answer" placeholderTextColor="#8696A0" style={styles.logInput} />
                              )}
                              {q.type === 'nps' && (
                                <TextInput value={String(val || '')} onChangeText={(t) => setLogAnswers(prev => ({ ...prev, [qid]: Number(t) }))} placeholder="0-10" placeholderTextColor="#8696A0" keyboardType="numeric" style={styles.logInput} />
                              )}
                              {q.type === 'rating' && (
                                <TextInput value={String(val || '')} onChangeText={(t) => setLogAnswers(prev => ({ ...prev, [qid]: Number(t) }))} placeholder="1-5" placeholderTextColor="#8696A0" keyboardType="numeric" style={styles.logInput} />
                              )}
                              {q.type === 'choice' && (
                                <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
                                  {(q.options || []).map((opt: string, oi: number) => (
                                    <TouchableOpacity key={oi} onPress={() => setLogAnswers(prev => ({ ...prev, [qid]: opt }))} style={[styles.sendButton, { backgroundColor: val === opt ? '#00A884' : '#102027', marginRight: 8, marginBottom: 8 }]}>
                                      <Text style={styles.sendButtonText}>{opt}</Text>
                                    </TouchableOpacity>
                                  ))}
                                </View>
                              )}
                            </View>
                          );
                        })}

                        {/* extras */}
                        {extraFields.map(f => (
                          <View key={f.id} style={{ marginBottom: 8 }}>
                            <TextInput value={f.label} onChangeText={(t) => setExtraFields(prev => prev.map(x => x.id === f.id ? { ...x, label: t } : x))} placeholder="Field label" placeholderTextColor="#8696A0" style={styles.logInput} />
                            <TextInput value={f.value} onChangeText={(t) => setExtraFields(prev => prev.map(x => x.id === f.id ? { ...x, value: t } : x))} placeholder="Value" placeholderTextColor="#8696A0" style={[styles.logInput, { marginTop: 6 }]} />
                            <TouchableOpacity onPress={() => setExtraFields(prev => prev.filter(x => x.id !== f.id))} style={[styles.sendButton, { backgroundColor: '#8696A0', marginTop: 6 }]}>
                              <Text style={styles.sendButtonText}>Remove field</Text>
                            </TouchableOpacity>
                          </View>
                        ))}

                        <TouchableOpacity onPress={() => setExtraFields(prev => [...prev, { id: `custom_${Date.now()}`, label: 'Custom field', value: '' }])} style={[styles.sendButton, { backgroundColor: '#102027' }]}>
                          <Text style={styles.sendButtonText}>Add field</Text>
                        </TouchableOpacity>

                        <View style={{ flexDirection: 'row', marginTop: 8 }}>
                          <TouchableOpacity style={styles.sendButton} onPress={() => onLogResponse(item.id || item._id)} disabled={logging}>
                            <Text style={styles.sendButtonText}>{logging ? 'Saving...' : 'Save'}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#8696A0', marginLeft: 8 }]} onPress={() => { setLoggingSurveyId(null); setLogRating(''); setLogComment(''); setSurveyDetails(null); setLogAnswers({}); setExtraFields([]); }}>
                            <Text style={styles.sendButtonText}>Cancel</Text>
                          </TouchableOpacity>
                        </View>
                      </>
                    ) : (
                      <>
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
                      </>
                    )}
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
