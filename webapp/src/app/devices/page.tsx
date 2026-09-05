import HealthSyncPanel from './HealthSyncPanel'

export default function DevicesPage() {
  return (
    <div>
      <h1 className="page-title mb-2">Devices</h1>
      <p className="mb-6 text-sm text-slate-400">
        Pair companion apps and manage access to data imported into Nutrition.
      </p>
      <HealthSyncPanel />
    </div>
  )
}