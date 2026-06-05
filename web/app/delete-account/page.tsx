import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Delete Account · Zilo",
  description: "Request account deletion and user data removal from Zilo.",
};

export default function DeleteAccountPage() {
  const appName = "Zilo";
  const contactEmail = "sam@zilo.pro";
  const website = "https://zilo.pro";

  return (
    <main className="min-h-screen bg-white px-4 py-16">
      <div className="mx-auto max-w-3xl">
        <p className="mb-6 text-sm text-gray-500">
          <Link href="/" className="text-brand-dark underline hover:no-underline">
            ← Back to home
          </Link>
        </p>
        <h1 className="mb-2 text-4xl font-bold text-gray-900">Delete Your {appName} Account</h1>
        <p className="mb-10 text-sm text-gray-500">
          We are sorry to see you go. This page explains how to request deletion of your {appName} account and associated data.
        </p>

        <section className="prose prose-gray max-w-none space-y-8 leading-relaxed text-gray-700">
          <div className="rounded-lg border-l-4 border-yellow-500 bg-yellow-50 p-4 text-yellow-800">
            <p className="font-semibold">⚠️ Warning:</p>
            <p className="mt-1">
              Account deletion is permanent and cannot be undone. All your data will be permanently removed from our servers.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">What Gets Deleted</h2>
            <p>When you delete your {appName} account, the following data will be permanently removed:</p>
            <ul className="mt-2 list-disc space-y-1 pl-6">
              <li><strong>Account Information:</strong> Your phone number, business name, and profile details.</li>
              <li><strong>Customer Data:</strong> All imported contacts, customer profiles, and conversation history.</li>
              <li><strong>Messages:</strong> All messaging records stored in the CRM (WhatsApp, email, social integrations).</li>
              <li><strong>Business Data:</strong> Products, orders, bookings, sales records, and analytics.</li>
              <li><strong>Subscription Information:</strong> Your subscription status and payment history.</li>
            </ul>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">Data Retention Period</h2>
            <p>Once you submit a deletion request:</p>
            <ul className="mt-2 list-disc space-y-1 pl-6">
              <li>Your account will be deactivated immediately.</li>
              <li>All personal and business data will be permanently deleted within <strong>30 days</strong>.</li>
              <li>Some transaction records may be retained for up to 90 days for legal and accounting purposes only.</li>
            </ul>
          </div>

          <div className="rounded-lg border-l-4 border-blue-500 bg-blue-50 p-4 text-blue-800">
            <p className="font-semibold">ℹ️ Note on Third-Party Data:</p>
            <p className="mt-1">
              Messages sent or received via third-party services (such as WhatsApp, Facebook, or Instagram) are also stored on those platform's servers. Deleting your {appName} account does not delete message history from third-party networks. You must manage/delete conversations on those apps directly.
            </p>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">How to Request Account Deletion</h2>
            <p>To request deletion of your account and all associated data, you can do either of the following:</p>
            
            <div className="mt-4 space-y-6">
              <div>
                <h3 className="text-lg font-medium text-gray-800 mb-1">Option 1: Request via Email</h3>
                <p>Please send an email from your registered email address:</p>
                <ul className="mt-2 list-disc space-y-1 pl-6">
                  <li><strong>To:</strong> <a href={`mailto:${contactEmail}`} className="text-blue-600 underline font-medium">{contactEmail}</a></li>
                  <li><strong>Subject:</strong> Account Deletion Request - {appName}</li>
                  <li><strong>Body:</strong> Include your registered phone number and business name.</li>
                </ul>
                <div className="mt-3">
                  <a
                    href={`mailto:${contactEmail}?subject=Account%20Deletion%20Request%20-%20${appName}&body=Please%20delete%20my%20${appName}%20account.%0A%0AMy%20registered%20phone%20number%2Femail%3A%20`}
                    className="inline-block rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-700 focus:outline-none"
                  >
                    📧 Send Deletion Request Email
                  </a>
                </div>
              </div>

              <div>
                <h3 className="text-lg font-medium text-gray-800 mb-1">Option 2: Delete Account In-App</h3>
                <p>If you still have access to the app dashboard, you can delete your account directly:</p>
                <ol className="mt-2 list-decimal space-y-1 pl-6">
                  <li>Open the {appName} application dashboard.</li>
                  <li>Navigate to the <strong>Settings</strong> page.</li>
                  <li>Scroll to the bottom of the page and click <strong>&quot;Delete Account&quot;</strong>.</li>
                  <li>Confirm the deletion request when prompted.</li>
                </ol>
              </div>
            </div>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-semibold text-gray-900">Questions?</h2>
            <p>
              If you have any questions about our data deletion practices or privacy policies, please contact us at{" "}
              <a href={`mailto:${contactEmail}`} className="text-blue-600 underline font-medium">
                {contactEmail}
              </a>
              .
            </p>
            
            <div className="mt-8 border-t border-gray-200 pt-6 text-sm text-gray-500">
              <Link href="/privacy-policy" className="text-brand-dark underline hover:no-underline">
                Privacy Policy
              </Link>
              <span className="mx-2">|</span>
              <a href={`mailto:${contactEmail}`} className="text-brand-dark underline hover:no-underline">
                Contact Support
              </a>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
