'use client'

import { motion } from 'framer-motion'
import { Activity, ArrowRight, Target, UtensilsCrossed, Weight } from 'lucide-react'
import { signOut, useSession } from 'next-auth/react'
import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'
import { gql, graphqlRequest } from '@/lib/graphql'
import {
  buildWeightTrendSeries,
  isCurrentLocalDate,
  millisecondsUntilNextLocalDay,
  type DashboardMeasurement,
} from './dashboardHelpers'
import WeightTrendChart from './WeightTrendChart'

const DASHBOARD_QUERY = gql`
  query GetDashboard($timezoneOffsetMinutes: Int!) {
    me {
      firstName
      dashboard(timezoneOffsetMinutes: $timezoneOffsetMinutes) {
        latestWeight
        latestBodyFat
        goalBodyFat
        recentMeasurements {
          id
          createdAt
          weight
          bodyFatPerc
        }
        todayNutrition {
          id
          day
          energyKcal
          energyKcalGoal
          intakeCount
        }
      }
    }
  }
`

interface TodayNutrition {
  id: string
  day: string
  energyKcal: number
  energyKcalGoal: number
  intakeCount: number
}

interface DashboardSummary {
  latestWeight: number | null
  latestBodyFat: number | null
  goalBodyFat: number | null
  recentMeasurements: DashboardMeasurement[]
  todayNutrition: TodayNutrition | null
}

interface DashboardResponse {
  me: {
    firstName: string
    dashboard: DashboardSummary
  } | null
}

