"use client";

import React, { useEffect, useState } from "react";

interface DiscountOffer {
  campaign_id: string;
  campaign_name: string;
  discount_code: string;
  discount_type: string;
  discount_value: number;
  message: string;
  delivery_method: string;
  expires_at: string;
}

interface BehaviorDiscountWidgetProps {
  businessId: string;
  visitorId: string;
}

export default function BehaviorDiscountWidget({ businessId, visitorId }: BehaviorDiscountWidgetProps) {
  const [offer, setOffer] = useState<DiscountOffer | null>(null);
  const [showPopup, setShowPopup] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    checkForOffer();
  }, [businessId, visitorId]);

  const checkForOffer = async () => {
    try {
      const response = await fetch(`/api/marketing/behavior-discount/check?visitor_id=${visitorId}`);
      if (response.ok) {
        const data = await response.json();
        if (data.offer) {
          setOffer(data.offer);
          if (data.offer.delivery_method === "popup") {
            setTimeout(() => setShowPopup(true), 2000); // Show after 2 seconds
          }
        }
      }
    } catch (error) {
      console.error("Failed to check for discount offer:", error);
    }
  };

  const copyCode = () => {
    if (offer) {
      navigator.clipboard.writeText(offer.discount_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const closePopup = () => {
    setShowPopup(false);
    // Mark as shown
    if (offer) {
      fetch(`/api/marketing/behavior-discount/mark-shown`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ visitor_id: visitorId, campaign_id: offer.campaign_id }),
      });
    }
  };

  if (!offer || !showPopup) return null;

  return (
    <>
      {/* Overlay */}
      <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
        {/* Popup */}
        <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 relative animate-in fade-in zoom-in duration-300">
          {/* Close button */}
          <button
            onClick={closePopup}
            className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

          {/* Content */}
          <div className="text-center">
            {/* Icon */}
            <div className="w-16 h-16 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7" />
              </svg>
            </div>

            {/* Title */}
            <h3 className="text-2xl font-bold text-slate-900 mb-2">
              Special Offer Just For You! 🎉
            </h3>

            {/* Message */}
            <p className="text-slate-600 mb-6">
              {offer.message}
            </p>

            {/* Discount Code */}
            <div className="bg-gradient-to-r from-green-50 to-emerald-50 border-2 border-green-200 rounded-xl p-4 mb-6">
              <p className="text-xs text-slate-600 mb-1">Your Discount Code:</p>
              <div className="flex items-center justify-center gap-2">
                <code className="text-2xl font-bold text-green-700 tracking-wider">
                  {offer.discount_code}
                </code>
                <button
                  onClick={copyCode}
                  className="p-2 hover:bg-green-100 rounded-lg transition-colors"
                  title="Copy code"
                >
                  {copied ? (
                    <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Discount Details */}
            <div className="flex items-center justify-center gap-2 mb-6">
              <span className="text-3xl font-bold text-green-600">
                {offer.discount_type === "percentage" ? `${offer.discount_value}%` : `$${offer.discount_value}`}
              </span>
              <span className="text-slate-600">OFF</span>
            </div>

            {/* Expiry */}
            <p className="text-xs text-slate-500 mb-6">
              Expires: {new Date(offer.expires_at).toLocaleDateString()}
            </p>

            {/* CTA Button */}
            <button
              onClick={closePopup}
              className="w-full bg-gradient-to-r from-green-500 to-emerald-600 text-white font-semibold py-3 px-6 rounded-xl hover:from-green-600 hover:to-emerald-700 transition-all shadow-lg hover:shadow-xl"
            >
              Continue Shopping
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
