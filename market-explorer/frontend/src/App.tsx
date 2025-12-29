import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { MarketsPage } from './pages/MarketsPage'
import { MarketDetailPage } from './pages/MarketDetailPage'
import { EventsPage } from './pages/EventsPage'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<MarketsPage />} />
        <Route path="/markets" element={<MarketsPage />} />
        <Route path="/markets/:conditionId" element={<MarketDetailPage />} />
        <Route path="/events" element={<EventsPage />} />
      </Routes>
    </Layout>
  )
}

export default App