export default function Dashboard() {
  const { data: session, status } = useSession()
  const [response, setResponse] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const requestSequence = useRef(0)

  useEffect(() => {
    if (status !== 'authenticated') return
    let cancelled = false
    let midnightTimer: ReturnType<typeof setTimeout> | undefined

    async function loadDashboard() {
      const requestId = ++requestSequence.current
      setLoading(true)
      setError(false)
      try {
        const result = await graphqlRequest<DashboardResponse>(DASHBOARD_QUERY, {
          timezoneOffsetMinutes: new Date().getTimezoneOffset(),
        })
        if (!result.me && requestId === requestSequence.current) {
          await signOut({ callbackUrl: '/login' })
          return
        }
        if (!cancelled && requestId === requestSequence.current) setResponse(result)
      } catch (loadError) {
        console.error('Failed to fetch dashboard data', loadError)
        if (!cancelled && requestId === requestSequence.current) setError(true)
      } finally {
        if (!cancelled && requestId === requestSequence.current) setLoading(false)
      }
    }

    function scheduleMidnightRefresh() {
      midnightTimer = setTimeout(async () => {
        await loadDashboard()
        if (!cancelled) scheduleMidnightRefresh()
      }, millisecondsUntilNextLocalDay())
    }

    function refreshWhenVisible() {
      if (!document.hidden) void loadDashboard()
    }

    void loadDashboard()
    scheduleMidnightRefresh()
    window.addEventListener('focus', refreshWhenVisible)
    document.addEventListener('visibilitychange', refreshWhenVisible)

    return () => {
      cancelled = true
      requestSequence.current += 1
      // scheduleMidnightRefresh() always ran before any cleanup, so the timer
      // handle is set; clearTimeout(undefined) is a documented no-op.
      clearTimeout(midnightTimer)
      window.removeEventListener('focus', refreshWhenVisible)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [status])

  const summary = response?.me?.dashboard
  // Memoize the fallback so the dependency identity stays stable across renders.
  const measurements = useMemo(() => summary?.recentMeasurements ?? [], [summary?.recentMeasurements])
  const trend = useMemo(() => buildWeightTrendSeries(measurements, 14), [measurements])
  const latestMeasurement = measurements.at(-1)
  const today = summary?.todayNutrition ?? null
  const todayIsCurrent = today !== null && isCurrentLocalDate(today.day)
  const currentWeight = latestMeasurement?.weight ?? summary?.latestWeight ?? null
  const currentBodyFat = latestMeasurement?.bodyFatPerc ?? summary?.latestBodyFat ?? null
  const firstName = response?.me?.firstName || session?.user?.name?.split(' ')[0] || 'Athlete'
  const mealHref = !loading && todayIsCurrent
    ? `/scan?mode=intake&dayId=${encodeURIComponent(today.id)}`
    : '/days'

  return (
    <div className="min-h-screen p-6 text-white md:p-12">
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-10"
      >
        <p className="mb-2 text-sm font-bold uppercase tracking-[0.22em] text-purple-400">Daily dashboard</p>
        <h1 data-testid="dashboard-greeting" className="mb-3 text-4xl font-black tracking-tight md:text-6xl">
          {`Time to dominate, ${firstName}!`}
        </h1>
        <p className="max-w-2xl text-lg text-slate-400">
          Log what matters today and keep your progress moving.
        </p>
      </motion.header>

      <section aria-label="Quick actions" className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <QuickAction
          href="/measurements/new"
          icon={<Weight size={24} />}
          title="Log today weight"
          description="Add your daily weight and body-fat measurement."
          accent="purple"
        />
        <QuickAction
          href={mealHref}
          icon={<UtensilsCrossed size={24} />}
          title="Log a meal"
          description={!loading && todayIsCurrent ? 'Scan a product to add it to today.' : 'Choose a day, then add your meal.'}
          accent="emerald"
        />
      </section>

      {error && (
        <div role="alert" className="mb-8 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-red-200">
          Dashboard data could not be loaded. Please refresh and try again.
        </div>
      )}

      <section aria-label="Today at a glance" className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <Card delay={0.1}>
          <CardHeader title="Current Weight" icon={<Activity size={24} />} color="purple" />
          {loading ? <LoadingValue /> : currentWeight === null ? (
            <EmptyValue message="No weight logged yet" href="/measurements/new" linkText="Add your first measurement" />
          ) : (
            <div className="flex items-end gap-2">
              <span className="text-5xl font-black">{currentWeight}</span>
              <span className="mb-1 text-xl font-medium text-slate-400">kg</span>
            </div>
          )}
        </Card>

        <Card delay={0.2}>
          <CardHeader title="Body Composition" icon={<Target size={24} />} color="emerald" />
          {loading ? <LoadingValue /> : currentBodyFat === null && summary?.goalBodyFat === null ? (
            <EmptyValue message="No body composition data yet" href="/measurements/new" linkText="Add a measurement" />
          ) : (
            <div className="flex items-end gap-5">
              <Metric label="Current" value={currentBodyFat} suffix="%" />
              <div className="mb-1 h-9 w-px bg-slate-700" />
              <Metric label="Goal" value={summary?.goalBodyFat ?? null} suffix="%" highlight />
            </div>
          )}
        </Card>

        <Card delay={0.3}>
          <CardHeader title="Today's Nutrition" icon={<UtensilsCrossed size={24} />} color="blue" />
          {loading ? <LoadingValue /> : today && todayIsCurrent ? (
            <div>
              <div className="mb-2 flex items-end gap-2">
                <span className="text-4xl font-black">{Math.round(today.energyKcal)}</span>
                <span className="mb-1 text-sm text-slate-400">/ {Math.round(today.energyKcalGoal)} kcal</span>
              </div>
              <div className="mb-3 h-2 overflow-hidden rounded-full bg-slate-800">
                <div
                  role="progressbar"
                  aria-label="Calories logged today"
                  aria-valuemin={0}
                  aria-valuemax={Math.max(1, Math.round(today.energyKcalGoal))}
                  aria-valuenow={Math.min(
                    Math.round(today.energyKcal),
                    Math.max(1, Math.round(today.energyKcalGoal)),
                  )}
                  aria-valuetext={`${Math.round(today.energyKcal)} of ${Math.round(today.energyKcalGoal)} kilocalories`}
                  className="h-full rounded-full bg-blue-400"
                  style={{ width: `${Math.min(100, today.energyKcalGoal > 0 ? (today.energyKcal / today.energyKcalGoal) * 100 : 0)}%` }}
                />
              </div>
              <p className="text-sm text-slate-400">{today.intakeCount} entries logged today</p>
            </div>
          ) : (
            <EmptyValue message="No plan day found for today" href="/days" linkText="Choose a day" />
          )}
        </Card>
      </section>

      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35, duration: 0.5 }}
        className="glass-card mt-8 rounded-3xl p-6"
        aria-labelledby="weight-trend-title"
      >
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="weight-trend-title" className="text-xl font-bold">Recent weight trend</h2>
            <p className="text-sm text-slate-400">Your last {trend.length || 0} measurements</p>
          </div>
          <Link href="/measurements" className="flex items-center gap-2 text-sm font-bold text-purple-300 hover:text-purple-200">
            View all <ArrowRight size={16} />
          </Link>
        </div>
        {loading ? <div className="h-40 animate-pulse rounded-2xl bg-white/5" /> : (
          <WeightTrendChart
            series={trend}
            emptyMessage="Log at least two measurements to see your trend"
            emptyActionHref="/measurements/new"
            emptyActionLabel="Log weight"
          />
        )}
      </motion.section>
    </div>
  )
}

