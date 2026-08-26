'use client'

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'
import { usePathname } from 'next/navigation'
import { useSession, signOut } from 'next-auth/react'
import {
  ChefHat,
  Dumbbell,
  Footprints,
  Home,
  LogOut,
  Barcode,
  Package,
  ShoppingBasket,
  Target,
  UtensilsCrossed,
  Weight,
  Calendar,
  CalendarDays,
  Menu,
  X,
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
      { label: 'Scan products', href: '/scan', icon: <Barcode size={18} /> },
      { label: 'Recipes', href: '/recipes', icon: <ChefHat size={18} /> },
      { label: 'Cupboard', href: '/cupboard', icon: <ShoppingBasket size={18} /> },
    ],
  },
]

function focusMainContent() {
  requestAnimationFrame(() => {
    document.querySelector<HTMLElement>('.main-content')?.focus({ preventScroll: true })
  })
}

export default function Sidebar() {
  const pathname = usePathname()
  const { data: session } = useSession()
  const authenticated = Boolean(session)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const drawerRef = useRef<HTMLElement>(null)
  const previousPathnameRef = useRef(pathname)

  const closeMenu = useCallback(() => {
    setMenuOpen(false)
    requestAnimationFrame(() => menuButtonRef.current?.focus())
  }, [])

  useEffect(() => {
    if (previousPathnameRef.current === pathname) return
    previousPathnameRef.current = pathname
    // Intentional reset: the drawer must close when navigation changes the
    // route. This is a response to an external change (usePathname), not a
    // cascading render, so the effect is the correct synchronization point.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMenuOpen(false)
    focusMainContent()
  }, [pathname])

  useEffect(() => {
    // Intentional reset: closing the drawer when the session ends mirrors
    // external auth state; the rule is disabled because the value is read
    // from an external store (useSession) rather than derived props.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!authenticated) setMenuOpen(false)
  }, [authenticated])

  useEffect(() => {
    if (!menuOpen || !authenticated) return

    const mobileMedia = window.matchMedia('(max-width: 768px)')
    if (!mobileMedia.matches) {
      // Intentional reset: on desktop the drawer never stays open; this is a
      // one-shot correction for a media-query change, not a cascading render.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMenuOpen(false)
      focusMainContent()
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeMenu()
        return
      }

      if (event.key === 'Tab') {
        // The drawer ref is always attached while the drawer effect is active:
        // the listener below is only added when menuOpen && authenticated, which
        // requires the session (and therefore the rendered nav) to exist.
        const focusable = Array.from(
          drawerRef.current!.querySelectorAll<HTMLElement>(
            'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        )
        if (focusable.length === 0) return

        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }

    const handleBreakpointChange = (event: MediaQueryListEvent) => {
      if (!event.matches) {
        setMenuOpen(false)
        focusMainContent()
      }
    }

    const previousOverflow = document.body.style.overflow
    const mainContent = document.querySelector<HTMLElement>('.main-content')
    const mobileHeader = document.querySelector<HTMLElement>('.mobile-header')
    const mainWasInert = mainContent?.hasAttribute('inert') ?? false
    // The mobile header is rendered unconditionally whenever a session exists,
    // and this effect body only runs while authenticated with the menu open.
    const headerWasInert = mobileHeader!.hasAttribute('inert')
    document.body.style.overflow = 'hidden'
    mainContent?.setAttribute('inert', '')
    mobileHeader?.setAttribute('inert', '')
    document.addEventListener('keydown', handleKeyDown)
    mobileMedia.addEventListener('change', handleBreakpointChange)
    closeButtonRef.current?.focus()

    return () => {
      document.body.style.overflow = previousOverflow
      if (!mainWasInert) mainContent?.removeAttribute('inert')
      if (!headerWasInert) mobileHeader?.removeAttribute('inert')
      document.removeEventListener('keydown', handleKeyDown)
      mobileMedia.removeEventListener('change', handleBreakpointChange)
    }
  }, [authenticated, closeMenu, menuOpen])

  if (!session) return null

  return (
    <>
      <header className="mobile-header">
        <Link href="/" aria-label="Go to dashboard" className="mobile-header-button">
          <Home size={22} aria-hidden="true" />
        </Link>
        <Link href="/" className="text-lg font-black tracking-tight no-underline">
          <span className="text-gradient">Nutrition</span>
        </Link>
        <button
          ref={menuButtonRef}
          type="button"
          className="mobile-header-button"
          aria-label="Open navigation menu"
          aria-expanded={menuOpen}
          aria-controls="primary-navigation"
          onClick={() => setMenuOpen(true)}
        >
          <Menu size={24} aria-hidden="true" />
        </button>
      </header>
      <button
        type="button"
        className={`sidebar-overlay ${menuOpen ? 'open' : ''}`}
        aria-label="Close navigation menu"
        tabIndex={-1}
        onClick={closeMenu}
      />
      <nav
        ref={drawerRef}
        id="primary-navigation"
        aria-label="Primary navigation"
        className={`sidebar ${menuOpen ? 'open' : ''}`}
        data-testid="sidebar"
      >
        <button
          ref={closeButtonRef}
          type="button"
          className="sidebar-close"
          aria-label="Close navigation menu"
          onClick={closeMenu}
        >
          <X size={24} aria-hidden="true" />
        </button>
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
                  aria-current={isActive ? 'page' : undefined}
                  data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, '-')}`}
                  onClick={closeMenu}
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
            onClick={() => {
              closeMenu()
              void signOut()
            }}
            className="sidebar-link w-full text-left"
            data-testid="nav-logout"
          >
            <LogOut size={18} />
            Sign Out
          </button>
        </div>
      </nav>
    </>
  )
}
