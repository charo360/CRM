import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, FlatList, TextInput, Linking, Modal, Share, Alert, ScrollView } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Ionicons } from '@expo/vector-icons';
import { feedbackAPI } from '../../context/api';

type Props = {
  customerId: string;
  visible: boolean;
  onClose: () => void;
};

type QuestionType = 'nps' | 'rating' | 'choice' | 'text';
type SurveyQuestionDraft = { id: string; text: string; type: QuestionType; optionsText?: string };

const QUESTION_TYPES: Array<{ type: QuestionType; label: string; hint: string }> = [
  { type: 'nps', label: '0–10 score', hint: 'Customer replies with a score from 0 to 10.' },
  { type: 'rating', label: '1–5 rating', hint: 'Customer replies with a score from 1 to 5.' },
  { type: 'choice', label: 'Choice', hint: 'Customer replies with one of your options.' },
  { type: 'text', label: 'Text answer', hint: 'Customer can type a short answer.' },
];

const makeQuestion = (type: QuestionType = 'rating'): SurveyQuestionDraft => ({
  id: `question_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
  text: '',
  type,
  optionsText: type === 'choice' ? '' : undefined,
});

export default function CustomerFeedbackModal({ customerId, visible, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [surveys, setSurveys] = useState<any[]>([]);
  const [responses, setResponses] = useState<any[]>([]);
  const [sending, setSending] = useState(false);
  const [creatingSurvey, setCreatingSurvey] = useState(false);
  const [builderVisible, setBuilderVisible] = useState(false);
  const [draftTitle, setDraftTitle] = useState('Customer satisfaction');
  const [draftDescription, setDraftDescription] = useState('A quick survey to help us improve.');
  const [draftQuestions, setDraftQuestions] = useState<SurveyQuestionDraft[]>([]);
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

  const onSendWhatsApp = async (surveyId: string) => {
    setSending(true);
    try {
      await feedbackAPI.sendSurveyLink(surveyId, customerId, 'whatsapp_chat');
      Alert.alert('Survey started', 'The first question was sent in WhatsApp. Zilo will send each next question after the customer replies.');
    } catch (err: any) {
      console.error('Send survey error', err);
      const msg = err?.response?.data?.detail || err?.message || 'Could not send the survey on WhatsApp';
      Alert.alert('Could not send survey', String(msg));
    } finally {
      setSending(false);
    }
  };

  const onSendLink = async (surveyId: string) => {
    setSending(true);
    try {
      const res = await feedbackAPI.sendSurveyLink(surveyId, customerId, 'link');
      if (!res?.url) throw new Error('Zilo did not return a survey link');
      setLastLink(res.url);
      Alert.alert('Link sent', 'A private feedback link was sent to this customer on WhatsApp.');
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Could not send the survey link';
      Alert.alert('Could not send link', String(msg));
    } finally {
      setSending(false);
    }
  };

  const openBuilder = () => {
    setDraftTitle('Customer satisfaction');
    setDraftDescription('A quick survey to help us improve.');
    setDraftQuestions([
      { id: 'recommend', text: 'How likely are you to recommend us to a friend?', type: 'nps' },
      { id: 'comment', text: 'What could we do better?', type: 'text' },
    ]);
    setBuilderVisible(true);
  };

  const createSurvey = async () => {
    const title = draftTitle.trim();
    const questions = draftQuestions
      .map((question) => ({
        ...question,
        text: question.text.trim(),
        options: question.type === 'choice'
          ? (question.optionsText || '').split(/[\n,]/).map((option) => option.trim()).filter(Boolean)
          : undefined,
      }))
      .filter((question) => question.text);
    if (!title) {
      Alert.alert('Add a title', 'Give this survey a name first.');
      return;
    }
    if (!questions.length) {
      Alert.alert('Add a question', 'A WhatsApp survey needs at least one question.');
      return;
    }
    const incompleteChoice = questions.find((question) => question.type === 'choice' && (question.options || []).length < 2);
    if (incompleteChoice) {
      Alert.alert('Add choices', 'Choice questions need at least two options.');
      return;
    }
    setCreatingSurvey(true);
    try {
      await feedbackAPI.createSurvey({
        title,
        description: draftDescription.trim(),
        active: true,
        questions: questions.map(({ id, text, type, options }) => ({ id, text, type, options })),
      });
      await load();
      setBuilderVisible(false);
      Alert.alert('Survey ready', 'Send it in WhatsApp when you are ready.');
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Could not create the survey';
      Alert.alert('Could not create survey', String(msg));
    } finally {
      setCreatingSurvey(false);
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

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
    <View style={styles.overlay}>
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>{builderVisible ? 'Create survey' : 'Customer Feedback'}</Text>
          <View style={styles.headerActions}>
            {!builderVisible && (
              <TouchableOpacity style={styles.newSurveyButton} onPress={openBuilder}>
                <Ionicons name="add" size={18} color="#00A884" />
                <Text style={styles.newSurveyText}>New</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={() => builderVisible ? setBuilderVisible(false) : onClose()}>
              <Ionicons name={builderVisible ? 'arrow-back' : 'close'} size={22} color="#8696A0" />
            </TouchableOpacity>
          </View>
        </View>

        {builderVisible ? (
          <ScrollView contentContainerStyle={styles.builderContent} keyboardShouldPersistTaps="handled">
            <Text style={styles.builderIntro}>Create a short survey that customers answer directly in WhatsApp, one question at a time.</Text>
            <Text style={styles.fieldLabel}>Survey name</Text>
            <TextInput value={draftTitle} onChangeText={setDraftTitle} placeholder="e.g. After-purchase feedback" placeholderTextColor="#8696A0" style={styles.logInput} />
            <Text style={styles.fieldLabel}>Description (optional)</Text>
            <TextInput value={draftDescription} onChangeText={setDraftDescription} placeholder="Why you are asking" placeholderTextColor="#8696A0" style={styles.logInput} />

            <Text style={styles.builderSectionTitle}>Questions</Text>
            {draftQuestions.map((question, index) => (
              <View key={question.id} style={styles.questionCard}>
                <View style={styles.questionCardHeader}>
                  <Text style={styles.questionCount}>Question {index + 1}</Text>
                  <TouchableOpacity onPress={() => setDraftQuestions((items) => items.filter((item) => item.id !== question.id))}>
                    <Ionicons name="trash-outline" size={19} color="#EF5350" />
                  </TouchableOpacity>
                </View>
                <TextInput
                  value={question.text}
                  onChangeText={(text) => setDraftQuestions((items) => items.map((item) => item.id === question.id ? { ...item, text } : item))}
                  placeholder="Write your question"
                  placeholderTextColor="#8696A0"
                  style={styles.logInput}
                />
                <View style={styles.typeRow}>
                  {QUESTION_TYPES.map((option) => (
                    <TouchableOpacity
                      key={option.type}
                      onPress={() => setDraftQuestions((items) => items.map((item) => item.id === question.id ? { ...item, type: option.type, optionsText: option.type === 'choice' ? (item.optionsText || '') : undefined } : item))}
                      style={[styles.typeButton, question.type === option.type && styles.typeButtonSelected]}
                    >
                      <Text style={[styles.typeButtonText, question.type === option.type && styles.typeButtonTextSelected]}>{option.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.questionHint}>{QUESTION_TYPES.find((option) => option.type === question.type)?.hint}</Text>
                {question.type === 'choice' && (
                  <TextInput
                    value={question.optionsText || ''}
                    onChangeText={(optionsText) => setDraftQuestions((items) => items.map((item) => item.id === question.id ? { ...item, optionsText } : item))}
                    placeholder="Options, separated by commas or new lines"
                    placeholderTextColor="#8696A0"
                    multiline
                    style={[styles.logInput, styles.choiceInput]}
                  />
                )}
              </View>
            ))}
            <View style={styles.addQuestionRow}>
              {QUESTION_TYPES.map((option) => (
                <TouchableOpacity key={option.type} style={styles.addQuestionButton} onPress={() => setDraftQuestions((items) => [...items, makeQuestion(option.type)])}>
                  <Text style={styles.addQuestionText}>+ {option.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TouchableOpacity style={styles.createButton} onPress={createSurvey} disabled={creatingSurvey}>
              {creatingSurvey ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.createButtonText}>Save survey</Text>}
            </TouchableOpacity>
          </ScrollView>
        ) : loading ? (
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
                    <Text style={styles.surveyLink}>{(item.questions || []).length} question{(item.questions || []).length === 1 ? '' : 's'} · replies stay in WhatsApp</Text>
                  </View>
                  <View style={styles.surveyActions}>
                    <TouchableOpacity style={styles.sendButton} onPress={() => onSendWhatsApp(item.id || item._id)} disabled={sending}>
                      <Text style={styles.sendButtonText}>{sending ? 'Sending...' : 'Send in WhatsApp'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#102027' }]} onPress={() => onSendLink(item.id || item._id)} disabled={sending}>
                      <Text style={styles.sendButtonText}>Send link</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#102027' }]} onPress={() => onShare(derivedSurveyLink(item))}>
                      <Text style={styles.sendButtonText}>Share</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.sendButton, { backgroundColor: '#0B141A', borderWidth: 1, borderColor: '#00A884' }]} onPress={() => setLoggingSurveyId(item.id || item._id)}>
                      <Text style={[styles.sendButtonText, { color: '#00A884' }]}>Log response</Text>
                    </TouchableOpacity>
                  </View>
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
            ListEmptyComponent={
              <View style={styles.emptyState}>
                <Ionicons name="chatbubbles-outline" size={34} color="#8696A0" />
                <Text style={styles.emptyTitle}>No feedback survey yet</Text>
                <Text style={styles.emptyText}>Create your questions, then send the survey directly in WhatsApp.</Text>
                <TouchableOpacity style={styles.createButton} onPress={openBuilder}>
                  <Text style={styles.createButtonText}>Create survey</Text>
                </TouchableOpacity>
              </View>
            }
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
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', alignItems: 'center' },
  container: { width: '92%', maxHeight: '86%', backgroundColor: '#0B141A', borderRadius: 12, padding: 12 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  newSurveyButton: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  newSurveyText: { color: '#00A884', fontWeight: '700' },
  title: { color: '#E9EDEF', fontSize: 18, fontWeight: '700' },
  builderContent: { paddingBottom: 8 },
  builderIntro: { color: '#B8C5CC', lineHeight: 19, marginBottom: 14 },
  builderSectionTitle: { color: '#E9EDEF', fontSize: 16, fontWeight: '700', marginTop: 18, marginBottom: 8 },
  fieldLabel: { color: '#B8C5CC', fontSize: 12, marginBottom: 6, marginTop: 10 },
  questionCard: { backgroundColor: '#102027', borderRadius: 10, padding: 10, marginBottom: 10 },
  questionCardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  questionCount: { color: '#E9EDEF', fontWeight: '700' },
  typeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 9 },
  typeButton: { borderWidth: 1, borderColor: '#2A3942', borderRadius: 14, paddingHorizontal: 8, paddingVertical: 5 },
  typeButtonSelected: { borderColor: '#00A884', backgroundColor: '#113C35' },
  typeButtonText: { color: '#B8C5CC', fontSize: 11 },
  typeButtonTextSelected: { color: '#53D89B', fontWeight: '700' },
  questionHint: { color: '#8696A0', fontSize: 11, marginTop: 8, lineHeight: 15 },
  choiceInput: { minHeight: 60, marginTop: 9, textAlignVertical: 'top' },
  addQuestionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 2 },
  addQuestionButton: { borderWidth: 1, borderColor: '#00A884', borderRadius: 8, paddingHorizontal: 9, paddingVertical: 7 },
  addQuestionText: { color: '#00A884', fontSize: 12, fontWeight: '700' },
  surveyRow: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(134,150,160,0.05)' },
  surveyActions: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 8 },
  surveyTitle: { color: '#E9EDEF', fontWeight: '700' },
  surveySubtitle: { color: '#8696A0', fontSize: 12 },
  sendButton: { backgroundColor: '#00A884', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, marginRight: 8, marginTop: 6 },
  sendButtonText: { color: '#fff', fontWeight: '700' },
  logForm: { marginTop: 8, backgroundColor: '#102027', padding: 10, borderRadius: 8 },
  logInput: { backgroundColor: '#0B141A', color: '#E9EDEF', paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8 },
  linkBox: { margin: 12, backgroundColor: '#102027', padding: 10, borderRadius: 8 },
  linkLabel: { color: '#8696A0', fontSize: 12 },
  linkText: { color: '#00A884', marginTop: 6 },
  surveyLink: { color: '#00A884', marginTop: 6, fontSize: 12 },
  responsesSection: { marginTop: 12 },
  emptyState: { alignItems: 'center', padding: 24 },
  emptyTitle: { color: '#E9EDEF', fontWeight: '700', fontSize: 16, marginTop: 12 },
  emptyText: { color: '#8696A0', textAlign: 'center', marginTop: 6, lineHeight: 19 },
  createButton: { backgroundColor: '#00A884', paddingHorizontal: 16, paddingVertical: 11, borderRadius: 8, marginTop: 16, minWidth: 132, alignItems: 'center' },
  createButtonText: { color: '#FFFFFF', fontWeight: '700' },
  sectionTitle: { color: '#E9EDEF', fontWeight: '700', marginBottom: 8 },
  responseRow: { backgroundColor: '#1F2C34', padding: 10, borderRadius: 8, marginBottom: 8, flexDirection: 'row', justifyContent: 'space-between' },
  responseText: { color: '#E9EDEF', flex: 1, marginRight: 8 },
  viewLink: { color: '#00A884', fontWeight: '700' },
});
