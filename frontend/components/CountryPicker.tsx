import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Modal,
  FlatList,
  TextInput,
  SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export interface Country {
  name: string;
  code: string;    // ISO 3166-1 alpha-2
  dial: string;    // e.g. "+1"
  flag: string;    // emoji flag
  currency?: string;
  currencySymbol?: string;
}

export const COUNTRIES: Country[] = [
  { name: "Afghanistan", code: "AF", dial: "+93", flag: "🇦🇫", currency: "AFN", currencySymbol: "؋" },
  { name: "Albania", code: "AL", dial: "+355", flag: "🇦🇱", currency: "ALL", currencySymbol: "L" },
  { name: "Algeria", code: "DZ", dial: "+213", flag: "🇩🇿", currency: "DZD", currencySymbol: "د.ج" },
  { name: "Angola", code: "AO", dial: "+244", flag: "🇦🇴", currency: "AOA", currencySymbol: "Kz" },
  { name: "Argentina", code: "AR", dial: "+54", flag: "🇦🇷", currency: "ARS", currencySymbol: "$" },
  { name: "Australia", code: "AU", dial: "+61", flag: "🇦🇺", currency: "AUD", currencySymbol: "A$" },
  { name: "Austria", code: "AT", dial: "+43", flag: "🇦🇹", currency: "EUR", currencySymbol: "€" },
  { name: "Bahrain", code: "BH", dial: "+973", flag: "🇧🇭", currency: "BHD", currencySymbol: "BD" },
  { name: "Bangladesh", code: "BD", dial: "+880", flag: "🇧🇩", currency: "BDT", currencySymbol: "৳" },
  { name: "Belgium", code: "BE", dial: "+32", flag: "🇧🇪", currency: "EUR", currencySymbol: "€" },
  { name: "Benin", code: "BJ", dial: "+229", flag: "🇧🇯", currency: "XOF", currencySymbol: "CFA" },
  { name: "Botswana", code: "BW", dial: "+267", flag: "🇧🇼", currency: "BWP", currencySymbol: "P" },
  { name: "Brazil", code: "BR", dial: "+55", flag: "🇧🇷", currency: "BRL", currencySymbol: "R$" },
  { name: "Burkina Faso", code: "BF", dial: "+226", flag: "🇧🇫", currency: "XOF", currencySymbol: "CFA" },
  { name: "Burundi", code: "BI", dial: "+257", flag: "🇧🇮", currency: "BIF", currencySymbol: "FBu" },
  { name: "Cameroon", code: "CM", dial: "+237", flag: "🇨🇲", currency: "XAF", currencySymbol: "FCFA" },
  { name: "Canada", code: "CA", dial: "+1", flag: "🇨🇦", currency: "CAD", currencySymbol: "C$" },
  { name: "Chad", code: "TD", dial: "+235", flag: "🇹🇩", currency: "XAF", currencySymbol: "FCFA" },
  { name: "Chile", code: "CL", dial: "+56", flag: "🇨🇱", currency: "CLP", currencySymbol: "$" },
  { name: "China", code: "CN", dial: "+86", flag: "🇨🇳", currency: "CNY", currencySymbol: "¥" },
  { name: "Colombia", code: "CO", dial: "+57", flag: "🇨🇴", currency: "COP", currencySymbol: "$" },
  { name: "Congo (DRC)", code: "CD", dial: "+243", flag: "🇨🇩", currency: "CDF", currencySymbol: "FC" },
  { name: "Congo (Republic)", code: "CG", dial: "+242", flag: "🇨🇬", currency: "XAF", currencySymbol: "FCFA" },
  { name: "Costa Rica", code: "CR", dial: "+506", flag: "🇨🇷", currency: "CRC", currencySymbol: "₡" },
  { name: "Côte d'Ivoire", code: "CI", dial: "+225", flag: "🇨🇮", currency: "XOF", currencySymbol: "CFA" },
  { name: "Croatia", code: "HR", dial: "+385", flag: "🇭🇷", currency: "EUR", currencySymbol: "€" },
  { name: "Cuba", code: "CU", dial: "+53", flag: "🇨🇺", currency: "CUP", currencySymbol: "$" },
  { name: "Czech Republic", code: "CZ", dial: "+420", flag: "🇨🇿", currency: "CZK", currencySymbol: "Kč" },
  { name: "Denmark", code: "DK", dial: "+45", flag: "🇩🇰", currency: "DKK", currencySymbol: "kr" },
  { name: "Ecuador", code: "EC", dial: "+593", flag: "🇪🇨", currency: "USD", currencySymbol: "$" },
  { name: "Egypt", code: "EG", dial: "+20", flag: "🇪🇬", currency: "EGP", currencySymbol: "E£" },
  { name: "El Salvador", code: "SV", dial: "+503", flag: "🇸🇻", currency: "USD", currencySymbol: "$" },
  { name: "Eritrea", code: "ER", dial: "+291", flag: "🇪🇷", currency: "ERN", currencySymbol: "Nfk" },
  { name: "Ethiopia", code: "ET", dial: "+251", flag: "🇪🇹", currency: "ETB", currencySymbol: "Br" },
  { name: "Finland", code: "FI", dial: "+358", flag: "🇫🇮", currency: "EUR", currencySymbol: "€" },
  { name: "France", code: "FR", dial: "+33", flag: "🇫🇷", currency: "EUR", currencySymbol: "€" },
  { name: "Gabon", code: "GA", dial: "+241", flag: "🇬🇦", currency: "XAF", currencySymbol: "FCFA" },
  { name: "Gambia", code: "GM", dial: "+220", flag: "🇬🇲", currency: "GMD", currencySymbol: "D" },
  { name: "Germany", code: "DE", dial: "+49", flag: "🇩🇪", currency: "EUR", currencySymbol: "€" },
  { name: "Ghana", code: "GH", dial: "+233", flag: "🇬🇭", currency: "GHS", currencySymbol: "GH₵" },
  { name: "Greece", code: "GR", dial: "+30", flag: "🇬🇷", currency: "EUR", currencySymbol: "€" },
  { name: "Guatemala", code: "GT", dial: "+502", flag: "🇬🇹", currency: "GTQ", currencySymbol: "Q" },
  { name: "Guinea", code: "GN", dial: "+224", flag: "🇬🇳", currency: "GNF", currencySymbol: "FG" },
  { name: "Haiti", code: "HT", dial: "+509", flag: "🇭🇹", currency: "HTG", currencySymbol: "G" },
  { name: "Honduras", code: "HN", dial: "+504", flag: "🇭🇳", currency: "HNL", currencySymbol: "L" },
  { name: "Hong Kong", code: "HK", dial: "+852", flag: "🇭🇰", currency: "HKD", currencySymbol: "HK$" },
  { name: "Hungary", code: "HU", dial: "+36", flag: "🇭🇺", currency: "HUF", currencySymbol: "Ft" },
  { name: "India", code: "IN", dial: "+91", flag: "🇮🇳", currency: "INR", currencySymbol: "₹" },
  { name: "Indonesia", code: "ID", dial: "+62", flag: "🇮🇩", currency: "IDR", currencySymbol: "Rp" },
  { name: "Iran", code: "IR", dial: "+98", flag: "🇮🇷", currency: "IRR", currencySymbol: "﷼" },
  { name: "Iraq", code: "IQ", dial: "+964", flag: "🇮🇶", currency: "IQD", currencySymbol: "ع.د" },
  { name: "Ireland", code: "IE", dial: "+353", flag: "🇮🇪", currency: "EUR", currencySymbol: "€" },
  { name: "Israel", code: "IL", dial: "+972", flag: "🇮🇱", currency: "ILS", currencySymbol: "₪" },
  { name: "Italy", code: "IT", dial: "+39", flag: "🇮🇹", currency: "EUR", currencySymbol: "€" },
  { name: "Jamaica", code: "JM", dial: "+1876", flag: "🇯🇲", currency: "JMD", currencySymbol: "J$" },
  { name: "Japan", code: "JP", dial: "+81", flag: "🇯🇵", currency: "JPY", currencySymbol: "¥" },
  { name: "Jordan", code: "JO", dial: "+962", flag: "🇯🇴", currency: "JOD", currencySymbol: "JD" },
  { name: "Kazakhstan", code: "KZ", dial: "+7", flag: "🇰🇿", currency: "KZT", currencySymbol: "₸" },
  { name: "Kenya", code: "KE", dial: "+254", flag: "🇰🇪", currency: "KES", currencySymbol: "KSh" },
  { name: "Kuwait", code: "KW", dial: "+965", flag: "🇰🇼", currency: "KWD", currencySymbol: "KD" },
  { name: "Lebanon", code: "LB", dial: "+961", flag: "🇱🇧", currency: "LBP", currencySymbol: "L£" },
  { name: "Lesotho", code: "LS", dial: "+266", flag: "🇱🇸", currency: "LSL", currencySymbol: "L" },
  { name: "Liberia", code: "LR", dial: "+231", flag: "🇱🇷", currency: "LRD", currencySymbol: "L$" },
  { name: "Libya", code: "LY", dial: "+218", flag: "🇱🇾", currency: "LYD", currencySymbol: "LD" },
  { name: "Madagascar", code: "MG", dial: "+261", flag: "🇲🇬", currency: "MGA", currencySymbol: "Ar" },
  { name: "Malawi", code: "MW", dial: "+265", flag: "🇲🇼", currency: "MWK", currencySymbol: "MK" },
  { name: "Malaysia", code: "MY", dial: "+60", flag: "🇲🇾", currency: "MYR", currencySymbol: "RM" },
  { name: "Mali", code: "ML", dial: "+223", flag: "🇲🇱", currency: "XOF", currencySymbol: "CFA" },
  { name: "Mexico", code: "MX", dial: "+52", flag: "🇲🇽", currency: "MXN", currencySymbol: "Mex$" },
  { name: "Morocco", code: "MA", dial: "+212", flag: "🇲🇦", currency: "MAD", currencySymbol: "MAD" },
  { name: "Mozambique", code: "MZ", dial: "+258", flag: "🇲🇿", currency: "MZN", currencySymbol: "MT" },
  { name: "Myanmar", code: "MM", dial: "+95", flag: "🇲🇲", currency: "MMK", currencySymbol: "K" },
  { name: "Namibia", code: "NA", dial: "+264", flag: "🇳🇦", currency: "NAD", currencySymbol: "N$" },
  { name: "Nepal", code: "NP", dial: "+977", flag: "🇳🇵", currency: "NPR", currencySymbol: "Rs" },
  { name: "Netherlands", code: "NL", dial: "+31", flag: "🇳🇱", currency: "EUR", currencySymbol: "€" },
  { name: "New Zealand", code: "NZ", dial: "+64", flag: "🇳🇿", currency: "NZD", currencySymbol: "NZ$" },
  { name: "Nicaragua", code: "NI", dial: "+505", flag: "🇳🇮", currency: "NIO", currencySymbol: "C$" },
  { name: "Niger", code: "NE", dial: "+227", flag: "🇳🇪", currency: "XOF", currencySymbol: "CFA" },
  { name: "Nigeria", code: "NG", dial: "+234", flag: "🇳🇬", currency: "NGN", currencySymbol: "₦" },
  { name: "Norway", code: "NO", dial: "+47", flag: "🇳🇴", currency: "NOK", currencySymbol: "kr" },
  { name: "Oman", code: "OM", dial: "+968", flag: "🇴🇲", currency: "OMR", currencySymbol: "OMR" },
  { name: "Pakistan", code: "PK", dial: "+92", flag: "🇵🇰", currency: "PKR", currencySymbol: "Rs" },
  { name: "Panama", code: "PA", dial: "+507", flag: "🇵🇦", currency: "PAB", currencySymbol: "B/." },
  { name: "Paraguay", code: "PY", dial: "+595", flag: "🇵🇾", currency: "PYG", currencySymbol: "₲" },
  { name: "Peru", code: "PE", dial: "+51", flag: "🇵🇪", currency: "PEN", currencySymbol: "S/." },
  { name: "Philippines", code: "PH", dial: "+63", flag: "🇵🇭", currency: "PHP", currencySymbol: "₱" },
  { name: "Poland", code: "PL", dial: "+48", flag: "🇵🇱", currency: "PLN", currencySymbol: "zł" },
  { name: "Portugal", code: "PT", dial: "+351", flag: "🇵🇹", currency: "EUR", currencySymbol: "€" },
  { name: "Qatar", code: "QA", dial: "+974", flag: "🇶🇦", currency: "QAR", currencySymbol: "QR" },
  { name: "Romania", code: "RO", dial: "+40", flag: "🇷🇴", currency: "RON", currencySymbol: "lei" },
  { name: "Russia", code: "RU", dial: "+7", flag: "🇷🇺", currency: "RUB", currencySymbol: "₽" },
  { name: "Rwanda", code: "RW", dial: "+250", flag: "🇷🇼", currency: "RWF", currencySymbol: "RF" },
  { name: "Saudi Arabia", code: "SA", dial: "+966", flag: "🇸🇦", currency: "SAR", currencySymbol: "SR" },
  { name: "Senegal", code: "SN", dial: "+221", flag: "🇸🇳", currency: "XOF", currencySymbol: "CFA" },
  { name: "Sierra Leone", code: "SL", dial: "+232", flag: "🇸🇱", currency: "SLL", currencySymbol: "Le" },
  { name: "Singapore", code: "SG", dial: "+65", flag: "🇸🇬", currency: "SGD", currencySymbol: "S$" },
  { name: "Somalia", code: "SO", dial: "+252", flag: "🇸🇴", currency: "SOS", currencySymbol: "Sh" },
  { name: "South Africa", code: "ZA", dial: "+27", flag: "🇿🇦", currency: "ZAR", currencySymbol: "R" },
  { name: "South Korea", code: "KR", dial: "+82", flag: "🇰🇷", currency: "KRW", currencySymbol: "₩" },
  { name: "South Sudan", code: "SS", dial: "+211", flag: "🇸🇸", currency: "SSP", currencySymbol: "SS£" },
  { name: "Spain", code: "ES", dial: "+34", flag: "🇪🇸", currency: "EUR", currencySymbol: "€" },
  { name: "Sri Lanka", code: "LK", dial: "+94", flag: "🇱🇰", currency: "LKR", currencySymbol: "Rs" },
  { name: "Sudan", code: "SD", dial: "+249", flag: "🇸🇩", currency: "SDG", currencySymbol: "SD" },
  { name: "Sweden", code: "SE", dial: "+46", flag: "🇸🇪", currency: "SEK", currencySymbol: "kr" },
  { name: "Switzerland", code: "CH", dial: "+41", flag: "🇨🇭", currency: "CHF", currencySymbol: "CHF" },
  { name: "Syria", code: "SY", dial: "+963", flag: "🇸🇾", currency: "SYP", currencySymbol: "S£" },
  { name: "Taiwan", code: "TW", dial: "+886", flag: "🇹🇼", currency: "TWD", currencySymbol: "NT$" },
  { name: "Tanzania", code: "TZ", dial: "+255", flag: "🇹🇿", currency: "TZS", currencySymbol: "TSh" },
  { name: "Thailand", code: "TH", dial: "+66", flag: "🇹🇭", currency: "THB", currencySymbol: "฿" },
  { name: "Togo", code: "TG", dial: "+228", flag: "🇹🇬", currency: "XOF", currencySymbol: "CFA" },
  { name: "Trinidad and Tobago", code: "TT", dial: "+1868", flag: "🇹🇹", currency: "TTD", currencySymbol: "TT$" },
  { name: "Tunisia", code: "TN", dial: "+216", flag: "🇹🇳", currency: "TND", currencySymbol: "DT" },
  { name: "Turkey", code: "TR", dial: "+90", flag: "🇹🇷", currency: "TRY", currencySymbol: "₺" },
  { name: "Uganda", code: "UG", dial: "+256", flag: "🇺🇬", currency: "UGX", currencySymbol: "USh" },
  { name: "Ukraine", code: "UA", dial: "+380", flag: "🇺🇦", currency: "UAH", currencySymbol: "₴" },
  { name: "United Arab Emirates", code: "AE", dial: "+971", flag: "🇦🇪", currency: "AED", currencySymbol: "AED" },
  { name: "United Kingdom", code: "GB", dial: "+44", flag: "🇬🇧", currency: "GBP", currencySymbol: "£" },
  { name: "United States", code: "US", dial: "+1", flag: "🇺🇸", currency: "USD", currencySymbol: "$" },
  { name: "Uruguay", code: "UY", dial: "+598", flag: "🇺🇾", currency: "UYU", currencySymbol: "$U" },
  { name: "Uzbekistan", code: "UZ", dial: "+998", flag: "🇺🇿", currency: "UZS", currencySymbol: "сўм" },
  { name: "Venezuela", code: "VE", dial: "+58", flag: "🇻🇪", currency: "VES", currencySymbol: "Bs." },
  { name: "Vietnam", code: "VN", dial: "+84", flag: "🇻🇳", currency: "VND", currencySymbol: "₫" },
  { name: "Yemen", code: "YE", dial: "+967", flag: "🇾🇪", currency: "YER", currencySymbol: "﷼" },
  { name: "Zambia", code: "ZM", dial: "+260", flag: "🇿🇲", currency: "ZMW", currencySymbol: "ZK" },
  { name: "Zimbabwe", code: "ZW", dial: "+263", flag: "🇿🇼", currency: "ZWL", currencySymbol: "Z$" },
];

