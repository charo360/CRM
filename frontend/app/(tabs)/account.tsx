import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Switch,
  Modal,
  Platform,
  TextInput,
  Linking,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import DateTimePicker from '@react-native-community/datetimepicker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../../context/AuthContext';
import { useBusiness } from '../../context/BusinessContext';
import { apiClient, settingsAPI, whatsappAPI, accountAPI } from '../../context/api';

import { NotificationHandler } from '../../utils/notification-handler';
import TeamManagementModal from '../../components/TeamManagementModal';
import SubscriptionModal from '../../components/SubscriptionModal';
// IAP stubs — real react-native-iap is linked only in native production builds
type ProductPurchase = { purchaseToken?: string; transactionId?: string };
type PurchaseError = { code?: string; message?: string };
const initConnection = async () => {};
const requestPurchase = async (_opts: any) => { throw new Error('IAP not available in this build'); };
const purchaseUpdatedListener = (_cb: any): { remove: () => void } => ({ remove: () => {} });
const purchaseErrorListener = (_cb: any): { remove: () => void } => ({ remove: () => {} });
const finishTransaction = async (_opts: any) => {};

// Product IDs for credit bundles on each platform
const CREDIT_PRODUCT_IDS: Record<string, string> = {
  credits_500:  Platform.OS === 'ios' ? 'com.charo360.credits500'  : 'charo360_credits_500',
  credits_1000: Platform.OS === 'ios' ? 'com.charo360.credits1000' : 'charo360_credits_1000',
  credits_2500: Platform.OS === 'ios' ? 'com.charo360.credits2500' : 'charo360_credits_2500',
  credits_5000: Platform.OS === 'ios' ? 'com.charo360.credits5000' : 'charo360_credits_5000',
};

interface SubscriptionPlan {
  id: string;
  name: string;
  amount: number;
  currency: string;
  amount_display: string;
  interval: string;
  features: string[];
}

interface Stats {
  customers_count: number;
  pending_followups: number;
  sales_this_month: number;
  revenue_this_month: number;
}

interface Product {
  id: string;
  name: string;
  price: number;
  image_url: string;
  category: string;
  in_stock: boolean;
}

