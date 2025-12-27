import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { MarketsPage } from './pages/MarketsPage'
import { MarketDetailPage } from './pages/MarketDetailPage'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<MarketsPage />} />
        <Route path="/markets" element={<MarketsPage />} />
        <Route path="/markets/:conditionId" element={<MarketDetailPage />} />
      </Routes>
    </Layout>
  )
}

export default App
