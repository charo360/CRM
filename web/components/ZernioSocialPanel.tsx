"use client";

import { useCallback, useEffect, useState } from "react";
import { zernioApi } from "@/lib/api";
import { CheckCircle2, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { ZiloLogo } from "@/components/ZiloLogo";

// ── Platform catalogue ──────────────────────────────────────────────────────

interface PlatformDef {
  id: string;
  label: string;
  guideUrl: string;
  bg: string;
  text: string;
  border: string;
  ring: string;
  logo: React.ReactNode;
}

export const SOCIAL_PLATFORMS: PlatformDef[] = [
  {
    id: "facebook",
    label: "Facebook",
    guideUrl: "https://docs.zernio.com/guides/facebook",
    bg: "bg-[#1877F2]/10",
    text: "text-[#1877F2]",
    border: "border-[#1877F2]/30",
    ring: "ring-[#1877F2]/40",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#1877F2]">
        <path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.791-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.97h-1.513c-1.491 0-1.956.93-1.956 1.883v2.252h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/>
      </svg>
    ),
  },
  {
    id: "instagram",
    label: "Instagram",
    guideUrl: "https://docs.zernio.com/guides/instagram",
    bg: "bg-pink-50",
    text: "text-pink-600",
    border: "border-pink-200",
    ring: "ring-pink-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-pink-600">
        <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
      </svg>
    ),
  },
  {
    id: "twitter",
    label: "Twitter / X",
    guideUrl: "https://docs.zernio.com/guides/twitter",
    bg: "bg-slate-100",
    text: "text-slate-800",
    border: "border-slate-300",
    ring: "ring-slate-400",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-slate-800">
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.742l7.73-8.835L1.254 2.25H8.08l4.26 5.632zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
      </svg>
    ),
  },
  {
    id: "linkedin",
    label: "LinkedIn",
    guideUrl: "https://docs.zernio.com/guides/linkedin",
    bg: "bg-[#0A66C2]/10",
    text: "text-[#0A66C2]",
    border: "border-[#0A66C2]/30",
    ring: "ring-[#0A66C2]/40",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#0A66C2]">
        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
      </svg>
    ),
  },
  {
    id: "tiktok",
    label: "TikTok",
    guideUrl: "https://docs.zernio.com/guides/tiktok",
    bg: "bg-slate-900/5",
    text: "text-slate-900",
    border: "border-slate-300",
    ring: "ring-slate-400",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-slate-900">
        <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 00-.79-.05 6.34 6.34 0 00-6.34 6.34 6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.33-6.34V8.69a8.18 8.18 0 004.78 1.52V6.75a4.85 4.85 0 01-1.01-.06z"/>
      </svg>
    ),
  },
  {
    id: "youtube",
    label: "YouTube",
    guideUrl: "https://docs.zernio.com/guides/youtube",
    bg: "bg-red-50",
    text: "text-red-600",
    border: "border-red-200",
    ring: "ring-red-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-red-600">
        <path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
      </svg>
    ),
  },
  {
    id: "pinterest",
    label: "Pinterest",
    guideUrl: "https://docs.zernio.com/guides/pinterest",
    bg: "bg-red-50",
    text: "text-[#E60023]",
    border: "border-red-200",
    ring: "ring-red-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#E60023]">
        <path d="M12 0C5.373 0 0 5.372 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738a.36.36 0 01.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z"/>
      </svg>
    ),
  },
  {
    id: "reddit",
    label: "Reddit",
    guideUrl: "https://docs.zernio.com/guides/reddit",
    bg: "bg-orange-50",
    text: "text-[#FF4500]",
    border: "border-orange-200",
    ring: "ring-orange-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#FF4500]">
        <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z"/>
      </svg>
    ),
  },
  {
    id: "bluesky",
    label: "Bluesky",
    guideUrl: "https://docs.zernio.com/guides/bluesky",
    bg: "bg-sky-50",
    text: "text-[#0085FF]",
    border: "border-sky-200",
    ring: "ring-sky-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#0085FF]">
        <path d="M12 10.8c-1.087-2.114-4.046-6.053-6.798-7.995C2.566.944 1.561 1.266.902 1.565.139 1.908 0 3.08 0 3.768c0 .69.378 5.65.624 6.479.815 2.736 3.713 3.66 6.383 3.364.136-.02.275-.039.415-.056-.138.022-.276.04-.415.056-3.912.58-7.387 2.005-2.83 7.078 5.013 5.19 6.87-1.113 7.823-4.308.953 3.195 2.05 9.271 7.733 4.308 4.267-4.308 1.172-6.498-2.74-7.078a8.741 8.741 0 0 1-.415-.056c.14.017.279.036.415.056 2.67.297 5.568-.628 6.383-3.364.246-.828.624-5.79.624-6.478 0-.69-.139-1.861-.902-2.204-.659-.298-1.664-.62-4.3 1.24C16.046 4.748 13.087 8.687 12 10.8z"/>
      </svg>
    ),
  },
  {
    id: "threads",
    label: "Threads",
    guideUrl: "https://docs.zernio.com/guides/threads",
    bg: "bg-slate-100",
    text: "text-slate-900",
    border: "border-slate-300",
    ring: "ring-slate-400",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-slate-900">
        <path d="M12.186 24h-.007c-3.581-.024-6.334-1.205-8.184-3.509C2.35 18.44 1.5 15.586 1.472 12.01v-.017c.03-3.579.879-6.43 2.525-8.482C5.845 1.205 8.6.024 12.18 0h.014c2.746.02 5.043.725 6.826 2.098 1.677 1.29 2.858 3.13 3.509 5.467l-2.04.569c-1.104-3.96-3.898-5.984-8.304-6.015-2.91.022-5.11.936-6.54 2.717C4.307 6.504 3.616 8.914 3.589 12c.027 3.086.718 5.496 2.057 7.164 1.43 1.783 3.631 2.698 6.54 2.717 2.623-.02 4.358-.631 5.8-2.045 1.647-1.613 1.618-3.593 1.09-4.798-.31-.71-.873-1.3-1.634-1.75-.192 1.352-.622 2.446-1.284 3.272-.886 1.102-2.14 1.704-3.73 1.79-1.202.065-2.361-.218-3.259-.801-1.063-.689-1.685-1.74-1.752-2.964-.065-1.19.408-2.285 1.33-3.082.88-.76 2.119-1.207 3.583-1.291a13.853 13.853 0 0 1 3.02.142c-.126-.742-.375-1.332-.75-1.757-.513-.586-1.308-.883-2.359-.89h-.029c-.844 0-1.992.232-2.721 1.32L7.734 9.13c.98-1.454 2.568-2.292 4.478-2.308h.037c1.633.01 2.928.473 3.852 1.375.898.88 1.397 2.122 1.484 3.688.152.088.302.181.45.277 1.52.99 2.48 2.376 2.82 4.022.45 2.178-.257 4.782-2.354 6.912C16.705 24.104 14.472 24 12.187 24zm-.48-9.343c-.997.057-1.786.33-2.296.79-.43.384-.647.864-.623 1.378.04.672.42 1.255 1.07 1.643.658.394 1.49.543 2.387.497 1.117-.06 1.952-.435 2.48-1.115.43-.542.678-1.273.737-2.175a11.03 11.03 0 0 0-2.432-.22c-.43 0-.866.07-1.323.202z"/>
      </svg>
    ),
  },
  {
    id: "googlebusiness",
    label: "Google Business",
    guideUrl: "https://docs.zernio.com/guides/googlebusiness",
    bg: "bg-blue-50",
    text: "text-[#4285F4]",
    border: "border-blue-200",
    ring: "ring-blue-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#4285F4]">
        <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
      </svg>
    ),
  },
  {
    id: "telegram",
    label: "Telegram",
    guideUrl: "https://docs.zernio.com/guides/telegram",
    bg: "bg-sky-50",
    text: "text-[#26A5E4]",
    border: "border-sky-200",
    ring: "ring-sky-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#26A5E4]">
        <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
      </svg>
    ),
  },
  {
    id: "snapchat",
    label: "Snapchat",
    guideUrl: "https://docs.zernio.com/guides/snapchat",
    bg: "bg-yellow-50",
    text: "text-yellow-700",
    border: "border-yellow-200",
    ring: "ring-yellow-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-yellow-500">
        <path d="M12.206.793c.99 0 4.347.276 5.93 3.821.529 1.193.403 3.219.299 4.847l-.003.06c-.012.18-.022.345-.03.51.075.045.203.09.401.09.3-.016.659-.12 1.033-.301.165-.088.344-.104.464-.104.182 0 .359.029.509.09.45.149.734.479.734.838.015.449-.39.839-1.213 1.168-.089.029-.209.075-.344.119-.45.135-1.139.36-1.333.81-.09.224-.061.524.12.868l.015.015c.06.136 1.526 3.475 4.791 4.014.255.044.435.27.42.509 0 .075-.015.149-.045.209-.24.569-1.273.988-3.146 1.271-.059.091-.12.375-.164.57-.029.179-.074.36-.134.553-.076.271-.27.405-.555.405h-.03c-.135 0-.313-.031-.538-.074-.36-.075-.765-.135-1.273-.135-.3 0-.599.015-.913.074-.6.104-1.123.464-1.723.884-.853.599-1.826 1.288-3.294 1.288-.06 0-.119-.015-.18-.015h-.149c-1.468 0-2.427-.675-3.279-1.288-.599-.42-1.107-.779-1.707-.884-.314-.045-.629-.074-.928-.074-.54 0-.958.089-1.272.149-.211.043-.391.074-.54.074-.374 0-.523-.224-.583-.42-.061-.192-.09-.389-.135-.567-.046-.181-.105-.494-.166-.57-1.918-.222-2.95-.642-3.189-1.226-.031-.063-.052-.15-.055-.225-.015-.243.165-.465.42-.509 3.264-.54 4.73-3.879 4.791-4.02l.016-.029c.18-.345.224-.645.119-.869-.195-.434-.884-.658-1.332-.809-.121-.029-.24-.074-.346-.119-1.107-.435-1.257-.93-1.197-1.273.09-.479.674-.793 1.168-.793.146 0 .27.029.383.074.42.194.789.3 1.104.3.234 0 .384-.06.465-.105l-.031-.569c-.098-1.626-.225-3.651.304-4.837C7.392 1.077 10.739.807 11.727.807l.419-.015h.06z"/>
      </svg>
    ),
  },
  {
    id: "whatsapp",
    label: "WhatsApp",
    guideUrl: "https://docs.zernio.com/guides/whatsapp",
    bg: "bg-green-50",
    text: "text-[#25D366]",
    border: "border-green-200",
    ring: "ring-green-300",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#25D366]">
        <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
      </svg>
    ),
  },
  {
    id: "discord",
    label: "Discord",
    guideUrl: "https://docs.zernio.com/guides/discord",
    bg: "bg-brand/10",
    text: "text-[#5865F2]",
    border: "border-brand/30",
    ring: "ring-brand/50",
    logo: (
      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-[#5865F2]">
        <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057.1 18.079.111 18.1.127 18.114a19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
      </svg>
    ),
  },
];

