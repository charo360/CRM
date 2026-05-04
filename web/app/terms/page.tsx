import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms & Conditions · Zilo",
  description: "Terms and Conditions for using the Zilo workspace and services.",
};

export default function TermsPage() {
  const lastUpdated = "May 2, 2026";
  const contactEmail = "legal@zilo.pro";
  const appName = "Zilo";
  const website = "https://zilo.pro";

  return (
    <main className="min-h-screen bg-white px-4 py-16">
      <div className="mx-auto max-w-3xl">
        <p className="mb-6 text-sm text-gray-500">
          <Link href="/" className="text-brand-dark underline hover:no-underline">
            ← Back to home
          </Link>
        </p>
        <h1 className="mb-2 text-4xl font-bold text-gray-900">{appName} Terms &amp; Conditions</h1>
        <p className="mb-10 text-sm text-gray-500">Last updated: {lastUpdated}</p>

        <section className="prose prose-gray max-w-none space-y-8 leading-relaxed text-gray-700">
          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">1. Agreement</h2>
            <p>
              These Terms &amp; Conditions (&quot;Terms&quot;) govern your access to and use of {appName},
              including {website} and related applications (the &quot;Service&quot;). By creating an account or
              using the Service, you agree to these Terms and our{" "}
              <Link href="/privacy-policy" className="text-blue-600 underline">
                Privacy Policy
              </Link>
              .
            </p>
            <p className="mt-2">
              If you use {appName} on behalf of a company or organization, you represent that you have
              authority to bind that entity.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">2. The Service</h2>
            <p>
              {appName} provides an omnichannel business workspace that may include messaging, CRM,
              commerce integrations, marketing tools, analytics, and AI-assisted features. We may modify,
              suspend, or discontinue parts of the Service with reasonable notice where practicable.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">3. Accounts &amp; security</h2>
            <p>
              You must provide accurate registration information and keep your credentials confidential.
              You are responsible for activity under your account. Notify us promptly at{" "}
              <a href={`mailto:${contactEmail}`} className="text-blue-600 underline">
                {contactEmail}
              </a>{" "}
              if you suspect unauthorized access.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">4. Acceptable use</h2>
            <p>You agree not to:</p>
            <ul className="mt-2 list-disc space-y-1 pl-6">
              <li>Use the Service unlawfully, fraudulently, or to harass others</li>
              <li>Attempt to probe, scan, or breach our systems or other users&apos; data without authorization</li>
              <li>Reverse engineer or circumvent technical limits except where law forbids such restriction</li>
              <li>Upload malware or content that infringes intellectual property or privacy rights</li>
              <li>Use the Service to send spam or violate carrier/platform rules (e.g. WhatsApp, Meta, Google)</li>
            </ul>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">5. Third-party integrations</h2>
            <p>
              The Service may connect to third-party platforms (e.g. Shopify, Stripe, Google, Meta,
              WhatsApp). Your use of those services is also governed by their respective terms. We are not
              responsible for outages or changes made by third parties; some features depend on permissions
              you grant through OAuth or API connections.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">6. AI-assisted features</h2>
            <p>
              AI-generated drafts, summaries, or suggestions may be inaccurate or incomplete. You remain
              responsible for reviewing content before it is sent to customers or published. Do not rely on
              AI output as legal, financial, or medical advice.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">7. Intellectual property</h2>
            <p>
              {appName} and its branding, software, and documentation are protected by intellectual
              property laws. We grant you a limited, non-exclusive, non-transferable right to use the
              Service during your subscription or trial. You retain ownership of content you submit; you
              grant us a license to host and process it as needed to operate the Service.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">8. Fees</h2>
            <p>
              If you subscribe to paid plans, fees and billing cycles are described at checkout or in your
              account. Unless stated otherwise, fees are non-refundable except as required by law. We may
              change pricing with advance notice.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">9. Suspension &amp; termination</h2>
            <p>
              We may suspend or terminate access for breach of these Terms, risk to the Service or other
              users, or legal requirements. You may stop using the Service and request account deletion as
              described in our Privacy Policy.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">10. Disclaimers</h2>
            <p>
              THE SERVICE IS PROVIDED &quot;AS IS&quot; AND &quot;AS AVAILABLE&quot; WITHOUT WARRANTIES OF ANY KIND,
              WHETHER EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
              NON-INFRINGEMENT, TO THE MAXIMUM EXTENT PERMITTED BY LAW.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">11. Limitation of liability</h2>
            <p>
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, ZILO AND ITS AFFILIATES WILL NOT BE
              LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR LOSS OF
              PROFITS, DATA, OR GOODWILL. OUR AGGREGATE LIABILITY FOR CLAIMS RELATING TO THE SERVICE SHALL
              NOT EXCEED THE GREATER OF (A) THE AMOUNTS YOU PAID US FOR THE SERVICE IN THE TWELVE MONTHS
              BEFORE THE CLAIM OR (B) ONE HUNDRED US DOLLARS (US$100), EXCEPT WHERE LIABILITY CANNOT BE
              LIMITED BY LAW.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">12. Indemnity</h2>
            <p>
              You will defend and indemnify {appName} and its team against claims arising from your content,
              your breach of these Terms, or your misuse of the Service, except to the extent caused by our
              gross negligence or willful misconduct.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">13. Governing law</h2>
            <p>
              These Terms are governed by the laws applicable to the operating entity behind {appName},
              without regard to conflict-of-law rules. Courts in that jurisdiction will have exclusive
              venue, subject to mandatory consumer protections in your country of residence where they
              cannot be waived.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">14. Changes</h2>
            <p>
              We may update these Terms by posting a new version on this page and updating the &quot;Last
              updated&quot; date. Continued use after changes constitutes acceptance where permitted by law.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">15. Contact</h2>
            <p>
              Questions about these Terms:{" "}
              <a href={`mailto:${contactEmail}`} className="text-blue-600 underline">
                {contactEmail}
              </a>
              .
            </p>
            <div className="mt-3 rounded-lg bg-gray-50 p-4 text-sm">
              <p className="font-medium text-gray-900">{appName}</p>
              <p className="mt-1">
                Website:{" "}
                <a href={website} className="text-blue-600 underline">
                  {website}
                </a>
              </p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
