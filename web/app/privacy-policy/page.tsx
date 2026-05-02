import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy · Zilo",
  description: "Privacy Policy for Zilo — how we collect, use, and protect your data.",
};

export default function PrivacyPolicyPage() {
  const lastUpdated = "May 2, 2026";
  const contactEmail = "privacy@zilo.pro";
  const appName = "Zilo";
  const website = "https://zilo.pro";

  return (
    <main className="min-h-screen bg-white px-4 py-16">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-2 text-4xl font-bold text-gray-900">{appName} Privacy Policy</h1>
        <p className="mb-10 text-sm text-gray-500">Last updated: {lastUpdated}</p>

        <section className="prose prose-gray max-w-none space-y-8 text-gray-700 leading-relaxed">

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">1. Introduction</h2>
            <p>
              {appName} (&quot;we&quot;, &quot;our&quot;, or &quot;us&quot;) operates {website} and provides
              an omnichannel business workspace that brings together social media, email, WhatsApp,
              and other communication channels in one place. This Privacy Policy explains how we
              collect, use, disclose, and protect information when you use our service.
            </p>
            <p className="mt-2">
              By using {appName}, you agree to the collection and use of information in accordance
              with this policy.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">2. Information We Collect</h2>
            <h3 className="text-lg font-medium text-gray-800 mb-2">Account Information</h3>
            <p>
              When you register for {appName}, we collect your name, email address, business name,
              phone number, and password. We use this information to create and manage your account.
            </p>

            <h3 className="text-lg font-medium text-gray-800 mb-2 mt-4">Connected Service Data</h3>
            <p>
              When you connect third-party services (such as Gmail, Google Calendar, Slack, Shopify,
              Facebook, Instagram, or WhatsApp), we access data from those services strictly to
              provide the features you request within {appName}. This may include:
            </p>
            <ul className="list-disc pl-6 mt-2 space-y-1">
              <li>Email messages, metadata, and contact information (Gmail / Outlook)</li>
              <li>Calendar events and scheduling data (Google Calendar)</li>
              <li>Social media posts, comments, messages, and engagement metrics</li>
              <li>E-commerce orders, products, and customer data (Shopify)</li>
              <li>Workspace messages and channel data (Slack)</li>
              <li>Payment and invoice data (Stripe)</li>
            </ul>

            <h3 className="text-lg font-medium text-gray-800 mb-2 mt-4">Usage Data</h3>
            <p>
              We collect information about how you interact with {appName}, including pages visited,
              features used, and actions taken, to improve our service and provide support.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">
              3. Google API Services — Limited Use Disclosure
            </h2>
            <p className="font-medium text-gray-800">
              {appName}&apos;s use of information received from Google APIs adheres to the{" "}
              <a
                href="https://developers.google.com/terms/api-services-user-data-policy"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline"
              >
                Google API Services User Data Policy
              </a>
              , including the Limited Use requirements.
            </p>
            <p className="mt-3">
              When you connect your Google account (Gmail, Google Calendar, or Google Sheets),
              {appName} accesses your Google data <strong>only</strong> to provide the following
              in-app features:
            </p>
            <ul className="list-disc pl-6 mt-2 space-y-1">
              <li>
                <strong>Gmail:</strong> Reading, composing, sending, and managing emails so you can
                handle customer conversations from within {appName}. The AI assistant may draft
                email replies on your behalf — always with your review and approval.
              </li>
              <li>
                <strong>Google Calendar:</strong> Viewing and creating calendar events for booking
                and scheduling management.
              </li>
              <li>
                <strong>Google Sheets:</strong> Reading and writing data to spreadsheets you
                explicitly connect for reporting or data sync.
              </li>
            </ul>

            <p className="mt-4">
              We do <strong>not</strong> use your Google data to:
            </p>
            <ul className="list-disc pl-6 mt-2 space-y-1">
              <li>Serve advertising or build advertising profiles</li>
              <li>Sell, rent, or share your data with third parties for their own use</li>
              <li>Train AI or machine learning models on your personal email content</li>
              <li>Process data for purposes unrelated to providing the {appName} service</li>
            </ul>

            <p className="mt-4">
              Google data is stored securely and retained only while your account is active or as
              required to deliver the service. You may disconnect your Google account at any time
              from the Integrations settings page, which revokes our access.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">4. How We Use Your Information</h2>
            <p>We use the information we collect to:</p>
            <ul className="list-disc pl-6 mt-2 space-y-1">
              <li>Provide, operate, and maintain the {appName} service</li>
              <li>Enable AI-powered features such as drafting messages, summarising conversations, and generating reports</li>
              <li>Sync data between your connected accounts and the {appName} workspace</li>
              <li>Send you service-related notifications and updates</li>
              <li>Provide customer support and respond to enquiries</li>
              <li>Monitor and improve the performance and security of the service</li>
              <li>Comply with legal obligations</li>
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">5. Data Sharing and Disclosure</h2>
            <p>
              We do not sell your personal data. We may share data with:
            </p>
            <ul className="list-disc pl-6 mt-2 space-y-1">
              <li>
                <strong>Service providers:</strong> Third-party vendors who help us operate {appName}
                (e.g., cloud hosting, database providers, AI inference services). These providers
                process data only on our behalf and under strict confidentiality obligations.
              </li>
              <li>
                <strong>Legal requirements:</strong> If required by law, court order, or government
                authority, we may disclose information as legally required.
              </li>
              <li>
                <strong>Business transfers:</strong> In the event of a merger or acquisition, your
                data may be transferred as part of that transaction.
              </li>
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">6. Data Security</h2>
            <p>
              We implement industry-standard security measures including encrypted data transmission
              (TLS/HTTPS), encrypted storage, access controls, and regular security assessments to
              protect your information. However, no method of transmission over the internet is 100%
              secure, and we cannot guarantee absolute security.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">7. Data Retention</h2>
            <p>
              We retain your data for as long as your account is active or as needed to provide the
              service. If you close your account, we will delete or anonymise your personal data
              within 30 days, unless we are required by law to retain it longer.
            </p>
            <p className="mt-2">
              Data from connected Google services is retained only while the connection is active.
              Revoking access in {appName}&apos;s Integrations page or in your Google Account
              permissions removes our ability to access that data going forward.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">8. Your Rights</h2>
            <p>You have the right to:</p>
            <ul className="list-disc pl-6 mt-2 space-y-1">
              <li>Access the personal data we hold about you</li>
              <li>Correct inaccurate or incomplete data</li>
              <li>Request deletion of your data</li>
              <li>Withdraw consent for data processing</li>
              <li>Export your data in a portable format</li>
              <li>Object to or restrict certain types of processing</li>
            </ul>
            <p className="mt-3">
              To exercise any of these rights, contact us at{" "}
              <a href={`mailto:${contactEmail}`} className="text-blue-600 underline">
                {contactEmail}
              </a>
              .
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">9. Cookies</h2>
            <p>
              {appName} uses cookies and similar tracking technologies to maintain your session,
              remember your preferences, and analyse usage patterns. You can control cookies through
              your browser settings, though disabling certain cookies may affect functionality.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">10. Children&apos;s Privacy</h2>
            <p>
              {appName} is not directed to children under the age of 13. We do not knowingly collect
              personal data from children. If you believe a child has provided us with personal data,
              please contact us immediately.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">11. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. We will notify you of significant
              changes by posting the new policy on this page and updating the &quot;Last updated&quot;
              date. We encourage you to review this policy periodically.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-3">12. Contact Us</h2>
            <p>
              If you have any questions about this Privacy Policy or our data practices, please
              contact us:
            </p>
            <div className="mt-3 rounded-lg bg-gray-50 p-4 text-sm">
              <p className="font-medium text-gray-900">{appName}</p>
              <p className="mt-1">
                Email:{" "}
                <a href={`mailto:${contactEmail}`} className="text-blue-600 underline">
                  {contactEmail}
                </a>
              </p>
              <p>Website: <a href={website} className="text-blue-600 underline">{website}</a></p>
            </div>
          </div>

        </section>
      </div>
    </main>
  );
}
