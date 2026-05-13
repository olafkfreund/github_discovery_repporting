import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import DashboardPage from './pages/DashboardPage'
import CustomersPage from './pages/CustomersPage'
import CustomerDetailPage from './pages/CustomerDetailPage'
import ScanDetailPage from './pages/ScanDetailPage'
import ScanProfilesPage from './pages/ScanProfilesPage'
import SettingsLayout from './pages/settings/SettingsLayout'
import LLMProvidersPage from './pages/settings/LLMProvidersPage'
import RemediationPolicyPage from './pages/settings/RemediationPolicyPage'
import SkillsPage from './pages/settings/SkillsPage'
import AgentInstructionsPage from './pages/settings/AgentInstructionsPage'
import GlobalSettingsPage from './pages/settings/GlobalSettingsPage'
import AgentRunsListPage from './pages/AgentRunsListPage'
import AgentRunDetailPage from './pages/AgentRunDetailPage'
import { HelpLayout } from './pages/help/HelpLayout'
import { HelpHomePage } from './pages/help/HelpHomePage'
import { DocPage } from './pages/help/DocPage'
import SkillsLibraryPage from './pages/help/SkillsLibraryPage'
import AgentProfilesGalleryPage from './pages/help/AgentProfilesGalleryPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          {/* Existing routes */}
          <Route path="/" element={<DashboardPage />} />
          <Route path="/customers" element={<CustomersPage />} />
          <Route path="/customers/:id" element={<CustomerDetailPage />} />
          <Route path="/customers/:id/scan-profiles" element={<ScanProfilesPage />} />
          <Route path="/scans/:id" element={<ScanDetailPage />} />

          {/* Settings — index redirects to default sub-tab */}
          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<Navigate to="/settings/llm-providers" replace />} />
            <Route path="llm-providers" element={<LLMProvidersPage />} />
            <Route path="remediation-policy" element={<RemediationPolicyPage />} />
            <Route path="skills" element={<SkillsPage />} />
            <Route path="agent-instructions" element={<AgentInstructionsPage />} />
            <Route path="global" element={<GlobalSettingsPage />} />
          </Route>

          {/* Agents Running */}
          <Route path="/agents" element={<AgentRunsListPage />} />
          <Route path="/agents/:id" element={<AgentRunDetailPage />} />

          {/* Help & Docs — live registry routes must precede :slug */}
          <Route path="/help" element={<HelpLayout />}>
            <Route index element={<HelpHomePage />} />
            <Route path="skills-lib" element={<SkillsLibraryPage />} />
            <Route path="profiles" element={<AgentProfilesGalleryPage />} />
            <Route path=":slug" element={<DocPage />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
