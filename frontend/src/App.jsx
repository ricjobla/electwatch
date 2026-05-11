import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'

import Country from './pages/Country.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Election from './pages/Election.jsx'
import IngestLog from './pages/IngestLog.jsx'

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-950 text-slate-100">
        <header className="border-b border-slate-800 px-4 py-4 sm:px-6">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <div>
              <Link to="/" className="block">
                <h1 className="text-xl font-semibold tracking-tight">
                  ElectWatch
                </h1>
                <p className="mt-0.5 text-xs text-slate-400 sm:text-sm">
                  European elections — calendar, map, and historic results
                </p>
              </Link>
            </div>
            <nav className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-wider text-slate-500">
              {import.meta.env.DEV ? (
                <>
                  <Link
                    to="/debug/ingest-log"
                    className="hover:text-slate-300"
                  >
                    Ingest log
                  </Link>
                  <span aria-hidden="true">·</span>
                </>
              ) : null}
              <a
                href="https://www.wikidata.org"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-slate-300"
              >
                Wikidata
              </a>
              <span aria-hidden="true">·</span>
              <a
                href="https://parlgov.org"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-slate-300"
              >
                ParlGov
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/country/:iso" element={<Country />} />
            <Route path="/election/:id" element={<Election />} />
            <Route path="/debug/ingest-log" element={<IngestLog />} />
            <Route
              path="*"
              element={
                <div className="rounded border border-dashed border-slate-700 bg-slate-900/30 p-10 text-center">
                  <p className="font-serif text-lg text-slate-300">
                    Page not found
                  </p>
                  <Link
                    to="/"
                    className="mt-4 inline-block font-mono text-xs text-sky-400 hover:underline"
                  >
                    ← Back to dashboard
                  </Link>
                </div>
              }
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
