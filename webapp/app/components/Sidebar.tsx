'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useSession, signOut } from 'next-auth/react'
import {
  Activity,
  BarChart3,
  ChefHat,
  Dumbbell,
  Footprints,
  Home,
  LogOut,
  Package,
  ShoppingBasket,
  Target,
  UtensilsCrossed,
  Weight,
  Calendar,
  CalendarDays,
} from 'lucide-react'

interface NavItem {
  label: string
  href: string
  icon: React.ReactNode
}

interface NavSection {
  title: string
  items: NavItem[]
}

const navSections: NavSection[] = [
  {
    title: '',
    items: [
      { label: 'Dashboard', href: '/', icon: <Home size={18} /> },
    ],
  },
  {
    title: 'Plans',
    items: [
      { label: 'Week Plans', href: '/plans', icon: <Calendar size={18} /> },
      { label: 'Days', href: '/days', icon: <CalendarDays size={18} /> },
      { label: 'Intakes', href: '/intakes', icon: <UtensilsCrossed size={18} /> },
    ],
  },
  {
    title: 'Body',
    items: [
      { label: 'Measurements', href: '/measurements', icon: <Weight size={18} /> },
      { label: 'Goals', href: '/goals', icon: <Target size={18} /> },
    ],
  },
  {
    title: 'Exercise',
    items: [
      { label: 'Exercises', href: '/exercises', icon: <Dumbbell size={18} /> },
      { label: 'Steps', href: '/steps', icon: <Footprints size={18} /> },
    ],
  },
  {
    title: 'Food',
    items: [
      { label: 'Products', href: '/products', icon: <Package size={18} /> },
      { label: 'Recipes', href: '/recipes', icon: <ChefHat size={18} /> },
      { label: 'Cupboard', href: '/cupboard', icon: <ShoppingBasket size={18} /> },
    ],
  },
]

export default function Sidebar() {
  const pathname = usePathname()
  const { data: session } = useSession()

  if (!session) return null

  return (
    <nav className="sidebar" data-testid="sidebar">
      <div className="px-6 mb-6">
        <Link href="/" className="text-xl font-black tracking-tight text-white no-underline">
          <span className="text-gradient">Nutrition</span>
        </Link>
      </div>

      {navSections.map((section) => (
        <div key={section.title || 'main'}>
          {section.title && (
            <div className="sidebar-section">{section.title}</div>
          )}
          {section.items.map((item) => {
            const isActive = pathname === item.href ||
              (item.href !== '/' && pathname.startsWith(item.href))
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`sidebar-link ${isActive ? 'active' : ''}`}
                data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
              >
                {item.icon}
                {item.label}
              </Link>
            )
          })}
        </div>
      ))}

      <div className="mt-auto pt-6 border-t border-white/5 mx-4">
        <button
          onClick={() => signOut()}
          className="sidebar-link w-full text-left"
          data-testid="nav-logout"
        >
          <LogOut size={18} />
          Sign Out
        </button>
      </div>
    </nav>
  )
}