// ── Types ───────────────────────────────────────────────────────────────────

interface ZernioAccount {
  id: string;
  platform: string;
  name?: string;
  username?: string;
}

interface Props {
  context?: "meta" | "google";
  hideBranding?: boolean;
}

// ── Component ───────────────────────────────────────────────────────────────

export function ZernioSocialPanel({ context = "meta", hideBranding = false }: Props) {
  const [accounts, setAccounts] = useState<ZernioAccount[]>([]);
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [connecting, setConnecting] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const status = await zernioApi.status();
      const isConnected = status.connected === true;
      setApiConnected(isConnected);
      if (isConnected) {
        const list: ZernioAccount[] = (status.accounts as ZernioAccount[] | undefined) ?? [];
        setAccounts(list);
      }
    } catch {
      setApiConnected(false);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const connectPlatform = useCallback(async (platformId: string) => {
    setConnecting(platformId);
    try {
      const { authUrl } = await zernioApi.connect(platformId);
      if (authUrl) window.open(authUrl, "_blank", "noopener,noreferrer");
    } catch (e) {
      console.error("Failed to get connect URL:", e);
    } finally {
      setConnecting(null);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const connectedPlatforms = new Set(accounts.map((a) => a.platform.toLowerCase()));
  const connectedCount = SOCIAL_PLATFORMS.filter((p) => connectedPlatforms.has(p.id)).length;

  const contextLabel =
    context === "google"
      ? "Extend your Google Ads reach across social channels"
      : "Promote Meta campaigns across every social platform";

  if (loading) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 flex items-center justify-center gap-3 text-slate-500">
        <Loader2 size={16} className="animate-spin" />
        <span className="text-sm">Loading Zernio social accounts…</span>
      </section>
    );
  }

  if (apiConnected === false) {
    // Compact version for integrations page (already inside a card)
    if (hideBranding) {
      return (
        <div className="space-y-3 py-1">
          <p className="text-center text-xs text-slate-400">
            Not yet activated — all {SOCIAL_PLATFORMS.length} platforms will be available once enabled.
          </p>
          <div className="grid grid-cols-5 sm:grid-cols-6 lg:grid-cols-8 gap-1.5">
            {SOCIAL_PLATFORMS.map((p) => (
              <div key={p.id} className="flex flex-col items-center gap-1 rounded-lg p-2 border border-slate-200 bg-slate-50 opacity-50 grayscale">
                {p.logo}
                <span className="text-[9px] font-medium text-slate-500 text-center leading-tight truncate w-full text-center">{p.label}</span>
              </div>
            ))}
          </div>
        </div>
      );
    }
    return (
      <section className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
          <div className="flex items-center gap-2.5">
            <ZiloLogo size={28} className="shrink-0" />
            <div>
              <p className="text-sm font-semibold text-slate-800">Social Media Integration</p>
              <p className="text-[11px] text-slate-500">{contextLabel}</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold bg-amber-100 text-amber-700">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            Coming soon
          </span>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-5 sm:grid-cols-6 lg:grid-cols-8 gap-1.5">
            {SOCIAL_PLATFORMS.map((p) => (
              <div key={p.id} className="flex flex-col items-center gap-1 rounded-lg p-2 border border-slate-200 bg-slate-50 opacity-50 grayscale">
                {p.logo}
                <span className="text-[9px] font-medium text-slate-500 text-center leading-tight truncate w-full text-center">{p.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  if (hideBranding) {
    return (
      <div className="rounded-lg bg-slate-50/60 p-2 sm:p-3">
        {/* Status bar — stack on narrow screens so controls stay right-side up */}
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
          {apiConnected !== null && (
            <span className={`inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
              apiConnected ? "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200" : "bg-slate-100 text-slate-600 ring-1 ring-slate-200"
            }`}>
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${apiConnected ? "bg-emerald-500" : "bg-slate-400"}`} />
              {apiConnected ? `${connectedCount} / ${SOCIAL_PLATFORMS.length} connected` : "0 / " + SOCIAL_PLATFORMS.length + " connected"}
            </span>
          )}
          <div className="flex flex-wrap items-center gap-2 sm:ml-auto sm:justify-end">
            <a href="/dashboard/social-inbox" className="inline-flex items-center gap-1 rounded-lg border border-brand/30 bg-white px-2.5 py-1 text-[10px] font-semibold text-brand-dark shadow-sm hover:bg-brand/10 transition-colors">
              Social Inbox <ExternalLink size={9} />
            </a>
            <button type="button" onClick={() => void load(true)} disabled={refreshing}
              className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-500 shadow-sm hover:border-brand/40 hover:text-brand-dark transition-colors disabled:opacity-40" title="Refresh">
              <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
        {/* Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {SOCIAL_PLATFORMS.map((p) => {
            const isConnected = connectedPlatforms.has(p.id);
            const account = accounts.find((a) => a.platform.toLowerCase() === p.id);
            return (
              <div key={p.id} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 border transition-all ${
                isConnected ? `${p.bg} ${p.border} shadow-sm` : "border-slate-200 bg-white shadow-sm"
              }`}>
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                  isConnected ? "bg-white shadow-sm ring-1 ring-slate-900/5" : "bg-slate-50 ring-1 ring-slate-200/80"
                }`}>{p.logo}</div>
                <div className="flex-1 min-w-0">
                  <p className={`text-xs font-semibold truncate ${isConnected ? "text-slate-800" : "text-slate-600"}`}>{p.label}</p>
                  {isConnected && account ? (
                    <p className="text-[10px] text-slate-500 truncate">{account.username ? `@${account.username}` : account.name ?? "Connected"}</p>
                  ) : isConnected ? (
                    <p className="text-[10px] text-slate-500">Connected</p>
                  ) : (
                    <p className="text-[10px] text-slate-400">Not connected</p>
                  )}
                </div>
                {isConnected ? (
                  <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                ) : (
                  <button type="button" disabled={connecting === p.id} onClick={() => void connectPlatform(p.id)}
                    className="inline-flex shrink-0 items-center gap-0.5 rounded-lg border border-brand-dark/30 bg-brand-dark px-2 py-1 text-[10px] font-semibold text-white shadow-sm hover:bg-brand disabled:opacity-50 transition-colors">
                    {connecting === p.id ? <Loader2 size={9} className="animate-spin" /> : <><span>Connect</span><ExternalLink size={9} /></>}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
        <div className="flex items-center gap-2.5">
          <ZiloLogo size={28} className="shrink-0" />
          <div>
            <p className="text-sm font-semibold text-slate-800">Social Media Channels</p>
            <p className="text-[11px] text-slate-500">{contextLabel}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {apiConnected !== null && (
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
              apiConnected ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${apiConnected ? "bg-emerald-500" : "bg-slate-400"}`} />
              {apiConnected ? `${connectedCount} / ${SOCIAL_PLATFORMS.length} connected` : "API key needed"}
            </span>
          )}
          <button type="button" onClick={() => void load(true)} disabled={refreshing}
            className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-500 shadow-sm hover:border-brand/40 hover:text-brand-dark transition-colors disabled:opacity-40" title="Refresh">
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Platform grid */}
      <div className="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {SOCIAL_PLATFORMS.map((p) => {
            const isConnected = connectedPlatforms.has(p.id);
            const account = accounts.find((a) => a.platform.toLowerCase() === p.id);

            return (
              <div
                key={p.id}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 border transition-all ${
                  isConnected
                    ? `${p.bg} ${p.border} shadow-sm`
                    : "border-slate-200 bg-white shadow-sm"
                }`}
              >
                {/* Logo */}
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                    isConnected ? "bg-white shadow-sm ring-1 ring-slate-900/5" : "bg-slate-50 ring-1 ring-slate-200/80"
                  }`}
                >
                  {p.logo}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className={`text-xs font-semibold truncate ${isConnected ? "text-slate-800" : "text-slate-500"}`}>
                    {p.label}
                  </p>
                  {isConnected && account ? (
                    <p className="text-[10px] text-slate-500 truncate">
                      {account.username ? `@${account.username}` : account.name ?? "Connected"}
                    </p>
                  ) : isConnected ? (
                    <p className="text-[10px] text-slate-500">Connected</p>
                  ) : (
                    <p className="text-[10px] text-slate-400">Not connected</p>
                  )}
                </div>

                {/* Status / Action */}
                {isConnected ? (
                  <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                ) : (
                  <button
                    type="button"
                    disabled={connecting === p.id}
                    onClick={() => void connectPlatform(p.id)}
                    className="inline-flex shrink-0 items-center gap-0.5 rounded-lg border border-brand-dark/30 bg-brand-dark px-2 py-1 text-[10px] font-semibold text-white shadow-sm hover:bg-brand disabled:opacity-50 transition-colors"
                    title={`Connect ${p.label}`}
                  >
                    {connecting === p.id
                      ? <Loader2 size={9} className="animate-spin" />
                      : <><span>Connect</span><ExternalLink size={9} /></>}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="mt-3 flex items-center justify-between">
          {!hideBranding ? (
            <p className="text-[10px] text-slate-400">
              Powered by{" "}
              <a href="https://zernio.com" target="_blank" rel="noopener noreferrer" className="font-medium text-brand hover:underline">
                Zernio
              </a>{" "}
              — click Connect on any platform above
            </p>
          ) : (
            <p className="text-[10px] text-slate-400">Click Connect on any platform to link your account</p>
          )}
          <a
            href="/dashboard/social-inbox"
            className="inline-flex items-center gap-1 rounded-lg border border-brand/30 bg-brand/10 px-3 py-1 text-[10px] font-semibold text-brand-dark hover:bg-brand/15 transition-colors"
          >
            Social Inbox <ExternalLink size={10} />
          </a>
        </div>
      </div>
    </section>
  );
}
