"use client";

import { motion } from "framer-motion";
import { Activity, Droplets, Target } from "lucide-react";
import { signOut, useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import { request, gql } from "graphql-request";

const DASHBOARD_QUERY = gql`
  query GetDashboard {
    me {
      firstName
      dashboard {
        latestWeight
        latestBodyFat
        goalBodyFat
      }
    }
  }
`;

interface DashboardData {
    latestWeight: number | null;
    latestBodyFat: number | null;
    goalBodyFat: number | null;
}

interface DashboardResponse {
    me: {
        firstName: string;
        dashboard: DashboardData | null;
    } | null;
}

export default function Dashboard() {
    const { data: session } = useSession();
    const [data, setData] = useState<DashboardData | null>(null);
    const [fetchedName, setFetchedName] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!session?.accessToken) return;

        let cancelled = false;
        setLoading(true);

        const loadDashboard = async () => {
            try {
                const response = await request<DashboardResponse>(
                    "/api/graphql",
                    DASHBOARD_QUERY,
                    {},
                    { Authorization: `Bearer ${session.accessToken}` },
                );

                if (!response.me) {
                    await signOut({ callbackUrl: "/login" });
                    return;
                }

                if (!cancelled && response.me.dashboard) {
                    setData(response.me.dashboard);
                }
                if (!cancelled && response.me.firstName) {
                    setFetchedName(response.me.firstName);
                }
            } catch (error) {
                console.error("Failed to fetch dashboard data", error);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        void loadDashboard();
        return () => {
            cancelled = true;
        };
    }, [session]);

    const firstName = fetchedName || session?.user?.name?.split(" ")[0] || "Athlete";

    return (
        <div className="min-h-screen p-6 md:p-12 text-white">
            {/* Header */}
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6 }}
                className="mb-12"
            >
                <h1 data-testid="dashboard-greeting" className="text-4xl md:text-6xl font-black tracking-tight mb-2">
                    {`Time to dominate, ${firstName}!`}
                </h1>
                <p className="text-slate-400 text-lg">
                    Review your latest measurements and goals.
                </p>
            </motion.div>

            {/* Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

                {/* Weight Card */}
                <Card delay={0.1}>
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-xl font-bold text-slate-200">Current Weight</h3>
                        <div className="p-2 bg-purple-500/20 rounded-full text-purple-400">
                            <Activity size={24} />
                        </div>
                    </div>
                    <div className="flex items-end gap-2">
                        <span className="text-5xl font-black">{data?.latestWeight ?? "--"}</span>
                        <span className="text-slate-400 text-xl font-medium mb-1">kg</span>
                    </div>
                </Card>

                {/* Body Fat Goal Card */}
                <Card delay={0.2}>
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-xl font-bold text-slate-200">Body Composition</h3>
                        <div className="p-2 bg-emerald-500/20 rounded-full text-emerald-400">
                            <Target size={24} />
                        </div>
                    </div>
                    <div className="flex items-end gap-4">
                        <div>
                            <p className="text-xs text-slate-500 uppercase font-bold tracking-wider">Current</p>
                            <div className="flex items-end gap-1">
                                <span className="text-4xl font-black text-white">{data?.latestBodyFat ?? "--"}</span>
                                <span className="text-slate-400 text-sm mb-1">%</span>
                            </div>
                        </div>
                        <div className="h-8 w-[1px] bg-slate-700 mb-1"></div>
                        <div>
                            <p className="text-xs text-slate-500 uppercase font-bold tracking-wider">Goal</p>
                            <div className="flex items-end gap-1">
                                <span className="text-4xl font-black text-emerald-400">{data?.goalBodyFat ?? "--"}</span>
                                <span className="text-emerald-500/50 text-sm mb-1">%</span>
                            </div>
                        </div>
                    </div>
                </Card>

                {/* Placeholder: Hydration / Streak */}
                <Card delay={0.3}>
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-xl font-bold text-slate-200">Hydration</h3>
                        <div className="p-2 bg-blue-500/20 rounded-full text-blue-400">
                            <Droplets size={24} />
                        </div>
                    </div>
                    <div className="text-center py-6">
                        <div className="text-4xl font-black text-blue-400 mb-2">--</div>
                        <p className="text-slate-400">Data unavailable</p>
                    </div>
                </Card>

            </div>

            {/* Measurement logging status */}
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5, duration: 0.8 }}
                className="mt-12 p-6 glass-card rounded-2xl"
            >
                <h4 className="font-bold text-lg">Measurement logging</h4>
                <p className="text-slate-400">
                    Logging new measurements from the dashboard is not available yet.
                </p>
            </motion.div>
        </div>
    );
}

function Card({ children, delay }: { children: React.ReactNode; delay: number }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay, duration: 0.5, ease: "easeOut" }}
            className="glass-card p-6 rounded-3xl hover:bg-white/5 transition-colors"
        >
            {children}
        </motion.div>
    );
}
