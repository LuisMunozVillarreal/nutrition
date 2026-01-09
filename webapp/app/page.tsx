'use client'

import { useSession } from "next-auth/react";
import Link from "next/link";
import Dashboard from "./components/Dashboard";

export default function Home() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-[#0f111a]">
        <div className="text-center">
          <p className="text-slate-400">Loading...</p>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-[#0f111a]">
        <div className="text-center space-y-6">
          <h1 className="text-5xl font-black text-white tracking-tighter">
            <span className="text-gradient">Nutrition</span> App
          </h1>
          <p className="text-slate-400">Please sign in to view your dashboard.</p>
          <Link href="/api/auth/signin" className="inline-block px-8 py-3 bg-purple-600 hover:bg-purple-700 text-white font-bold rounded-full transition-all shadow-[0_0_20px_rgba(139,92,246,0.5)]">
            Get Started
          </Link>
        </div>
      </main>
    );
  }

  return <Dashboard />;
}
