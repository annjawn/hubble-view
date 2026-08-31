import { Activity } from 'lucide-react'

export function LoadingState({ error }: { error?: Error | null }) {
  return <div className="grid min-h-[420px] place-items-center text-center">
    <div><Activity className="mx-auto mb-3 animate-pulse text-indigo-400" />
      <p className="font-medium">{error ? 'Waiting for the local data service' : 'Reading local usage'}</p>
      <p className="mt-1 text-sm text-zinc-500">{error ? 'The Python backend may still be starting.' : 'This takes a moment on the first scan.'}</p>
    </div>
  </div>
}

