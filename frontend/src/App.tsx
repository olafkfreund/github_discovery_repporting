import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout'
import DashboardPage from './pages/DashboardPage'
import CustomersPage from './pages/CustomersPage'
import CustomerDetailPage from './pages/CustomerDetailPage'
import ScanDetailPage from './pages/ScanDetailPage'
import ScanProfilesPage from './pages/ScanProfilesPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/customers" element={<CustomersPage />} />
          <Route path="/customers/:id" element={<CustomerDetailPage />} />
          <Route path="/customers/:id/scan-profiles" element={<ScanProfilesPage />} />
          <Route path="/scans/:id" element={<ScanDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