function QuickAction({ href, icon, title, description, accent }: { href: string; icon: React.ReactNode; title: string; description: string; accent: 'purple' | 'emerald' }) {
  const colors = accent === 'purple' ? 'border-purple-400/20 bg-purple-500/10 text-purple-300' : 'border-emerald-400/20 bg-emerald-500/10 text-emerald-300'
  return (
    <Link href={href} className={`group flex items-center gap-4 rounded-2xl border p-5 transition hover:-translate-y-0.5 hover:bg-white/10 ${colors}`}>
      <div className="rounded-xl bg-black/20 p-3">{icon}</div>
      <div className="flex-1"><h2 className="font-bold text-white">{title}</h2><p className="text-sm text-slate-400">{description}</p></div>
      <ArrowRight className="transition-transform group-hover:translate-x-1" size={20} />
    </Link>
  )
}

function CardHeader({ title, icon, color }: { title: string; icon: React.ReactNode; color: 'purple' | 'emerald' | 'blue' }) {
  const colors = { purple: 'bg-purple-500/20 text-purple-400', emerald: 'bg-emerald-500/20 text-emerald-400', blue: 'bg-blue-500/20 text-blue-400' }
  return <div className="mb-4 flex items-center justify-between"><h3 className="text-xl font-bold text-slate-200">{title}</h3><div className={`rounded-full p-2 ${colors[color]}`}>{icon}</div></div>
}

function Metric({ label, value, suffix, highlight = false }: { label: string; value: number | null; suffix: string; highlight?: boolean }) {
  return <div><p className="text-xs font-bold uppercase tracking-wider text-slate-400">{label}</p><div className="flex items-end gap-1"><span className={`text-4xl font-black ${highlight ? 'text-emerald-400' : 'text-white'}`}>{value ?? 'Not set'}</span>{value !== null && <span className="mb-1 text-sm text-slate-400">{suffix}</span>}</div></div>
}

function LoadingValue() {
  return <div aria-label="Loading dashboard value" className="h-12 w-36 animate-pulse rounded-xl bg-white/5" />
}

function EmptyValue({ message, href, linkText }: { message: string; href: string; linkText: string }) {
  return <div className="py-3"><p className="mb-2 text-slate-400">{message}</p><Link href={href} className="text-sm font-bold text-purple-300 hover:text-purple-200">{linkText} →</Link></div>
}

function Card({ children, delay }: { children: React.ReactNode; delay: number }) {
  return <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.5, ease: 'easeOut' }} className="glass-card rounded-3xl p-6 transition-colors hover:bg-white/5">{children}</motion.div>
}
