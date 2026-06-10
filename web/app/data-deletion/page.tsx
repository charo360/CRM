import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Data Deletion · Zilo",
  description: "How to request deletion of your data from Zilo.",
};

export default function DataDeletionPage() {
  const contactEmail = "sam@zilo.pro";
  const appName = "Zilo";
  const website = "https://zilo.pro";

  return (
    <main className="min-h-screen bg-white px-4 py-16">
      <div className="mx-auto max-w-3xl">
        <p className="mb-6 text-sm text-gray-500">
          <Link href="/" className="text-blue-600 underline hover:no-underline">
            ← Back to home
          </Link>
        </p>

        <h1 className="mb-2 text-4xl font-bold text-gray-900">Data Deletion Request</h1>
        <p className="mb-10 text-sm text-gray-500">Last updated: June 2026</p>

        <section className="space-y-8 text-gray-700 leading-relaxed">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Your Right to Delete Your Data</h2>
            <p>
              When you connect your Facebook account to {appName}, we may store certain account
              information such as your Facebook Page ID, access tokens, and message history to power
              the autoreply and social publishing features.
            </p>
            <p className="mt-3">
              You have the right to request deletion of all personal data we hold about you at any
              time.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">How to Request Deletion</h2>
            <p>You can request deletion of your data in any of the following ways:</p>
            <ul className="mt-3 list-disc pl-6 space-y-2">
              <li>
                <strong>From the app:</strong> Go to <em>Settings → Account → Delete My Data</em> to
                submit an instant deletion request.
              </li>
              <li>
                <strong>By email:</strong> Send a request to{" "}
                <a href={`mailto:${contactEmail}`} className="text-blue-600 underline">
                  {contactEmail}
                </a>{" "}
                with the subject line <em>"Data Deletion Request"</em> and your registered email
                address.
              </li>
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">What We Delete</h2>
            <p>Upon a verified deletion request we will permanently remove:</p>
            <ul className="mt-3 list-disc pl-6 space-y-2">
              <li>Your account profile and login credentials</li>
              <li>Facebook and Instagram Page access tokens</li>
              <li>All stored messages and conversation history</li>
              <li>Scheduled and published social posts</li>
              <li>Any autoreply rules and CRM contact data linked to your account</li>
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Timeline</h2>
            <p>
              We will process your request and confirm deletion within <strong>30 days</strong>. You
              will receive a confirmation email once the process is complete.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Facebook-Specific Data</h2>
            <p>
              If you connected your Facebook account via Facebook Login, you can also revoke{" "}
              {appName}&apos;s access directly from your Facebook settings:
            </p>
            <ol className="mt-3 list-decimal pl-6 space-y-2">
              <li>
                Go to <strong>Facebook Settings → Security and Login → Apps and Websites</strong>
              </li>
              <li>Find <strong>{appName}</strong> and click <strong>Remove</strong></li>
              <li>
                Then contact us at{" "}
                <a href={`mailto:${contactEmail}`} className="text-blue-600 underline">
                  {contactEmail}
                </a>{" "}
                to confirm full backend deletion.
              </li>
            </ol>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Contact</h2>
            <p>
              For any questions about data deletion, contact us at{" "}
              <a href={`mailto:${contactEmail}`} className="text-blue-600 underline">
                {contactEmail}
              </a>{" "}
              or visit{" "}
              <a href={website} className="text-blue-600 underline">
                {website}
              </a>
              .
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
