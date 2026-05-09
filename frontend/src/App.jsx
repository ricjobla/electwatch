import ElectionsDashboard from './pages/ElectionsDashboard.jsx'

function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <h1 className="text-xl font-semibold tracking-tight">ElectWatch</h1>
        <p className="mt-1 text-sm text-slate-400">
          European elections — Phase 1 calendar & results
        </p>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-10">
        <ElectionsDashboard />
      </main>
    </div>
  )
}

export default App