export default function AccountScreen() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(false);

  // WhatsApp connection state
  const [waConnected, setWaConnected] = useState(false);
  const [waStatus, setWaStatus] = useState('not_connected');
  const [waNumber, setWaNumber] = useState('');
  const [waPhoneInput, setWaPhoneInput] = useState('');
  const [waPairingCode, setWaPairingCode] = useState('');
  const [waConnecting, setWaConnecting] = useState(false);
  const [waDisconnecting, setWaDisconnecting] = useState(false);
  const [waMsgSent, setWaMsgSent] = useState(0);
  const [waMsgLimit, setWaMsgLimit] = useState(50);
  const [waCountdown, setWaCountdown] = useState(0);
  const [waCopied, setWaCopied] = useState(false);
  const waCountdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const waPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const waRefreshRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Daily Pulse state
  const [pulseEnabled, setPulseEnabled] = useState(false);
  const [pulseTime, setPulseTime] = useState('20:00');
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [pulsePreview, setPulsePreview] = useState<string | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const [sendingPulse, setSendingPulse] = useState(false);

  // Credit Top-up State
  const [extraCredits, setExtraCredits] = useState(0);
  const [showTopUpModal, setShowTopUpModal] = useState(false);
  const [buyingCredits, setBuyingCredits] = useState<string | null>(null);

  // AI Model State
  const [aiModel, setAiModel] = useState('standard');
  const [showModelPicker, setShowModelPicker] = useState(false);

  // Auto Reply State
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(false);
  const [autoReplyAudience, setAutoReplyAudience] = useState<'everyone' | 'customers_only' | 'new_contacts_only'>('everyone');
  const [showAudiencePicker, setShowAudiencePicker] = useState(false);

  // Team Management State
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [showSubscriptionModal, setShowSubscriptionModal] = useState(false);

  // Business Type State
  const [businessType, setBusinessType] = useState('');
  const [showBusinessTypePicker, setShowBusinessTypePicker] = useState(false);
  const [restaurantHasReservations, setRestaurantHasReservations] = useState(false);

  // Journey Settings — per-business-type config
  // Shared
  const [journeyDeliveryInfo, setJourneyDeliveryInfo] = useState('');
  const [journeyBusinessHours, setJourneyBusinessHours] = useState('');
  // Retail
  const [retailHasCustomOrders, setRetailHasCustomOrders] = useState(false);
  const [retailCustomLeadTime, setRetailCustomLeadTime] = useState('');
  const [retailReturnPolicy, setRetailReturnPolicy] = useState('');
  // Restaurant / food
  const [restaurantAvgWait, setRestaurantAvgWait] = useState('');
  const [restaurantMinDelivery, setRestaurantMinDelivery] = useState('');
  const [restaurantTableRange, setRestaurantTableRange] = useState('');
  // Bakery
  const [bakeryAdvanceDays, setBakeryAdvanceDays] = useState('3');
  const [bakeryDepositRequired, setBakeryDepositRequired] = useState(false);
  const [bakeryDepositPct, setBakeryDepositPct] = useState('50');
  // Grocery
  const [groceryDeliverySlots, setGroceryDeliverySlots] = useState('');
  const [groceryMinOrder, setGroceryMinOrder] = useState('');
  const [groceryAllowSubs, setGroceryAllowSubs] = useState(true);
  // Wholesale
  const [wholesaleLeadTime, setWholesaleLeadTime] = useState('');
  const [wholesaleMinOrderValue, setWholesaleMinOrderValue] = useState('');
  const [wholesalePaymentTerms, setWholesalePaymentTerms] = useState('');
  const [wholesaleHasCredit, setWholesaleHasCredit] = useState(false);
  // Salon
  const [salonMultipleStylists, setSalonMultipleStylists] = useState(false);
  const [salonStylistNames, setSalonStylistNames] = useState('');
  const [salonDepositRequired, setSalonDepositRequired] = useState(false);
  const [salonDepositPct, setSalonDepositPct] = useState('50');
  const [salonCancellationPolicy, setSalonCancellationPolicy] = useState('');
  // Spa
  const [spaHasCouples, setSpaHasCouples] = useState(true);
  const [spaDepositRequired, setSpaDepositRequired] = useState(true);
  const [spaDepositPct, setSpaDepositPct] = useState('50');
  const [spaCancellationHours, setSpaCancellationHours] = useState('24');
  // Repair
  const [repairHasOnsite, setRepairHasOnsite] = useState(true);
  const [repairHasDropoff, setRepairHasDropoff] = useState(true);
  const [repairDiagnosisFree, setRepairDiagnosisFree] = useState(true);
  const [repairTurnaround, setRepairTurnaround] = useState('');
  const [repairWarranty, setRepairWarranty] = useState('');
  // Services / Freelance
  const [servicesHasOnsite, setServicesHasOnsite] = useState(true);
  const [servicesHasRemote, setServicesHasRemote] = useState(true);
  const [servicesQuoteFirst, setServicesQuoteFirst] = useState(false);
  const [servicesDepositRequired, setServicesDepositRequired] = useState(false);
  const [servicesTurnaround, setServicesTurnaround] = useState('');
  const [servicesCancellationPolicy, setServicesCancellationPolicy] = useState('');
  // Support Agent
  const [supportResponseSla, setSupportResponseSla] = useState('');
  const [supportHasLiveHandoff, setSupportHasLiveHandoff] = useState(false);
  const [supportHasBilling, setSupportHasBilling] = useState(true);
  const [supportHasTechnical, setSupportHasTechnical] = useState(true);
  const [supportHasComplaints, setSupportHasComplaints] = useState(true);
  const [supportEscalationPolicy, setSupportEscalationPolicy] = useState('');
  const [supportRefundPolicy, setSupportRefundPolicy] = useState('');
  const [supportTicketPrefix, setSupportTicketPrefix] = useState('TKT');
  // Hotel
  const [hotelCheckinTime, setHotelCheckinTime] = useState('2:00 PM');
  const [hotelCheckoutTime, setHotelCheckoutTime] = useState('11:00 AM');
  const [hotelMinNights, setHotelMinNights] = useState('');
  const [hotelDepositRequired, setHotelDepositRequired] = useState(true);
  const [hotelDepositPct, setHotelDepositPct] = useState('30');
  const [hotelHasMealPlans, setHotelHasMealPlans] = useState(false);
  const [hotelMealPlanOptions, setHotelMealPlanOptions] = useState('');
  const [hotelHasAirportTransfer, setHotelHasAirportTransfer] = useState(false);
  const [hotelHasSpa, setHotelHasSpa] = useState(false);
  const [hotelHasPool, setHotelHasPool] = useState(false);
  const [hotelCancellationPolicy, setHotelCancellationPolicy] = useState('');
  // Rental
  const [rentalType, setRentalType] = useState('property');
  const [rentalDepositRequired, setRentalDepositRequired] = useState(true);
  const [rentalDepositPct, setRentalDepositPct] = useState('30');
  const [rentalMinNights, setRentalMinNights] = useState('');
  const [rentalCheckinTime, setRentalCheckinTime] = useState('');
  const [rentalCheckoutTime, setRentalCheckoutTime] = useState('');
  const [rentalPetPolicy, setRentalPetPolicy] = useState('');
  const [rentalCancellationPolicy, setRentalCancellationPolicy] = useState('');
  const [rentalHasExtras, setRentalHasExtras] = useState(false);
  // Cleaning
  const [cleaningHasRecurring, setCleaningHasRecurring] = useState(true);
  const [cleaningHasCommercial, setCleaningHasCommercial] = useState(false);
  const [cleaningSuppliesIncluded, setCleaningSuppliesIncluded] = useState(true);
  // Fitness
  const [fitnessHasClasses, setFitnessHasClasses] = useState(true);
  const [fitnessHasMemberships, setFitnessHasMemberships] = useState(true);
  const [fitnessHasPT, setFitnessHasPT] = useState(false);
  const [fitnessHasTrial, setFitnessHasTrial] = useState(true);
  const [fitnessClassSchedule, setFitnessClassSchedule] = useState('');
  // Events
  const [eventsDepositPct, setEventsDepositPct] = useState('50');
  const [eventsLeadTime, setEventsLeadTime] = useState('');
  const [eventsDeliveryDays, setEventsDeliveryDays] = useState('');
  // Healthcare
  const [hcConsultationFee, setHcConsultationFee] = useState('');
  const [hcHasLabTests, setHcHasLabTests] = useState(false);
  const [hcHasHomeVisit, setHcHasHomeVisit] = useState(false);
  const [hcPrepInstructions, setHcPrepInstructions] = useState('');
  const [hcInsuranceAccepted, setHcInsuranceAccepted] = useState('');
  // Creator
  const [creatorNiche, setCreatorNiche] = useState('');
  const [creatorPlatforms, setCreatorPlatforms] = useState('');
  const [creatorFollowers, setCreatorFollowers] = useState('');
  const [creatorLeadTime, setCreatorLeadTime] = useState('');
  const [creatorRevisions, setCreatorRevisions] = useState('');
  const [creatorUsageRights, setCreatorUsageRights] = useState('');
  const [creatorDepositPct, setCreatorDepositPct] = useState('50');
  const [creatorRatesOnRequest, setCreatorRatesOnRequest] = useState(false);
  const [journeySaving, setJourneySaving] = useState(false);

  // Staff list
  const [staffList, setStaffList] = useState<{id: string; name: string}[]>([]);
  const [newStaffName, setNewStaffName] = useState('');
  const [addingStaff, setAddingStaff] = useState(false);

  const { user, logout, refreshUser } = useAuth();
  const { refresh: refreshBusinessContext } = useBusiness();
  const router = useRouter();

  // IAP refs for purchase callbacks
  const pendingBundleIdRef = useRef<string | null>(null);
  const purchaseListenerRef = useRef<any>(null);
  const errorListenerRef = useRef<any>(null);

  useEffect(() => {
    fetchData();
    // Init IAP connection
    initConnection().catch(() => {});
    return () => {
      purchaseListenerRef.current?.remove();
      errorListenerRef.current?.remove();
    };
  }, []);

  const [currency, setCurrency] = useState('USD');

  const fetchJourneySettings = useCallback(async () => {
    try {
      const bk = await settingsAPI.getBusinessKnowledge() as any;
      setJourneyDeliveryInfo(bk.delivery_info || '');
      setJourneyBusinessHours(bk.business_hours || '');
      setRetailHasCustomOrders(!!bk.retail_has_custom_orders);
      setRetailCustomLeadTime(bk.retail_custom_lead_time || '');
      setRetailReturnPolicy(bk.retail_return_policy || '');
      setRestaurantAvgWait(bk.restaurant_avg_wait || '');
      setRestaurantMinDelivery(bk.restaurant_min_delivery || '');
      setRestaurantTableRange(bk.restaurant_table_range || '');
      setBakeryAdvanceDays(String(bk.bakery_advance_days ?? 3));
      setBakeryDepositRequired(!!bk.bakery_deposit_required);
      setBakeryDepositPct(String(bk.bakery_deposit_pct ?? 50));
      setGroceryDeliverySlots(bk.grocery_delivery_slots || '');
      setGroceryMinOrder(bk.grocery_min_order || '');
      setGroceryAllowSubs(bk.grocery_allow_substitutions !== false);
      setWholesaleLeadTime(bk.wholesale_lead_time || '');
      setWholesaleMinOrderValue(bk.wholesale_min_order_value || '');
      setWholesalePaymentTerms(bk.wholesale_payment_terms || '');
      setWholesaleHasCredit(!!bk.wholesale_has_credit_account);
      setSalonMultipleStylists(!!bk.salon_multiple_stylists);
      setSalonStylistNames(bk.salon_stylist_names || '');
      setSalonDepositRequired(!!bk.salon_deposit_required);
      setSalonDepositPct(String(bk.salon_deposit_pct ?? 50));
      setSalonCancellationPolicy(bk.salon_cancellation_policy || '');
      setSpaHasCouples(bk.spa_has_couples !== false);
      setSpaDepositRequired(bk.spa_deposit_required !== false);
      setSpaDepositPct(String(bk.spa_deposit_pct ?? 50));
      setSpaCancellationHours(String(bk.spa_cancellation_hours ?? 24));
      setRepairHasOnsite(bk.repair_has_onsite !== false);
      setRepairHasDropoff(bk.repair_has_dropoff !== false);
      setRepairDiagnosisFree(bk.repair_diagnosis_free !== false);
      setRepairTurnaround(bk.repair_turnaround || '');
      setRepairWarranty(bk.repair_warranty || '');
      setServicesHasOnsite(bk.services_has_onsite !== false);
      setServicesHasRemote(bk.services_has_remote !== false);
      setServicesQuoteFirst(!!bk.services_quote_first);
      setServicesDepositRequired(!!bk.services_deposit_required);
      setServicesTurnaround(bk.services_turnaround || '');
      setServicesCancellationPolicy(bk.services_cancellation_policy || '');
      setSupportResponseSla(bk.support_response_sla || '');
      setSupportHasLiveHandoff(!!bk.support_has_live_handoff);
      setSupportHasBilling(bk.support_has_billing_support !== false);
      setSupportHasTechnical(bk.support_has_technical_support !== false);
      setSupportHasComplaints(bk.support_has_complaints !== false);
      setSupportEscalationPolicy(bk.support_escalation_policy || '');
      setSupportRefundPolicy(bk.support_refund_policy || '');
      setSupportTicketPrefix(bk.support_ticket_prefix || 'TKT');
      setHotelCheckinTime(bk.hotel_checkin_time || '2:00 PM');
      setHotelCheckoutTime(bk.hotel_checkout_time || '11:00 AM');
      setHotelMinNights(String(bk.hotel_min_nights || ''));
      setHotelDepositRequired(bk.hotel_deposit_required !== false);
      setHotelDepositPct(String(bk.hotel_deposit_pct || 30));
      setHotelHasMealPlans(!!bk.hotel_has_meal_plans);
      setHotelMealPlanOptions(bk.hotel_meal_plan_options || '');
      setHotelHasAirportTransfer(!!bk.hotel_has_airport_transfer);
      setHotelHasSpa(!!bk.hotel_has_spa);
      setHotelHasPool(!!bk.hotel_has_pool);
      setHotelCancellationPolicy(bk.hotel_cancellation_policy || '');
      setRentalType(bk.rental_type || 'property');
      setRentalDepositRequired(bk.rental_deposit_required !== false);
      setRentalDepositPct(String(bk.rental_deposit_pct || 30));
      setRentalMinNights(String(bk.rental_min_nights || ''));
      setRentalCheckinTime(bk.rental_checkin_time || '');
      setRentalCheckoutTime(bk.rental_checkout_time || '');
      setRentalPetPolicy(bk.rental_pet_policy || '');
      setRentalCancellationPolicy(bk.rental_cancellation_policy || '');
      setRentalHasExtras(!!bk.rental_has_extras);
      setCleaningHasRecurring(bk.cleaning_has_recurring !== false);
      setCleaningHasCommercial(!!bk.cleaning_has_commercial);
      setCleaningSuppliesIncluded(bk.cleaning_supplies_included !== false);
      setFitnessHasClasses(bk.fitness_has_classes !== false);
      setFitnessHasMemberships(bk.fitness_has_memberships !== false);
      setFitnessHasPT(!!bk.fitness_has_personal_training);
      setFitnessHasTrial(bk.fitness_has_trial !== false);
      setFitnessClassSchedule(bk.fitness_class_schedule || '');
      setEventsDepositPct(String(bk.events_deposit_pct ?? 50));
      setEventsLeadTime(bk.events_lead_time || '');
      setEventsDeliveryDays(bk.events_delivery_days || '');
      setHcConsultationFee(bk.hc_consultation_fee || '');
      setHcHasLabTests(!!bk.hc_has_lab_tests);
      setHcHasHomeVisit(!!bk.hc_has_home_visit);
      setHcPrepInstructions(bk.hc_prep_instructions || '');
      setHcInsuranceAccepted(bk.hc_insurance_accepted || '');
      setCreatorNiche(bk.creator_niche || '');
      setCreatorPlatforms(bk.creator_platforms || '');
      setCreatorFollowers(bk.creator_followers || '');
      setCreatorLeadTime(bk.creator_lead_time || '');
      setCreatorRevisions(bk.creator_revisions || '');
      setCreatorUsageRights(bk.creator_usage_rights || '');
      setCreatorDepositPct(String(bk.creator_deposit_pct ?? 50));
      setCreatorRatesOnRequest(!!bk.creator_rates_on_request);
    } catch (e) {}
  }, []);

  // Re-sync journey settings every time the account tab gains focus
  // (keeps them in sync with BusinessKnowledgeModal which writes to the same keys)
  useFocusEffect(useCallback(() => {
    fetchJourneySettings();
  }, [fetchJourneySettings]));

  const fetchData = async () => {
    try {
      const [plansRes, statsRes, settingsRes] = await Promise.all([
        apiClient.get('/subscription/plans'),
        apiClient.get('/stats'),
        apiClient.get('/settings'),
      ]);
      setPlans(plansRes.data);
      setStats(statsRes.data);
      setPulseEnabled(settingsRes.data.daily_pulse_enabled || false);
      setPulseTime(settingsRes.data.daily_pulse_time || '20:00');
      if (settingsRes.data.currency) setCurrency(settingsRes.data.currency);
      setAiModel(settingsRes.data.ai_model || 'standard');
      setAutoReplyEnabled(settingsRes.data.auto_reply_enabled || false);
      setAutoReplyAudience(settingsRes.data.auto_reply_audience || 'everyone');
      setBusinessType(settingsRes.data.business_type || 'retail');
      setRestaurantHasReservations(settingsRes.data.restaurant_has_reservations || false);

      // Journey settings — load from business-knowledge
      await fetchJourneySettings();

      try {
        const staffRes = await apiClient.get('/settings/staff');
        setStaffList(staffRes.data.staff || []);
      } catch (e) {}

      // Fetch WhatsApp status
      try {
        const waRes = await whatsappAPI.getStatus();
        setWaConnected(waRes.connected);
        setWaStatus(waRes.status);
        setWaNumber(waRes.number || '');
        setWaMsgSent(waRes.messages_sent || 0);
        setWaMsgLimit(waRes.messages_limit || 50);
      } catch (e) {
        console.log('WhatsApp status not available');
      }

      // Load extra credits balance
      try {
        const statusRes = await apiClient.get('/subscription/status');
        setExtraCredits(statusRes.data.extra_credits || 0);
      } catch (e) { }
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const clearWaTimers = useCallback(() => {
    if (waCountdownRef.current) { clearInterval(waCountdownRef.current); waCountdownRef.current = null; }
    if (waPollingRef.current) { clearInterval(waPollingRef.current); waPollingRef.current = null; }
    if (waRefreshRef.current) { clearTimeout(waRefreshRef.current); waRefreshRef.current = null; }
  }, []);

  useEffect(() => {
    return () => clearWaTimers();
  }, [clearWaTimers]);

  const startPairingTimers = useCallback((code: string) => {
    clearWaTimers();
    setWaPairingCode(code);
    setWaCountdown(60);
    setWaCopied(false);

    // Copy to clipboard immediately
    Clipboard.setStringAsync(code).then(() => {
      setWaCopied(true);
      setTimeout(() => setWaCopied(false), 2000);
    });

    // Countdown timer
    waCountdownRef.current = setInterval(() => {
      setWaCountdown(prev => {
        if (prev <= 1) {
          if (waCountdownRef.current) clearInterval(waCountdownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    // Auto-refresh code at 50s (before 60s expiry)
    waRefreshRef.current = setTimeout(async () => {
      try {
        const res = await whatsappAPI.connect(waPhoneInput.trim());
        if (res.pairing_code) {
          startPairingTimers(res.pairing_code);
        }
      } catch (e) {
        console.log('Auto-refresh pairing code failed');
      }
    }, 50000);

    // Poll for connection every 5s
    waPollingRef.current = setInterval(async () => {
      try {
        const waRes = await whatsappAPI.getStatus();
        if (waRes.connected) {
          clearWaTimers();
          setWaConnected(true);
          setWaStatus(waRes.status);
          setWaNumber(waRes.number || '');
          setWaPairingCode('');
          setWaMsgSent(waRes.messages_sent || 0);
          setWaMsgLimit(waRes.messages_limit || 50);
          Alert.alert('Connected!', 'WhatsApp linked successfully.');
        }
      } catch (e) { /* ignore */ }
    }, 5000);
  }, [clearWaTimers, waPhoneInput]);

  const handleCopyCode = async () => {
    if (!waPairingCode) return;
    await Clipboard.setStringAsync(waPairingCode);
    setWaCopied(true);
    setTimeout(() => setWaCopied(false), 2000);
  };

  const handleOpenWhatsApp = () => {
    if (waPairingCode) {
      const link = `https://wa.me/login?code=${waPairingCode}`;
      Linking.openURL(link)
        .catch(() => Linking.openURL('whatsapp://'))
        .catch(() => {
          Alert.alert('Error', 'Could not open WhatsApp. Please open it manually and go to Linked Devices.');
        });
    } else {
      Linking.openURL('whatsapp://')
        .catch(() => {
          Alert.alert('Error', 'Could not open WhatsApp. Please open it manually.');
        });
    }
  };

  const handleWhatsAppConnect = async () => {
    if (!waPhoneInput.trim()) {
      Alert.alert('Error', 'Please enter your WhatsApp phone number');
      return;
    }
    setWaConnecting(true);
    setWaPairingCode('');
    try {
      const res = await whatsappAPI.connect(waPhoneInput.trim());
      if (res.pairing_code) {
        startPairingTimers(res.pairing_code);
      } else {
        Alert.alert('Error', res.message || 'Failed to get pairing code');
      }
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to connect WhatsApp');
    } finally {
      setWaConnecting(false);
    }
  };

  const handleWhatsAppDisconnect = async () => {
    Alert.alert(
      'Disconnect WhatsApp',
      'Are you sure? You will need to re-pair to send messages.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: async () => {
            setWaDisconnecting(true);
            try {
              await whatsappAPI.disconnect();
              setWaConnected(false);
              setWaStatus('not_connected');
              setWaNumber('');
              setWaPairingCode('');
              setWaPhoneInput('');
            } catch (error: any) {
              Alert.alert('Error', error.response?.data?.detail || 'Failed to disconnect');
            } finally {
              setWaDisconnecting(false);
            }
          },
        },
      ]
    );
  };

  const handleSubscribe = async (plan: SubscriptionPlan) => {
    if (!user) return;

    Alert.alert(
      'Subscribe',
      `Subscribe to ${plan.name} plan (${plan.currency || currency} ${plan.amount_display})?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Subscribe',
          onPress: async () => {
            setSubscribing(true);
            try {
              await apiClient.post('/subscription/verify-purchase', {
                plan_id: plan.id,
                purchase_token: `manual_${Date.now()}`,
                platform: Platform.OS,
              });
              Alert.alert('Success', 'Your subscription has been activated!');
              refreshUser();
            } catch (error: any) {
              Alert.alert('Error', error.response?.data?.detail || 'Failed to activate subscription');
            } finally {
              setSubscribing(false);
            }
          },
        },
      ]
    );
  };

  const handleTogglePulse = async (value: boolean) => {
    setPulseEnabled(value);
    try {
      await apiClient.put('/settings', { daily_pulse_enabled: value });
      if (value) {
        Alert.alert('Daily Pulse Enabled', `You'll receive your business summary every day at ${formatTime(pulseTime)} via WhatsApp.`);
      }
    } catch (error) {
      setPulseEnabled(!value);
      Alert.alert('Error', 'Failed to update setting');
    }
  };

  const handlePulseTimeChange = async (event: any, selectedDate?: Date) => {
    setShowTimePicker(false);
    if (event.type === 'set' && selectedDate) {
      const hours = selectedDate.getHours().toString().padStart(2, '0');
      const minutes = selectedDate.getMinutes().toString().padStart(2, '0');
      const newTime = `${hours}:${minutes}`;
      setPulseTime(newTime);
      try {
        await apiClient.put('/settings', { daily_pulse_time: newTime });
      } catch (error) {
        Alert.alert('Error', 'Failed to update time');
      }
    }
  };

  const formatTime = (time: string) => {
    const [h, m] = time.split(':');
    const hour = parseInt(h);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const hour12 = hour % 12 || 12;
    return `${hour12}:${m} ${ampm}`;
  };

  const handlePreviewPulse = async () => {
    setLoadingPreview(true);
    setPreviewVisible(true);
    try {
      const res = await apiClient.get('/daily-pulse/preview');
      setPulsePreview(res.data.message);
    } catch (error) {
      setPulsePreview('Failed to load preview. Please try again.');
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleSendPulseNow = async () => {
    setSendingPulse(true);
    try {
      await apiClient.post('/daily-pulse/send');
      Alert.alert('Sent!', 'Daily pulse sent to your WhatsApp!');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to send pulse');
    } finally {
      setSendingPulse(false);
    }
  };

  const handleModelChange = async (model: string) => {
    setAiModel(model);
    setShowModelPicker(false);
    try {
      await apiClient.put('/settings', { ai_model: model });
      Alert.alert('Success', `AI Model updated to ${getModelName(model)}`);
    } catch (error) {
      setAiModel('standard'); // revert
      Alert.alert('Error', 'Failed to update AI model');
    }
  };

  const getModelName = (modelId: string) => {
    switch (modelId) {
      case 'deepseek': return 'DeepSeek V3 (1x)';
      case 'standard': return 'GPT-4o Mini (1.6x)';
      case 'grok': return 'Grok 4.1 (1.7x)';
      case 'gpt5': return 'GPT-5 (12x)';
      case 'premium': return 'GPT-4o (15x)';
      case 'claude-3.5': return 'Claude 3.5 (12x)';
      default: return 'GPT-4o Mini (1.6x)';
    }
  };

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/');
          },
        },
      ]
    );
  };

  const saveJourneySettings = async (patch: Record<string, any>) => {
    setJourneySaving(true);
    try {
      await settingsAPI.updateBusinessKnowledge(patch);
    } catch (e) { console.log('Journey save error', e); }
    finally { setJourneySaving(false); }
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
      <ScrollView contentContainerStyle={styles.scrollContent}>

        {/* Business Info */}
        <View style={styles.section}>
          <View style={styles.businessCard}>
            <View style={styles.businessAvatar}>
              <Text style={styles.businessAvatarText}>
                {user?.business_name?.charAt(0) || 'B'}
              </Text>
            </View>
            <View style={styles.businessInfo}>
              <Text style={styles.businessName}>{user?.business_name || 'Your Business'}</Text>
              <Text style={styles.businessPhone}>{user?.phone_number}</Text>
              {user?.owner_name && (
                <Text style={styles.ownerName}>{user.owner_name}</Text>
              )}
            </View>
            <View style={[
              styles.subscriptionBadge,
              user?.subscription_active && styles.subscriptionActive,
            ]}>
              <Text style={styles.subscriptionText}>
                {user?.subscription_active ? user?.subscription_plan || 'Active' : 'Free Trial'}
              </Text>
            </View>
          </View>
        </View>

        {/* WhatsApp Business */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>WhatsApp Business</Text>
          <View style={styles.settingsCard}>
            {waConnected ? (
              <View>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: '#25D366', marginRight: 10 }} />
                  <Text style={{ color: '#25D366', fontSize: 16, fontWeight: '600', flex: 1 }}>Connected</Text>
                  <TouchableOpacity onPress={handleWhatsAppDisconnect} disabled={waDisconnecting}>
                    <Text style={{ color: '#FF4444', fontSize: 14 }}>{waDisconnecting ? 'Disconnecting...' : 'Disconnect'}</Text>
                  </TouchableOpacity>
                </View>
                <Text style={{ color: '#8B9DC3', fontSize: 14 }}>Number: {waNumber}</Text>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                  <Text style={{ color: '#8B9DC3', fontSize: 13 }}>Messages this month</Text>
                  <Text style={{ color: '#FFFFFF', fontSize: 13, fontWeight: '600' }}>{waMsgSent} / {waMsgLimit}</Text>
                </View>
                <View style={{ height: 4, backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 2, marginTop: 6 }}>
                  <View style={{ height: 4, backgroundColor: waMsgSent / waMsgLimit > 0.9 ? '#FF4444' : '#25D366', borderRadius: 2, width: `${Math.min((waMsgSent / waMsgLimit) * 100, 100)}%` }} />
                </View>
                <TouchableOpacity
                  style={{ backgroundColor: 'rgba(37,211,102,0.1)', borderRadius: 10, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginTop: 12 }}
                  onPress={async () => {
                    try {
                      Alert.alert('Syncing...', 'Pulling contacts and chat history from WhatsApp. This may take a few minutes...');
                      const result = await whatsappAPI.sync();
                      const c = result.contacts || {};
                      const h = result.history || {};
                      const t = result.totals || {};
                      Alert.alert(
                        'Sync Complete',
                        `This sync: ${c.created || 0} new contacts, ${c.updated || 0} updated, ${h.chats_synced || 0} chats synced, ${h.messages_synced || 0} messages pulled\n\nTotal in app: ${t.customers || 0} contacts, ${t.messages || 0} messages (${t.synced_messages || 0} from WhatsApp history)\n\nAI classification running in background. Go to Customers tab to see your contacts and tap any to view chat history.`
                      );
                    } catch (e: any) {
                      Alert.alert('Sync Failed', e.response?.data?.detail || e.message || 'Could not sync WhatsApp data. Try again.');
                    }
                  }}
                >
                  <Ionicons name="sync-outline" size={18} color="#25D366" />
                  <Text style={{ color: '#25D366', fontSize: 14, fontWeight: '600', marginLeft: 8 }}>Sync WhatsApp Contacts & Chats</Text>
                </TouchableOpacity>
              </View>
            ) : waPairingCode ? (
              <View>
                <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginBottom: 8 }}>Enter this code in WhatsApp</Text>
                <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 12 }}>
                  Open WhatsApp {'>'} Linked Devices {'>'} Link a Device {'>'} Link with phone number
                </Text>
                <TouchableOpacity
                  onPress={handleCopyCode}
                  activeOpacity={0.7}
                  style={{ backgroundColor: 'rgba(37,211,102,0.1)', borderRadius: 12, padding: 20, alignItems: 'center', marginBottom: 8 }}
                >
                  <Text style={{ color: '#25D366', fontSize: 32, fontWeight: '700', letterSpacing: 8 }}>{waPairingCode}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 10 }}>
                    <Ionicons name={waCopied ? 'checkmark-circle' : 'copy-outline'} size={16} color={waCopied ? '#25D366' : '#8B9DC3'} />
                    <Text style={{ color: waCopied ? '#25D366' : '#8B9DC3', fontSize: 12, marginLeft: 6 }}>
                      {waCopied ? 'Copied to clipboard!' : 'Tap to copy code'}
                    </Text>
                  </View>
                </TouchableOpacity>
                <View style={{ backgroundColor: 'rgba(37,211,102,0.05)', borderRadius: 10, padding: 12, marginBottom: 12 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
                    <Ionicons name="notifications" size={18} color="#25D366" />
                    <Text style={{ color: '#25D366', fontSize: 13, fontWeight: '600', marginLeft: 8 }}>Check your phone for push notification</Text>
                  </View>
                  <Text style={{ color: '#8B9DC3', fontSize: 12, lineHeight: 18 }}>
                    WhatsApp will send a notification to link this device. Tap it to open the pairing screen, then enter the code above.
                  </Text>
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginBottom: 12 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: waCountdown > 10 ? '#25D366' : '#FF4444', marginRight: 8 }} />
                  <Text style={{ color: waCountdown > 10 ? '#8B9DC3' : '#FF4444', fontSize: 12 }}>
                    {waCountdown > 0 ? `Code refreshes in ${waCountdown}s` : 'Refreshing code...'}
                  </Text>
                </View>
                <ActivityIndicator size="small" color="#25D366" />
                <Text style={{ color: '#8B9DC3', fontSize: 11, textAlign: 'center', marginTop: 6 }}>Waiting for connection...</Text>
                <TouchableOpacity
                  style={{ marginTop: 14, alignItems: 'center' }}
                  onPress={() => { clearWaTimers(); setWaPairingCode(''); setWaPhoneInput(''); }}
                >
                  <Text style={{ color: '#8B9DC3', fontSize: 14 }}>Cancel</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
                  <Ionicons name="logo-whatsapp" size={24} color="#25D366" />
                  <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginLeft: 10 }}>Connect WhatsApp</Text>
                </View>
                <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 16 }}>
                  Link your WhatsApp number to send messages directly from the app.
                </Text>
                <TextInput
                  style={{
                    backgroundColor: 'rgba(255,255,255,0.08)',
                    borderRadius: 10,
                    paddingHorizontal: 16,
                    paddingVertical: 12,
                    fontSize: 16,
                    color: '#FFFFFF',
                    marginBottom: 12,
                  }}
                  placeholder="+1234567890"
                  placeholderTextColor="#666"
                  value={waPhoneInput}
                  onChangeText={setWaPhoneInput}
                  keyboardType="phone-pad"
                />
                <TouchableOpacity
                  style={{
                    backgroundColor: '#25D366',
                    borderRadius: 10,
                    paddingVertical: 14,
                    alignItems: 'center',
                    opacity: waConnecting ? 0.7 : 1,
                  }}
                  onPress={handleWhatsAppConnect}
                  disabled={waConnecting}
                >
                  {waConnecting ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600' }}>Get Pairing Code</Text>
                  )}
                </TouchableOpacity>
              </View>
            )}
          </View>
        </View>

        {/* Message Credits */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Message Credits</Text>
          <View style={styles.settingsCard}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text style={{ color: '#8B9DC3', fontSize: 13 }}>Plan quota used</Text>
              <Text style={{ color: '#FFFFFF', fontSize: 13, fontWeight: '600' }}>{waMsgSent} / {waMsgLimit}</Text>
            </View>
            <View style={{ height: 4, backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 2, marginBottom: 8 }}>
              <View style={{ height: 4, backgroundColor: waMsgSent / Math.max(waMsgLimit, 1) > 0.9 ? '#FF4444' : '#25D366', borderRadius: 2, width: `${Math.min((waMsgSent / Math.max(waMsgLimit, 1)) * 100, 100)}%` }} />
            </View>
            {extraCredits > 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 }}>
                <Ionicons name="wallet-outline" size={14} color="#FFC107" />
                <Text style={{ color: '#FFC107', fontSize: 12, marginLeft: 6 }}>{extraCredits} extra credits in balance</Text>
              </View>
            )}
            <TouchableOpacity
              style={{ backgroundColor: 'rgba(255,193,7,0.1)', borderRadius: 10, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(255,193,7,0.3)' }}
              onPress={() => setShowTopUpModal(true)}
            >
              <Ionicons name="add-circle-outline" size={18} color="#FFC107" />
              <Text style={{ color: '#FFC107', fontSize: 14, fontWeight: '600', marginLeft: 8 }}>Buy Extra Credits</Text>
            </TouchableOpacity>
            <Text style={{ color: '#555', fontSize: 11, textAlign: 'center', marginTop: 8 }}>Credits never expire · Stack on top of your plan</Text>
          </View>
        </View>

        {/* Stats */}
        {
          stats && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>This Month</Text>
              <View style={styles.statsGrid}>
                <View style={styles.statCard}>
                  <Ionicons name="people" size={24} color="#25D366" />
                  <Text style={styles.statValue}>{stats.customers_count}</Text>
                  <Text style={styles.statLabel}>Customers</Text>
                </View>
                <View style={styles.statCard}>
                  <Ionicons name="notifications" size={24} color="#FFD700" />
                  <Text style={styles.statValue}>{stats.pending_followups}</Text>
                  <Text style={styles.statLabel}>Follow-ups</Text>
                </View>
                <View style={styles.statCard}>
                  <Ionicons name="receipt" size={24} color="#4A90D9" />
                  <Text style={styles.statValue}>{stats.sales_this_month}</Text>
                  <Text style={styles.statLabel}>Sales</Text>
                </View>
                <View style={styles.statCard}>
                  <Ionicons name="cash" size={24} color="#25D366" />
                  <Text style={styles.statValue}>{currency} {stats.revenue_this_month.toLocaleString()}</Text>
                  <Text style={styles.statLabel}>Revenue</Text>
                </View>
              </View>
            </View>
          )
        }

        {/* Smart Sourcing Agent - Prominent Access */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Smart Sourcing</Text>
          <TouchableOpacity
            style={styles.businessCard} // Reusing business card style for consistency
            onPress={() => router.push('/(tabs)/customers?mode=suppliers')}
          >
            <View style={[styles.businessAvatar, { backgroundColor: '#4A90D9' }]}>
              <Ionicons name="cube" size={24} color="#FFFFFF" />
            </View>
            <View style={styles.businessInfo}>
              <Text style={styles.businessName}>Sourcing Agent</Text>
              <Text style={styles.businessPhone}>Manage suppliers & inventory alerts</Text>
            </View>
            <Ionicons name="chevron-forward" size={24} color="#666" />
          </TouchableOpacity>
        </View>

        {/* Subscription Plans */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Subscription</Text>
          <TouchableOpacity
            style={styles.upgradeCard}
            onPress={() => setShowSubscriptionModal(true)}
            activeOpacity={0.85}
          >
            <View style={styles.upgradeCardLeft}>
              <Text style={styles.upgradeEmoji}>🎉</Text>
              <View>
                <Text style={styles.upgradeTitle}>
                  {user?.subscription_plan && user.subscription_plan !== 'free'
                    ? `Active: ${user.subscription_plan}`
                    : '50% OFF — First 3 Months'}
                </Text>
                <Text style={styles.upgradeSubtitle}>
                  {user?.subscription_plan && user.subscription_plan !== 'free'
                    ? 'Tap to manage your subscription'
                    : 'Limited-time launch offer · Tap to upgrade'}
                </Text>
              </View>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#25D366" />
          </TouchableOpacity>
        </View>

        {/* Settings */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Settings</Text>
          <View style={styles.settingsCard}>
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => setShowTeamModal(true)}
            >
              <Ionicons 
                name={user?.team_members_count && user.team_members_count > 1 ? "people" : "person-add-outline"} 
                size={24} 
                color={user?.team_members_count && user.team_members_count > 1 ? "#4A90D9" : "#25D366"} 
              />
              <Text style={styles.settingText}>
                {user?.team_members_count && user.team_members_count > 1 ? "Team Management" : "Add Team Members"}
              </Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => router.push('../analytics' as any)}
            >
              <Ionicons name="analytics-outline" size={24} color="#25D366" />
              <Text style={styles.settingText}>Analytics</Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => setShowBusinessTypePicker(true)}
            >
              <Ionicons name="storefront-outline" size={24} color="#25D366" />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.settingText}>Business Type</Text>
                <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                  {({
                    retail: 'Retail / Shop', wholesale: 'Wholesale / B2B',
                    restaurant: 'Restaurant / Café', food: 'Food Delivery',
                    bakery: 'Bakery', grocery: 'Grocery / Supermarket',
                    salon: 'Salon & Beauty', spa: 'Spa & Wellness',
                    services: 'Services / Freelance', repair: 'Repair & Maintenance',
                    cleaning: 'Cleaning Services', fitness: 'Gym & Fitness',
                    events: 'Events & Photography', healthcare: 'Healthcare / Clinic',
                    rental: 'Rental / Airbnb', hotel: 'Hotel / Hospitality', support: 'Support Agent', creator: 'Creator / Digital',
                    general: 'General / Other',
                  } as any)[businessType] || businessType}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            {['restaurant', 'food', 'bakery'].includes(businessType) && (
              <View style={[styles.settingItem, { paddingVertical: 14 }]}>
                <Ionicons name="calendar-outline" size={24} color="#25D366" />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.settingText}>Table Reservations</Text>
                  <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>Customers can book tables via WhatsApp</Text>
                </View>
                <Switch
                  value={restaurantHasReservations}
                  onValueChange={async (val) => {
                    setRestaurantHasReservations(val);
                    try {
                      await settingsAPI.updateSettings({ restaurant_has_reservations: val } as any);
                    } catch (e) { console.log('Failed to save reservation setting', e); }
                  }}
                  trackColor={{ false: '#333', true: '#1A3A2A' }}
                  thumbColor={restaurantHasReservations ? '#25D366' : '#666'}
                />
              </View>
            )}

            {/* ── Journey Settings (per-business-type) ── */}
            {(() => {
              const jLabelStyle = { fontSize: 13, color: '#8B9DC3', marginBottom: 4, marginTop: 12 };
              const jInputStyle = { backgroundColor: '#1a1a1a', borderRadius: 8, borderWidth: 1, borderColor: '#333', color: '#fff', fontSize: 14, paddingHorizontal: 12, paddingVertical: 9 };
              const jHintStyle = { fontSize: 11, color: '#555', marginTop: 3 };
              const jRowStyle = { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, paddingVertical: 10 };
              const jSwitchRow = (label: string, hint: string, value: boolean, onToggle: (v: boolean) => void) => (
                <View style={jRowStyle}>
                  <View style={{ flex: 1, marginRight: 12 }}>
                    <Text style={{ color: '#ccc', fontSize: 14 }}>{label}</Text>
                    {!!hint && <Text style={jHintStyle}>{hint}</Text>}
                  </View>
                  <Switch value={value} onValueChange={onToggle} trackColor={{ false: '#333', true: '#1A3A2A' }} thumbColor={value ? '#25D366' : '#666'} />
                </View>
              );
              const jTextField = (label: string, hint: string, value: string, onChange: (v: string) => void, onBlur: () => void, placeholder?: string, multiline?: boolean) => (
                <View>
                  <Text style={jLabelStyle}>{label}</Text>
                  <TextInput
                    style={[jInputStyle, multiline && { minHeight: 60, textAlignVertical: 'top' }]}
                    value={value}
                    onChangeText={onChange}
                    onBlur={onBlur}
                    placeholder={placeholder || ''}
                    placeholderTextColor="#555"
                    multiline={multiline}
                  />
                  {!!hint && <Text style={jHintStyle}>{hint}</Text>}
                </View>
              );

              const sharedFields = (
                <>
                  {jTextField('Delivery Info', 'Zones, fees, estimated times — shared in AI replies', journeyDeliveryInfo, setJourneyDeliveryInfo, () => saveJourneySettings({ delivery_info: journeyDeliveryInfo }), 'e.g. Free delivery within CBD, KES 200 outside')}
                  {jTextField('Business Hours', 'When you are open — AI will quote these', journeyBusinessHours, setJourneyBusinessHours, () => saveJourneySettings({ business_hours: journeyBusinessHours }), 'e.g. Mon–Sat 8am–8pm, Sun 10am–4pm')}
                </>
              );

              if (businessType === 'restaurant' || businessType === 'food') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🍽️ Service Settings</Text>
                  {sharedFields}
                  {jTextField('Avg. Wait / Prep Time', 'Shown to customers after ordering', restaurantAvgWait, setRestaurantAvgWait, () => saveJourneySettings({ restaurant_avg_wait: restaurantAvgWait }), 'e.g. 25–35 minutes')}
                  {jTextField('Min. Delivery Order', '', restaurantMinDelivery, setRestaurantMinDelivery, () => saveJourneySettings({ restaurant_min_delivery: restaurantMinDelivery }), 'e.g. KES 500')}
                  {businessType === 'restaurant' && jTextField('Table Range', 'Helps AI ask for the right table number', restaurantTableRange, setRestaurantTableRange, () => saveJourneySettings({ restaurant_table_range: restaurantTableRange }), 'e.g. Tables 1–20')}
                </View>
              );

              if (businessType === 'bakery') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🧁 Bakery Settings</Text>
                  {sharedFields}
                  {jTextField('Advance Notice (days)', 'Minimum days required for custom/cake orders', bakeryAdvanceDays, setBakeryAdvanceDays, () => saveJourneySettings({ bakery_advance_days: parseInt(bakeryAdvanceDays) || 3 }), 'e.g. 3')}
                  {jSwitchRow('Require Deposit for Custom Orders', 'AI will request a deposit before confirming', bakeryDepositRequired, (v) => { setBakeryDepositRequired(v); saveJourneySettings({ bakery_deposit_required: v }); })}
                  {bakeryDepositRequired && jTextField('Deposit %', '', bakeryDepositPct, setBakeryDepositPct, () => saveJourneySettings({ bakery_deposit_pct: parseInt(bakeryDepositPct) || 50 }), 'e.g. 50')}
                </View>
              );

              if (businessType === 'grocery') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🛒 Grocery Settings</Text>
                  {sharedFields}
                  {jTextField('Min. Order Value', '', groceryMinOrder, setGroceryMinOrder, () => saveJourneySettings({ grocery_min_order: groceryMinOrder }), 'e.g. KES 500')}
                  {jTextField('Delivery Slots', 'AI will present these options to customers', groceryDeliverySlots, setGroceryDeliverySlots, () => saveJourneySettings({ grocery_delivery_slots: groceryDeliverySlots }), 'e.g. Morning (8–12), Afternoon (13–17)')}
                  {jSwitchRow('Suggest Substitutes', 'Offer alternatives when item is out of stock', groceryAllowSubs, (v) => { setGroceryAllowSubs(v); saveJourneySettings({ grocery_allow_substitutions: v }); })}
                </View>
              );

              if (businessType === 'wholesale') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>📦 Wholesale Settings</Text>
                  {sharedFields}
                  {jTextField('Lead Time', 'How long to prepare/deliver orders', wholesaleLeadTime, setWholesaleLeadTime, () => saveJourneySettings({ wholesale_lead_time: wholesaleLeadTime }), 'e.g. 2–3 business days')}
                  {jTextField('Min. Order Value', '', wholesaleMinOrderValue, setWholesaleMinOrderValue, () => saveJourneySettings({ wholesale_min_order_value: wholesaleMinOrderValue }), 'e.g. KES 5,000')}
                  {jTextField('Payment Terms', 'AI will quote these to B2B customers', wholesalePaymentTerms, setWholesalePaymentTerms, () => saveJourneySettings({ wholesale_payment_terms: wholesalePaymentTerms }), 'e.g. Cash on delivery, Bank transfer net 7')}
                  {jSwitchRow('Credit Accounts', 'Some customers pay on credit terms', wholesaleHasCredit, (v) => { setWholesaleHasCredit(v); saveJourneySettings({ wholesale_has_credit_account: v }); })}
                </View>
              );

              if (businessType === 'salon' || businessType === 'beauty') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>💇 Salon Settings</Text>
                  {sharedFields}
                  {jSwitchRow('Multiple Stylists', 'AI will ask for stylist preference', salonMultipleStylists, (v) => { setSalonMultipleStylists(v); saveJourneySettings({ salon_multiple_stylists: v }); })}
                  {salonMultipleStylists && jTextField('Stylist Names', 'Comma-separated list', salonStylistNames, setSalonStylistNames, () => saveJourneySettings({ salon_stylist_names: salonStylistNames }), 'e.g. Grace, Diana, Amina')}
                  {jSwitchRow('Require Deposit', 'Deposit needed to confirm booking', salonDepositRequired, (v) => { setSalonDepositRequired(v); saveJourneySettings({ salon_deposit_required: v }); })}
                  {salonDepositRequired && jTextField('Deposit %', '', salonDepositPct, setSalonDepositPct, () => saveJourneySettings({ salon_deposit_pct: parseInt(salonDepositPct) || 50 }), 'e.g. 50')}
                  {jTextField('Cancellation Policy', 'Shown to customer at booking', salonCancellationPolicy, setSalonCancellationPolicy, () => saveJourneySettings({ salon_cancellation_policy: salonCancellationPolicy }), 'e.g. 24hrs notice required')}
                </View>
              );

              if (businessType === 'spa') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🌿 Spa Settings</Text>
                  {sharedFields}
                  {jSwitchRow('Couples Treatments', 'AI will ask if booking is solo or couple', spaHasCouples, (v) => { setSpaHasCouples(v); saveJourneySettings({ spa_has_couples: v }); })}
                  {jSwitchRow('Require Deposit', '', spaDepositRequired, (v) => { setSpaDepositRequired(v); saveJourneySettings({ spa_deposit_required: v }); })}
                  {spaDepositRequired && jTextField('Deposit %', '', spaDepositPct, setSpaDepositPct, () => saveJourneySettings({ spa_deposit_pct: parseInt(spaDepositPct) || 50 }), 'e.g. 50')}
                  {jTextField('Cancellation Notice (hours)', '', spaCancellationHours, setSpaCancellationHours, () => saveJourneySettings({ spa_cancellation_hours: parseInt(spaCancellationHours) || 24 }), 'e.g. 24')}
                </View>
              );

              if (businessType === 'repair') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🛠️ Repair Settings</Text>
                  {sharedFields}
                  {jSwitchRow('On-site Visits', 'AI will offer on-site repair option', repairHasOnsite, (v) => { setRepairHasOnsite(v); saveJourneySettings({ repair_has_onsite: v }); })}
                  {jSwitchRow('Drop-off at Shop', 'AI will offer drop-off option', repairHasDropoff, (v) => { setRepairHasDropoff(v); saveJourneySettings({ repair_has_dropoff: v }); })}
                  {jSwitchRow('Free Diagnosis', 'Initial diagnosis is free — no commitment', repairDiagnosisFree, (v) => { setRepairDiagnosisFree(v); saveJourneySettings({ repair_diagnosis_free: v }); })}
                  {jTextField('Typical Turnaround', '', repairTurnaround, setRepairTurnaround, () => saveJourneySettings({ repair_turnaround: repairTurnaround }), 'e.g. Same day to 3 days')}
                  {jTextField('Warranty Policy', 'AI will mention this after booking', repairWarranty, setRepairWarranty, () => saveJourneySettings({ repair_warranty: repairWarranty }), 'e.g. 3-month warranty on parts')}
                </View>
              );

              if (businessType === 'services') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🔧 Services / Freelance Settings</Text>
                  {sharedFields}
                  {jSwitchRow('On-site / Field Work', 'AI will offer on-site or field visits', servicesHasOnsite, (v) => { setServicesHasOnsite(v); saveJourneySettings({ services_has_onsite: v }); })}
                  {jSwitchRow('Remote Work', 'AI will offer remote / online delivery', servicesHasRemote, (v) => { setServicesHasRemote(v); saveJourneySettings({ services_has_remote: v }); })}
                  {jSwitchRow('Quote First', 'AI collects requirements then notifies owner before confirming price', servicesQuoteFirst, (v) => { setServicesQuoteFirst(v); saveJourneySettings({ services_quote_first: v }); })}
                  {jSwitchRow('Require Deposit', 'Deposit needed to confirm booking', servicesDepositRequired, (v) => { setServicesDepositRequired(v); saveJourneySettings({ services_deposit_required: v }); })}
                  {jTextField('Typical Turnaround', 'Shown to customers when scoping work', servicesTurnaround, setServicesTurnaround, () => saveJourneySettings({ services_turnaround: servicesTurnaround }), 'e.g. 3–5 business days')}
                  {jTextField('Cancellation Policy', '', servicesCancellationPolicy, setServicesCancellationPolicy, () => saveJourneySettings({ services_cancellation_policy: servicesCancellationPolicy }), 'e.g. 48hrs notice required')}
                </View>
              );

              if (businessType === 'support') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 2 }}>🎧 Support Agent Settings</Text>
                  <Text style={{ color: '#8B9DC3', fontSize: 11, marginBottom: 8 }}>Configure how your AI handles customer queries, complaints and escalations</Text>
                  {jTextField('Ticket Prefix', 'Used in ticket reference numbers shown to customers', supportTicketPrefix, setSupportTicketPrefix, () => saveJourneySettings({ support_ticket_prefix: supportTicketPrefix }), 'e.g. TKT, REF, CASE')}
                  {jTextField('Response SLA', 'Quoted to customers when logging a ticket', supportResponseSla, setSupportResponseSla, () => saveJourneySettings({ support_response_sla: supportResponseSla }), 'e.g. within 2 business hours')}
                  {jSwitchRow('Billing Support', 'AI handles payment, invoice & refund queries', supportHasBilling, (v) => { setSupportHasBilling(v); saveJourneySettings({ support_has_billing_support: v }); })}
                  {jSwitchRow('Technical Support', 'AI handles bugs, errors & setup issues', supportHasTechnical, (v) => { setSupportHasTechnical(v); saveJourneySettings({ support_has_technical_support: v }); })}
                  {jSwitchRow('Complaints Handling', 'AI empathetically handles formal complaints', supportHasComplaints, (v) => { setSupportHasComplaints(v); saveJourneySettings({ support_has_complaints: v }); })}
                  {jSwitchRow('Live Handoff', 'AI can connect customer to a human agent on request', supportHasLiveHandoff, (v) => { setSupportHasLiveHandoff(v); saveJourneySettings({ support_has_live_handoff: v }); })}
                  {jTextField('Escalation Policy', 'Rules for when AI should notify the owner', supportEscalationPolicy, setSupportEscalationPolicy, () => saveJourneySettings({ support_escalation_policy: supportEscalationPolicy }), 'e.g. Billing disputes and complaints always escalate', true)}
                  {supportHasBilling && jTextField('Refund Policy', 'Shared with customers who ask about refunds', supportRefundPolicy, setSupportRefundPolicy, () => saveJourneySettings({ support_refund_policy: supportRefundPolicy }), 'e.g. Refunds processed within 5–7 business days', true)}
                </View>
              );

              if (businessType === 'hotel') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🏨 Hotel Settings</Text>
                  {jTextField('Check-in Time', '', hotelCheckinTime, setHotelCheckinTime, () => saveJourneySettings({ hotel_checkin_time: hotelCheckinTime }), 'e.g. 2:00 PM')}
                  {jTextField('Check-out Time', '', hotelCheckoutTime, setHotelCheckoutTime, () => saveJourneySettings({ hotel_checkout_time: hotelCheckoutTime }), 'e.g. 11:00 AM')}
                  {jTextField('Minimum Nights', 'Leave blank if no minimum', hotelMinNights, setHotelMinNights, () => saveJourneySettings({ hotel_min_nights: parseInt(hotelMinNights) || 0 }), 'e.g. 2')}
                  {jSwitchRow('Require Deposit', 'AI will request deposit to confirm reservation', hotelDepositRequired, (v) => { setHotelDepositRequired(v); saveJourneySettings({ hotel_deposit_required: v }); })}
                  {hotelDepositRequired && jTextField('Deposit %', '', hotelDepositPct, setHotelDepositPct, () => saveJourneySettings({ hotel_deposit_pct: parseInt(hotelDepositPct) || 30 }), 'e.g. 30')}
                  {jSwitchRow('Meal Plans', 'AI will ask guests to choose a meal plan', hotelHasMealPlans, (v) => { setHotelHasMealPlans(v); saveJourneySettings({ hotel_has_meal_plans: v }); })}
                  {hotelHasMealPlans && jTextField('Meal Plan Options', 'Comma-separated', hotelMealPlanOptions, setHotelMealPlanOptions, () => saveJourneySettings({ hotel_meal_plan_options: hotelMealPlanOptions }), 'e.g. Room Only, B&B, Half Board, Full Board')}
                  {jSwitchRow('Airport Transfer', 'AI will offer and collect flight details', hotelHasAirportTransfer, (v) => { setHotelHasAirportTransfer(v); saveJourneySettings({ hotel_has_airport_transfer: v }); })}
                  {jSwitchRow('Spa', 'Mention spa as an amenity during booking', hotelHasSpa, (v) => { setHotelHasSpa(v); saveJourneySettings({ hotel_has_spa: v }); })}
                  {jSwitchRow('Swimming Pool', 'Mention pool as an amenity during booking', hotelHasPool, (v) => { setHotelHasPool(v); saveJourneySettings({ hotel_has_pool: v }); })}
                  {jTextField('Cancellation Policy', '', hotelCancellationPolicy, setHotelCancellationPolicy, () => saveJourneySettings({ hotel_cancellation_policy: hotelCancellationPolicy }), 'e.g. Free cancellation 48hrs before check-in')}
                </View>
              );

              if (businessType === 'rental') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🏠 Rental Settings</Text>
                  {jTextField('Rental Type', 'Helps AI use the right language', rentalType, setRentalType, () => saveJourneySettings({ rental_type: rentalType }), 'property / car / equipment / mixed')}
                  {jSwitchRow('Require Deposit', 'AI will collect deposit to confirm booking', rentalDepositRequired, (v) => { setRentalDepositRequired(v); saveJourneySettings({ rental_deposit_required: v }); })}
                  {rentalDepositRequired && jTextField('Deposit %', '', rentalDepositPct, setRentalDepositPct, () => saveJourneySettings({ rental_deposit_pct: parseInt(rentalDepositPct) || 30 }), 'e.g. 30')}
                  {jTextField('Minimum Nights / Days', 'Leave blank if no minimum', rentalMinNights, setRentalMinNights, () => saveJourneySettings({ rental_min_nights: parseInt(rentalMinNights) || 0 }), 'e.g. 2')}
                  {jTextField('Check-in Time', '', rentalCheckinTime, setRentalCheckinTime, () => saveJourneySettings({ rental_checkin_time: rentalCheckinTime }), 'e.g. 2:00 PM')}
                  {jTextField('Check-out Time', '', rentalCheckoutTime, setRentalCheckoutTime, () => saveJourneySettings({ rental_checkout_time: rentalCheckoutTime }), 'e.g. 11:00 AM')}
                  {jTextField('Pet Policy', 'Shown when customers ask about pets', rentalPetPolicy, setRentalPetPolicy, () => saveJourneySettings({ rental_pet_policy: rentalPetPolicy }), 'e.g. No pets / Pets allowed with KES 1,000 deposit')}
                  {jTextField('Cancellation Policy', '', rentalCancellationPolicy, setRentalCancellationPolicy, () => saveJourneySettings({ rental_cancellation_policy: rentalCancellationPolicy }), 'e.g. Full refund if cancelled 7 days before check-in')}
                  {jSwitchRow('Extras / Add-ons Available', 'AI will mention extras like breakfast, airport pickup, etc.', rentalHasExtras, (v) => { setRentalHasExtras(v); saveJourneySettings({ rental_has_extras: v }); })}
                </View>
              );

              if (businessType === 'cleaning') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🧹 Cleaning Settings</Text>
                  {sharedFields}
                  {jSwitchRow('Offer Recurring Bookings', 'AI will suggest weekly/monthly schedules', cleaningHasRecurring, (v) => { setCleaningHasRecurring(v); saveJourneySettings({ cleaning_has_recurring: v }); })}
                  {jSwitchRow('Commercial Cleaning', 'AI will handle office/commercial enquiries', cleaningHasCommercial, (v) => { setCleaningHasCommercial(v); saveJourneySettings({ cleaning_has_commercial: v }); })}
                  {jSwitchRow('Supplies Included', 'Your team brings cleaning supplies', cleaningSuppliesIncluded, (v) => { setCleaningSuppliesIncluded(v); saveJourneySettings({ cleaning_supplies_included: v }); })}
                </View>
              );

              if (businessType === 'fitness' || businessType === 'gym') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>💪 Fitness Settings</Text>
                  {sharedFields}
                  {jSwitchRow('Memberships', 'Offer monthly/annual membership plans', fitnessHasMemberships, (v) => { setFitnessHasMemberships(v); saveJourneySettings({ fitness_has_memberships: v }); })}
                  {jSwitchRow('Drop-in Classes', 'Customers can book individual classes', fitnessHasClasses, (v) => { setFitnessHasClasses(v); saveJourneySettings({ fitness_has_classes: v }); })}
                  {jSwitchRow('Personal Training', 'AI will handle PT enquiries', fitnessHasPT, (v) => { setFitnessHasPT(v); saveJourneySettings({ fitness_has_personal_training: v }); })}
                  {jSwitchRow('Trial Session', 'Offer a first-visit / trial option', fitnessHasTrial, (v) => { setFitnessHasTrial(v); saveJourneySettings({ fitness_has_trial: v }); })}
                  {jTextField('Class Schedule', 'AI will show this when listing classes', fitnessClassSchedule, setFitnessClassSchedule, () => saveJourneySettings({ fitness_class_schedule: fitnessClassSchedule }), 'e.g. Mon/Wed/Fri 7am, Tue/Thu 6pm', true)}
                </View>
              );

              if (businessType === 'events' || businessType === 'photography') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>📸 Events / Photography Settings</Text>
                  {sharedFields}
                  {jTextField('Deposit %', 'Required to confirm event date', eventsDepositPct, setEventsDepositPct, () => saveJourneySettings({ events_deposit_pct: parseInt(eventsDepositPct) || 50 }), 'e.g. 50')}
                  {jTextField('Lead Time Required', 'Minimum notice before event date', eventsLeadTime, setEventsLeadTime, () => saveJourneySettings({ events_lead_time: eventsLeadTime }), 'e.g. 2 weeks minimum')}
                  {jTextField('Delivery Timeframe', 'When edited photos/videos are delivered', eventsDeliveryDays, setEventsDeliveryDays, () => saveJourneySettings({ events_delivery_days: eventsDeliveryDays }), 'e.g. 7–14 days after event')}
                </View>
              );

              if (businessType === 'healthcare' || businessType === 'clinic') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🏥 Clinic / Healthcare Settings</Text>
                  {sharedFields}
                  {jTextField('Consultation Fee', 'Shown to patients before confirming', hcConsultationFee, setHcConsultationFee, () => saveJourneySettings({ hc_consultation_fee: hcConsultationFee }), 'e.g. KES 1,500')}
                  {jSwitchRow('Lab Tests Available', 'AI will handle lab test bookings', hcHasLabTests, (v) => { setHcHasLabTests(v); saveJourneySettings({ hc_has_lab_tests: v }); })}
                  {jSwitchRow('Home Visits', 'AI will accept home visit requests', hcHasHomeVisit, (v) => { setHcHasHomeVisit(v); saveJourneySettings({ hc_has_home_visit: v }); })}
                  {jTextField('Prep Instructions', 'Told to patients before their appointment', hcPrepInstructions, setHcPrepInstructions, () => saveJourneySettings({ hc_prep_instructions: hcPrepInstructions }), 'e.g. Fast for 8 hours before blood tests', true)}
                  {jTextField('Insurance Accepted', '', hcInsuranceAccepted, setHcInsuranceAccepted, () => saveJourneySettings({ hc_insurance_accepted: hcInsuranceAccepted }), 'e.g. NHIF, AAR, Jubilee')}
                </View>
              );

              if (businessType === 'creator') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>✨ Creator Settings</Text>
                  {jTextField('Niche', 'AI pitches this to brands', creatorNiche, setCreatorNiche, () => saveJourneySettings({ creator_niche: creatorNiche }), 'e.g. lifestyle, beauty, food')}
                  {jTextField('Platforms', '', creatorPlatforms, setCreatorPlatforms, () => saveJourneySettings({ creator_platforms: creatorPlatforms }), 'e.g. Instagram, TikTok, YouTube')}
                  {jTextField('Follower Count', '', creatorFollowers, setCreatorFollowers, () => saveJourneySettings({ creator_followers: creatorFollowers }), 'e.g. 45K')}
                  {jTextField('Content Lead Time', 'Time from brief approval to posting', creatorLeadTime, setCreatorLeadTime, () => saveJourneySettings({ creator_lead_time: creatorLeadTime }), 'e.g. 5–7 business days')}
                  {jTextField('Revision Policy', '', creatorRevisions, setCreatorRevisions, () => saveJourneySettings({ creator_revisions: creatorRevisions }), 'e.g. 1 free revision included')}
                  {jTextField('Usage Rights', 'What brands can do with the content', creatorUsageRights, setCreatorUsageRights, () => saveJourneySettings({ creator_usage_rights: creatorUsageRights }), 'e.g. 30-day organic use only')}
                  {jTextField('Deposit %', 'Upfront deposit for brand collabs', creatorDepositPct, setCreatorDepositPct, () => saveJourneySettings({ creator_deposit_pct: parseInt(creatorDepositPct) || 50 }), 'e.g. 50')}
                  {jSwitchRow('Rates on Request', "Don't show rates publicly — quote per brand", creatorRatesOnRequest, (v) => { setCreatorRatesOnRequest(v); saveJourneySettings({ creator_rates_on_request: v }); })}
                </View>
              );

              if (businessType === 'retail') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>🛍️ Retail Settings</Text>
                  {sharedFields}
                  {jSwitchRow('Custom / Made-to-Order Items', 'AI will collect custom specs and confirm lead time', retailHasCustomOrders, (v) => { setRetailHasCustomOrders(v); saveJourneySettings({ retail_has_custom_orders: v }); })}
                  {retailHasCustomOrders && jTextField('Custom Order Lead Time', 'Shown to customers when ordering custom items', retailCustomLeadTime, setRetailCustomLeadTime, () => saveJourneySettings({ retail_custom_lead_time: retailCustomLeadTime }), 'e.g. 5–7 business days')}
                  {jTextField('Return / Exchange Policy', 'Shown when customers ask about returns', retailReturnPolicy, setRetailReturnPolicy, () => saveJourneySettings({ retail_return_policy: retailReturnPolicy }), 'e.g. Exchange within 7 days with receipt')}
                </View>
              );

              if (businessType === 'general') return (
                <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13, marginTop: 8, marginBottom: 4 }}>⚙️ Order Settings</Text>
                  {sharedFields}
                </View>
              );

              return null;
            })()}

            {/* Staff List */}
            <View style={[styles.settingItem, { flexDirection: 'column', alignItems: 'flex-start', paddingVertical: 14 }]}>
              <View style={{ flexDirection: 'row', alignItems: 'center', width: '100%', marginBottom: staffList.length > 0 ? 10 : 0 }}>
                <Ionicons name="people-outline" size={24} color="#25D366" />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.settingText}>Staff / Attendants</Text>
                  <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>Names used to assign orders</Text>
                </View>
              </View>
              {staffList.map(s => (
                <View key={s.id} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 6, paddingLeft: 36, width: '100%' }}>
                  <Ionicons name="person-circle-outline" size={18} color="#555" />
                  <Text style={{ flex: 1, color: '#ccc', fontSize: 14, marginLeft: 8 }}>{s.name}</Text>
                  <TouchableOpacity onPress={async () => {
                    try {
                      await apiClient.delete(`/settings/staff/${s.id}`);
                      setStaffList(staffList.filter(m => m.id !== s.id));
                    } catch (e) {}
                  }}>
                    <Ionicons name="remove-circle-outline" size={20} color="#e05252" />
                  </TouchableOpacity>
                </View>
              ))}
              {addingStaff ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', paddingLeft: 36, width: '100%', marginTop: 8, gap: 8 }}>
                  <TextInput
                    style={{ flex: 1, backgroundColor: '#1E1E1E', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, color: '#fff', fontSize: 14, borderWidth: 1, borderColor: '#333' }}
                    value={newStaffName}
                    onChangeText={setNewStaffName}
                    placeholder="Staff name"
                    placeholderTextColor="#555"
                    autoFocus
                  />
                  <TouchableOpacity
                    style={{ backgroundColor: '#25D366', borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8 }}
                    onPress={async () => {
                      if (!newStaffName.trim()) return;
                      try {
                        const res = await apiClient.post('/settings/staff', { name: newStaffName.trim() });
                        setStaffList([...staffList, res.data]);
                        setNewStaffName('');
                        setAddingStaff(false);
                      } catch (e) {}
                    }}
                  >
                    <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>Add</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => { setAddingStaff(false); setNewStaffName(''); }}>
                    <Ionicons name="close" size={20} color="#888" />
                  </TouchableOpacity>
                </View>
              ) : (
                <TouchableOpacity
                  style={{ flexDirection: 'row', alignItems: 'center', paddingLeft: 36, marginTop: 8, gap: 6 }}
                  onPress={() => setAddingStaff(true)}
                >
                  <Ionicons name="add-circle-outline" size={18} color="#25D366" />
                  <Text style={{ color: '#25D366', fontSize: 13, fontWeight: '600' }}>Add staff member</Text>
                </TouchableOpacity>
              )}
            </View>
            <TouchableOpacity style={styles.settingItem}>
              <Ionicons name="cube-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Product Catalog</Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity style={styles.settingItem}>
              <Ionicons name="book-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Business Knowledge</Text>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.settingItem}
              onPress={() => setShowModelPicker(true)}
            >
              <Ionicons name="hardware-chip-outline" size={24} color="#666" />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.settingText}>AI Model</Text>
                <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                  {getModelName(aiModel)}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
            <View style={styles.settingItem}>
              <Ionicons name="chatbubble-outline" size={24} color="#666" />
              <View style={{ flex: 1, marginLeft: 0 }}>
                <Text style={styles.settingText}>Auto Reply</Text>
                {autoReplyEnabled && (
                  <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                    {autoReplyAudience === 'everyone' ? 'Replying to everyone' :
                     autoReplyAudience === 'customers_only' ? 'Customers only' :
                     'New contacts only'}
                  </Text>
                )}
              </View>
              <Switch
                value={autoReplyEnabled}
                onValueChange={async (val) => {
                  setAutoReplyEnabled(val);
                  try {
                    await settingsAPI.updateSettings({ auto_reply_enabled: val });
                  } catch (e) {
                    setAutoReplyEnabled(!val);
                  }
                }}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </View>
            {autoReplyEnabled && (
              <TouchableOpacity
                style={[styles.settingItem, { borderTopWidth: 1, borderTopColor: '#1e2d3d' }]}
                onPress={() => setShowAudiencePicker(true)}
              >
                <Ionicons name="people-outline" size={24} color="#666" />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.settingText}>Reply Audience</Text>
                  <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                    {autoReplyAudience === 'everyone' ? 'Everyone who messages' :
                     autoReplyAudience === 'customers_only' ? 'Only saved customers' :
                     'Only new / first-time contacts'}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color="#666" />
              </TouchableOpacity>
            )}
            <TouchableOpacity style={styles.settingItem}>
              <Ionicons name="notifications-outline" size={24} color="#666" />
              <Text style={styles.settingText}>Notifications</Text>
              <Switch
                value={true}
                onValueChange={() => { }}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </TouchableOpacity>
            <View style={styles.settingItem}>
              <Ionicons name="pulse" size={24} color="#25D366" />
              <Text style={styles.settingText}>Daily Pulse</Text>
              <Switch
                value={pulseEnabled}
                onValueChange={handleTogglePulse}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </View>
          </View>
        </View>

        {/* Daily Pulse */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Daily Pulse</Text>
          <View style={styles.settingsCard}>
            <View style={styles.pulseHeader}>
              <View style={styles.pulseIconContainer}>
                <Ionicons name="pulse" size={24} color="#25D366" />
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: '#FFFFFF' }}>Business Summary</Text>
                <Text style={{ fontSize: 12, color: '#8B9DC3', marginTop: 2 }}>
                  Get your daily sales, profit & insights via WhatsApp
                </Text>
              </View>
              <Switch
                value={pulseEnabled}
                onValueChange={handleTogglePulse}
                trackColor={{ false: '#3e3e3e', true: '#25D366' }}
                thumbColor="#f4f3f4"
              />
            </View>

            {pulseEnabled && (
              <>
                <View style={styles.pulseDivider} />
                <TouchableOpacity
                  style={styles.pulseTimeRow}
                  onPress={() => setShowTimePicker(true)}
                >
                  <Ionicons name="time-outline" size={20} color="#8B9DC3" />
                  <Text style={{ flex: 1, fontSize: 14, color: '#FFFFFF', marginLeft: 12 }}>
                    Send at
                  </Text>
                  <View style={styles.pulseTimeBadge}>
                    <Text style={styles.pulseTimeText}>{formatTime(pulseTime)}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color="#666" style={{ marginLeft: 8 }} />
                </TouchableOpacity>

                <View style={styles.pulseDivider} />
                <View style={styles.pulseActions}>
                  <TouchableOpacity
                    style={styles.pulsePreviewButton}
                    onPress={handlePreviewPulse}
                  >
                    <Ionicons name="eye-outline" size={18} color="#4A90D9" />
                    <Text style={{ color: '#4A90D9', fontSize: 14, fontWeight: '600', marginLeft: 6 }}>Preview</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.pulseSendButton}
                    onPress={handleSendPulseNow}
                    disabled={sendingPulse}
                  >
                    <Ionicons name="send" size={16} color="#FFFFFF" />
                    <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '600', marginLeft: 6 }}>
                      {sendingPulse ? 'Sending...' : 'Test Now'}
                    </Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>
        </View>



        {/* Business Type Picker Modal */}
        <Modal
          visible={showBusinessTypePicker}
          transparent={true}
          animationType="slide"
          onRequestClose={() => setShowBusinessTypePicker(false)}
        >
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'flex-end' }}>
            <View style={{ backgroundColor: '#1E1E1E', borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingTop: 20, paddingHorizontal: 20, paddingBottom: 0, maxHeight: '78%' }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <Text style={{ fontSize: 18, fontWeight: 'bold', color: '#FFFFFF' }}>Business Type</Text>
                <TouchableOpacity onPress={() => setShowBusinessTypePicker(false)}>
                  <Text style={{ color: '#8B9DC3', fontSize: 16 }}>Close</Text>
                </TouchableOpacity>
              </View>
              <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 14 }}>
                Changing your business type personalises your dashboard, catalog labels, and booking features.
              </Text>
              <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 36 }}>
                {[
                  { id: 'retail',     icon: '🛍️',  label: 'Retail / Shop',        desc: 'Physical or online store' },
                  { id: 'wholesale',  icon: '📦',   label: 'Wholesale / B2B',      desc: 'Bulk orders & distribution' },
                  { id: 'restaurant', icon: '🍽️',  label: 'Restaurant / Café',    desc: 'Dine-in, takeaway & delivery' },
                  { id: 'food',       icon: '🥡',   label: 'Food Delivery',        desc: 'Home kitchen & delivery-only' },
                  { id: 'bakery',     icon: '🍰',   label: 'Bakery',               desc: 'Cakes, pastries & custom orders' },
                  { id: 'grocery',    icon: '🛒',   label: 'Grocery / Supermarket',desc: 'Fresh produce & packaged goods' },
                  { id: 'salon',      icon: '✂️',   label: 'Salon & Beauty',       desc: 'Hair, nails & beauty services' },
                  { id: 'spa',        icon: '💆',   label: 'Spa & Wellness',       desc: 'Massages, treatments & relaxation' },
                  { id: 'services',   icon: '🔧',   label: 'Services / Freelance', desc: 'IT, trades, freelance & consulting' },
                  { id: 'repair',     icon: '🛠️',  label: 'Repair & Maintenance', desc: 'Electronics, appliances & vehicles' },
                  { id: 'cleaning',   icon: '🧹',   label: 'Cleaning Services',    desc: 'Home, office & commercial cleaning' },
                  { id: 'fitness',    icon: '🏋️',  label: 'Gym & Fitness',        desc: 'Memberships, classes & training' },
                  { id: 'events',     icon: '📸',   label: 'Events & Photography', desc: 'Events, shoots & productions' },
                  { id: 'healthcare', icon: '🏥',   label: 'Healthcare / Clinic',  desc: 'Consultations & medical services' },
                  { id: 'rental',     icon: '🏠',   label: 'Rental / Airbnb',      desc: 'Properties, cars & equipment' },
                  { id: 'hotel',      icon: '🏨',   label: 'Hotel / Hospitality',   desc: 'Hotels, lodges, guesthouses & resorts' },
                  { id: 'support',    icon: '🎧',   label: 'Support Agent',         desc: 'For businesses that need AI-powered customer support & care — not sales' },
                  { id: 'creator',    icon: '�',   label: 'Creator / Digital',    desc: 'Courses, content & digital products' },
                  { id: 'general',    icon: '💬',   label: 'General / Other',      desc: 'Fintech, NGO, info & assistant' },
                ].map((bt, idx, arr) => (
                  <TouchableOpacity
                    key={bt.id}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      paddingVertical: 13,
                      paddingHorizontal: 12,
                      borderRadius: 12,
                      marginBottom: 6,
                      backgroundColor: businessType === bt.id ? 'rgba(37,211,102,0.08)' : 'rgba(255,255,255,0.04)',
                      borderWidth: 1.5,
                      borderColor: businessType === bt.id ? '#25D366' : 'transparent',
                    }}
                    onPress={async () => {
                      setBusinessType(bt.id);
                      setShowBusinessTypePicker(false);
                      try {
                        await settingsAPI.updateSettings({ business_type: bt.id });
                        await refreshBusinessContext();
                      } catch (e) {
                        console.log('Failed to update business type', e);
                      }
                    }}
                    activeOpacity={0.75}
                  >
                    <Text style={{ fontSize: 26, width: 40 }}>{bt.icon}</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 14, fontWeight: '700', color: businessType === bt.id ? '#25D366' : '#FFFFFF', marginBottom: 2 }}>{bt.label}</Text>
                      <Text style={{ fontSize: 12, color: '#64748B' }}>{bt.desc}</Text>
                    </View>
                    {businessType === bt.id && (
                      <Ionicons name="checkmark-circle" size={20} color="#25D366" />
                    )}
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          </View>
        </Modal>

        {/* AI Model Picker Modal */}
        <Modal
          visible={showModelPicker}
          transparent={true}
          animationType="slide"
          onRequestClose={() => setShowModelPicker(false)}
        >
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'flex-end' }}>
            <View style={{ backgroundColor: '#1E1E1E', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <Text style={{ fontSize: 18, fontWeight: 'bold', color: '#FFFFFF' }}>Select AI Model</Text>
                <TouchableOpacity onPress={() => setShowModelPicker(false)}>
                  <Text style={{ color: '#8B9DC3', fontSize: 16 }}>Close</Text>
                </TouchableOpacity>
              </View>

              <Text style={{ color: '#8B9DC3', marginBottom: 15, fontSize: 13 }}>
                Each model costs a different number of credits per message sent. Higher-capability models use more credits from your monthly quota.
              </Text>

              {[
                { id: 'deepseek', name: 'DeepSeek V3', desc: 'Best value — analytical & multilingual', credits: '1x', creditsColor: '#25D366' },
                { id: 'standard', name: 'GPT-4o Mini', desc: 'Fast, reliable, great for daily use', credits: '1.6x', creditsColor: '#25D366' },
                { id: 'grok', name: 'Grok 4.1', desc: 'Witty, relaxed conversational style', credits: '1.7x', creditsColor: '#FFA500' },
                { id: 'gpt5', name: 'GPT-5', desc: 'Most capable reasoning & writing', credits: '12x', creditsColor: '#FF6B6B' },
                { id: 'premium', name: 'GPT-4o', desc: 'Smarter, better reasoning, slightly slower', credits: '15x', creditsColor: '#FF6B6B' },
              ].map((model) => (
                <TouchableOpacity
                  key={model.id}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    backgroundColor: aiModel === model.id ? 'rgba(37,211,102,0.1)' : 'rgba(255,255,255,0.05)',
                    padding: 16,
                    borderRadius: 12,
                    marginBottom: 10,
                    borderWidth: 1,
                    borderColor: aiModel === model.id ? '#25D366' : 'transparent'
                  }}
                  onPress={() => handleModelChange(model.id)}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '600', marginBottom: 4 }}>{model.name}</Text>
                    <Text style={{ color: '#8B9DC3', fontSize: 12 }}>{model.desc}</Text>
                  </View>
                  <View style={{ alignItems: 'center', marginLeft: 10 }}>
                    <Text style={{ color: (model as any).creditsColor || '#8B9DC3', fontSize: 13, fontWeight: '700' }}>{(model as any).credits}</Text>
                    <Text style={{ color: '#666', fontSize: 10 }}>credits</Text>
                  </View>
                  {aiModel === model.id && (
                    <Ionicons name="checkmark-circle" size={24} color="#25D366" style={{ marginLeft: 8 }} />
                  )}
                </TouchableOpacity>
              ))}

              <View style={{ height: 20 }} />
            </View>
          </View>
        </Modal>

        {/* Credit Top-Up Modal */}
        <Modal
          visible={showTopUpModal}
          transparent={true}
          animationType="slide"
          onRequestClose={() => setShowTopUpModal(false)}
        >
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'flex-end' }}>
            <View style={{ backgroundColor: '#1E1E1E', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <Text style={{ fontSize: 18, fontWeight: 'bold', color: '#FFFFFF' }}>Buy Extra Credits</Text>
                <TouchableOpacity onPress={() => setShowTopUpModal(false)}>
                  <Text style={{ color: '#8B9DC3', fontSize: 16 }}>Close</Text>
                </TouchableOpacity>
              </View>
              <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 16 }}>
                Credits never expire and stack on top of your monthly plan quota.
              </Text>

              {extraCredits > 0 && (
                <View style={{ backgroundColor: 'rgba(37,211,102,0.1)', borderRadius: 10, padding: 10, marginBottom: 14, flexDirection: 'row', alignItems: 'center' }}>
                  <Ionicons name="wallet-outline" size={16} color="#25D366" />
                  <Text style={{ color: '#25D366', fontSize: 13, marginLeft: 8 }}>Current balance: <Text style={{ fontWeight: '700' }}>{extraCredits} credits</Text></Text>
                </View>
              )}

              {[
                { bundle_id: 'credits_500',  label: '500 Credits',   price: '$2.99',  note: '~500 manual msgs or ~312 GPT-4o mini replies' },
                { bundle_id: 'credits_1000', label: '1,000 Credits', price: '$4.99',  note: '~1,000 manual msgs or ~625 GPT-4o mini replies' },
                { bundle_id: 'credits_2500', label: '2,500 Credits', price: '$9.99',  note: '~2,500 manual msgs or ~1,562 GPT-4o mini replies' },
                { bundle_id: 'credits_5000', label: '5,000 Credits', price: '$17.99', note: 'Best value — ~5,000 manual msgs or ~3,125 GPT-4o mini replies' },
              ].map((bundle) => (
                <TouchableOpacity
                  key={bundle.bundle_id}
                  style={{
                    backgroundColor: 'rgba(255,255,255,0.05)',
                    borderRadius: 12,
                    padding: 14,
                    marginBottom: 10,
                    flexDirection: 'row',
                    alignItems: 'center',
                    borderWidth: bundle.bundle_id === 'credits_2500' ? 1 : 0,
                    borderColor: bundle.bundle_id === 'credits_2500' ? '#FFC107' : 'transparent',
                  }}
                  disabled={buyingCredits !== null}
                  onPress={async () => {
                    const productId = CREDIT_PRODUCT_IDS[bundle.bundle_id];
                    if (!productId) {
                      Alert.alert('Error', 'Product not found');
                      return;
                    }
                    setBuyingCredits(bundle.bundle_id);
                    pendingBundleIdRef.current = bundle.bundle_id;

                    // Set up one-time purchase listener
                    purchaseListenerRef.current?.remove();
                    errorListenerRef.current?.remove();

                    purchaseListenerRef.current = purchaseUpdatedListener(async (purchase: ProductPurchase) => {
                      const token = purchase.purchaseToken || purchase.transactionId || '';
                      try {
                        const res = await apiClient.post('/subscription/add-credits', {
                          bundle_id: pendingBundleIdRef.current,
                          purchase_token: token,
                          platform: Platform.OS === 'ios' ? 'ios' : 'android',
                        });
                        await finishTransaction({ purchase, isConsumable: true });
                        setExtraCredits(res.data.total_extra_credits);
                        setWaMsgLimit(waMsgLimit + res.data.credits_added);
                        Alert.alert('Credits Added!', res.data.message);
                        setShowTopUpModal(false);
                      } catch (e: any) {
                        Alert.alert('Failed', e.response?.data?.detail || 'Could not verify purchase');
                      } finally {
                        setBuyingCredits(null);
                        pendingBundleIdRef.current = null;
                      }
                    });

                    errorListenerRef.current = purchaseErrorListener((error: PurchaseError) => {
                      if (error.code !== 'E_USER_CANCELLED') {
                        Alert.alert('Purchase Failed', error.message || 'Could not complete purchase');
                      }
                      setBuyingCredits(null);
                      pendingBundleIdRef.current = null;
                    });

                    try {
                      await requestPurchase({ sku: productId });
                    } catch (e: any) {
                      if (e.code !== 'E_USER_CANCELLED') {
                        Alert.alert('Purchase Failed', e.message || 'Could not start purchase');
                      }
                      setBuyingCredits(null);
                      pendingBundleIdRef.current = null;
                    }
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                      <Text style={{ color: '#FFFFFF', fontSize: 16, fontWeight: '700' }}>{bundle.label}</Text>
                      {bundle.bundle_id === 'credits_2500' && (
                        <View style={{ backgroundColor: '#FFC107', borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2, marginLeft: 8 }}>
                          <Text style={{ color: '#000', fontSize: 10, fontWeight: '700' }}>POPULAR</Text>
                        </View>
                      )}
                    </View>
                    <Text style={{ color: '#8B9DC3', fontSize: 11, marginTop: 3 }}>{bundle.note}</Text>
                  </View>
                  {buyingCredits === bundle.bundle_id ? (
                    <ActivityIndicator size="small" color="#FFC107" />
                  ) : (
                    <Text style={{ color: '#FFC107', fontSize: 16, fontWeight: '700' }}>{bundle.price}</Text>
                  )}
                </TouchableOpacity>
              ))}

              <View style={{ height: 10 }} />
            </View>
          </View>
        </Modal>

        {showTimePicker && (
          <DateTimePicker
            value={(() => {
              const [h, m] = pulseTime.split(':');
              const d = new Date();
              d.setHours(parseInt(h), parseInt(m), 0, 0);
              return d;
            })()}
            mode="time"
            display="default"
            onChange={handlePulseTimeChange}
          />
        )}

        {/* Data & Account Management */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Data & Privacy</Text>

          <TouchableOpacity
            style={styles.dataButton}
            onPress={async () => {
              try {
                Alert.alert('Exporting...', 'Preparing your data export.');
                const data = await accountAPI.exportData();
                await Clipboard.setStringAsync(JSON.stringify(data, null, 2));
                Alert.alert('Exported!', 'Your data has been copied to clipboard as JSON.');
              } catch (e: any) {
                Alert.alert('Error', e.response?.data?.detail || 'Failed to export data');
              }
            }}
          >
            <Ionicons name="download-outline" size={22} color="#25D366" />
            <Text style={styles.dataButtonText}>Export My Data</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.dataButton, { borderColor: '#FF4444' }]}
            onPress={() => {
              Alert.alert(
                'Delete Account',
                'This will permanently delete your account and ALL data (customers, messages, sales, products). This cannot be undone.',
                [
                  { text: 'Cancel', style: 'cancel' },
                  {
                    text: 'Delete Forever',
                    style: 'destructive',
                    onPress: () => {
                      Alert.alert(
                        'Are you absolutely sure?',
                        'Type DELETE to confirm.',
                        [
                          { text: 'Cancel', style: 'cancel' },
                          {
                            text: 'Yes, Delete Everything',
                            style: 'destructive',
                            onPress: async () => {
                              try {
                                await accountAPI.deleteAccount();
                                await logout();
                                router.replace('/');
                              } catch (e: any) {
                                Alert.alert('Error', e.response?.data?.detail || 'Failed to delete account');
                              }
                            },
                          },
                        ]
                      );
                    },
                  },
                ]
              );
            }}
          >
            <Ionicons name="trash-outline" size={22} color="#FF4444" />
            <Text style={[styles.dataButtonText, { color: '#FF4444' }]}>Delete Account</Text>
          </TouchableOpacity>
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={24} color="#FF4444" />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>

        <Text style={styles.version}>Version 1.0.0</Text>
      </ScrollView>

      {/* Auto Reply Audience Picker Modal */}
      <Modal
        visible={showAudiencePicker}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowAudiencePicker(false)}
      >
        <SafeAreaView style={styles.container}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: '#1e2d3d' }}>
            <TouchableOpacity onPress={() => setShowAudiencePicker(false)}>
              <Ionicons name="close" size={24} color="#FFFFFF" />
            </TouchableOpacity>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#FFFFFF' }}>Reply Audience</Text>
            <View style={{ width: 24 }} />
          </View>
          <ScrollView style={{ flex: 1, padding: 16 }}>
            <Text style={{ color: '#8B9DC3', fontSize: 13, marginBottom: 16 }}>
              Choose who the AI auto-reply responds to. Individual contact overrides always take priority.
            </Text>
            {([
              { value: 'everyone', label: 'Everyone', desc: 'Reply to all incoming messages' },
              { value: 'customers_only', label: 'Customers Only', desc: 'Only reply to contacts you have saved as customers' },
              { value: 'new_contacts_only', label: 'New Contacts Only', desc: 'Only reply to first-time or uncontacted messages' },
            ] as const).map((opt) => (
              <TouchableOpacity
                key={opt.value}
                style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: '#1A2942', borderRadius: 12, padding: 16, marginBottom: 10, borderWidth: 2, borderColor: autoReplyAudience === opt.value ? '#25D366' : 'transparent' }}
                onPress={async () => {
                  setAutoReplyAudience(opt.value);
                  setShowAudiencePicker(false);
                  try {
                    await settingsAPI.updateSettings({ auto_reply_audience: opt.value });
                  } catch (e) {}
                }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: '#FFFFFF', fontWeight: '600', fontSize: 15 }}>{opt.label}</Text>
                  <Text style={{ color: '#8B9DC3', fontSize: 13, marginTop: 4 }}>{opt.desc}</Text>
                </View>
                {autoReplyAudience === opt.value && (
                  <Ionicons name="checkmark-circle" size={24} color="#25D366" />
                )}
              </TouchableOpacity>
            ))}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Daily Pulse Preview Modal */}
      <Modal
        visible={previewVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setPreviewVisible(false)}
      >
        <SafeAreaView style={styles.container}>
          <View style={styles.pulseModalHeader}>
            <TouchableOpacity onPress={() => setPreviewVisible(false)}>
              <Ionicons name="close" size={24} color="#FFFFFF" />
            </TouchableOpacity>
            <Text style={{ fontSize: 18, fontWeight: '600', color: '#FFFFFF' }}>Daily Pulse Preview</Text>
            <View style={{ width: 24 }} />
          </View>
          <ScrollView style={{ flex: 1, padding: 20 }}>
            {loadingPreview ? (
              <View style={{ alignItems: 'center', paddingTop: 40 }}>
                <ActivityIndicator size="large" color="#25D366" />
                <Text style={{ color: '#8B9DC3', marginTop: 12 }}>Generating your pulse...</Text>
              </View>
            ) : (
              <>
                <View style={styles.pulsePreviewCard}>
                  <View style={styles.pulsePreviewWhatsApp}>
                    <Ionicons name="logo-whatsapp" size={16} color="#25D366" />
                    <Text style={{ color: '#25D366', fontSize: 12, marginLeft: 6 }}>WhatsApp Message Preview</Text>
                  </View>
                  <Text style={styles.pulsePreviewText}>{pulsePreview}</Text>
                </View>
                <Text style={{ color: '#8B9DC3', fontSize: 12, textAlign: 'center', marginTop: 16 }}>
                  This is what you'll receive every day at {formatTime(pulseTime)}
                </Text>
              </>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>

      {/* Team Management Modal */}
      <TeamManagementModal
        visible={showTeamModal}
        onClose={() => setShowTeamModal(false)}
        userRole={user?.role || 'owner'}
        userId={user?.id || ''}
      />

      <SubscriptionModal
        visible={showSubscriptionModal}
        onClose={() => setShowSubscriptionModal(false)}
        onSuccess={() => { setShowSubscriptionModal(false); fetchData(); }}
        currentPlan={user?.subscription_plan || null}
      />

    </SafeAreaView >
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
  scrollContent: {
    paddingBottom: 40,
  },
  header: {
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  section: {
    paddingHorizontal: 16,
    marginBottom: 16,
  },
  upgradeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#0F2D1A',
    borderWidth: 1.5,
    borderColor: '#25D366',
    borderRadius: 12,
    padding: 14,
  },
  upgradeCardLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  upgradeEmoji: {
    fontSize: 26,
  },
  upgradeTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#25D366',
  },
  upgradeSubtitle: {
    fontSize: 12,
    color: '#6B9E7A',
    marginTop: 2,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  businessCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 12,
  },
  businessAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#25D366',
    justifyContent: 'center',
    alignItems: 'center',
  },
  businessAvatarText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  businessInfo: {
    flex: 1,
    marginLeft: 12,
  },
  businessName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  businessPhone: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },
  ownerName: {
    fontSize: 12,
    color: '#888',
    marginTop: 2,
  },
  subscriptionBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#666',
    borderRadius: 12,
  },
  subscriptionActive: {
    backgroundColor: '#25D366',
  },
  subscriptionText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#FFFFFF',
    textTransform: 'capitalize',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  statCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 10,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 6,
  },
  statLabel: {
    fontSize: 11,
    color: '#666',
    marginTop: 2,
  },
  planCard: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
  },
  planCardActive: {
    borderWidth: 2,
    borderColor: '#25D366',
  },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  planName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  planPrice: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#25D366',
  },
  planFeatures: {
    marginBottom: 10,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  featureText: {
    fontSize: 12,
    color: '#888',
    marginLeft: 8,
  },
  currentPlanBadge: {
    backgroundColor: '#25D366',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  currentPlanText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  subscribeButton: {
    backgroundColor: '#25D366',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  subscribeButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  settingsCard: {
    backgroundColor: '#1A2942',
    borderRadius: 12,
    overflow: 'hidden',
  },
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#0A1628',
  },
  settingText: {
    flex: 1,
    fontSize: 14,
    color: '#FFFFFF',
    marginLeft: 10,
  },
  dataButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0D1B2A',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1A2942',
    padding: 14,
    marginBottom: 10,
  },
  dataButtonText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#25D366',
    marginLeft: 10,
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 16,
    backgroundColor: '#1A2942',
    borderRadius: 10,
    padding: 12,
    marginTop: 8,
  },
  logoutText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FF4444',
    marginLeft: 8,
  },
  version: {
    fontSize: 12,
    color: '#666',
    textAlign: 'center',
    marginTop: 20,
  },
  // Product Catalog Styles
  catalogHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: '#F5F5F5',
    borderRadius: 12,
    marginBottom: 8,
  },
  catalogHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  catalogIcon: {
    fontSize: 20,
  },
  catalogContent: {
    marginTop: 12,
  },
  uploadButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#25D366',
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 12,
    gap: 8,
    marginBottom: 16,
  },
  uploadButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  productCount: {
    fontSize: 14,
    color: '#666',
    marginBottom: 12,
  },
  productGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  productCard: {
    width: '31%',
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#E0E0E0',
  },
  productImage: {
    width: '100%',
    height: 100,
    backgroundColor: '#F5F5F5',
  },
  productInfo: {
    padding: 8,
  },
  productName: {
    fontSize: 12,
    fontWeight: '600',
    color: '#333',
    marginBottom: 4,
  },
  productPrice: {
    fontSize: 11,
    color: '#25D366',
    fontWeight: '600',
  },
  deleteButton: {
    position: 'absolute',
    top: 4,
    right: 4,
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 4,
  },
  emptyText: {
    textAlign: 'center',
    color: '#999',
    fontSize: 14,
    paddingVertical: 20,
  },
  // Daily Pulse styles
  pulseHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
  },
  pulseIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#1A3A2A',
    justifyContent: 'center',
    alignItems: 'center',
  },
  pulseDivider: {
    height: 1,
    backgroundColor: '#0A1628',
    marginHorizontal: 16,
  },
  pulseTimeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
  },
  pulseTimeBadge: {
    backgroundColor: '#0A1628',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  pulseTimeText: {
    color: '#25D366',
    fontSize: 14,
    fontWeight: '600',
  },
  pulseActions: {
    flexDirection: 'row',
    padding: 16,
    gap: 12,
  },
  pulsePreviewButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#4A90D9',
  },
  pulseSendButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: '#25D366',
  },
  pulseModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  pulsePreviewCard: {
    backgroundColor: '#1A2942',
    borderRadius: 16,
    padding: 20,
    borderLeftWidth: 4,
    borderLeftColor: '#25D366',
  },
  pulsePreviewWhatsApp: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#0A1628',
  },
  pulsePreviewText: {
    color: '#FFFFFF',
    fontSize: 14,
    lineHeight: 22,
  },
});
