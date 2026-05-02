import React from 'react';
import { ScrollView, View, Text, StyleSheet, Linking, TouchableOpacity, Platform } from 'react-native';
import { Stack } from 'expo-router';

const APP_NAME = 'Zilo';
const WEBSITE = 'https://zilo.pro';
const CONTACT_EMAIL = 'privacy@zilo.pro';
const LAST_UPDATED = 'May 2, 2026';

export default function PrivacyPolicyScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Privacy Policy', headerShown: false }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>{APP_NAME} Privacy Policy</Text>
          <Text style={styles.updated}>Last updated: {LAST_UPDATED}</Text>
        </View>

        <Section title="1. Introduction">
          <Body>
            {APP_NAME} ("we", "our", or "us") operates {WEBSITE} and provides an omnichannel
            business workspace that brings together social media, email, WhatsApp, and other
            communication channels in one place. This Privacy Policy explains how we collect,
            use, disclose, and protect your information when you use our service.
          </Body>
          <Body>By using {APP_NAME}, you agree to the collection and use of information in accordance with this policy.</Body>
        </Section>

        <Section title="2. Information We Collect">
          <SubHeading>Account Information</SubHeading>
          <Body>
            When you register, we collect your name, email address, business name, phone number,
            and password to create and manage your account.
          </Body>
          <SubHeading>Connected Service Data</SubHeading>
          <Body>
            When you connect third-party services (Gmail, Google Calendar, Slack, Shopify,
            Facebook, Instagram, WhatsApp), we access data strictly to provide the features you
            request within {APP_NAME}. This may include:
          </Body>
          <BulletList items={[
            'Email messages, metadata, and contacts (Gmail / Outlook)',
            'Calendar events and scheduling data (Google Calendar)',
            'Social media posts, comments, messages, and engagement metrics',
            'E-commerce orders, products, and customer data (Shopify)',
            'Workspace messages and channel data (Slack)',
            'Payment and invoice data (Stripe)',
          ]} />
          <SubHeading>Usage Data</SubHeading>
          <Body>We collect information about how you interact with {APP_NAME} to improve our service and provide support.</Body>
        </Section>

        <Section title="3. Google API Services — Limited Use Disclosure">
          <Body weight="600">
            {APP_NAME}'s use of information received from Google APIs adheres to the Google API
            Services User Data Policy, including the Limited Use requirements.
          </Body>
          <Body>When you connect your Google account, {APP_NAME} accesses your Google data only to provide the following features:</Body>
          <BulletList items={[
            'Gmail: Reading, composing, sending, and managing emails so you can handle customer conversations within ' + APP_NAME + '. The AI may draft replies for your review and approval.',
            'Google Calendar: Viewing and creating calendar events for booking and scheduling.',
            'Google Sheets: Reading and writing data to spreadsheets you explicitly connect for reporting or data sync.',
          ]} />
          <Body weight="600">We do NOT use your Google data to:</Body>
          <BulletList items={[
            'Serve advertising or build advertising profiles',
            'Sell, rent, or share your data with third parties for their own use',
            'Train AI or machine learning models on your personal email content',
            'Process data for purposes unrelated to providing the ' + APP_NAME + ' service',
          ]} />
          <Body>
            Google data is retained only while your account is active. You may disconnect your
            Google account at any time from the Integrations settings page, which revokes our
            access immediately.
          </Body>
        </Section>

        <Section title="4. How We Use Your Information">
          <BulletList items={[
            'Provide, operate, and maintain the ' + APP_NAME + ' service',
            'Enable AI-powered features such as drafting messages, summarising conversations, and generating reports',
            'Sync data between your connected accounts and the ' + APP_NAME + ' workspace',
            'Send service-related notifications and updates',
            'Provide customer support and respond to enquiries',
            'Monitor and improve the performance and security of the service',
            'Comply with legal obligations',
          ]} />
        </Section>

        <Section title="5. Data Sharing and Disclosure">
          <Body>We do not sell your personal data. We may share data with:</Body>
          <BulletList items={[
            'Service providers: Third-party vendors who help us operate ' + APP_NAME + ' (cloud hosting, database providers, AI inference). These providers process data only on our behalf under strict confidentiality obligations.',
            'Legal requirements: If required by law, court order, or government authority.',
            'Business transfers: In the event of a merger or acquisition.',
          ]} />
        </Section>

        <Section title="6. Data Security">
          <Body>
            We implement industry-standard security measures including encrypted data transmission
            (TLS/HTTPS), encrypted storage, access controls, and regular security assessments to
            protect your information.
          </Body>
        </Section>

        <Section title="7. Data Retention">
          <Body>
            We retain your data for as long as your account is active. If you close your account,
            we delete or anonymise your personal data within 30 days, unless legally required to
            retain it longer.
          </Body>
          <Body>
            Data from connected Google services is retained only while the connection is active.
            Revoking access removes our ability to access that data immediately.
          </Body>
        </Section>

        <Section title="8. Your Rights">
          <Body>You have the right to:</Body>
          <BulletList items={[
            'Access the personal data we hold about you',
            'Correct inaccurate or incomplete data',
            'Request deletion of your data',
            'Withdraw consent for data processing',
            'Export your data in a portable format',
            'Object to or restrict certain types of processing',
          ]} />
          <Body>
            To exercise any of these rights, contact us at{' '}
            <TouchableOpacity onPress={() => Linking.openURL(`mailto:${CONTACT_EMAIL}`)}>
              <Text style={styles.link}>{CONTACT_EMAIL}</Text>
            </TouchableOpacity>
          </Body>
        </Section>

        <Section title="9. Cookies">
          <Body>
            {APP_NAME} uses cookies and similar tracking technologies to maintain your session,
            remember preferences, and analyse usage. You can control cookies through your browser
            settings, though disabling certain cookies may affect functionality.
          </Body>
        </Section>

        <Section title="10. Children's Privacy">
          <Body>
            {APP_NAME} is not directed to children under 13. We do not knowingly collect personal
            data from children.
          </Body>
        </Section>

        <Section title="11. Changes to This Policy">
          <Body>
            We may update this Privacy Policy from time to time. We will notify you of significant
            changes by updating the "Last updated" date at the top of this page.
          </Body>
        </Section>

        <Section title="12. Contact Us">
          <View style={styles.contactBox}>
            <Text style={styles.contactName}>{APP_NAME} (Charo360)</Text>
            <TouchableOpacity onPress={() => Linking.openURL(`mailto:${CONTACT_EMAIL}`)}>
              <Text style={styles.link}>Email: {CONTACT_EMAIL}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => Linking.openURL(WEBSITE)}>
              <Text style={styles.link}>Website: {WEBSITE}</Text>
            </TouchableOpacity>
          </View>
        </Section>

        <View style={{ height: 40 }} />
      </ScrollView>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <Text style={styles.subHeading}>{children}</Text>;
}