export function getCountryByCode(code: string): Country | undefined {
  return COUNTRIES.find(c => c.code === code);
}

export function getCountryByDial(dial: string): Country | undefined {
  return COUNTRIES.find(c => c.dial === dial);
}

export function detectCountryFromPhone(phone: string): Country | undefined {
  const cleaned = phone.replace(/\s/g, '');
  if (!cleaned.startsWith('+')) return undefined;
  // Try longest dial codes first (e.g. +1868 before +1)
  const sorted = [...COUNTRIES].sort((a, b) => b.dial.length - a.dial.length);
  return sorted.find(c => cleaned.startsWith(c.dial));
}

interface CountryPickerProps {
  selectedCountry: Country;
  onSelect: (country: Country) => void;
  label?: string;
}

export default function CountryPicker({ selectedCountry, onSelect, label }: CountryPickerProps) {
  const [visible, setVisible] = useState(false);
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return COUNTRIES;
    const q = search.toLowerCase();
    return COUNTRIES.filter(
      c => c.name.toLowerCase().includes(q) || c.dial.includes(q) || c.code.toLowerCase().includes(q)
    );
  }, [search]);

  const handleSelect = (country: Country) => {
    onSelect(country);
    setVisible(false);
    setSearch('');
  };

  const renderItem = ({ item }: { item: Country }) => (
    <TouchableOpacity
      style={[pickerStyles.item, item.code === selectedCountry.code && pickerStyles.itemSelected]}
      onPress={() => handleSelect(item)}
    >
      <Text style={pickerStyles.flag}>{item.flag}</Text>
      <View style={pickerStyles.itemInfo}>
        <Text style={pickerStyles.itemName}>{item.name}</Text>
        <Text style={pickerStyles.itemDial}>{item.dial}</Text>
      </View>
      {item.code === selectedCountry.code && (
        <Ionicons name="checkmark-circle" size={20} color="#25D366" />
      )}
    </TouchableOpacity>
  );

  return (
    <>
      <TouchableOpacity style={pickerStyles.trigger} onPress={() => setVisible(true)}>
        <Text style={pickerStyles.triggerFlag}>{selectedCountry.flag}</Text>
        <Text style={pickerStyles.triggerDial}>{selectedCountry.dial}</Text>
        <Ionicons name="chevron-down" size={16} color="#666" />
      </TouchableOpacity>

      <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={pickerStyles.modal}>
          <View style={pickerStyles.header}>
            <TouchableOpacity onPress={() => { setVisible(false); setSearch(''); }}>
              <Text style={pickerStyles.cancel}>Cancel</Text>
            </TouchableOpacity>
            <Text style={pickerStyles.title}>{label || 'Select Country'}</Text>
            <View style={{ width: 60 }} />
          </View>

          <View style={pickerStyles.searchContainer}>
            <Ionicons name="search" size={18} color="#666" />
            <TextInput
              style={pickerStyles.searchInput}
              value={search}
              onChangeText={setSearch}
              placeholder="Search country or code..."
              placeholderTextColor="#666"
              autoFocus
            />
            {search.length > 0 && (
              <TouchableOpacity onPress={() => setSearch('')}>
                <Ionicons name="close-circle" size={18} color="#666" />
              </TouchableOpacity>
            )}
          </View>

          <FlatList
            data={filtered}
            renderItem={renderItem}
            keyExtractor={(item) => item.code}
            style={pickerStyles.list}
            keyboardShouldPersistTaps="handled"
            initialNumToRender={30}
          />
        </SafeAreaView>
      </Modal>
    </>
  );
}

const pickerStyles = StyleSheet.create({
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    paddingHorizontal: 12,
    paddingVertical: 14,
    borderRadius: 12,
    borderRightWidth: 1,
    borderRightColor: '#2A3A52',
    gap: 6,
  },
  triggerFlag: {
    fontSize: 20,
  },
  triggerDial: {
    fontSize: 16,
    color: '#FFFFFF',
    fontWeight: '500',
  },
  modal: {
    flex: 1,
    backgroundColor: '#0A1628',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
  },
  cancel: {
    color: '#3B82F6',
    fontSize: 16,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1A2942',
    marginHorizontal: 16,
    marginVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 10,
    gap: 8,
  },
  searchInput: {
    flex: 1,
    height: 44,
    fontSize: 16,
    color: '#FFFFFF',
  },
  list: {
    flex: 1,
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#1A2942',
    gap: 12,
  },
  itemSelected: {
    backgroundColor: 'rgba(37, 211, 102, 0.1)',
  },
  flag: {
    fontSize: 24,
  },
  itemInfo: {
    flex: 1,
  },
  itemName: {
    color: '#FFFFFF',
    fontSize: 16,
  },
  itemDial: {
    color: '#666',
    fontSize: 14,
    marginTop: 2,
  },
});