function Body({ children, weight }: { children: React.ReactNode; weight?: '400' | '600' }) {
  return <Text style={[styles.body, weight === '600' && styles.bodyBold]}>{children}</Text>;
}

function BulletList({ items }: { items: string[] }) {
  return (
    <View style={styles.bulletList}>
      {items.map((item, i) => (
        <View key={i} style={styles.bulletRow}>
          <Text style={styles.bullet}>•</Text>
          <Text style={styles.bulletText}>{item}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#ffffff',
  },
  content: {
    paddingHorizontal: Platform.OS === 'web' ? '10%' : 20,
    paddingTop: 60,
    maxWidth: Platform.OS === 'web' ? 800 : undefined,
    alignSelf: Platform.OS === 'web' ? 'center' : undefined,
    width: Platform.OS === 'web' ? '100%' : undefined,
  },
  header: {
    marginBottom: 32,
  },
  title: {
    fontSize: Platform.OS === 'web' ? 36 : 28,
    fontWeight: '700',
    color: '#111827',
    marginBottom: 6,
  },
  updated: {
    fontSize: 13,
    color: '#6b7280',
  },
  section: {
    marginBottom: 28,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#111827',
    marginBottom: 10,
  },
  subHeading: {
    fontSize: 15,
    fontWeight: '600',
    color: '#374151',
    marginTop: 12,
    marginBottom: 6,
  },
  body: {
    fontSize: 15,
    color: '#4b5563',
    lineHeight: 24,
    marginBottom: 8,
  },
  bodyBold: {
    fontWeight: '600',
    color: '#374151',
  },
  bulletList: {
    marginVertical: 6,
    paddingLeft: 4,
  },
  bulletRow: {
    flexDirection: 'row',
    marginBottom: 6,
  },
  bullet: {
    fontSize: 15,
    color: '#6b7280',
    marginRight: 8,
    marginTop: 1,
  },
  bulletText: {
    flex: 1,
    fontSize: 15,
    color: '#4b5563',
    lineHeight: 22,
  },
  link: {
    fontSize: 15,
    color: '#2563eb',
    textDecorationLine: 'underline',
  },
  contactBox: {
    backgroundColor: '#f9fafb',
    borderRadius: 8,
    padding: 16,
    gap: 6,
  },
  contactName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#111827',
    marginBottom: 4,
  },
});
